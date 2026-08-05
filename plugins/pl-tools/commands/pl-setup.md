---
description: Configure your parcelLab account and credentials for every pl-tools skill
---

Set up my parcelLab tooling. Work through these steps in order. Stop at the first
failure and tell me what went wrong — never guess a value, and never skip ahead.

## 1. Check the CLI is installed

Run `command -v parcellab`. If it prints nothing (non-zero exit), stop and tell me
the CLI needs installing (internal users get it from the `parcellab-cli` repo). Do
not continue.

Note: the binary is `parcellab`. `parcellab-cli` is the repo it ships from, not a
command. **Do not use `parcellab --version`** — that option does not exist and the
CLI errors on it, which would look like the CLI is missing when it is installed
and working.

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

## 6. Order API token — check first, then ask

**First check whether I already have one:** if `$PARCELLAB_TOKEN` is set, say so
and skip the rest of this step. Do not ask me to paste a credential I already
have. (Mention that if it turns out to be wrong or expired — an unexplained `401`
from an order skill — the fix is to re-run the `--token` command below.)

If it is not set: only two skills need it, `create-order` and `order-lifecycle`.
Ask whether I will use them. If not, skip this step and tell me it was skipped.

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

## 6a. Custom Demo Creator token — check first, then ask

Only `demo-request` needs this.

**First check whether I already have one:** if `$CDC_DEMO_API_TOKEN` is set, say so
and skip the rest of this step.

If it is not set: ask whether I will use `demo-request`. If not, skip this step
and tell me it was skipped.

If I will, print this command and ask me to run it myself, the same way as the
Order API token above — terminal icon top right, paste, press Enter, nothing
appears on screen and that is correct:

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --cdc-token

This one is simpler than the Order API token: it's a single value, not a base64
pair, so there is nothing to decode. The base URL is filled in automatically.

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
