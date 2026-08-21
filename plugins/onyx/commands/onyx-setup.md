---
description: Deprecated — no credentials can restore this route
---

This setup command is deprecated and cannot fix anything.

`scripts/setup-onyx.mjs` only writes `ONYX_*` env vars into `~/.claude/settings.json`; it makes no
network call. No credential restores access, because `onyx.parcellab.com/api` validates every
`Authorization: Bearer` value as an OIDC JWT via Envoy/Keycloak — a freshly minted PAT fails
identically to an old one.

Install the **`pl-knowledge`** plugin instead. Its prerequisites are the parcelLab MCP connector
and/or the `parcellab` CLI (`parcellab auth`).

Tell the user this plainly and do not run the setup script.
