---
description: Connect your own Onyx account to this plugin (per-user credential setup)
---

Walk me through connecting my own Onyx account to this plugin:

1. Ask me for my Onyx base API URL. Mention the Onyx Cloud default, `https://cloud.onyx.app/api`, and that a self-hosted instance looks like `https://onyx.your-company.com/api` — it must end in `/api`.
2. Ask me for my personal Onyx API token. Tell me where to get one: in Onyx, go to **Settings → API Keys** (admin) or create a **Personal Access Token** from my user settings. Reassure me it stays local to my machine — never shared, logged, or echoed back to me.
3. Do not ask about assistant/persona id. The default persona is `5` (`pauL — your go to Agent`), parcelLab's general-purpose Onyx assistant. Only override it if I explicitly name a different persona id myself.
4. Run this command, substituting what I gave you (omit `--persona` to use the script's default of `5`):

   `node ${CLAUDE_PLUGIN_ROOT}/scripts/setup-onyx.mjs --url "<url>" --token "<token>" --persona "<persona>"`

5. Report the script's output back to me in plain language, and remind me to fully quit and reopen Claude Code so the Onyx MCP server restarts with the new credentials.

Never print my token back to me or repeat it anywhere in chat — pass it straight through to the script argument in step 4.
