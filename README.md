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

### Each plugin has its own setup command

Run the one for each plugin you installed. They configure different credentials
and neither covers the other:

| Installed | Run | Sets up |
|---|---|---|
| `pl-tools` | **`/pl-setup`** | Your parcelLab account, the CLI write guard, and the Order API token if you use `create-order` or `order-lifecycle`. See [One-time setup](#one-time-setup). |
| `onyx` | **`/onyx-setup`** | Your Onyx API URL and personal token. See [onyx](#onyx). |

If you installed both, run both — then **quit and reopen the app once (⌘Q)**. Both
write into the same `env` block, and it's read only at startup, so a single restart
covers both. Each section below says "restart afterwards", which reads like two
restarts if you're doing the pair.

`/pl-setup` takes about two minutes and every parcelLab skill depends on it.

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

You need two things on your machine first:

- **The `parcellab` CLI**, installed. Internal users have this already. The binary
  is `parcellab`; `parcellab-cli` is the repo it ships from, not a command.
- **Python 3** — `/pl-setup` writes your credentials with a stdlib-only Python
  script. macOS ships it, so `python3 --version` should just answer. If it
  doesn't, `xcode-select --install`.

Then, in the Claude Code desktop app:

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

1. **Node.js** — the skill submits through `submit_demo_request.mjs`, which uses
   only Node's built-ins (`node:fs`, `node:os`, `node:path`). Nothing to install.
2. Custom Demo Creator API access

> **No `npm install` needed.** An earlier version of this README told you to run
> one to fetch Playwright. That was only ever required by `fetch_page.mjs`, which
> this skill does not invoke — it browses through the Playwright *MCP* instead.
> Running it would download several hundred MB of browsers for nothing.
>
> `check_images.mjs` and `fetch_page.mjs` ship in `scripts/` but are not wired
> into `SKILL.md`. Known loose end: either dead code to remove or a gap in the
> skill's instructions. Being looked at separately — it doesn't affect using the
> skill.

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
4. **The org's `parcellab-product-api` plugin** — a hard requirement, and it comes
   from a *different* marketplace, so installing `pl-tools` does not bring it.
   This skill routes to its `parcellab-product-configuration` entry point rather
   than duplicating that config knowledge (returns, OSP, Journey, filters, carrier
   connections, product feed…), so without it the investigation stalls at the
   config-inspection step.

   In the desktop app: **+** → **Plugins** → **Add plugin** → source
   `parcelLab/parcellab-cli` → install `parcellab-product-api`. Or in the CLI:

   ```bash
   claude plugin marketplace add parcelLab/parcellab-cli
   claude plugin install parcellab-product-api@parcellab
   ```

   Adding a marketplace only *reads* that repo — no push, no fork, nothing written
   to the org.
5. **A headless Chrome/Chromium install** for the PDF export (the HTML/artifact deliverables don't need it — only the PDF render does)

**Note:** the whole investigation (Steps 1-4) is read-only, and the bug report is written and published before any config change. Applying a mitigation is a separate, later decision that requires restating and confirming the exact account number/resource code — not implied by an earlier general approval — especially when the change alters real customer-facing behaviour rather than just the bug's trigger condition. If a mitigation is applied after the report already went out, the HTML/PDF get regenerated and redelivered — they don't auto-update the way the artifact's URL does.

## Already have these skills the old way? Remove them first

Some of the team are running earlier versions of these skills that were shared
by hand — a `SKILL.md` copied straight into `~/.claude/skills/`. **Delete those
before installing from this marketplace.**

Why — and note the reason is **not** that the names clash. Since the rename they
don't: your hand-copied copy is `parcellab-create-order`, the plugin's is
`create-order`. Different handles.

The problem is that Claude decides which skill to run by matching your request
against each skill's **description**, not its name. Two copies of the same skill
carry near-identical descriptions, so both match, and you have no control over
which one wins. The hand-copied one is frozen at whatever day it was copied — no
account-confirmation guard, no CLI edit-mode guard, none of the later fixes. You'd
get intermittent old behaviour with no visible cause, which is a miserable thing
to debug.

So a different name does **not** make it safe to keep the old copy.

To find them:

```bash
ls ~/.claude/skills/
```

Anything parcelLab- or onyx-related in that listing is a hand-copied copy — plugin
skills never live there. Move them aside rather than deleting, so you can get them
back if something turns out to be missing:

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

**Releasing a change to `pl-tools`:**

1. Make the change.
2. Commit and push to `main`.
3. Tell the team to run `/pl-update`.

That's it — **there is no version number to bump.** `pl-tools` deliberately omits
`version` from its `plugin.json`, so its version resolves to the git commit SHA and
every push is automatically a new version.

> **Why it's done this way.** Setting `version` *pins* the plugin: push new commits
> without changing that string and `plugin update` reports *"already at the latest
> version"* and does nothing — no error, no warning — while a *fresh* install pulls
> current `main` and does get the change. Two groups, silently different code,
> which is the exact problem this repo exists to prevent. It happened once
> (`fe9efe6`, fixed in `d0b766c`) before the version field was removed. The docs
> recommend omitting it for internal, actively-developed plugins for this reason.
>
> The cost is that `claude plugin list` shows a commit SHA rather than a friendly
> number. Worth it: a forgotten bump fails invisibly, whereas an extra update
> ships a typo fix.
>
> **If you ever reintroduce `version`, you own the bump on every single release.**
> Don't set it in both `plugin.json` and the marketplace entry —
> `plugin.json` silently wins.

`onyx` still pins a version, because it changes rarely and its MCP server benefits
from a legible number. Bump it when you change it.

**Receiving a change** — for your team, and for you on another machine:

```
/pl-update
```

It refreshes the marketplace, updates `pl-tools` (and `onyx` if installed), says
whether anything actually changed, and tells you whether a restart is needed.
Equivalent to running `claude plugin marketplace update parcellab-skills` then
`claude plugin update pl-tools@parcellab-skills` by hand.

**Nothing updates by itself.** No notification, no background pull. Your team keeps
running old code until they run `/pl-update` — so "tell the team" is a permanent
part of releasing, not an optional courtesy.

## For maintainers — adding a new skill

> **Use `/anthropic-skills:skill-creator` to write it.** That skill knows how to
> structure a `SKILL.md`, write a description that triggers reliably, and test the
> result. Don't hand-roll a new skill from scratch or copy an existing one and
> edit — that's how conventions drift. Everything below is the *repo-specific*
> context skill-creator doesn't know: where files go here and which house rules
> apply.
>
> The rules with **silent** failure modes are also in [CLAUDE.md](CLAUDE.md), which
> Claude loads automatically when working in this repo — so they apply even if
> nobody thinks to open this file. Keep the two in step: this README is the full
> reference for people, `CLAUDE.md` is the short list of things that break quietly.

New parcelLab skills go **inside `pl-tools`**. No new plugin, no new marketplace
entry.

### The steps

1. Run `/anthropic-skills:skill-creator` and describe the skill you want.
2. Place the result at `plugins/pl-tools/skills/<name>/SKILL.md`.
3. Apply the house rules below.
4. `git add . && git commit -m "feat(pl-tools): add <name> skill" && git push` —
   **no version bump**, see [Updating](#updating).
5. Run `/pl-update`, restart (⌘Q), then
   `claude plugin details pl-tools@parcellab-skills` to confirm the new skill is
   listed. If it's missing, the frontmatter `name:` almost certainly doesn't match
   the directory name.

### House rules

**Frontmatter `name:` must match the directory name exactly.** A mismatch makes
the skill vanish from the plugin's inventory with no error at all — it simply
isn't there. This is the single most likely reason a new skill "didn't install".

**`description:` is the trigger text, not a label.** Claude decides whether to run
a skill by matching the request against this string. Two consequences:

- **Keep "parcelLab" in it**, spelled out. That's what makes *"push a parcelLab
  order"* work. Add "pL" alongside if you like; don't replace.
- Include the phrasings a real person would use. Look at `create-order`'s
  description for the pattern — it lists several concrete trigger phrases.

**Don't prefix the directory name with `pl-`.** The `pl-tools:` plugin prefix
already namespaces it, so `pl-create-order` would read as
`pl-tools:pl-create-order`. The one exception is the two commands (`pl-setup`,
`pl-update`), which keep the prefix because their bare forms (`/setup`, `/update`)
are generic enough to collide with any other plugin.

**Optional frontmatter, used where it earns its place:** `allowed-tools` to
restrict what the skill may call, and `argument-hint` for skills taking an argument
(`demo-request` uses both). Everything else uses just `name` and `description`.

**Reference scripts and files via `${CLAUDE_PLUGIN_ROOT}`** — never `~/.claude/skills/…`
and never a path relative to this repo. Installed users run from
`~/.claude/plugins/cache/parcellab-skills/pl-tools/<version>/`, not from a clone.
`demo-request` shipped a broken submit step for weeks because it pointed at
`~/.claude/skills/parcellab-demo-request/scripts/`, a location that stopped
existing when skills became plugins. Supporting files live alongside `SKILL.md` in
`references/`, `scripts/`, or `assets/`.

**Any skill that writes to a parcelLab account must confirm the account first.**
Resolve it from `$PARCELLAB_ACCOUNT_ID` (accept `$PARCELLAB_USER_ID` as a legacy
alias; never write it), look up the human name with
`parcellab account account show <id>`, and confirm **by name** before the first
write of a conversation — a wrong number looks fine, a wrong name is obvious. Copy
the pattern from `create-order`, `order-lifecycle`, or `bug-investigation`, which
all carry it. Read-only inspection needs no confirmation.

**Never accept a credential in chat.** Chat messages are stored in the transcript.
If a skill needs a secret, route it through
`${CLAUDE_PLUGIN_ROOT}/scripts/pl_credentials.py --token`, which prompts with
hidden input, and tell the user to run it in the app's built-in terminal. Never
pass a secret as a command-line argument either — it lands in the process table
and shell history.

**Tests are stdlib `unittest`.** `pytest` is not installed and no step should
`pip install` anything. See `plugins/pl-tools/scripts/tests/` for the pattern:
pure functions, tested against a temp file, run with
`python3 -m unittest discover -s tests -v`.

**Never commit `node_modules`** — covered by `.gitignore`.

**Follow the planning workflow for anything non-trivial**: `superpowers:brainstorming`
to shape it, `superpowers:writing-plans` to break it down, then execute. A new skill
is exactly the case that workflow exists for.

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
