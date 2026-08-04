# parcelLab Claude skills

A private Claude Code plugin marketplace for parcelLab team skills. One plugin,
**`pl-tools`**, carries all five parcelLab skills plus its setup command. Onyx
ships separately.

> 🔒 **This repo is private.** You need to be invited as a collaborator before you can add it as a marketplace or install anything. Ask Jamie (`jamie1leesmith-lgtm`) for access.

## Install (Claude desktop app — no terminal needed)

1. Open the Claude desktop app → **Code** tab
2. Click **+** next to the prompt box → **Plugins** → **Add plugin**
3. Enter this repo as the marketplace source: `jamie1leesmith-lgtm/parcellab-claude-skills`
4. Install **`pl-tools`** (and **`onyx`** if you want Onyx search too)

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
/plugin install pl-tools@parcellab-skills
```

Add `/plugin install onyx@parcellab-skills` for Onyx knowledge search.

## Available skills

Everything below `pl-tools` arrives in one install. Type `/pl` to see them all —
they deliberately don't share the `parcellab-` prefix used by the org's
`parcellab-product-api` plugin, so the two sets stay separable.

| Handle | What it does | Trigger example |
|-------|--------------|-----------------|
| `pl-tools:create-order` | Creates a real order in your parcelLab account via the production Order API, filling in realistic dummy data | *"Push a test order to parcelLab for a UK delivery"* |
| `pl-tools:order-lifecycle` | Simulates a full post-purchase journey: creates an untracked order, then pushes timed checkpoints (warehouse → carrier → delivery) so parcelLab fires the comms for each stage | *"Simulate the full journey for [brand]"* |
| `pl-tools:branded-template` | Builds a branded transactional email layout in your parcelLab account from a brand URL, with live preview in the desktop app | *"Create a parcelLab layout for www.nike.com"* |
| `pl-tools:demo-request` | Creates a custom demo request from a prospect website URL — collects products, verifies images, submits to the Custom Demo Creator | *"Create a demo request for www.example.com"* |
| `pl-tools:bug-investigation` | Investigates a product bug end to end: checks live config via the `parcellab` CLI, reproduces it in Claude-in-Chrome with real screenshot/recording capture, isolates root cause against sibling portals, and publishes a shareable bug report as an artifact, HTML file, and PDF — always *before* any mitigation, which needs express account-number-specific sign-off | *"Investigate this bug on [portal]"* |
| `pl-tools:pl-setup` | One-time setup: account, CLI write guard, and Order API token | *`/pl-setup`* |
| `onyx` *(separate plugin)* | Pulls knowledge from your parcelLab Onyx instance into Claude — semantic search, cited RAG answers, and document retrieval | *"Search Onyx for our return policy on damaged items"* |

---

## Your default account

Every skill here writes into a parcelLab account. Rather than naming one each
time, they all read a single default and confirm it before writing anything.

`PARCELLAB_ACCOUNT_ID` in the `env` block of your global `~/.claude/settings.json`
holds your demo account:

```json
{ "env": { "PARCELLAB_ACCOUNT_ID": "1626718" } }
```

You do not set this up by hand — `/pl-setup` writes it for you, looking your
account up by name so you can confirm it's the right one.

Two skills additionally need an Order API token (`PARCELLAB_TOKEN`):
`create-order` and `order-lifecycle`. Nothing else does.

> `PARCELLAB_USER_ID` is still accepted as an alias for `PARCELLAB_ACCOUNT_ID`,
> so anyone set up before this convention keeps working. New setups use
> `PARCELLAB_ACCOUNT_ID`.

### One-time setup

You need the parcelLab CLI installed — internal users have this already. Then, in
the Claude Code desktop app:

1. **Install:** **+** → **Plugins** → **Add plugin** → marketplace source
   `jamie1leesmith-lgtm/parcellab-claude-skills` → install `pl-tools`.
2. **In a _new_ conversation, run `/pl-setup`.** Not the one you installed
   from — newly installed plugins aren't loaded into a conversation that was
   already running.
3. It checks the CLI, logs you in (`parcellab auth login` opens your browser),
   finds your demo account **by name** so you can confirm it, writes
   `PARCELLAB_ACCOUNT_ID` to your global settings, and points the CLI's write
   guard at that same account
   (`parcellab settings edit-mode set account-restricted`). That guard is what
   stops a skill writing into a colleague's demo account — there are 13 side by
   side under *Demo SolCon*.
4. **Order API token — only if you use `create-order` or `order-lifecycle`.**
   `/pl-setup` asks. If you say yes, it hands you one command to run in the app's
   built-in terminal (**click the terminal icon, top right**), which prompts for
   the credential.

   **Nothing appears on screen as you paste it — no dots, no asterisks, no
   cursor movement. That is correct**; the input is hidden on purpose. Paste
   once, press Enter once. Pasting twice because "it didn't work" is the most
   common way this goes wrong.

   Paste the **base64** value from the portal, not the raw token — it carries
   both your account ID and your token, so one paste covers both.
5. **Fully quit the app (⌘Q) and reopen.** Not just closing the window.
   Environment variables are read only at startup, so nothing above takes effect
   until you do.
6. **Check it worked.** Ask *"which parcelLab account am I set up against?"* —
   Claude should name your demo account and its ID without asking you anything.

The token never enters the chat, a command-line argument, or your shell history.
Claude will not accept it pasted into the chat box, and shouldn't — chat messages
are stored in the conversation transcript. If you ever see your token in chat, it
went in the wrong place: rotate it.

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

### pl-tools:branded-template

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

### pl-tools:create-order

Creates (or updates) a real order in your ParcelLab account with a single request to the production Order API. Give it a bit of context — a country, a scenario, tracked vs. untracked — and it fills the rest with plausible dummy data.

**Prerequisites:** your default account plus an Order API token — see
[Your default account](#your-default-account).

> **Production only.** This skill targets `api.parcellab.com` and writes real
> orders into whichever account it's pointed at. There is no test environment
> toggle, which is why it confirms the account before every first write.

### pl-tools:demo-request

Researches a prospect's website, collects four representative products from real product pages, verifies the image URLs, asks you to approve the selection, then submits a custom demo request through the Custom Demo Creator API.

**Prerequisites:**

1. **Node.js** — the skill runs helper scripts in `plugins/pl-tools/skills/demo-request/scripts/`
2. **Install script dependencies once** — `node_modules` is intentionally *not* committed, so run `npm install` inside that `scripts/` folder before first use (installs Playwright)
3. Custom Demo Creator API access

### pl-tools:order-lifecycle

Simulates a complete post-purchase journey: sources a real product from a brand site, creates an **untracked** order, then pushes a timed sequence of tracking checkpoints so ParcelLab ingests each stage and fires the configured comms. Uses `references/run-lifecycle.sh`.

**Prerequisites:**

1. **Your default account plus an Order API token** — the same credentials as
   `create-order`, so setting up either skill sets up both. See
   [Your default account](#your-default-account). The skill stops on its first
   step if they aren't set, and tells you how to fix it.
2. **Bash and `curl`** — the checkpoint driver is a shell script
   (`references/run-lifecycle.sh`); no other dependencies to install.

See `references/status-codes.md` for the checkpoint status codes used.

### pl-tools:bug-investigation

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

Fixes pushed to this repo reach installed users via plugin update (Manage plugins → update, or `/plugin marketplace update parcellab-skills` in the CLI).

> ⚠️ **You must bump `version` in the plugin's `plugin.json`, or the release
> reaches nobody.** Updates are gated on that version string, *not* on git
> commits. Push without bumping and `plugin update` reports
> *"already at the latest version"* and does nothing — no error, no warning.
> Meanwhile a *fresh* install pulls current `main` and does get your change, so
> you end up with two groups on silently different versions of the same skill:
> exactly what this repo exists to prevent. This has already happened once
> (commit `fe9efe6`, fixed in `d0b766c`).

**Releasing a change, in order:**

1. Make the change.
2. Bump `version` in the affected plugin's `.claude-plugin/plugin.json`. One
   plugin changed means one bump — the repo-root `README.md` is the exception,
   as it sits outside every plugin and is read on GitHub.
3. Commit and push.
4. Verify it actually shipped: `claude plugin marketplace update parcellab-skills`
   then `claude plugin update <plugin>@parcellab-skills`. You want to see
   *"updated from X to Y"*. If you see *"already at the latest version"*, you
   forgot step 2.
5. Tell the team to update and restart the app (⌘Q) — plugins load at startup.

Because everyone installs from the same source, an update is a push from the
maintainer and a *Manage plugins → update* from each person — no re-sharing
files, and no way for two people to end up on quietly different versions of the
same skill.

## For maintainers — adding a new skill

New parcelLab skills go inside `pl-tools`. No new plugin, no new marketplace entry.

1. Create `plugins/pl-tools/skills/<name>/SKILL.md`, with frontmatter `name:`
   **matching the directory name exactly** — a mismatch makes the skill vanish
   silently from the plugin's inventory.
2. Keep "parcelLab" in the `description:`. That text is what Claude matches
   against to decide whether to trigger the skill; the directory name is only the
   typed handle. Don't use `pl-` in the identifier either — the `pl-tools:` prefix
   already namespaces it, and repeating it just stutters.
3. Bump `version` in `plugins/pl-tools/.claude-plugin/plugin.json`.
4. `git add . && git commit -m "feat(pl-tools): add <name> skill" && git push`
5. Verify it shipped and appears:
   `claude plugin marketplace update parcellab-skills`,
   `claude plugin update pl-tools@parcellab-skills`, then
   `claude plugin details pl-tools@parcellab-skills` to confirm it's listed.

Never commit `node_modules` — it's covered by `.gitignore`.

### Renaming things — read this first

Not every `parcellab-` string in this repo is ours. A blind find-and-replace
breaks working behaviour in ways that don't look like errors. Leave these alone:

- **`parcellab-product-api` / `parcellab-product-configuration`** — the *org's*
  plugin, from `parcelLab/parcellab-cli`. `bug-investigation` routes to it.
- **`parcellab-brand-layout`** — the *external* Cowork/CLI variant in another
  repo, which `branded-template` references for contrast.
- **`$HOME/parcellab-previews/`** and **`{brand}-parcellab-layout.html`** —
  a real directory and real output filenames.
- **`~/.claude/parcellab-demo-request.env`** — a user config file that exists on
  disk. Renaming it breaks working setups.
- **`parcellab-demo-request-scripts`** — an npm package name, internal to that
  `scripts/` project.

Both `SKILL.md` files carrying the first two have an HTML comment saying so,
immediately above the reference.
