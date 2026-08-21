---
description: Deprecated — use the pl-knowledge skill instead
---

This command is deprecated and cannot work.

The question the user typed is: $ARGUMENTS

Direct Onyx API access is blocked by an Envoy `jwt_authn` filter fronted by Keycloak, so
`onyx_pat_...` tokens never reach Onyx. This is not an expired token — do not mint a new one.

Use the **`pl-knowledge`** skill instead: invoke the Skill tool with the skill named
`pl-knowledge`, passing it the question above. It routes through the parcelLab MCP connector or
the `parcellab knowledge` CLI, and covers both product knowledge and customer/account research.

Tell the user this in one short sentence, then invoke `pl-knowledge` on their question.

**If the `pl-knowledge` skill is not available** (not installed on this machine), say so and tell
the user to run `/plugin install pl-knowledge@parcellab-skills`, then stop — do not attempt the
question through any other route.
