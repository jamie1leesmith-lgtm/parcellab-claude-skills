# pl-knowledge

Research parcelLab knowledge and customer accounts through Onyx, without the dead direct-API route.

## Why this exists

`onyx.parcellab.com/api` now sits behind an Envoy `jwt_authn` filter fronted by Keycloak. Any
`Authorization: Bearer` value is validated as an OIDC JWT, so `onyx_pat_...` personal access tokens
never reach Onyx — which killed the `onyx` plugin's bundled MCP server and its `onyx-ask` /
`onyx-search` skills for everyone.

Two routes still reach Onyx from inside the network, and this plugin uses whichever you have.

## Prerequisites

At least one of:

- **parcelLab MCP connector** enabled in your Claude client — gives fast raw retrieval. Preferred.
- **`parcellab` CLI** installed and authenticated (`parcellab auth`) — gives cited synthesis plus
  Notion read/write. Note the binary is `parcellab`, and it lives in `~/.local/bin`, which is not
  on Claude's default PATH.

Both is best: retrieval is fast, synthesis survives questions that time out over MCP.

## What you get

- **Fast by default.** An ordinary lookup is one call, a few seconds.
- **Depth on request.** Ask for a brief, positioning or objections and it runs the slower synthesis
  and GTM-agent routes — after telling you it's about to.
- **Account research.** Onyx indexes Gong, Salesforce, Notion, Jira, Slack and Zendesk, so customer
  and deal research works through the same routes.

## Usage

Just ask. Examples:

- "How does the returns v2 draft preview URL work?"
- "What do we know about River Island's post-purchase setup?"
- "Brief me for the WISMO agent call with River Island."

## Known limitations

- The synthesis routes time out on long multi-part questions; the skill splits them rather than
  failing.
- `knowledge_ask_gtm_agent` has no account-specific context — it is for framing, not facts.
- Degradation behaviour has been verified only where both routes are available.
