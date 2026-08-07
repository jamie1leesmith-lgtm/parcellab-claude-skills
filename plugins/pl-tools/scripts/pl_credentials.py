#!/usr/bin/env python3
"""Write parcelLab credentials into the global Claude Code settings env block.

Two modes:

    pl_credentials.py --account 1626718   # account ID only, no secret, no prompt
    pl_credentials.py --cdc-token         # hidden prompt for the Custom Demo Creator token

(An Order API `--token` mode existed until 2026-08-07. It was removed when the
order skills switched to the parcellab CLI's OAuth session — there is no Order
API token anymore. A stale PARCELLAB_TOKEN in settings.json is harmless and
simply unused.)

No secret is EVER accepted as a command-line value — that would expose a live
credential to the process table and shell history. `--cdc-token` is a bare flag
that triggers a hidden getpass prompt.

Merges into the `env` block of ~/.claude/settings.json without touching any other
key. Safe to re-run: updates in place rather than duplicating. Never prints a
secret.
"""
import argparse
import getpass
import json
import pathlib
import sys

SETTINGS_PATH = pathlib.Path.home() / ".claude" / "settings.json"
CDC_DEFAULT_BASE_URL = "https://experience.parcellab.com"


def read_settings(path):
    """Return the parsed settings dict. Raises ValueError on malformed JSON."""
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    raw = path.read_text().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise ValueError(
            f"{path} contains invalid JSON and was left untouched. "
            f"Fix or back up that file, then run /pl-setup again. ({err})"
        ) from err


def merge_env(settings, updates):
    """Return a new settings dict with `updates` merged into its env block."""
    nxt = dict(settings)
    env = dict(nxt.get("env", {}))
    env.update(updates)
    nxt["env"] = env
    return nxt


def write_settings(path, settings):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")


def existing_account(env):
    """Current account ID: canonical key, else the legacy alias. Never written back."""
    return env.get("PARCELLAB_ACCOUNT_ID") or env.get("PARCELLAB_USER_ID")


def run_account(settings, account_id):
    """Return (updated_settings, message) for --account mode."""
    updated = merge_env(settings, {"PARCELLAB_ACCOUNT_ID": account_id})
    return updated, f"  PARCELLAB_ACCOUNT_ID = {account_id}"


def run_cdc_token(settings, prompt=getpass.getpass):
    """Return (updated_settings, message) for --cdc-token mode. Prompts for the secret."""
    print("Paste the Custom Demo Creator API token.")
    print("Input is hidden — nothing is echoed as you paste. That is expected.\n")
    token = prompt("CDC API token: ").strip()
    if not token:
        raise ValueError("Nothing entered; no changes made.")

    updated = merge_env(
        settings,
        {
            "CDC_DEMO_API_TOKEN": token,
            "CDC_DEMO_API_BASE_URL": CDC_DEFAULT_BASE_URL,
        },
    )
    return updated, (
        f"  CDC_DEMO_API_BASE_URL = {CDC_DEFAULT_BASE_URL}\n"
        f"  CDC_DEMO_API_TOKEN    = (set, {len(token)} characters)"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write parcelLab credentials into ~/.claude/settings.json"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", metavar="ID",
                       help="write PARCELLAB_ACCOUNT_ID only (no secret)")
    group.add_argument("--cdc-token", action="store_true",
                       help="prompt (hidden) for the Custom Demo Creator API token")
    args = parser.parse_args(argv)

    try:
        settings = read_settings(SETTINGS_PATH)
        if args.account:
            if not args.account.strip().isdigit():
                raise ValueError(f"Account ID must be numeric, got: {args.account!r}")
            settings, message = run_account(settings, args.account.strip())
        else:
            settings, message = run_cdc_token(settings)
    except ValueError as err:
        sys.exit(str(err))

    write_settings(SETTINGS_PATH, settings)
    print(f"\nUpdated {SETTINGS_PATH}")
    print(message)
    print("\nFully quit and reopen Claude Code (Cmd-Q) — "
          "environment variables are only read at startup.")


if __name__ == "__main__":
    main()
