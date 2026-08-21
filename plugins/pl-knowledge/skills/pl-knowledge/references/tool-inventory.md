# Route inventory

MCP tool names appear with a per-connector prefix (e.g. `mcp__<connector-id>__knowledge_search_documents`).
This file uses the **suffix** — match whatever prefix is in your tool list.

Every CLI command must be prefixed with `export PATH="$HOME/.local/bin:$PATH";`.
The binary is `parcellab`. There is no `parcellab-cli` binary.

## Retrieval (no LLM in the path — fast)

| Route | Returns | Latency | Use for |
|---|---|---|---|
| `knowledge_search_documents` | raw chunks, full text | ~2-5s | Default for everything |
| `knowledge_search_document_set` | raw chunks, one named set | ~2-5s | Internal technical/best-practice docs |
| `knowledge_search_public_document_set` | raw chunks, public docs | ~2-5s | "What do the customer-facing docs say" |
| `knowledge_gpt_search_documents` | full matching chunks | ~2-5s | Alternate retrieval endpoint |
| `knowledge_discover_onyx_filters` | 20 document sets, 13 connectors | ~2s | Get an exact set name before scoping |
| `knowledge_get_document_info` | document metadata | fast | Identify a document from a search hit |
| `knowledge_get_chunk_content` | one chunk's full content | fast | A search chunk was truncated |
| CLI `knowledge search-set --document-set <name>` | raw chunks | ~2-5s | CLI equivalent of scoped search |
| CLI `knowledge document-info <id>` | metadata | fast | CLI equivalent |
| CLI `knowledge chunk-content` | chunk content | fast | CLI equivalent |
| CLI `knowledge discover-filters` | filter values | fast | CLI equivalent |

## Synthesis (an agent answers — slow, announce first)

| Route | Returns | Latency | Use for |
|---|---|---|---|
| `knowledge_ask_gtm_agent` | answer + citations | ~30-60s | Positioning, objection handling, pilot design |
| `knowledge_query_parcellab_knowledge` | answer + citations | times out on long questions | Short questions only; prefer the CLI |
| CLI `knowledge search "<q>"` | answer + citations, JSON | ~42s measured | Cited narrative answer; survives MCP timeouts |

Both synthesis routes accept `session_id` to continue a thread. Both time out on long multi-part
questions and succeed on tight single ones — **split the question, do not report a timeout as a
broken tool**.

`knowledge_ask_gtm_agent` is a *separate* GTM-tuned agent. It is strong on framing and weak on facts:
it carries **no account-specific context**. Always pair it with a retrieval pass for customer facts.

## Notion (CLI only — not exposed over MCP)

| Command | Effect |
|---|---|
| `knowledge read-page` | Read a Notion page as markdown |
| `knowledge update-page` | Targeted markdown replacements |
| `knowledge replace-page` | Replace an entire page |

`update-page` and `replace-page` **write** to Notion. Confirm with the user before either.

## Indexed sources

file, gitbook, github, gong, jira, notion, s3, salesforce, sharepoint, slack, teams, web, zendesk.
Account and deal research therefore works through these routes — the separate Gong MCP is not required.

## Dead routes — do not attempt

Direct `onyx.parcellab.com/api` calls with an `onyx_pat_...` PAT, and the `onyx:onyx-ask` /
`onyx:onyx-search` plugin skills. The host sits behind an Envoy `jwt_authn` filter fronted by
Keycloak, so any `Authorization: Bearer` value is validated as an OIDC JWT and the PAT never
reaches Onyx.

**A bogus bearer returns the identical 401 as a valid PAT** —
`Jwt is not in the form of Header.Payload.Signature with two dots and 3 sections`.
Never diagnose this as an expired token and never mint a replacement PAT.
