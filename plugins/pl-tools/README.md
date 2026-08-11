# pl-tools

parcelLab internal tooling for Claude Code — six skills and one setup command in
a single plugin.

| Handle | What it does |
|---|---|
| `pl-tools:create-order` | Create a real order via the production Order API |
| `pl-tools:order-lifecycle` | Simulate a full post-purchase journey with timed checkpoints |
| `pl-tools:branded-template` | Build a branded transactional email layout from a brand URL |
| `pl-tools:demo-request` | Raise a custom demo request from a prospect URL |
| `pl-tools:bug-investigation` | Investigate and document a live product bug |
| `pl-tools:demo-environment` | One interview → a full parcelLab demo: branded template, 1–5 fraud-tagged orders with good/bad journeys, optional Shopify build, CDC request linking the real orders |
| `pl-tools:shopify-seed` | Seed a prospect's real products into a Shopify dev store for exchange demos |
| `pl-tools:pl-setup` | One-time setup (below) |
| `pl-tools:pl-update` | Pull the latest skills and fixes, then tell you if a restart is needed |

## Setup

Run `/pl-setup` once after installing, then fully quit and reopen the app.

It first checks `~/.claude/skills/` for a hand-copied version of any of these
skills from before this marketplace existed, and tells you by name if it finds
one — those are frozen at whatever day they were copied and never receive the
fixes this plugin ships. Then it checks the `parcellab` CLI, logs you in if
needed, resolves your demo account and writes it to the `env` block of your
global `~/.claude/settings.json` as `PARCELLAB_ACCOUNT_ID`, and points the CLI's
write guard at that same account so a skill cannot write into a colleague's demo
account.

### No Order API token

`create-order` and `order-lifecycle` write through the `parcellab` CLI's own
OAuth login — there is no separate credential. (They required an Order API token
before 2026-08-07; a leftover `PARCELLAB_TOKEN` in settings is harmless and
unused.) The protection is the CLI's `edit-mode account-restricted` guard, which
`/pl-setup` points at your own demo account and the skills verify before every
first write.

### Custom Demo Creator token

Only `demo-request` needs one. `/pl-setup` asks, and if you say yes it hands you
this to run in the app's built-in terminal:

    python3 <plugin>/scripts/pl_credentials.py --cdc-token

It's a single value, nothing to decode. The base URL is filled in for you.

The token is never accepted in chat and never passed as a command-line argument,
so it stays out of the conversation transcript, the process table, and your shell
history.

## Prerequisites

- The `parcellab` CLI, authenticated
- Python 3 (macOS ships it) — the setup script is stdlib-only
- `bug-investigation` additionally needs the org's `parcellab-product-api` plugin
  (from `parcelLab/parcellab-cli`) for Product API config knowledge, and
  Claude-in-Chrome for screenshot/recording capture
- `demo-request` uses only Node's built-ins (`node:fs`, `node:os`, `node:path`) —
  nothing to install
- `branded-template` needs the ParcelLab MCP connector and the built-in Browser pane

## Staying up to date

Run `/pl-update`, then fully quit and reopen the app (⌘Q) if it says anything
changed. Nothing updates by itself — there's no notification and no background
pull, so you keep running the version you installed until you run it.

This plugin has **no pinned version**: its version is the marketplace repo's commit
SHA, so every push by the maintainer is automatically a new version. That's why
`claude plugin list` shows something like `43de6eb94ef0` rather than `2.0.1`, and
why `claude plugin validate` warns about a missing `version` — both intentional.

## Tests

```bash
cd scripts && python3 -m unittest discover -s tests -v
```
