# pl-tools Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate five single-skill `parcellab-*` plugins into one `pl-tools` plugin holding five renamed skills plus a `/pl-setup` command backed by a tested, hidden-input credential script.

**Architecture:** One plugin directory, `plugins/pl-tools/`, containing `skills/` (five skills, moved with `git mv` to preserve history), `commands/pl-setup.md` (instructions for Claude), and `scripts/pl_credentials.py` (stdlib-only Python, unit-tested pure functions, secret read via `getpass` and never via argv). The marketplace drops from six entries to two. Skill *descriptions* keep the word "parcelLab" so prose triggering is unaffected; only identifiers change.

**Tech Stack:** Markdown skills/commands, Python 3 stdlib (`argparse`, `base64`, `getpass`, `json`, `pathlib`), `unittest` for tests, `git mv`, `claude plugin` CLI, `parcellab` CLI.

## Global Constraints

- **Python stdlib only.** `pytest` is NOT installed on this machine (verified). Tests use `unittest`. No `pip install` in any step.
- **Python 3.14.4** is what's installed. Invoke as `python3`.
- **Script filename uses an underscore**: `pl_credentials.py`, not `pl-credentials.py`. A hyphen makes the module non-importable, which would make the unit tests impossible. (This corrects the spec, which wrote a hyphen.)
- **The secret is never an argv value.** `--token` is a bare flag that triggers a `getpass` prompt. Never `--token <value>`.
- **Never print the token.** Confirm only as `(set, N characters)`.
- **Descriptions keep "parcelLab".** Only `name:` fields, directory names, and internal cross-references change. Never edit a `description:` line in this plan.
- **Writes only `PARCELLAB_ACCOUNT_ID`**, never the legacy `PARCELLAB_USER_ID` alias (read it, don't write it).
- **All work on `main`**, remote `jamie1leesmith-lgtm/parcellab-claude-skills`. Personal account only — never the parcelLab org. Verify with `git remote -v` before any push.
- **`pl-tools` version is `2.0.0`.** Every later release must bump it; updates are gated on the version string, not on git commits.
- **Commit after every task. Do not push until Task 6** — a half-consolidated marketplace on `main` is installable by a teammate.

### DO-NOT-RENAME list (verified occurrences)

A blind `parcellab-` → `pl-` replacement breaks all of these. They stay exactly as they are:

| Token | Where | Why |
|---|---|---|
| `parcellab-previews` (6×) | `branded-template/SKILL.md` | Filesystem directory `$HOME/parcellab-previews/` |
| `parcellab-layout` (3×) | `branded-template/SKILL.md` | Output filename fragment `{brand}-parcellab-layout.html` |
| `parcellab-brand-layout` (2×) | `branded-template/SKILL.md:10,381` | The **external** Cowork/CLI variant, referenced for contrast. Not this skill. |
| `parcellab-product-api` (2×) | `bug-investigation/SKILL.md:81,103` | The **org's** plugin, from `parcelLab/parcellab-cli` |
| `parcellab-product-configuration` (1×) | `bug-investigation/SKILL.md:81` | Skill inside the org's plugin |
| `~/.claude/parcellab-demo-request.env` (3×) | `demo-request/SKILL.md:16,213,249` | User config file that exists on disk (verified). Renaming breaks working setups. |

### RENAME list (the only 8 tokens that change)

| File | Line | From | To |
|---|---|---|---|
| `branded-template/SKILL.md` | 2 | `name: parcellab-brand-layout-desktop` | `name: branded-template` |
| `bug-investigation/SKILL.md` | 2 | `name: parcellab-bug-investigation` | `name: bug-investigation` |
| `create-order/SKILL.md` | 2 | `name: parcellab-create-order` | `name: create-order` |
| `demo-request/SKILL.md` | 2 | `name: parcellab-demo-request` | `name: demo-request` |
| `order-lifecycle/SKILL.md` | 2 | `name: parcellab-order-lifecycle` | `name: order-lifecycle` |
| `order-lifecycle/SKILL.md` | 107 | `` `parcellab-create-order` `` | `` `create-order` `` |
| `order-lifecycle/SKILL.md` | 200 | `` `parcellab-create-order` `` | `` `create-order` `` |
| `create-order/README.md` | 1 | `# parcellab-create-order — Skill README` | `# create-order — Skill README` |

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `plugins/pl-tools/.claude-plugin/plugin.json` | Manifest: name `pl-tools`, version `2.0.0` |
| `plugins/pl-tools/scripts/pl_credentials.py` | Write account ID / token into global settings `env`. Pure functions + CLI. |
| `plugins/pl-tools/scripts/tests/test_pl_credentials.py` | `unittest` suite for the pure functions |
| `plugins/pl-tools/commands/pl-setup.md` | Instructions Claude follows for `/pl-setup` |
| `plugins/pl-tools/README.md` | What the plugin contains, what `/pl-setup` does |

**Moved** (via `git mv`, preserving history):

| From | To |
|---|---|
| `plugins/parcellab-brand-layout/skills/parcellab-brand-layout-desktop/` | `plugins/pl-tools/skills/branded-template/` |
| `plugins/parcellab-bug-investigation/skills/parcellab-bug-investigation/` | `plugins/pl-tools/skills/bug-investigation/` |
| `plugins/parcellab-create-order/skills/parcellab-create-order/` | `plugins/pl-tools/skills/create-order/` |
| `plugins/parcellab-demo-request/skills/parcellab-demo-request/` | `plugins/pl-tools/skills/demo-request/` |
| `plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle/` | `plugins/pl-tools/skills/order-lifecycle/` |

**Deleted:** the five `plugins/parcellab-*/` directories (empty after the moves, plus their `.claude-plugin/plugin.json`).

**Modified:** `.claude-plugin/marketplace.json` (six entries → two), root `README.md`.

---

## Task 1: Credential script (TDD)

Self-contained. No dependency on the skill moves, so it can be reviewed on its own.

**Files:**
- Create: `plugins/pl-tools/scripts/pl_credentials.py`
- Test: `plugins/pl-tools/scripts/tests/test_pl_credentials.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `decode(value) -> tuple[str, str] | None`; `read_settings(path) -> dict` (raises `ValueError` on bad JSON); `merge_env(settings: dict, updates: dict) -> dict`; `write_settings(path, settings) -> None`; `existing_account(env: dict) -> str | None`. Task 2's command invokes the CLI as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --account <id>` and `... --token`.

- [ ] **Step 1: Create the directories**

```bash
mkdir -p ~/parcellab-claude-skills/plugins/pl-tools/scripts/tests
```

- [ ] **Step 2: Write the failing tests**

Create `plugins/pl-tools/scripts/tests/test_pl_credentials.py`:

```python
"""Unit tests for pl_credentials pure functions. Stdlib unittest — no pytest."""
import base64
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pl_credentials as plc


def b64(raw):
    return base64.b64encode(raw.encode()).decode()


class TestDecode(unittest.TestCase):
    def test_valid_pair(self):
        self.assertEqual(plc.decode(b64("1626718:secrettoken")),
                         ("1626718", "secrettoken"))

    def test_token_containing_colon_splits_once(self):
        self.assertEqual(plc.decode(b64("1626718:abc:def")),
                         ("1626718", "abc:def"))

    def test_surrounding_whitespace_stripped(self):
        self.assertEqual(plc.decode(b64(" 1626718 : secret ")),
                         ("1626718", "secret"))

    def test_base64_without_colon_is_rejected(self):
        self.assertIsNone(plc.decode(b64("noseparator")))

    def test_non_base64_is_rejected(self):
        self.assertIsNone(plc.decode("this-is-a-raw-token"))

    def test_empty_is_rejected(self):
        self.assertIsNone(plc.decode(""))

    def test_non_numeric_account_is_rejected(self):
        self.assertIsNone(plc.decode(b64("notanumber:secret")))

    def test_empty_token_is_rejected(self):
        self.assertIsNone(plc.decode(b64("1626718:")))


class TestMergeEnv(unittest.TestCase):
    def test_unrelated_env_keys_preserved(self):
        before = {"env": {"ONYX_API_TOKEN": "keep-me"}}
        after = plc.merge_env(before, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["env"]["ONYX_API_TOKEN"], "keep-me")
        self.assertEqual(after["env"]["PARCELLAB_ACCOUNT_ID"], "1")

    def test_non_env_settings_preserved(self):
        before = {"theme": "auto", "enabledPlugins": {"onyx@x": True}}
        after = plc.merge_env(before, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["theme"], "auto")
        self.assertEqual(after["enabledPlugins"], {"onyx@x": True})

    def test_missing_env_block_created(self):
        after = plc.merge_env({}, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(after["env"], {"PARCELLAB_ACCOUNT_ID": "1"})

    def test_does_not_mutate_input(self):
        before = {"env": {"A": "1"}}
        plc.merge_env(before, {"B": "2"})
        self.assertEqual(before, {"env": {"A": "1"}})

    def test_idempotent(self):
        once = plc.merge_env({}, {"PARCELLAB_ACCOUNT_ID": "1"})
        twice = plc.merge_env(once, {"PARCELLAB_ACCOUNT_ID": "1"})
        self.assertEqual(once, twice)


class TestExistingAccount(unittest.TestCase):
    def test_prefers_canonical_key(self):
        self.assertEqual(plc.existing_account(
            {"PARCELLAB_ACCOUNT_ID": "1", "PARCELLAB_USER_ID": "2"}), "1")

    def test_falls_back_to_legacy_alias(self):
        self.assertEqual(plc.existing_account({"PARCELLAB_USER_ID": "2"}), "2")

    def test_none_when_neither_present(self):
        self.assertIsNone(plc.existing_account({}))


class TestReadWriteSettings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_absent_file_returns_empty_dict(self):
        self.assertEqual(plc.read_settings(self.path), {})

    def test_empty_file_returns_empty_dict(self):
        self.path.write_text("")
        self.assertEqual(plc.read_settings(self.path), {})

    def test_invalid_json_raises_and_leaves_file_untouched(self):
        self.path.write_text("{not json")
        with self.assertRaises(ValueError):
            plc.read_settings(self.path)
        self.assertEqual(self.path.read_text(), "{not json")

    def test_write_creates_parent_directory(self):
        nested = pathlib.Path(self.tmp.name) / "a" / "b" / "settings.json"
        plc.write_settings(nested, {"env": {}})
        self.assertTrue(nested.exists())

    def test_write_output_is_valid_json_with_trailing_newline(self):
        plc.write_settings(self.path, {"env": {"X": "1"}})
        text = self.path.read_text()
        self.assertTrue(text.endswith("\n"))
        self.assertEqual(json.loads(text), {"env": {"X": "1"}})

    def test_round_trip(self):
        plc.write_settings(self.path, {"env": {"X": "1"}, "theme": "auto"})
        self.assertEqual(plc.read_settings(self.path),
                         {"env": {"X": "1"}, "theme": "auto"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd ~/parcellab-claude-skills/plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'pl_credentials'`.

- [ ] **Step 4: Write the implementation**

Create `plugins/pl-tools/scripts/pl_credentials.py`:

```python
#!/usr/bin/env python3
"""Write parcelLab credentials into the global Claude Code settings env block.

Two modes:

    pl_credentials.py --account 1626718   # account ID only, no secret, no prompt
    pl_credentials.py --token             # hidden prompt for the Order API credential

The token is NEVER accepted as a command-line value — that would expose a live
credential to the process table and shell history. `--token` is a bare flag that
triggers a hidden getpass prompt.

Merges into the `env` block of ~/.claude/settings.json without touching any other
key. Safe to re-run: updates in place rather than duplicating. Never prints the
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Write parcelLab credentials into ~/.claude/settings.json"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--account", metavar="ID",
                       help="write PARCELLAB_ACCOUNT_ID only (no secret)")
    group.add_argument("--token", action="store_true",
                       help="prompt (hidden) for the Order API credential")
    args = parser.parse_args(argv)

    try:
        settings = read_settings(SETTINGS_PATH)
        if args.account:
            if not args.account.strip().isdigit():
                raise ValueError(f"Account ID must be numeric, got: {args.account!r}")
            settings, message = run_account(settings, args.account.strip())
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
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd ~/parcellab-claude-skills/plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS, 24 tests, `OK`.

- [ ] **Step 6: Verify the CLI refuses to take a secret as a value**

```bash
cd ~/parcellab-claude-skills/plugins/pl-tools/scripts && python3 pl_credentials.py --token supersecret; echo "exit=$?"
```

Expected: argparse error, non-zero exit — `--token` takes no value, so a secret cannot be passed positionally. Also run `python3 pl_credentials.py` with no args and expect the "one of the arguments is required" error.

- [ ] **Step 7: Commit**

```bash
cd ~/parcellab-claude-skills && git add plugins/pl-tools/scripts && \
git commit -m "feat(pl-tools): add tested credential script with hidden input

Ports the working ~/.claude/scripts/set-parcellab-token.py into the repo, which
is the gap that made setup impossible for anyone but its author. Restructured
into pure functions for unit testing. The token is a bare flag triggering a
getpass prompt, never an argv value."
```

---

## Task 2: Plugin manifest, /pl-setup command, plugin README

**Files:**
- Create: `plugins/pl-tools/.claude-plugin/plugin.json`
- Create: `plugins/pl-tools/commands/pl-setup.md`
- Create: `plugins/pl-tools/README.md`

**Interfaces:**
- Consumes: `pl_credentials.py` from Task 1, invoked as `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --account <id>` and `... --token`.
- Produces: plugin name `pl-tools` at version `2.0.0`, referenced by `marketplace.json` in Task 5.

- [ ] **Step 1: Write the manifest**

Create `plugins/pl-tools/.claude-plugin/plugin.json`:

```json
{
  "name": "pl-tools",
  "version": "2.0.0",
  "description": "parcelLab internal tooling: create orders, simulate post-purchase journeys, build branded email layouts, raise demo requests, and investigate bugs. Run /pl-setup once after installing.",
  "author": {
    "name": "parcelLab",
    "email": "jamie.lee-smith@parcellab.com"
  },
  "keywords": ["parcellab", "pl", "orders", "returns", "email", "demo", "debugging"]
}
```

- [ ] **Step 2: Validate the manifest**

```bash
claude plugin validate ~/parcellab-claude-skills/plugins/pl-tools
```

Expected: `✔ Validation passed`. (It will pass with no skills present yet; the skills arrive in Tasks 3-4.)

- [ ] **Step 3: Write the /pl-setup command**

Create `plugins/pl-tools/commands/pl-setup.md`:

```markdown
---
description: Configure your parcelLab account and credentials for every pl-tools skill
---

Set up my parcelLab tooling. Work through these steps in order. Stop at the first
failure and tell me what went wrong — never guess a value, and never skip ahead.

## 1. Check the CLI is installed

Run `parcellab --version`. If it is not found, stop and tell me the CLI needs
installing (internal users get it from the `parcellab-cli` repo). Do not continue.

Note: the binary is `parcellab`. `parcellab-cli` is the repo it ships from, not a
command.

## 2. Check I am authenticated

Run `parcellab auth show`. If it shows I am not authenticated, run
`parcellab auth login` — it opens my browser for the device authorisation flow.
If login fails, stop and report it.

## 3. Resolve my account

- If `$PARCELLAB_ACCOUNT_ID` is already set, look up its name with
  `parcellab account account show $PARCELLAB_ACCOUNT_ID` and confirm with me:

  > Using **<account name>** (`<id>`) — your current default. Correct?

- If it is not set, ask me for my demo account's name, then find it with
  `parcellab account account search --name "<term>"`.

Always confirm by **name**, never by number alone. A wrong number looks fine; a
wrong name is obvious. If the search returns several matches, list them with names
and IDs and ask which one. If it returns none, tell me — do not pick the closest
match.

## 4. Write the account ID

Once I have confirmed:

`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --account <id>`

Report what the script prints.

## 5. Point the CLI's write guard at that account

`parcellab settings edit-mode set account-restricted --account <id>`

Then verify it took: `parcellab settings edit-mode show`.

Use my own leaf account — a parent account does not work. Without this, the CLI
may permit writes into a colleague's demo account and block my own, and that stays
invisible until a write fails. There are 13 demo accounts side by side under
*Demo SolCon*, so this matters.

If this step fails, say so plainly: setup is incomplete. Do not report success.

## 6. Order API token — ask first

Only two skills need an Order API token: `create-order` and `order-lifecycle`.
Ask me whether I will use them. If not, skip this step and tell me it was skipped.

If I will, print this command and ask me to run it myself:

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --token

Tell me, in these terms:

1. Click the terminal icon at the top right of the Claude Code window.
2. Paste that command and press Enter.
3. Paste the **base64** value from the parcelLab portal, then press Enter.
   **Nothing will appear on screen as you paste — no dots, no asterisks. That is
   correct, the input is hidden on purpose.** Paste once, press Enter once.

Prefer the base64 value over the raw token: it contains both my account ID and my
token, so one paste covers both, and it avoids the commonest error — pasting the
base64 blob into a field expecting the raw token, which shows up later as an
unexplained `401`.

**Do not offer to take the token in chat, and do not read it from a file path I
give you.** Chat messages are stored in the transcript. The terminal is the only
correct route.

## 7. Tell me to restart

I must fully quit Claude Code (**Cmd-Q**, not just closing the window) and reopen
it. Environment variables are read only at startup, so nothing above takes effect
until I do.

## 8. Give me a way to verify

Tell me that after restarting I should ask *"which parcelLab account am I set up
against?"* — and that you should be able to name the account and ID without
asking me anything.

---

Never echo my token back to me, and never include it in your reply.
```

- [ ] **Step 4: Write the plugin README**

Create `plugins/pl-tools/README.md`:

```markdown
# pl-tools

parcelLab internal tooling for Claude Code — five skills and one setup command in
a single plugin.

| Handle | What it does |
|---|---|
| `pl-tools:create-order` | Create a real order via the production Order API |
| `pl-tools:order-lifecycle` | Simulate a full post-purchase journey with timed checkpoints |
| `pl-tools:branded-template` | Build a branded transactional email layout from a brand URL |
| `pl-tools:demo-request` | Raise a custom demo request from a prospect URL |
| `pl-tools:bug-investigation` | Investigate and document a live product bug |
| `pl-tools:pl-setup` | One-time setup (below) |

## Setup

Run `/pl-setup` once after installing, then fully quit and reopen the app.

It checks the `parcellab` CLI, logs you in if needed, resolves your demo account
and writes it to the `env` block of your global `~/.claude/settings.json` as
`PARCELLAB_ACCOUNT_ID`, and points the CLI's write guard at that same account so a
skill cannot write into a colleague's demo account.

### Order API token

Only `create-order` and `order-lifecycle` need one. `/pl-setup` asks, and if you
say yes it hands you this to run in the app's built-in terminal:

    python3 <plugin>/scripts/pl_credentials.py --token

The prompt is hidden — **nothing appears as you paste, which is correct**. Paste
the base64 value from the portal (it carries both your account ID and token).

The token is never accepted in chat and never passed as a command-line argument,
so it stays out of the conversation transcript, the process table, and your shell
history.

## Prerequisites

- The `parcellab` CLI, authenticated
- Python 3 (macOS ships it) — the setup script is stdlib-only
- `bug-investigation` additionally needs the org's `parcellab-product-api` plugin
  (from `parcelLab/parcellab-cli`) for Product API config knowledge, and
  Claude-in-Chrome for screenshot/recording capture
- `demo-request` needs Node and a one-time `npm install` in
  `skills/demo-request/scripts/`
- `branded-template` needs the ParcelLab MCP connector and the built-in Browser pane

## Tests

```bash
cd scripts && python3 -m unittest discover -s tests -v
```
```

- [ ] **Step 5: Commit**

```bash
cd ~/parcellab-claude-skills && git add plugins/pl-tools && \
git commit -m "feat(pl-tools): add manifest, /pl-setup command, and plugin README

Replaces the paste-this-exact-prompt setup flow with a command. The command
routes the token through the built-in terminal and states plainly that hidden
input showing nothing is expected, which was the main confusion point."
```

---

## Task 3: Move the three straightforward skills

`create-order`, `order-lifecycle`, `demo-request`. Includes one internal
cross-reference rename and one live bug fix.

**Files:**
- Move: three skill directories into `plugins/pl-tools/skills/`
- Modify: `create-order/SKILL.md:2`, `create-order/README.md:1`, `order-lifecycle/SKILL.md:2,107,200`, `demo-request/SKILL.md:2,237`

**Interfaces:**
- Consumes: `plugins/pl-tools/` from Task 2.
- Produces: skills named `create-order`, `order-lifecycle`, `demo-request`, referenced by `pl-tools/README.md` and the root README.

- [ ] **Step 1: Move the three directories**

```bash
cd ~/parcellab-claude-skills && mkdir -p plugins/pl-tools/skills && \
git mv plugins/parcellab-create-order/skills/parcellab-create-order plugins/pl-tools/skills/create-order && \
git mv plugins/parcellab-order-lifecycle/skills/parcellab-order-lifecycle plugins/pl-tools/skills/order-lifecycle && \
git mv plugins/parcellab-demo-request/skills/parcellab-demo-request plugins/pl-tools/skills/demo-request
```

- [ ] **Step 2: Verify git tracked the moves as renames**

```bash
cd ~/parcellab-claude-skills && git status --short | head -20
```

Expected: lines beginning `R ` (renamed), not `D `/`A ` pairs. History is preserved.

- [ ] **Step 3: Rename the three `name:` fields**

In `plugins/pl-tools/skills/create-order/SKILL.md` line 2:

```
name: create-order
```

In `plugins/pl-tools/skills/order-lifecycle/SKILL.md` line 2:

```
name: order-lifecycle
```

In `plugins/pl-tools/skills/demo-request/SKILL.md` line 2:

```
name: demo-request
```

**Leave every `description:` line exactly as it is.** They contain "ParcelLab" and
"parcelLab", which is what makes the skills trigger on prose.

- [ ] **Step 4: Fix the create-order skill README title**

`plugins/pl-tools/skills/create-order/README.md` line 1:

```markdown
# create-order — Skill README
```

- [ ] **Step 5: Rename the two internal cross-references**

In `plugins/pl-tools/skills/order-lifecycle/SKILL.md`, lines 107 and 200, change
`` `parcellab-create-order` `` to `` `create-order` ``. Both refer to the sibling
skill moved in Step 1.

- [ ] **Step 6: Fix the broken script path in demo-request (live bug)**

`plugins/pl-tools/skills/demo-request/SKILL.md` line 237 currently reads:

```
node ~/.claude/skills/parcellab-demo-request/scripts/submit_demo_request.mjs /tmp/cdc-payload.json
```

That path does not exist — it is a leftover from when skills were hand-copied into
`~/.claude/skills/`, a directory that is now absent. The skill fails at its final
submit step today. Change it to:

```
node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/submit_demo_request.mjs /tmp/cdc-payload.json
```

- [ ] **Step 7: Confirm the config-file path was NOT changed**

```bash
cd ~/parcellab-claude-skills && grep -n "parcellab-demo-request.env" plugins/pl-tools/skills/demo-request/SKILL.md
```

Expected: 3 hits, all still `~/.claude/parcellab-demo-request.env`. That file
exists on disk; renaming it breaks working setups.

- [ ] **Step 8: Confirm no stray old identifiers remain in these three**

```bash
cd ~/parcellab-claude-skills && grep -rn "parcellab-create-order\|parcellab-order-lifecycle\|parcellab-demo-request" plugins/pl-tools/skills/create-order plugins/pl-tools/skills/order-lifecycle plugins/pl-tools/skills/demo-request | grep -v "parcellab-demo-request.env"
```

Expected: no output.

- [ ] **Step 9: Commit**

```bash
cd ~/parcellab-claude-skills && git add -A plugins && \
git commit -m "refactor(pl-tools): move create-order, order-lifecycle, demo-request

Renames the skills to drop the redundant plugin-name prefix. Descriptions keep
'parcelLab' so prose triggering is unchanged.

Also fixes a live bug: demo-request pointed at
~/.claude/skills/parcellab-demo-request/scripts/, a hand-copied-era path that no
longer exists, so its submit step failed. Now uses CLAUDE_PLUGIN_ROOT."
```

---

## Task 4: Move the two skills with protected external references

`branded-template` and `bug-investigation`. These carry references that look
renameable and are not, so they get their own task and their own review.

**Files:**
- Move: two skill directories into `plugins/pl-tools/skills/`
- Modify: `branded-template/SKILL.md:2`, `bug-investigation/SKILL.md:2` (only)

**Interfaces:**
- Consumes: `plugins/pl-tools/skills/` from Task 3.
- Produces: skills named `branded-template`, `bug-investigation`.

- [ ] **Step 1: Move the two directories**

```bash
cd ~/parcellab-claude-skills && \
git mv plugins/parcellab-brand-layout/skills/parcellab-brand-layout-desktop plugins/pl-tools/skills/branded-template && \
git mv plugins/parcellab-bug-investigation/skills/parcellab-bug-investigation plugins/pl-tools/skills/bug-investigation
```

- [ ] **Step 2: Rename the two `name:` fields — and nothing else**

`plugins/pl-tools/skills/branded-template/SKILL.md` line 2:

```
name: branded-template
```

`plugins/pl-tools/skills/bug-investigation/SKILL.md` line 2:

```
name: bug-investigation
```

Leave both `description:` lines untouched.

- [ ] **Step 3: Add a protective comment in branded-template**

The phrase `parcellab-brand-layout` appears at lines 10 and 381 and refers to the
**external** Cowork/CLI variant of this skill, which lives in a different repo —
not to this skill. Immediately above the line 381 heading
(`## Differences from \`parcellab-brand-layout\` (CLI/Playwright version)`), insert:

```markdown
<!-- Do not rename `parcellab-brand-layout` below: it names the separate
     Cowork/CLI variant in another repo, not this skill. -->
```

- [ ] **Step 4: Add a protective comment in bug-investigation**

`parcellab-product-api` and `parcellab-product-configuration` (lines 81 and 103)
belong to the **org's** plugin from `parcelLab/parcellab-cli`. Immediately above
the line 81 list item, insert:

```markdown
<!-- Do not rename `parcellab-product-api` / `parcellab-product-configuration`:
     they belong to the org's plugin (parcelLab/parcellab-cli), not to pl-tools. -->
```

- [ ] **Step 5: Verify every protected token survived**

```bash
cd ~/parcellab-claude-skills/plugins/pl-tools/skills && \
echo "parcellab-previews (expect 6):   $(grep -c 'parcellab-previews' branded-template/SKILL.md)" && \
echo "parcellab-layout (expect 3):     $(grep -o 'parcellab-layout' branded-template/SKILL.md | wc -l | tr -d ' ')" && \
echo "parcellab-brand-layout (expect 2): $(grep -o 'parcellab-brand-layout' branded-template/SKILL.md | wc -l | tr -d ' ')" && \
echo "parcellab-product-api (expect 2):  $(grep -o 'parcellab-product-api' bug-investigation/SKILL.md | wc -l | tr -d ' ')" && \
echo "parcellab-product-configuration (expect 1): $(grep -c 'parcellab-product-configuration' bug-investigation/SKILL.md)"
```

All five counts must match. A zero anywhere means a protected reference was
renamed — revert and redo Step 2.

- [ ] **Step 6: Confirm the old skill identifiers are gone**

```bash
cd ~/parcellab-claude-skills && grep -rn "parcellab-brand-layout-desktop\|name: parcellab-bug-investigation" plugins/pl-tools/skills/
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
cd ~/parcellab-claude-skills && git add -A plugins && \
git commit -m "refactor(pl-tools): move branded-template and bug-investigation

Drops the meaningless -desktop suffix (it distinguished this skill from the
Cowork variant, which now lives in a separate repo).

Adds comments protecting references that look renameable but are not: the
org-owned parcellab-product-api plugin, and parcellab-brand-layout, which names
the external Cowork variant rather than this skill."
```

---

## Task 5: Marketplace, root README, remove the old plugins

**Files:**
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`
- Delete: `plugins/parcellab-brand-layout/`, `plugins/parcellab-bug-investigation/`, `plugins/parcellab-create-order/`, `plugins/parcellab-demo-request/`, `plugins/parcellab-order-lifecycle/`

**Interfaces:**
- Consumes: `pl-tools` manifest (Task 2) and all five moved skills (Tasks 3-4).
- Produces: a marketplace with exactly two entries, ready for the Task 6 migration.

- [ ] **Step 1: Remove the five now-empty plugin directories**

```bash
cd ~/parcellab-claude-skills && \
git rm -r plugins/parcellab-brand-layout plugins/parcellab-bug-investigation \
          plugins/parcellab-create-order plugins/parcellab-demo-request \
          plugins/parcellab-order-lifecycle
```

Only the `.claude-plugin/plugin.json` files should remain in them at this point;
the skills moved in Tasks 3-4. Confirm with `git status --short` that nothing
unexpected is being deleted.

- [ ] **Step 2: Rewrite marketplace.json to two entries**

Replace `.claude-plugin/marketplace.json` entirely:

```json
{
  "name": "parcellab-skills",
  "owner": {
    "name": "Jamie Lee-Smith",
    "email": "jamie.lee-smith@parcellab.com"
  },
  "plugins": [
    {
      "name": "onyx",
      "source": "./plugins/onyx",
      "description": "Pull knowledge from your parcelLab Onyx instance into Claude — semantic search, cited RAG answers, and full-document retrieval. Run /onyx-setup after installing to connect your own account."
    },
    {
      "name": "pl-tools",
      "source": "./plugins/pl-tools",
      "description": "parcelLab internal tooling: create orders, simulate post-purchase journeys, build branded email layouts, raise demo requests, and investigate bugs. Five skills plus /pl-setup, which configures your account and credentials in one pass."
    }
  ]
}
```

- [ ] **Step 3: Validate the marketplace manifest**

```bash
claude plugin validate ~/parcellab-claude-skills
```

Expected: `✔ Validation passed`.

- [ ] **Step 4: Update the root README**

Four edits:

1. **Install section** — replace the per-skill install line with one plugin:

   ```
   /plugin marketplace add jamie1leesmith-lgtm/parcellab-claude-skills
   /plugin install pl-tools@parcellab-skills
   ```

2. **Remove the "install individually" premise.** The opening line currently reads
   *"Install skills individually — take only the ones you need."* That is no longer
   true. Replace with: *"One plugin, `pl-tools`, carries all five parcelLab skills
   plus its setup command. Onyx ships separately."*

3. **Replace the entire "One-time setup" numbered list and the "Entering your Order
   API token" section** with:

   ```markdown
   ### One-time setup

   1. Install: **+** → **Plugins** → **Add plugin** → marketplace source
      `jamie1leesmith-lgtm/parcellab-claude-skills` → install `pl-tools`.
   2. In a **new** conversation, run `/pl-setup`.
   3. It checks the CLI, logs you in, resolves your demo account, writes it to your
      global settings, and points the CLI's write guard at it.
   4. If you use `create-order` or `order-lifecycle`, it hands you one command to
      run in the app's built-in terminal (click the terminal icon, top right) and
      prompts for your Order API credential. **Nothing appears on screen as you
      paste it — that is correct, the input is hidden.** Paste the base64 value
      from the portal: it carries both your account ID and token.
   5. Fully quit the app (**Cmd-Q**) and reopen. Environment variables are read
      only at startup.
   6. Verify: ask *"which parcelLab account am I set up against?"* — Claude should
      name it without asking you anything.

   The token never enters the chat, a command-line argument, or your shell history.
   ```

4. **Update the skill table** to the `pl-tools:*` handles from the plugin README in
   Task 2, and update the "adding a new skill" maintainer section: new skills now
   go in `plugins/pl-tools/skills/<name>/` and need only a `pl-tools` version bump,
   not a new marketplace entry.

Leave the "Already have these skills the old way?" section and the release-process
checklist as they are — both still apply.

- [ ] **Step 5: Confirm no reference to a deleted plugin name remains**

```bash
cd ~/parcellab-claude-skills && grep -rn "parcellab-create-order\|parcellab-order-lifecycle\|parcellab-brand-layout\b\|parcellab-bug-investigation" README.md .claude-plugin/marketplace.json
```

Expected: no output. (`docs/` is historical and stays untouched.)

- [ ] **Step 6: Commit**

```bash
cd ~/parcellab-claude-skills && git add -A && \
git commit -m "refactor: collapse six marketplace entries into two

pl-tools replaces the five single-skill parcellab-* plugins. Rewrites the README
setup section around /pl-setup, removing the paste-this-exact-prompt workaround
and the now-untrue 'install skills individually' premise."
```

---

## Task 6: Push, migrate the local install, verify

The only task that pushes, and the only one that changes state outside the repo.

**Files:** none — this is verification and migration.

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: a working local install of `pl-tools` and a verified disjoint namespace.

- [ ] **Step 1: Confirm the remote is the personal account**

```bash
cd ~/parcellab-claude-skills && git remote -v
```

Expected: `jamie1leesmith-lgtm/parcellab-claude-skills`. If it shows the
`parcelLab` org, stop and ask — org pushes need explicit per-action approval.

- [ ] **Step 2: Run the full test suite once more**

```bash
cd ~/parcellab-claude-skills/plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: `OK`, 24 tests.

- [ ] **Step 3: Push**

```bash
cd ~/parcellab-claude-skills && git push origin main
```

- [ ] **Step 4: Refresh the marketplace**

```bash
claude plugin marketplace update parcellab-skills
```

- [ ] **Step 5: Confirm pl-tools is available BEFORE removing anything**

```bash
claude plugin list --available 2>/dev/null | grep -i "pl-tools" || \
  grep -o '"name": "pl-tools"' ~/.claude/plugins/marketplaces/parcellab-skills/.claude-plugin/marketplace.json
```

Expected: `pl-tools` appears. **Do not proceed past this step until it does** —
this is what makes uninstalling the working plugins safe.

- [ ] **Step 6: Uninstall the five old plugins**

```bash
for p in parcellab-brand-layout parcellab-bug-investigation parcellab-create-order \
         parcellab-demo-request parcellab-order-lifecycle; do
  claude plugin uninstall "$p@parcellab-skills" --yes 2>&1 | tail -1
done
```

Uninstall precedes install so the old and new never coexist — duplicate skills
with near-identical descriptions would make triggering nondeterministic.

- [ ] **Step 7: Install pl-tools**

```bash
claude plugin install pl-tools@parcellab-skills
```

- [ ] **Step 8: Confirm the installed state**

```bash
claude plugin list 2>&1 | grep -A2 -i "pl-tools\|onyx\|product-api"
```

Expected: `pl-tools` 2.0.0 enabled, `onyx` 0.2.1 enabled,
`parcellab-product-api` 0.1.0 enabled (the org's, untouched), and **no**
`parcellab-brand-layout` / `-create-order` / `-demo-request` /
`-order-lifecycle` / `-bug-investigation`.

- [ ] **Step 9: Confirm the component inventory**

```bash
claude plugin details pl-tools@parcellab-skills
```

Expected: 5 skills (`branded-template`, `bug-investigation`, `create-order`,
`demo-request`, `order-lifecycle`) plus the `pl-setup` command. If a skill is
missing, its `SKILL.md` frontmatter `name:` probably does not match its directory.

- [ ] **Step 10: Restart, then verify the namespace split**

Fully quit the app (**Cmd-Q**) and reopen — plugins load at startup.

Then, in a new conversation, confirm:

- `/pl` offers the six `pl-tools:*` handles and nothing from the org's plugin
- `/parcellab` offers only the org's `parcellab-product-api:*` skills
- The two sets are disjoint — this is the whole point of the rename

- [ ] **Step 11: Verify history survived the moves**

```bash
cd ~/parcellab-claude-skills && git log --follow --oneline -3 plugins/pl-tools/skills/create-order/SKILL.md
```

Expected: commits predating today's move. If only today's commit appears, the move
was recorded as delete+add rather than a rename.

- [ ] **Step 12: Verify prose triggering still works**

In a new conversation, confirm each skill still fires on natural phrasing — the
descriptions were deliberately left alone, so this should pass:

- *"create a parcelLab order for a UK delivery"* → `create-order`
- *"simulate the full journey for Nike"* → `order-lifecycle`
- *"create a parcelLab layout for nike.com"* → `branded-template`
- *"create a demo request for example.com"* → `demo-request`
- *"investigate this bug on portal 39625"* → `bug-investigation`

If any fails to trigger, a `description:` line was edited — check `git diff` for
that file against the pre-move version.

- [ ] **Step 13: End-to-end check of the setup flow**

Run `/pl-setup` and confirm it walks the eight steps, names your account rather
than just its number, and — if you opt into the token step — hands you the
terminal command rather than asking for the credential in chat.

- [ ] **Step 14: Update the memory note**

`project_parcellab_skills_next_session.md` describes building a `/parcellab-setup`
command across separate plugins. That is now done differently (one `pl-tools`
plugin, `/pl-setup`). Update it, and update
`project_skill_distribution.md`, which still says "4 skills" and lists the old
plugin names.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| One plugin `pl-tools`, six handles | 2, 3, 4, 5 |
| `pl-setup` as command not skill | 2 |
| Script: two modes, hidden input, no argv secret | 1 |
| Script: pure functions unit-tested | 1 |
| Script: base64/raw handling, mismatch prompt, bad JSON, idempotent | 1 |
| Legacy `PARCELLAB_USER_ID` read not written | 1 (`existing_account`) |
| Command: 8-step sequence, confirm by name, edit-mode guard | 2 |
| Token step conditional on a question, not on installed plugins | 2 (Step 3 §6) |
| Renames, identifiers only, descriptions untouched | 3, 4 |
| `-desktop` dropped | 4 |
| The org `parcellab-product-api` trap | 4 (Steps 4, 5) |
| Version `2.0.0`, bump mandatory | 2 (manifest), Global Constraints |
| Migration: verify-then-uninstall-then-install | 6 (Steps 5-7) |
| Error handling table | 1 (implementation), 2 (command text) |
| Testing: unit + manual list | 1, 6 |
| Docs: README rewrite, plugin README | 2, 5 |
| `git log --follow` history check | 6 (Step 11) |
| Deferred: `create-order` vs `order-lifecycle` | not in scope, unchanged |

No gaps.

**Placeholder scan:** none. Every code step contains real code; every rename step
names the file, the line, and the exact replacement text.

**Type consistency:** `decode`, `read_settings`, `merge_env`, `write_settings`,
`existing_account`, `run_account`, `run_token`, `main` — the names used in the
Task 1 tests match the Task 1 implementation, and the CLI invocation in Task 2
(`pl_credentials.py --account <id>` / `--token`) matches the argparse definition.
Script filename is `pl_credentials.py` (underscore) consistently in every step,
correcting the spec's hyphenated form.

**Two corrections to the spec, made deliberately:**

1. **Filename**: `pl_credentials.py`, not `pl-credentials.py` — a hyphen is not
   importable, which would block the unit tests.
2. **Rename surface**: the spec said "2 cross-references". The real figure is
   8 tokens renamed out of 26 `parcellab-*` occurrences; the other 18 are
   filesystem paths, filenames, the org's plugin, or the external Cowork variant.
   The DO-NOT-RENAME table in Global Constraints is the authoritative list.

**One live bug folded in** (Task 3, Step 6): `demo-request/SKILL.md:237` points at
`~/.claude/skills/parcellab-demo-request/scripts/`, which does not exist. The
skill's submit step fails today. Fixed to `${CLAUDE_PLUGIN_ROOT}` while the file
is being moved anyway.
