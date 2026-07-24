# parcelLab Claude skills

A private Claude Code plugin marketplace for parcelLab team skills. Install skills **individually** — take only the ones you need.

> 🔒 **This repo is private.** You need to be invited as a collaborator before you can add it as a marketplace or install anything. Ask Jamie (`jamie1leesmith-lgtm`) for access.

## Install (Claude desktop app — no terminal needed)

1. Open the Claude desktop app → **Code** tab
2. Click **+** next to the prompt box → **Plugins** → **Add plugin**
3. Enter this repo as the marketplace source: `jamie1leesmith-lgtm/parcellab-claude-skills`
4. Pick the skill you want → **Install** (repeat for any others)

Installed skills become available automatically in new conversations.

## Install (Claude Code CLI)

```
/plugin marketplace add jamie1leesmith-lgtm/parcellab-claude-skills
/plugin install parcellab-create-order@parcellab-skills
```

Swap `parcellab-create-order` for whichever skill you want — install as many or as few as you like.

## Available skills

| Skill | What it does | Trigger example |
|-------|--------------|-----------------|
| `parcellab-brand-layout` | Builds a branded transactional email layout in your ParcelLab account from a brand URL, with live preview in the desktop app | *"Create a ParcelLab layout for www.nike.com"* |
| `parcellab-create-order` | Creates a real order in your ParcelLab account via the production Order API, filling in realistic dummy data | *"Push a test order to ParcelLab for a UK delivery"* |
| `parcellab-demo-request` | Creates a custom demo request from a prospect website URL — collects products, verifies images, submits to the Custom Demo Creator | *"Create a demo request for www.example.com"* |
| `parcellab-order-lifecycle` | Simulates a full post-purchase journey: creates an untracked order, then pushes timed checkpoints (warehouse → carrier → delivery) so ParcelLab fires the comms for each stage | *"Simulate the full journey for [brand]"* |

---

### parcellab-brand-layout

Creates a branded transactional email layout in **your ParcelLab account** from any brand website URL. Claude scrapes the brand's styles and logo, builds an email layout, shows a live preview in the Claude app, and — after you approve — pushes the layout to ParcelLab as a draft.

**Prerequisites:**

1. **Claude desktop app** (Mac)
2. **Claude-in-Chrome browser extension** — installed in Chrome with a window connected
3. **ParcelLab MCP connector** — enabled in Settings → Connectors, signed in with your ParcelLab account
4. **Python 3** — for the local preview server (`python3 --version` to check; `xcode-select --install` if missing)

The skill detects your ParcelLab account(s) via the connector and confirms the target account with you before creating anything.

**Troubleshooting:**

- *"Claude-in-Chrome isn't connected"* → open Chrome, click the Claude extension, connect a window
- *"ParcelLab MCP connector isn't enabled"* → Settings → Connectors → enable/re-authenticate ParcelLab
- *Wrong account targeted* → tell Claude the account ID explicitly; it always confirms before pushing
- *Preview 404* → the preview folder must be `~/parcellab-previews/` (never under `~/Documents` — macOS blocks the preview server there)

### parcellab-create-order

Creates (or updates) a real order in your ParcelLab account with a single request to the production Order API. Give it a bit of context — a country, a scenario, tracked vs. untracked — and it fills the rest with plausible dummy data.

**Prerequisites:** ParcelLab Order API access for your account (user/token).

### parcellab-demo-request

Researches a prospect's website, collects four representative products from real product pages, verifies the image URLs, asks you to approve the selection, then submits a custom demo request through the Custom Demo Creator API.

**Prerequisites:**

1. **Node.js** — the skill runs helper scripts in `skills/parcellab-demo-request/scripts/`
2. **Install script dependencies once** — `node_modules` is intentionally *not* committed, so run `npm install` inside that `scripts/` folder before first use (installs Playwright)
3. Custom Demo Creator API access

### parcellab-order-lifecycle

Simulates a complete post-purchase journey: sources a real product from a brand site, creates an **untracked** order, then pushes a timed sequence of tracking checkpoints so ParcelLab ingests each stage and fires the configured comms. Uses `references/run-lifecycle.sh`.

**Prerequisites:** ParcelLab Order API access. See `references/status-codes.md` for the checkpoint status codes used.

## Updating

Fixes pushed to this repo reach installed users via plugin update (Manage plugins → update, or `/plugin marketplace update parcellab-skills` in the CLI). Bump `version` in the plugin's `plugin.json` when releasing changes.

## For maintainers — adding a new skill

1. Copy the skill into `plugins/<name>/skills/<name>/`
2. Add `plugins/<name>/.claude-plugin/plugin.json` (name, description, version, author)
3. Register it in `.claude-plugin/marketplace.json`
4. `git add . && git commit -m "Add <name> skill" && git push`

Never commit `node_modules` — it's covered by `.gitignore`.
