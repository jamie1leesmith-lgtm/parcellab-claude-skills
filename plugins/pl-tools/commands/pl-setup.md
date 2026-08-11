---
description: Configure your parcelLab account and credentials for every pl-tools skill
---

Set up my parcelLab tooling. Work through these steps in order. Stop at the first
failure and tell me what went wrong — never guess a value, and never skip ahead.

## 0. Check for hand-copied skills — do this first, every run

Some people have an earlier version of one or more of these skills as a
`SKILL.md` copied straight into `~/.claude/skills/`, from before this
marketplace existed. Run:

    ls ~/.claude/skills/ 2>/dev/null

If that directory doesn't exist or is empty, say nothing and move on — this is
the common case and doesn't need mentioning.

If it lists anything matching a `pl-tools` skill name — `create-order`,
`order-lifecycle`, `branded-template`, `demo-request`, `bug-investigation`,
`shopify-seed` — **or** an old pre-rename name (`parcellab-create-order`,
`parcellab-order-lifecycle`, `parcellab-brand-layout-desktop`,
`parcellab-demo-request`, `parcellab-bug-investigation`), stop and tell me
plainly, by name, which ones:

> You have a hand-copied `<name>` in `~/.claude/skills/`. Claude picks which
> skill to run by matching your request against each skill's *description*, not
> its name — so this old copy and the plugin's copy can both match the same
> request, and you have no control over which one wins. The hand-copied one is
> frozen at whatever day it was copied: none of this plugin's fixes reach it.
> Today alone that would have meant missing the destination-country fix to
> `create-order`, the fix that made `demo-request` runnable at all, and the
> account write-guard this setup just configured.

Then offer to move it aside rather than delete it:

    mkdir -p ~/claude-skills-archive && mv ~/.claude/skills/<name> ~/claude-skills-archive/

Only move files I confirm — don't do this without asking. Once moved, tell me
to quit and reopen the app so the stale skill stops loading.

This check runs every time `/pl-setup` runs, including re-runs, since a
straggler could be added to `~/.claude/skills/` at any point after the first
setup.

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

## 6. Custom Demo Creator token — check first, then ask

Only `demo-request` needs this.

**First check whether I already have one:** if `$CDC_DEMO_API_TOKEN` is set, say so
and skip the rest of this step.

If it is not set: ask whether I will use `demo-request`. If not, skip this step
and tell me it was skipped.

If I will, print this command and ask me to run it myself:

1. Click the terminal icon at the top right of the Claude Code window.
2. Paste the command and press Enter.
3. Paste the token, then press Enter. **Nothing will appear on screen as you
   paste — no dots, no asterisks. That is correct, the input is hidden on
   purpose.** Paste once, press Enter once.

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --cdc-token

It's a single value, nothing to decode. The base URL is filled in automatically.

### Optional: CDC account-config UUIDs (for demo-environment)

The `demo-environment` skill selects a CDC account configuration matching the
run's target account. Each user has up to three (visible in the CDC UI when
editing an account config — there is no API to list them). If the user has
them, append to `~/.claude/parcellab-demo-request.env`:

    CDC_ACCOUNT_CONFIG_DEFAULT=<uuid>        # their own demo account (the default target)
    CDC_ACCOUNT_CONFIG_PARCELFASHION=<uuid>  # the shared parcelfashion account
    CDC_ACCOUNT_CONFIG_SHOPIFY=<uuid>        # Shopify demos

All optional — demo-environment also captures a missing one on its first run
and offers to store it here. With none stored, the CDC uses the caller's
default config and demo-environment says so in its report. They are ids, not
credentials, but they still belong in the env file, not the transcript.

### Optional: Shopify CLI (for Shopify demos)

Only needed by users running Shopify demos (`shopify-seed`, or the
`demo-environment` skill's Retain-Shopify path). Skip freely otherwise —
everything else in pl-tools works without it.

1. Check: `command -v shopify && shopify version`. If present, skip to
   step 3.
2. Install (the plain brew install fails — the formula lives in a
   non-official tap that Homebrew refuses until trusted):

       brew tap shopify/shopify
       brew trust shopify/shopify
       brew install shopify-cli

   Then, before anything else: `shopify config autoupgrade off` — a
   self-upgrade firing mid-session uninstalls the CLI and leaves a dangling
   symlink.
3. Authenticate against the user's **dev store** (never a production
   merchant store), warning them a browser consent window will open. Request
   the full scope set up front — the demo-environment order engine needs the
   order and fulfilment scopes, and asking now avoids a re-consent
   mid-demo:

       shopify store auth -s <store>.myshopify.com \
         --scopes write_products,write_inventory,read_orders,write_orders,write_fulfillments

   Substitute the real subdomain — never write the literal text `<store>`.
4. Persist the store so skills stop asking:

       echo 'SHOPIFY_DEMO_STORE=<store>.myshopify.com' > ~/.claude/parcellab-shopify-seed.env

   (A config file, not an env var in settings.json — env vars are only read
   at app startup, and this one is read fresh from the file by each run.)

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
