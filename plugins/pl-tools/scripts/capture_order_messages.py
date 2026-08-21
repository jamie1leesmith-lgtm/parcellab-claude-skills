#!/usr/bin/env python3
"""Capture real parcelLab Engage message content for this run's linked orders.

CDC's "Message Timeline" view (custom-demo-creator PR #30) renders whatever
`rendered_html` this writes into `results/linked-orders.json[].messages` --
demo-request passes that file's array verbatim into the automation API's
`linked_orders`, and CDC never calls parcelLab itself. This script is the
only place that data gets produced.

The recipe (proven live 2026-08-21, see the demo-environment SKILL.md's
Phase 2.5 for why the timing matters):

  1. `parcellab track email list --account <id> --show-pii -o json --all` --
     the same account-scoped listing Beat 2 already uses for its comms
     count. Each record has `id`, `recipient`, `messageType`, `subject`,
     `createdAt` -- but no order/tracking field.
  2. `s = sha256(recipient)` -- documented internally as exactly this, not a
     secret key. Confirmed against a real sent email.
  3. `GET https://api.parcellab.com/email-web-view/{id}?s={s}` -- public, no
     auth. Returns the full real rendered HTML, exactly what the customer
     received. Rate-limited (429) after a handful of rapid calls, so this
     backs off and retries rather than firing every request back to back.
  4. There's no order/tracking field on the email record, so a message is
     matched to one of this run's orders by reading its own rendered
     content for "Order number: #<n>" -- not by any API filter.

Run as:

    python3 capture_order_messages.py <run dir> --since <ISO8601>

`--since` is required on purpose: an account accumulates history across
every run anyone has ever pointed at it, and a bare listing would happily
match this run's order numbers against some other run's stale messages if
they ever collided. Exit 0 means every linked order got at least one
message; exit 2 means some order captured zero and a retry after a further
wait is worth considering (mirrors the "comm missing at 5 minutes is not
yet a defect" re-check Beat 2 already does, applied here to capture instead
of verification); exit 1 means it couldn't run at all.
"""
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ORDER_NUMBER_RE = re.compile(r"Order number:\s*#?([A-Za-z0-9_-]+)",
                              re.IGNORECASE)
WEBVIEW_BASE = "https://api.parcellab.com/email-web-view"
DEFAULT_RETRIES = 4
DEFAULT_BACKOFF_SECONDS = 5


def signature_for(recipient: str) -> str:
    """The `s` query param email-web-view expects for this recipient.

    SHA-256 of the recipient address, lowercased and trimmed -- not a secret
    key, just a hash of who the email went to. Confirmed live 2026-08-21:
    sha256("testmail@parcellab.com") matches a real captured signature
    byte-for-byte.
    """
    normalised = recipient.strip().lower()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def extract_order_number(rendered_html: str):
    """The order number this rendered email actually names, or None.

    There's no order/tracking field on the track/emails record itself, so
    grouping a message to a specific order has to happen by reading the
    rendered content -- never by guessing from timing or account alone (two
    sibling orders in the same run can fire within seconds of each other).
    """
    match = ORDER_NUMBER_RE.search(rendered_html)
    return match.group(1) if match else None


def list_account_emails(account_id, page_size=100, max_pages=10):
    """Shell out to the parcellab CLI for this account's recent sent emails.

    `--show-pii` is required: the recipient address feeds signature_for()
    and never leaves this machine beyond that -- it's not written to any
    output file, only hashed.
    """
    result = subprocess.run(
        ["parcellab", "track", "email", "list",
         "--account", str(account_id),
         "--page-size", str(page_size),
         "--all", "--max-pages", str(max_pages),
         "--show-pii", "-o", "json"],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"parcellab track email list failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return data.get("results", [])


def fetch_rendered_content(email_id, signature, retries=DEFAULT_RETRIES,
                            backoff_seconds=DEFAULT_BACKOFF_SECONDS,
                            sleep=time.sleep):
    """GET the real rendered HTML for one sent email. Public, no auth.

    Observed a 429 after ~5 rapid calls live 2026-08-21 -- retries with a
    fixed backoff instead of failing the whole capture on one rate limit.
    """
    url = f"{WEBVIEW_BASE}/{email_id}?s={signature}"
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            last_error = err
            if err.code == 429 and attempt < retries - 1:
                sleep(backoff_seconds)
                continue
            break
        except urllib.error.URLError as err:
            last_error = err
            if attempt < retries - 1:
                sleep(backoff_seconds)
                continue
            break
    raise RuntimeError(
        f"email-web-view fetch failed after {retries} attempt(s): {last_error}")


def capture_messages(account_id, order_numbers, since_iso,
                      page_size=100, max_pages=10,
                      list_emails=list_account_emails,
                      fetch_content=fetch_rendered_content):
    """Fetch and group real message content for exactly these order numbers.

    Returns {order_number: [{message_type, subject, rendered_html,
    sent_at}]}, sorted oldest-to-newest per order. `list_emails` and
    `fetch_content` are injectable so tests never touch the network.
    """
    known = set(order_numbers)
    by_order = {number: [] for number in known}
    seen_ids = set()

    for record in list_emails(account_id, page_size=page_size,
                               max_pages=max_pages):
        created_at = record.get("createdAt") or ""
        if created_at < since_iso:
            continue
        email_id = record.get("id")
        if not email_id or email_id in seen_ids:
            continue
        recipient = record.get("recipient") or ""
        if not recipient:
            continue

        signature = signature_for(recipient)
        try:
            payload = fetch_content(email_id, signature)
        except Exception as err:  # noqa: BLE001
            print(f"warning: could not fetch {email_id}: {err}",
                  file=sys.stderr)
            continue

        rendered_html = payload.get("content") or ""
        order_number = extract_order_number(rendered_html)
        if order_number not in known:
            continue

        seen_ids.add(email_id)
        by_order[order_number].append({
            "message_type": record.get("messageType") or "",
            "subject": payload.get("subject") or record.get("subject") or "",
            "rendered_html": rendered_html,
            "sent_at": created_at,
        })

    for messages in by_order.values():
        messages.sort(key=lambda m: m["sent_at"])
    return by_order


def merge_into_linked_orders(linked_orders_path, captured_by_order):
    """Write `messages` onto each matching entry of linked-orders.json.

    Overwrites rather than appends: capture is meant to be re-run once after
    a further wait, and each run re-derives the full set from parcelLab's
    own history, so there's nothing to accumulate across attempts.
    """
    linked_orders = json.loads(linked_orders_path.read_text())
    gaps = []
    for order in linked_orders:
        number = order.get("order_number")
        messages = captured_by_order.get(number, [])
        order["messages"] = messages
        if not messages:
            gaps.append(number)
    linked_orders_path.write_text(json.dumps(linked_orders, indent=2) + "\n")
    return gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument(
        "--since", required=True,
        help="ISO8601 timestamp; only emails created at/after this are "
             "considered, so another run's history on the same account "
             "never bleeds into this one's capture")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()

    run_dir = pathlib.Path(args.run_dir)
    manifest_path = run_dir / "demo-manifest.json"
    if not manifest_path.exists():
        print(f"no demo-manifest.json under {run_dir}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text())
    account_id = manifest["account"]["id"]

    linked_orders_path = run_dir / "results" / "linked-orders.json"
    if not linked_orders_path.exists():
        print("no results/linked-orders.json -- nothing to capture into",
              file=sys.stderr)
        return 1

    linked_orders = json.loads(linked_orders_path.read_text())
    order_numbers = [o["order_number"] for o in linked_orders
                     if o.get("order_number")]
    if not order_numbers:
        print("results/linked-orders.json has no order_number entries",
              file=sys.stderr)
        return 1

    captured = capture_messages(account_id, order_numbers, args.since,
                                 page_size=args.page_size,
                                 max_pages=args.max_pages)
    gaps = merge_into_linked_orders(linked_orders_path, captured)

    total = sum(len(v) for v in captured.values())
    print(f"captured {total} message(s) across {len(order_numbers)} "
          f"order(s)")
    if gaps:
        print(f"no messages captured yet for: {', '.join(gaps)} -- "
              f"consider one retry after a further wait", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
