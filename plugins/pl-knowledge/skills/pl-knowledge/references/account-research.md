# Account and deal research

Onyx indexes Gong, Salesforce, Notion, Jira, Slack and Zendesk, so account research is the same
retrieval mechanism pointed at a customer name.

## Source-type preferences

| Source | Worth reading for | Watch out for |
|---|---|---|
| `notion` | One-pagers, business cases, win/loss analyses — the narrative backbone | — |
| `gong` | Verbatim call quotes; far more useful than paraphrase | Chunks are mid-conversation; read surrounding context |
| `salesforce` | Hard commercials only: ARR, opportunity stage, close dates, owner | Many chunks are raw field dumps (`IsDeleted: False`, `type: TaskRelation` repeated) that burn context for nothing — skip them |
| `jira` / `github` | Open defects and delivery state for the account's features | — |

Pass `source_type` to narrow when a query returns Salesforce noise.

## The cross-read step

This is the highest-value move and the reason to run two retrieval passes rather than one.

1. Retrieve what the **product** requires in order to work (its data dependencies, prerequisites,
   integration surface).
2. Retrieve what is **already known to be broken or missing** at this customer.
3. Report where those two collide.

Worked example: for a WISMO-agent conversation with River Island, the product depends on accurate
carrier tracking data, and the account file records long-standing international DPD tracking gaps.
That collision — a risk to answer quality — appears in neither the product docs nor the account
docs alone. It is the single most useful thing to bring to the call.

## Standard sweep for call prep

Run these retrieval passes, then cross-read:

- `<customer>` business case / problem statements / target outcomes
- `<customer>` stakeholders and decision makers
- `<customer>` carriers, systems, integrations
- `<customer>` known issues, escalations, open defects
- `<product>` prerequisites and technical requirements

Then, only if positioning or objections were asked for, add one `knowledge_ask_gtm_agent` call
(Tier 2 — announce it first).

## What to report

Lead with what is specific to this customer: named stakeholders, real systems, real carriers, live
commitments and dates. Generic product capability is the least valuable part of a brief — the user
already knows the product. Flag explicitly anything you could **not** find, rather than filling the
gap with generic material.
