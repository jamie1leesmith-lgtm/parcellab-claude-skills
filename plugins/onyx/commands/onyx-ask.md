---
description: Deprecated — use the pl-knowledge skill instead
---

This command is deprecated and cannot work.

Direct Onyx API access is blocked by an Envoy `jwt_authn` filter fronted by Keycloak, so
`onyx_pat_...` tokens never reach Onyx. This is not an expired token — do not mint a new one.

Use the **`pl-knowledge`** skill instead. It routes through the parcelLab MCP connector or the
`parcellab knowledge` CLI, and covers both product knowledge and customer/account research.

Tell the user this in one short sentence, then answer their question using `pl-knowledge`.
