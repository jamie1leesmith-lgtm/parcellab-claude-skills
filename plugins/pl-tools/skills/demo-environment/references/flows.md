# Phases & gates

The full run is intake → template (checkpoint → publish → assign) → orders
with events → one CDC call → report, in whichever of the three paths intake
selects.

## The three paths

| Path | Orders created via | Returns story | CDC account config |
|---|---|---|---|
| **Engage** | direct pL writes (order-lifecycle mechanics) | none | matches the target account (default / parcelfashion) |
| **Retain, non-Shopify** | direct pL writes (order-lifecycle mechanics) | pL returns portal on the account | matches the target account (default / parcelfashion) |
| **Retain, Shopify** | real Shopify orders via CLI → parcelLab Shopify integration syncs them | Shopify-linked Returns Portal v2 against the seeded dev store | shopify (user's own account) |

An Engage-only run never asks the Shopify question; Retain covers the
Engage comm story automatically, so "returns in scope?" is the only branch
point that matters before "is this a Shopify opp?".

## Phase 0 — Intake, front-loaded (main session + one agent)

Two lanes run concurrently after the path questions:

- **scrape agent** (background, owns the Browser pane): brand tokens +
  product pool + image validation → `scrape/` + `results/scrape.json`
- **interview** (chat): country, order plan, pace, CDC region/category,
  Shopify dev-store + location resolution on retain-shopify,
  target-account confirmation + edit-mode guard

They join at **pre-build** — template HTML, the fraud fragments, the direct
engine's create/track/event files (never on retain-shopify: its tracking and
courier do not exist yet), the proposed plan — all local, nothing sent.

Then **two approvals, in order**:

1. ★ **the template** — the pre-built HTML is served and previewed on its own,
   and iterated until the user says yes. It is the run's first deliverable and
   gates every comm, so it is approved before anything downstream is shown.
   The run page holds at a template-only state here. Skipped entirely when a
   repeat brand's layout already verified live.
2. ✋ **the plan** — products, distribution, order/scenario/fraud matrix, CDC
   fields, pace, account. One yes releases the sends: nothing before it has
   sent anything to parcelLab, Shopify or the CDC.

Finally the manifest is written and validated. Nothing past this phase starts
on an invalid manifest.

A repeat brand can skip the template lane entirely if its existing layout
verifies live as published and store-assigned; a failed scrape agent falls
back to the same browser pass inline.

## Phase 1 — Concurrent build

Main session builds the branded layout from `brand_tokens` (no re-scrape):
preview → **the run's one checkpoint** → publish → assign to store. On the
Shopify path a background agent shapes and pushes the seed set in parallel,
writing its result to the run dir. No demo-request agent runs here — the
CDC call moved to Phase 3.

## Phase 2 — Orders (main session)

Hard-gated on the layout's `releaseStatus: published` — order creation
fires the order-confirmation comm immediately, on every path. The Shopify
path additionally gates on seed verification. Direct paths create each
order, add tracking, then launch one detached event driver per order.
The Shopify path creates the order in Shopify, waits for pL ingestion,
enriches it with fraud data, fulfils it, then pushes the same events.

## Phase 3 — The CDC call (main session, after orders exist)

Exactly one CDC interaction per run, at the end — `linked_orders` is only
accepted on the creation call. One POST names the core 4 products, the
account config, and every order created in Phase 2 with its claimed slot.

## Phase 4 — Report (two beats)

Beat 1, immediately: what got built — layout, per-order detail (customer,
fraud level, slot, tracking, expected comms), Shopify seed table if
applicable, CDC request id/URL. Beat 2, after the drivers finish: verify
checkpoints and comms landed per order via the public order-info lookup,
covering both the good and bad arcs the run promised.
