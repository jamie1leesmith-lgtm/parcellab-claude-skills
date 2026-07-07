# parcelLab Claude skills

A Claude Code plugin marketplace for parcelLab team skills.

## Install (Claude desktop app — no terminal needed)

1. Open the Claude desktop app → **Code** tab
2. Click **+** next to the prompt box → **Plugins** → **Add plugin**
3. Enter this repo as the marketplace source: `<org>/<repo>` (GitHub owner/repo)
4. Select **parcellab-brand-layout** → **Install**

Skills from the plugin become available automatically in new conversations.

## Install (Claude Code CLI)

```
/plugin marketplace add <org>/<repo>
/plugin install parcellab-brand-layout@parcellab-skills
```

## Plugins

### parcellab-brand-layout

Creates a branded transactional email layout in **your ParcelLab account** from any brand website URL. Claude scrapes the brand's styles and logo, builds an email layout, shows a live preview in the Claude app, and — after you approve — pushes the layout to ParcelLab as a draft.

Trigger with: *"Create a ParcelLab layout for www.nike.com"*

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

## Updating

Fixes pushed to this repo reach installed users via plugin update (Manage plugins → update, or `/plugin marketplace update parcellab-skills` in the CLI). Bump `version` in the plugin's `plugin.json` when releasing changes.
