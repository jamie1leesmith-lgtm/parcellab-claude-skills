# pl-knowledge: routing design

**Date:** 2026-08-20
**Status:** Design approved in chat; not yet implemented
**Author:** Jamie Lee-Smith (with Claude)

## 1. Problem

Direct Onyx access from Claude is permanently blocked. `onyx.parcellab.com/api` now sits behind
an Envoy `jwt_authn` filter fronted by Keycloak (`auth.parcellab.com/realms/parcellab`,
`client_id=onyx-envoy`). Any `Authorization: Bearer` value is validated as an OIDC JWT, so
`onyx_pat_...` PATs never reach Onyx.

**Diagnostic signature (important — this is routinely misdiagnosed):** a deliberately bogus bearer
returns the *identical* 401 body as a valid PAT:

```
Authorization: Bearer totally-not-a-jwt
-> 401 "Jwt is not in the form of Header.Payload.Signature with two dots and 3 sections"
```

`Bearer aaa.bbb.ccc` returns `Jwt header is an invalid JSON`. Identical errors for fake and real
tokens prove the token is never evaluated. Do NOT conclude the PAT expired, and do not mint
replacements — a freshly issued PAT fails the same way.

Consequences:

- The `onyx` plugin's bundled MCP server (`plugins/onyx/mcp/onyx-server.mjs`) is dead for every
  colleague who installed it, not just locally.
- `/onyx:onyx-setup` cannot help: `scripts/setup-onyx.mjs` only merges env vars into
  `~/.claude/settings.json` and makes no network call.
- `ONYX_PERSONA_ID` is irrelevant to the working routes; only the dead plugin read it.

Two routes still reach Onyx, from inside the network:

| Route | Returns | Measured latency | Notes |
|---|---|---|---|
| MCP `knowledge_search_documents` | raw chunks, full text | ~2-5s | No LLM in path; best source material |
| MCP `knowledge_search_document_set` | raw chunks, scoped to one set | ~2-5s | Includes internal technical/best-practice docs |
| MCP `knowledge_search_public_document_set` | raw chunks, public docs only | ~2-5s | Use for "what do the customer-facing docs say" |
| MCP `knowledge_discover_onyx_filters` | 20 document sets, 13 connectors | ~2s | Needed to name a set correctly |
| MCP `knowledge_ask_gtm_agent` | synthesised + citations | ~30-60s | Separate GTM-tuned agent; positioning/objections |
| MCP `knowledge_query_parcellab_knowledge` | synthesised + citations | times out on long questions | Prefer the CLI for synthesis |
| CLI `parcellab knowledge search` | synthesised + citations | ~42s measured | Survives queries that time out over MCP |
| CLI `search-set` / `document-info` / `chunk-content` / `discover-filters` | raw | ~2-5s | CLI equivalents of the retrieval tools |
| CLI `read-page` / `update-page` / `replace-page` | Notion markdown | varies | **Not exposed over MCP**; can write to Notion |

Onyx indexes file, gitbook, github, gong, jira, notion, s3, salesforce, sharepoint, slack, teams,
web and zendesk — so account/deal research works through these routes without the separate Gong MCP.

## 2. Goals

- Match or beat the richness of the dead Onyx plugin's output.
- Keep simple lookups genuinely fast — one call, a few seconds.
- Never surprise the user with a 40-90s wait.
- Work for colleagues with either route available, or both.
- Un-break the experience for anyone still typing `/onyx-search`.

## 3. Non-goals

- Restoring direct PAT access (needs infra: a Keycloak service-account client for
  `client_credentials`, or a jwt_authn exemption for `/api`).
- Deleting the onyx plugin or its MCP server.
- Replacing the Gong MCP (`ask_account` / `ask_deal`) — out of scope, though Onyx covers much of it.

## 4. Deliverable

A new plugin, `pl-knowledge`, in this repo. Chosen over reworking `onyx` in place or folding into
`pl-tools`: clean slate, no legacy MCP server to reason about.

```
plugins/pl-knowledge/
  .claude-plugin/plugin.json          name: pl-knowledge; NO version field (SHA-versioned, push = release)
  README.md                           purpose, prerequisites, both routes, latency expectations
  skills/pl-knowledge/SKILL.md        the router: tiers, escalation rules, degradation
  skills/pl-knowledge/references/
    tool-inventory.md                 the table in section 1, plus what each tool returns
    account-research.md               account lane, source-type preferences, cross-read step
```

References are split out so SKILL.md stays short enough to be followed on every invocation; the
tool inventory is lookup material, not a preamble to re-read each time.

`marketplace.json`: add a `pl-knowledge` entry, and correct the marketplace-level description,
which currently advertises "Onyx knowledge search" as a working feature.

## 5. Routing tiers (the core contract)

### Tier 0 — Lookup. Default. ~2-5s, one call.

A single `knowledge_search_documents`, or `knowledge_search_public_document_set` when the question
is explicitly about customer-facing documentation. Answer from the returned chunks. Then **stop**.

This is the majority of use ("how does autoLayout work", "what's the returns v2 draft URL") and
must feel instant.

### Tier 1 — Deep dive. ~5-15s, retrieval only.

Adds: a scoped `knowledge_search_document_set` pass; `chunk-content` to pull a full document when a
chunk is visibly truncated; a second, differently-worded query to cross-check. Still no LLM in the
path, so still fast.

### Tier 2 — Synthesis / prep. 30-90s, announced before starting.

`knowledge_ask_gtm_agent` for positioning and objections; CLI `knowledge search` for a cited
narrative answer. For account prep, run the account-retrieval and GTM-positioning lanes in
parallel — they genuinely do not overlap.

### Rules

1. **Tier 0 is the default. Tier 2 is never entered implicitly** — only on an explicit request
   ("brief me", "positioning", "objections", "dig deep", call prep), or after Tier 0/1 failed.
2. **Escalation is announced with a reason and a time estimate**, and the user chooses.
3. **Never use CLI synthesis for anything Tier 0 could answer** — 40s for output that is *worse*
   for reading source material, because a persona has already flattened it.
4. **Split long questions.** Both synthesis routes time out on multi-part questions and succeed on
   tight ones. Decompose; never report a timeout as "the tool is broken".

## 6. Account-research lane

Same retrieval mechanism, pointed at a customer name. Encoded lessons from the River Island run:

- **Source-type preferences.** Prefer `notion` (one-pagers, business cases, win/loss) and `gong`
  (verbatim quotes — far more useful than paraphrase) for narrative. Treat `salesforce` as useful
  only for hard commercial facts (ARR, stage, close dates); its chunks frequently come back as raw
  field dumps (`IsDeleted: False`, `type: TaskRelation` repeated) that burn context for nothing.
- **The cross-read step is the highest-value move.** Ask: what does this product require to work,
  and what do we already know is broken at this customer? For River Island this surfaced that
  known international DPD tracking gaps directly undermine a WISMO agent's answer quality — a risk
  present in neither the product docs nor the account docs alone.
- **The GTM agent has no account context.** It produced strong generic positioning and objection
  handling but knew nothing of River Island's contacts, carriers, ReBound rip-out or October
  go-live. Always pair it with a retrieval pass for customer facts.

## 7. Degradation

The skill cannot introspect tool availability, so it probes and reacts:

1. Try the MCP retrieval call. If absent or erroring, fall back to the CLI.
2. **Always** prefix CLI calls with `export PATH="$HOME/.local/bin:$PATH";` and use binary name
   `parcellab` — NOT `parcellab-cli`, which does not exist as a binary.
3. CLI `command not found` -> report not installed, point at pl-tools setup.
4. CLI 401 -> device-flow session expired, run `parcellab auth`.
5. Neither route works -> state it plainly with the one-line diagnosis. Specifically, do NOT
   diagnose an Onyx 401 as an expired token (see section 1).

## 8. Deprecating onyx (reversible; nothing deleted)

- README deprecation banner explaining the Envoy/Keycloak block, pointing at `pl-knowledge`.
- `plugin.json` description prefixed `[DEPRECATED]`.
- `onyx-ask`, `onyx-search`, `onyx-setup` commands rewritten to state the route is dead and
  redirect — a colleague typing `/onyx-search` from habit gets a pointer, not a confusing 401.
- `mcp/onyx-server.mjs` and `scripts/setup-onyx.mjs` **left in place**; plugin stays listed in
  `marketplace.json`. If infra issues a Keycloak service-account client, the server becomes viable
  again with a small auth change.
- Full removal from the marketplace is a separate decision requiring explicit approval, best
  deferred until infra responds.

## 9. Risks and open questions

- **Unverified degradation path.** Only the both-routes-available setup can be tested locally. The
  CLI-without-MCP and MCP-without-CLI combinations are written from observed error signatures but
  not verified end to end.
- **Latency figures are single measurements**, not averages. CLI synthesis was 42s once.
- **`knowledge_query_parcellab_knowledge` may be viable for short questions** — it timed out on a
  long one and was not retried short. Worth a cheap test during implementation before writing it
  off in favour of the CLI.
- **Tier boundaries are judgement calls.** If Tier 0 proves insufficient in practice, the fix is
  better Tier 0 queries, not a lower default tier.
- **Infra dependency.** If a Keycloak service-account client is issued, revisit whether the onyx
  MCP server becomes the better route again.

## 10. Success criteria

- A simple lookup completes in one call and a few seconds, with no synthesis.
- No Tier 2 call ever starts without being announced first.
- An account-prep request yields customer-specific facts *and* positioning, with at least one
  cross-read risk or gap identified.
- A colleague with only the CLI gets working answers; one with neither gets an accurate diagnosis.
- `/onyx-search` gives a useful redirect rather than a 401.
