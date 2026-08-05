#!/usr/bin/env python3
"""Write parcelLab credentials into the global Claude Code settings env block.

Three modes:

    pl_credentials.py --account 1626718   # account ID only, no secret, no prompt
    pl_credentials.py --token             # hidden prompt for the Order API credential
    pl_credentials.py --cdc-token         # hidden prompt for the Custom Demo Creator token

No secret is EVER accepted as a command-line value — that would expose a live
credential to the process table and shell history. `--token` and `--cdc-token` are
bare flags that trigger a hidden getpass prompt.

Merges into the `env` block of ~/.claude/settings.json without touching any other
key. Safe to re-run: updates in place rather than duplicating. Never prints a
secret.
"""
import argparse
import base64
import binascii
import getpass
import json
import pathlib
import sys

SETTINGS_PATH = pathlib.Path.home() / ".claude" / "settings.json"
CDC_DEFAULT_BASE_URL = "https://experience.parcellab.com"


def decode(value):
    """Return (account_id, token) from a base64 'accountId:token' value, else None."""
    try:
        raw = base64.b64decode(value, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if ":" not in raw:
        return None
    account_id, token = raw.split(":", 1)
    account_id, token = account_id.strip(), token.strip()
    if not account_id.isdigit() or not token:
        return None
    return account_id, token


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


def run_token(settings, prompt=getpass.getpass, confirm=input):
    """Return (updated_settings, message) for --token mode. Prompts for the secret."""
    print("Paste the base64 value from the parcelLab portal (or the raw token).")
    print("Input is hidden — nothing is echoed as you paste. That is expected.\n")
    value = prompt("Order API credential: ").strip()
    if not value:
        raise ValueError("Nothing entered; no changes made.")

    env = settings.get("env", {})
    current = existing_account(env)
    pair = decode(value)

    if pair:
        account_id, token = pair
        if current and current != account_id:
            print(
                f"\nThe credential is for account {account_id}, but the current "
                f"default is {current}."
            )
            if confirm("Update the account ID to match? [y/N] ").strip().lower() != "y":
                account_id = current
        print(f"\nDecoded credential for account {account_id}.")
    else:
        token = value
        print("\nTreating input as a raw token (not a base64 accountId:token pair).")
        if not current:
            raise ValueError(
                "No account ID is set, and a raw token does not contain one. "
                "Re-run and paste the base64 value from the portal instead."
            )
        account_id = current

    updated = merge_env(
        settings, {"PARCELLAB_ACCOUNT_ID": account_id, "PARCELLAB_TOKEN": token}
    )
    return updated, (
        f"  PARCELLAB_ACCOUNT_ID = {account_id}\n"
        f"  PARCELLAB_TOKEN      = (set, {len(token)} characters)"
    )


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
    group.add_argument("--token", action="store_true",
                       help="prompt (hidden) for the Order API credential")
    group.add_argument("--cdc-token", action="store_true",
                       help="prompt (hidden) for the Custom Demo Creator API token")
    args = parser.parse_args(argv)

    try:
        settings = read_settings(SETTINGS_PATH)
        if args.account:
            if not args.account.strip().isdigit():
                raise ValueError(f"Account ID must be numeric, got: {args.account!r}")
            settings, message = run_account(settings, args.account.strip())
        elif args.cdc_token:
            settings, message = run_cdc_token(settings)
        else:
            settings, message = run_token(settings)
    except ValueError as err:
        sys.exit(str(err))

    write_settings(SETTINGS_PATH, settings)
    print(f"\nUpdated {SETTINGS_PATH}")
    print(message)
    print("\nFully quit and reopen Claude Code (Cmd-Q) — "
          "environment variables are only read at startup.")


if __name__ == "__main__":
    main()
