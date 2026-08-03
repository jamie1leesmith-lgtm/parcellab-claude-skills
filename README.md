# parcelLab Claude skills

A private Claude Code plugin marketplace for parcelLab team skills. Install skills **individually** — take only the ones you need.

> 🔒 **This repo is private.** You need to be invited as a collaborator before you can add it as a marketplace or install anything. Ask Jamie (`jamie1leesmith-lgtm`) for access.

## Install (Claude desktop app — no terminal needed)

1. Open the Claude desktop app → **Code** tab
2. Click **+** next to the prompt box → **Plugins** → **Add plugin**
3. Enter this repo as the marketplace source: `jamie1leesmith-lgtm/parcellab-claude-skills`
4. Pick the skill you want → **Install** (repeat for any others)

Installed skills become available automatically in **new** conversations — the
one you installed from won't see them.

Already running these skills as hand-copied `SKILL.md` files? Read
[Already have these skills the old way?](#already-have-these-skills-the-old-way-remove-them-first)
before installing.

Then do the [One-time setup](#one-time-setup) once — it takes about two minutes
and every parcelLab skill depends on it.

## Install (Claude Code CLI)

```
/plugin marketplace add jamie1leesmith-lgtm/parcellab-claude-skills
/plugin install parcellab-create-order@parcellab-skills
```

Swap `parcellab-create-order` for whichever skill you want — install as many or as few as you like.

## Available skills

| Skill | What it does | Trigger example |
|-------|--------------|-----------------|
| `onyx` | Pulls knowledge from your parcelLab Onyx instance into Claude — semantic search, cited RAG answers, and document retrieval | *"Search Onyx for our return policy on damaged items"* |
| `parcellab-brand-layout` | Builds a branded transactional email layout in your ParcelLab account from a brand URL, with live preview in the desktop app | *"Create a ParcelLab layout for www.nike.com"* |
| `parcellab-create-order` | Creates a real order in your ParcelLab account via the production Order API, filling in realistic dummy data | *"Push a test order to ParcelLab for a UK delivery"* |
| `parcellab-demo-request` | Creates a custom demo request from a prospect website URL — collects products, verifies images, submits to the Custom Demo Creator | *"Create a demo request for www.example.com"* |
| `parcellab-order-lifecycle` | Simulates a full post-purchase journey: creates an untracked order, then pushes timed checkpoints (warehouse → carrier → delivery) so ParcelLab fires the comms for each stage | *"Simulate the full journey for [brand]"* |
| `parcellab-bug-investigation` | Investigates a product bug end to end: checks live config via the `parcellab` CLI, reproduces it in Claude-in-Chrome with real screenshot/recording capture, isolates root cause against sibling portals, and publishes a shareable bug report as an artifact, HTML file, and PDF — always *before* any mitigation, which needs express account-number-specific sign-off | *"Investigate this bug on [portal]"* |

---

## Your default account

Every skill here writes into a parcelLab account. Rather than naming one each
time, they all read a single default and confirm it before writing anything.

`PARCELLAB_ACCOUNT_ID` in the `env` block of your global `~/.claude/settings.json`
holds your demo account:

```json
{ "env": { "PARCELLAB_ACCOUNT_ID": "1626718" } }
```

You do not set this up by hand. Ask Claude to set up your parcelLab skills, or
just use a skill — the first run walks you through it, looks your account up by
name, and writes the file for you.

Two skills additionally need an Order API token (`PARCELLAB_TOKEN`):
`parcellab-create-order` and `parcellab-order-lifecycle`. Nothing else does.

> `PARCELLAB_USER_ID` is still accepted as an alias for `PARCELLAB_ACCOUNT_ID`,
> so anyone set up before this convention keeps working. New setups use
> `PARCELLAB_ACCOUNT_ID`.

### One-time setup

You need the parcelLab CLI installed — internal users have this already. Then, in
the Claude Code desktop app:

**1. Install the plugins.** **+** → **Plugins** → **Add plugin** → marketplace
source `jamie1leesmith-lgtm/parcellab-claude-skills` → install the ones you want.

**2. Start a new conversation and paste this exact prompt:**

> **Set up the parcelLab skills for the plugins I've just installed. Check the
> `parcellab` CLI, log me in if needed, find my demo account, write it to my
> global settings, and set the CLI edit-mode guard to that account.**

Say it in a *fresh* conversation, not the one you were installing from — newly
installed plugins aren't loaded into a conversation that was already running.

That wording matters. "Set up parcelLab" on its own is vague enough that Claude
may only configure whichever single skill you last mentioned. The prompt above
names all four things the setup actually does.

**3. Claude runs the setup.** It checks the CLI is reachable, logs you in
(`parcellab auth login` opens your browser), finds your demo account by name,
and writes `PARCELLAB_ACCOUNT_ID` to the `env` block of your global
`~/.claude/settings.json` — you approve the edit when prompted.

**4. Claude points the CLI's write guard at that same account**
(`parcellab settings edit-mode set account-restricted --account <id>`). This is
what stops a skill writing into a colleague's demo account — there are 13 of them
side by side under *Demo SolCon*, so it matters.

**5. Order API token — only if you installed `parcellab-create-order` or
`parcellab-order-lifecycle`.** Nothing else needs it. See
[Entering your Order API token](#entering-your-order-api-token) below — this is
the one step that does *not* happen in the chat box.

**6. Quit and reopen the app.** Not just close the window — fully quit
(**⌘Q** on macOS). Environment variables are only read at startup, so nothing
above takes effect until you do.

**7. Check it worked.** In a new conversation, ask *"which parcelLab account am I
set up against?"* — Claude should name your demo account and its ID without
asking you anything.

### Entering your Order API token

Claude will not accept a token pasted into the chat box, and shouldn't — chat
messages are stored in the conversation transcript. Instead it hands you a
command to run yourself, in the terminal built into the app. Expect this, it's
not an error:

1. **Click the terminal icon at the top right of the Claude Code window.** A
   terminal panel opens below the conversation. It's a normal shell on your Mac.
2. **Paste the command Claude gave you and press Enter.** It'll prompt you for
   the credential.
3. **Paste the base64 value from the portal**, then press Enter.
   - **Nothing will appear as you paste — no dots, no asterisks, no cursor
     movement. That is correct.** The input is hidden on purpose. Paste once,
     press Enter once, and trust it. Pasting twice because "it didn't work" is
     the most common way this goes wrong.
   - Use the **base64** value from the portal, not the raw token. It contains
     both your account ID and your token, so one paste covers both. Pasting the
     base64 blob into a field that wanted the raw token is what produces an
     unexplained `401` later.
4. **Quit and reopen the app** (**⌘Q**). The token is written to
   `~/.claude/settings.json`, and that file is only read at startup — the skill
   will still say "credentials missing" until you restart.
5. Back in a new conversation, ask Claude to push a test order. If it 401s, the
   token went in wrong: rerun the same command and paste again.

Claude never echoes the token back to you, and it should never appear in the
conversation. If you ever see it in chat, it went in the wrong place — rotate it.

Everything after that is automatic. Before any skill writes to your account it
confirms which one:

> Using **Acme Demo** (`1626718`) — your default. Correct, or use a different
> account?

---

### onyx

Pulls knowledge from your parcelLab Onyx instance directly into Claude — semantic search, cited RAG answers, and full-document retrieval, via three tools (`onyx_search`, `onyx_ask`, `onyx_fetch_document`) and two commands (`/onyx-search`, `/onyx-ask`).

**Prerequisites:**

1. **Node.js 18+** — the MCP server and setup script use only Node's built-ins, no `npm install` needed.
2. **Your own Onyx account and API token** — after installing, run `/onyx-setup` and follow its two questions to connect your account. Nobody's credentials are bundled with the plugin; each person configures their own.

> **Already had Onyx working before installing this plugin?** It'll just work,
> no setup needed. Credentials live in the `env` block of your global
> `~/.claude/settings.json` (`ONYX_API_URL`, `ONYX_API_TOKEN`,
> `ONYX_PERSONA_ID`) — *not* inside the plugin. Anything that wrote those keys
> before (a hand-rolled MCP server, a manual edit) leaves them there when it's
> removed, and this plugin's MCP server reads the exact same three variables. So
> the plugin inherits your existing auth. Only run `/onyx-setup` if
> `/onyx-search` actually fails.

---

### parcellab-brand-layout

Creates a branded transactional email layout in **your ParcelLab account** from any brand website URL. Claude scrapes the brand's styles and logo using Claude Code's **built-in browser** (the Browser pane), builds an email layout, previews it live in that same pane, and — after you approve — pushes the layout to ParcelLab as a draft. No Chrome extension required.

**Prerequisites:**

1. **Your default account** — see [Your default account](#your-default-account)
2. **Claude Code with the built-in browser** (the Browser pane / `mcp__Claude_Browser__*` tools — loaded by default)
3. **ParcelLab MCP connector** — enabled in Settings → Connectors, signed in with your ParcelLab account
4. **The `parcellab` CLI** — used to resolve your account's name for the confirmation prompt
5. **Python 3** — for the local preview server (`python3 --version` to check; `xcode-select --install` if missing)

The skill confirms the target account with you before creating anything.

> **Note:** the built-in browser runs in a fresh context (no logged-in sessions), which is fine for public brand homepages. Scraping a site behind a login is the one case that would still need Claude-in-Chrome instead — this skill doesn't cover that.

**Troubleshooting:**

- *"The built-in browser isn't available"* → make sure you're on a Claude Code version with the Browser pane tools
- *"ParcelLab MCP connector isn't enabled"* → Settings → Connectors → enable/re-authenticate ParcelLab
- *Wrong account targeted* → tell Claude the account ID explicitly; it always confirms before pushing
- *Preview 404* → the preview folder must be `~/parcellab-previews/` (never under `~/Documents` — macOS blocks the preview server there)

### parcellab-create-order

Creates (or updates) a real order in your ParcelLab account with a single request to the production Order API. Give it a bit of context — a country, a scenario, tracked vs. untracked — and it fills the rest with plausible dummy data.

**Prerequisites:** your default account plus an Order API token — see
[Your default account](#your-default-account).

> **Production only.** This skill targets `api.parcellab.com` and writes real
> orders into whichever account it's pointed at. There is no test environment
> toggle, which is why it confirms the account before every first write.

### parcellab-demo-request

Researches a prospect's website, collects four representative products from real product pages, verifies the image URLs, asks you to approve the selection, then submits a custom demo request through the Custom Demo Creator API.

**Prerequisites:**

1. **Node.js** — the skill runs helper scripts in `skills/parcellab-demo-request/scripts/`
2. **Install script dependencies once** — `node_modules` is intentionally *not* committed, so run `npm install` inside that `scripts/` folder before first use (installs Playwright)
3. Custom Demo Creator API access

### parcellab-order-lifecycle

Simulates a complete post-purchase journey: sources a real product from a brand site, creates an **untracked** order, then pushes a timed sequence of tracking checkpoints so ParcelLab ingests each stage and fires the configured comms. Uses `references/run-lifecycle.sh`.

**Prerequisites:**

1. **Your default account plus an Order API token** — the same credentials as
   `parcellab-create-order`, so setting up either skill sets up both. See
   [Your default account](#your-default-account). The skill stops on its first
   step if they aren't set, and tells you how to fix it.
2. **Bash and `curl`** — the checkpoint driver is a shell script
   (`references/run-lifecycle.sh`); no other dependencies to install.

See `references/status-codes.md` for the checkpoint status codes used.

### parcellab-bug-investigation

Investigates and documents a live product bug: confirms the exact account up front, pulls draft + published config via the `parcellab` CLI, reproduces the issue in Claude-in-Chrome (the only surface that can save real screenshots and export a recording of the repro), compares against sibling portals/configs to tell config-specific from systemic, then **publishes the bug report before touching anything** — as a claude.ai artifact, a standalone HTML file, and a PDF, so it can be shared with people who don't have Claude access. A mitigation only happens afterward, if you ask for one, and only after you expressly confirm the exact account number/code again — not just a general "yes."

**Prerequisites:**

1. **Your default account** — see [Your default account](#your-default-account). An investigation can target any account, but the default is what it offers first
2. **Claude-in-Chrome connected** — this skill uses it specifically (not the built-in Browser pane) because only its `computer`/`gif_creator` tools can save a screenshot or export a GIF to disk
3. **The `parcellab` CLI**, authenticated (`parcellab auth login`). Note the binary is `parcellab`; `parcellab-cli` is the name of the repo it ships from, not a command
4. The relevant **`parcellab-product-api`** skill(s) for whatever surface you're debugging (returns, OSP, Journey, filters, carrier connections, product feed, etc. — this skill routes to `parcellab-product-configuration` as the entry point, it doesn't duplicate their config knowledge)
5. **A headless Chrome/Chromium install** for the PDF export (the HTML/artifact deliverables don't need it — only the PDF render does)

**Note:** the whole investigation (Steps 1-4) is read-only, and the bug report is written and published before any config change. Applying a mitigation is a separate, later decision that requires restating and confirming the exact account number/resource code — not implied by an earlier general approval — especially when the change alters real customer-facing behaviour rather than just the bug's trigger condition. If a mitigation is applied after the report already went out, the HTML/PDF get regenerated and redelivered — they don't auto-update the way the artifact's URL does.

## Already have these skills the old way? Remove them first

Some of the team are running earlier versions of these skills that were shared
by hand — a `SKILL.md` copied straight into `~/.claude/skills/`. **Delete those
before installing from this marketplace.**

Why: a hand-copied skill and a plugin skill can carry the same (or a very
similar) name. When two skills match the same request, you have no control over
which one Claude picks, and the hand-copied one is frozen at whatever day it was
copied — it won't have the account-confirmation guard, the CLI edit-mode guard,
or any later fix. You'd get intermittent old behaviour with no obvious cause,
which is a miserable thing to debug.

To find them:

```bash
ls ~/.claude/skills/
```

Anything parcelLab- or onyx-related in that listing is a hand-copied copy —
plugin skills do not live there. Move them somewhere else rather than deleting,
so you can get them back if something's missing:

```bash
mkdir -p ~/claude-skills-archive && mv ~/.claude/skills/<name> ~/claude-skills-archive/
```

Then quit and reopen the app. Once you're happy the marketplace versions cover
everything you were using, the archive folder can go.

This is the point of the repo: one canonical version of each skill, updated in
one place, so fixes and new skills reach everyone instead of being re-copied by
hand and silently drifting apart.

## Updating

Fixes pushed to this repo reach installed users via plugin update (Manage plugins → update, or `/plugin marketplace update parcellab-skills` in the CLI). Bump `version` in the plugin's `plugin.json` when releasing changes.

Because everyone installs from the same source, an update is a push from the
maintainer and a *Manage plugins → update* from each person — no re-sharing
files, and no way for two people to end up on quietly different versions of the
same skill.

## For maintainers — adding a new skill

1. Copy the skill into `plugins/<name>/skills/<name>/`
2. Add `plugins/<name>/.claude-plugin/plugin.json` (name, description, version, author)
3. Register it in `.claude-plugin/marketplace.json`
4. `git add . && git commit -m "Add <name> skill" && git push`

Never commit `node_modules` — it's covered by `.gitignore`.
