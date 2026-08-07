# Onyx plugin for Claude Code

Pull knowledge from your [Onyx](https://onyx.app) instance directly into Claude. This
plugin ships a small, **zero-dependency** MCP server that bridges Claude Code to the
Onyx REST API, so you can search your indexed documents, get cited RAG answers, and
retrieve full documents — then use that material for whatever you're working on.

## What you get

**Tools** (exposed to Claude automatically once configured):

| Tool | What it does |
|------|--------------|
| `onyx_search` | Semantic search across your Onyx knowledge base. Returns titles, source links, relevance scores, and snippets. Optionally scoped to document sets. |
| `onyx_ask` | Asks Onyx a question and returns a synthesized, cited answer using Onyx's LLM + RAG pipeline (as if chatting inside Onyx). |
| `onyx_fetch_document` | Reassembles the full text of a document by `document_id` (from a search result). |

**Slash commands:**

- `/onyx-search <query>` — search and pull results into context.
- `/onyx-ask <question>` — get a cited answer and work with it.

## Requirements

- Node.js 18+ (uses the built-in `fetch`; no `npm install` needed).
- An Onyx instance (Cloud or self-hosted) and an API token.

## Configuration

Each person who installs this plugin needs their **own** Onyx credentials — nothing is shared or bundled with the plugin.

> **If Onyx already worked for you before installing this plugin, you're done —
> skip this section.** Credentials live in the `env` block of your global
> `~/.claude/settings.json`, not inside the plugin. Anything that wrote
> `ONYX_API_URL` / `ONYX_API_TOKEN` / `ONYX_PERSONA_ID` there previously (a
> hand-rolled MCP server, a manual edit) leaves them in place when it's removed,
> and this plugin's MCP server reads those same three variables — so it inherits
> your existing auth. Only run `/onyx-setup` if `/onyx-search` actually fails.

### Quick setup (recommended)

1. In Claude Code, run:

   ```
   /onyx-setup
   ```

2. Answer the two questions it asks (your Onyx base API URL, and your personal API token — see "Getting an Onyx token" below). Claude may hand you a command to run in the app's built-in terminal rather than take the token in chat — click the terminal icon at the top right, paste, and press Enter. **Nothing appears on screen as you type or paste the token; that's intentional, not a failure.**
3. Fully quit Claude Code (**⌘Q**, not just closing the window) and reopen it, so the Onyx MCP server restarts with your new credentials.
4. Try `/onyx-search <something>` to confirm it worked.

`/onyx-setup` writes your credentials into the `env` block of your global `~/.claude/settings.json`, leaving every other setting in that file untouched. It's safe to run again later (e.g. if your token changes) — it updates in place rather than duplicating anything.

### Getting an Onyx token

In Onyx, go to **Settings → API Keys** (admin) or create a **Personal Access Token**
from your user settings. See the
[Onyx API docs](https://docs.onyx.app/developers/overview) for details.

### Manual setup (advanced)

If you'd rather skip the slash command, add the same three keys yourself to your
global `~/.claude/settings.json`, inside its top-level `env` object:

```json
{
  "env": {
    "ONYX_API_URL": "https://cloud.onyx.app/api",
    "ONYX_API_TOKEN": "onyx_pat_xxxxxxxxxxxxxxxx",
    "ONYX_PERSONA_ID": "5"
  }
}
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ONYX_API_URL` | yes | Base API URL **including `/api`**. Cloud: `https://cloud.onyx.app/api`. Self-hosted: `https://onyx.your-company.com/api`. |
| `ONYX_API_TOKEN` | yes | A Personal Access Token (`onyx_pat_...`) or an admin/basic API key. |
| `ONYX_PERSONA_ID` | no | Assistant/persona id used by `onyx_ask`. Default `5` = pauL, parcelLab's general-purpose Onyx agent. `/onyx-setup` no longer asks about this — set a different assistant's id (see `GET /api/persona`) yourself if you need a specialised one. |

If you already have other keys in that file (enabled plugins, other tokens), merge
these in carefully — a JSON syntax mistake can break your whole Claude Code
config, which is exactly why `/onyx-setup` exists.

## Installing

This is a standard Claude Code plugin. From a marketplace:

```
/plugin marketplace add jamie1leesmith-lgtm/parcellab-claude-skills   # or your marketplace repo
/plugin install onyx
```

Or point Claude Code at this directory directly during development.

## How it works

`mcp/onyx-server.mjs` implements the MCP stdio transport (newline-delimited
JSON-RPC 2.0) by hand and calls Onyx over HTTPS with Node's built-in `fetch` — no
third-party packages, nothing to build. Endpoints used:

- `POST /query/document-search` — semantic search (available to all roles)
- `POST /chat/create-chat-session` + `POST /chat/send-chat-message` — RAG chat
  (falls back to the legacy `/chat/send-message` on older Onyx builds)
- `GET  /document/document-size-info` + `GET /document/chunk-info` — full document text

The chat response parser handles both the current streaming schema
(`obj.type == "message_delta"`) and older `answer_piece` / single-object formats,
so it works across Onyx versions.

## Troubleshooting

- **"Onyx is not configured"** — run `/onyx-setup` to add your credentials, then fully restart Claude Code.
- **401 / 403** — check the token and that its role has search/chat access. (`/query/document-search`
  works for standard users; the admin-only `/admin/search` does not.)
- **`onyx_ask` returns odd JSON** (e.g. `{"is_wismo_query":...}`) — you've pointed `ONYX_PERSONA_ID`
  at a specialised agent. Use `5` (pauL, the default general-purpose assistant) or another
  general-purpose custom assistant.
- **Base URL** — must end in `/api` (e.g. `https://onyx.your-company.com/api`), not `/app`.
