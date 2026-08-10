# `demo-environment` — unified demo-build skill (design)

**Dated:** 2026-08-07, revised 2026-08-10 after Jamie's Lucidchart flow
walk-through ("Shopify Ultimate Demo Skill") and the CDC Automation API
Reference · **Status:** approved by Jamie 2026-08-10 (via flow-diagram review) ·
**Branch:** `feat/demo-environment`

**Flow diagrams** (four figures: paths, phase skeleton, Shopify order engine,
default order matrix): source in
[`2026-08-07-demo-environment-flows.html`](2026-08-07-demo-environment-flows.html),
published at https://claude.ai/code/artifact/6c3dfbe6-cbfb-43de-b4d1-0cf9a9ffaa2d

## Purpose

One skill that builds a complete parcelLab customer demo from a single
sitting: branded email template, 1–5 realistic orders walking through good and
bad delivery journeys with fraud-risk data attached, (if Shopify) real orders
in a seeded dev store flowing through the parcelLab Shopify integration, and a
CDC demo request that features those same orders. Today that is an hour of
supervised skill-by-skill work; this skill makes it one interview, one
template checkpoint, and a report.

**Success criteria**

- One invocation produces, per the chosen path: a published branded layout
  assigned to a store; the configured order set live in pL with scenarios
  running and fraud flags visible; (Shopify) the dev store seeded and the
  orders created *in Shopify*, synced through the real integration; and a CDC
  demo request created **with the real orders linked**.
- The user answers questions only at intake and at the single template
  checkpoint. Agents never ask anything.
- A failed lane reports and everything independent continues; any lane can be
  re-run inline from the manifest.
- Every sub-skill remains fully usable standalone, unchanged.

## Approach

**Conductor skill + shared manifest + brief-driven agents (Approach A), with
the sequential path (B) as built-in fallback.** The conductor never
re-implements a sub-skill; it prepares complete answers (the manifest), then
runs each sub-skill inline or in a background agent. A failed agent lane is
re-run inline from the same manifest — B is A minus concurrency, not a second
code path. (Rejected: merged mega-skill — forks every hard-won rule in the
sub-skills and every future fix would need making twice.)

## The three paths

The first intake question is **"Are returns in scope for this demo?"**
(Retain, or Engage + Retain — operationally identical, since the Retain
machinery fires all the Engage comms anyway). If yes, the second question is
**"Is this a Shopify opp?"** Engage-only runs never ask the Shopify question.

| Path | Orders created via | Returns story | CDC account config |
|---|---|---|---|
| **Engage** | direct pL writes (`order-lifecycle` mechanics) | none | standard |
| **Retain, non-Shopify** | direct pL writes (`order-lifecycle` mechanics) | pL returns portal on the account | standard |
| **Retain, Shopify** | **real Shopify orders** via CLI → parcelLab Shopify integration syncs them | Shopify-linked Returns Portal v2 against the seeded dev store | shopify |

All three share the same skeleton: intake → template (checkpoint → publish →
assign) → orders with events → **one CDC call** → report.

## Architecture — five phases

The conductor is a new skill at `plugins/pl-tools/skills/demo-environment/`
(no new plugin, no marketplace entry, no `pl-` directory prefix).

### Phase 0 — Intake (main session, all interaction lives here)

1. **Batched interview**: prospect URL (usually the invocation argument) ·
   returns in scope? · (if returns) Shopify opp? — confirm dev store by name
   (`~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`)
   and resolve the location GID immediately (shopify-seed Step 2 rules) ·
   destination country (never assumed) · **order plan** (see *Order model*):
   count (1–5, default 3), per-order fraud level + scenario, slots 4/5 on
   Retain runs · CDC region + category (US/UK/DE, Home/Electronics/Fashion),
   inferred then confirmed.
2. **parcelLab account confirmation** — resolve `$PARCELLAB_ACCOUNT_ID`
   (fallback `$PARCELLAB_USER_ID`), show the account **by name** via
   `parcellab account account show`, get a yes, verify
   `parcellab settings edit-mode show` says `account-restricted` for that
   account. Covers every pL write in the run.
3. **One browser pass** on the prospect site (the only browsing in the run):
   brand styles/logo/hero via the `branded-template` Step 3–6 snippets →
   `brand_tokens`; product pool (aim ≥8 PDP candidates) in the superset shape,
   following `shopify-seed`'s `references/product-scrape.md` discipline.
   Variant axes are **required** only on the Shopify path; elsewhere capture
   what the PDP shows without extra navigation. Validate images
   (`check_images.mjs` semantics).
4. **Product selection & the single approval gate.** The conductor proposes:
   core 4 (different types) → CDC request *and* order line items; per-order
   product distribution; (Shopify) the seed set = core products with full
   variant spread plus extra price points so `shape_product_mix.py` can
   guarantee all four exchange demos. One approval covers products, images,
   distribution, pricing adjustments, the order plan with expected comms per
   event, CDC fields, and the account. Then the manifest is written and
   validated.

### Phase 1 — Concurrent build

- **Main session — `branded-template`:** build HTML from `brand_tokens` +
  bundled `template.html` (no re-scrape) → serve preview → **★ the run's one
  checkpoint ★** → push (`journey_write_layout`) → publish (CLI, Step 9a
  rules) → assign to store (Step 9b autoLayout merge discipline; on the
  Shopify path the Shopify-linked client is pre-selected from intake).
- **Agent — `shopify-seed`** (background, Shopify path only): shape mix from
  the manifest → archive previous `pl-demo-seed` products → push → verify by
  returned IDs (media READY, ≥2 variants, stock, `availableForSale`) → write
  `results/shopify-seed.json`.

There is no demo-request agent any more — the CDC call moved to Phase 3
(see *The CDC call*). On non-Shopify paths Phase 1 is just the template.

Agent ground rules (verbatim in every brief): never open the Browser pane;
never ask the user anything (a gap is a failure report, not a question);
write results to the run dir.

### Phase 2 — Orders (main session)

**Hard-gated on `releaseStatus: published`** — order creation immediately
fires the order-confirmation comm, on every path (the Shopify integration
syncs new orders into pL near-instantly). On publish failure the conductor
offers: fix & re-publish / publish manually then continue / explicitly
proceed accepting unbranded comms. **The Shopify path additionally gates on
seed verification** — order line items reference seeded variants.

**Direct paths (Engage, Retain non-Shopify)** — per order in `orders[]`:
`create.json` (unique synthetic customer, unique order number, fraud `tags` +
`additional_attributes.riskAssessment` in the creation payload) + one PUT
with all `add_tracking` mutations (randomised tracking numbers, courier per
shipment, `tracking.articles` mirrored, split-shipment rules) → event files
`NN-<status>.json` into `orders/<nn>-<label>/` → `DRYRUN=1` → launch
`run-lifecycle.sh` detached, one driver per order, concurrently.

**Shopify path** — per order:

1. **Create the order in Shopify** (Admin GraphQL via
   `shopify store execute --allow-mutations`; needs order-write scope) with
   that order's synthetic customer and its line items from the seeded
   variants.
2. **Wait for pL ingestion** — the parcelLab Shopify app syncs the order;
   normally instant, so poll the order-info lookup briefly rather than
   assuming.
3. **Enrich the pL order** — the integration created it, so fraud data
   cannot ride in on creation: PUT update adding `tags` +
   `additional_attributes.riskAssessment`.
4. **Fulfil in Shopify** with a tracking number and a carrier pL recognises —
   the integration passes the fulfilment down and creates the pL tracking.
   Split-shipment orders fulfil in two fulfilments (two tracking numbers).
5. **Push shipment events** to pL against that courier + tracking number with
   the same event driver as the direct path.

### Phase 3 — The CDC call (main session, after orders exist)

**Exactly one CDC interaction per run**, at the end, because with a
`cdc_live_` token `linked_orders` is accepted **only on the creation call**
(Automation API Reference, 2026-08-10). One POST to
`/api/automation/demo-requests`: prospect fields + region/category + the core
4 products + `selected_account_config_id` (see below) +
`generate_orders: false` + `linked_orders` naming every order created in
Phase 2 with its claimed slot (see *Order model*). Report the returned
id/status/request_url. Linking is best-effort per item — failures land only
in the request's `job_logs`, so the report tells the user to eyeball the
request page (no list/read API exists).

`selected_account_config_id` comes from `~/.claude/parcellab-demo-request.env`:
`CDC_ACCOUNT_CONFIG_SHOPIFY` on the Shopify path, `CDC_ACCOUNT_CONFIG_STANDARD`
otherwise. Missing value → omit the field (the CDC then uses the caller's
default config) and say so in the report. Intake may optionally enable
synthetic generation (`generate_orders: true` + `order_types`) for slots not
covered by real orders; default is off.

### Phase 4 — Report (two beats)

- **Beat 1 — environment built:** layout id/status/store (+ any
  country-override warning) · per order: number, customer, fraud level,
  slot, shipment/tracking numbers, couriers, scenario, expected comm per
  event (with status-confidence labels) · (Shopify) seed table + available
  exchange demos + price adjustments · CDC request id/URL + which orders were
  submitted for linking.
- **Beat 2 — verified:** after each driver finishes and ≥5 min after its
  final event, verify per order via public order-info lookup: checkpoints
  attached + `contacted_with_messages` — explicitly covering both the good
  and bad comm arcs the run promised. Offer to record newly proven statuses
  in `order-lifecycle`'s `references/status-codes.md`.

## Order model

**Ground rules** (enforced by intake + `validate_manifest.py`):

1. 1–5 orders per run (hard cap 5), **default 3**.
2. Every order distinct: unique synthetic customer (region-appropriate name +
   email), unique order number, own product mix drawn from the core 4.
3. Every order carries a fraud-risk level (`low|medium|high`), injected as
   `tags` + `additional_attributes.riskAssessment` from the canned fragments
   (see *Fraud-risk data*). Levels vary across the run.
4. At least one split-shipment order per run of 2+ orders (a deliberate
   single-order run may use any scenario).
5. Retain runs: at least one order ends `Delivered` (return-eligible).

**Default matrix (the "default 3")** — chosen so one run shows all three comm
arcs (clean / stuck / recovered):

| # | Fraud | Journey | Comm arc | CDC slot |
|---|---|---|---|---|
| 1 | low | single, `InTransit → OutForDelivery → Delivered` | clean good path | `fraud_low` |
| 2 | medium | split: A happy → `Delivered` · B `InTransit → WarehouseDelay`, stays stuck | good and bad side by side | `fraud_medium` |
| 3 | high | single, `InTransit → WarehouseDelay → OutForDelivery → Delivered` | **delayed-but-recovered** — delay comm, then the save | `fraud_high` |

Optional orders on Retain runs:

| 4 | any | happy → `Delivered` | the order walked through the returns portal live in the demo | `manual_return` |
| 5 | any | happy → `Delivered` | return-prep order; **the return itself is registered manually by the AE** (v1 behaviour — decided 2026-08-10, no auto-registration machinery) | `return_tracking` |

Scenario vocabulary: `happy` / `stuck-delay` / `recovered` / `locker` /
`custom`. Statuses outside the proven set (`InTransit`, `OutForDelivery`,
`Delivered`, `WarehouseDelay`) — e.g. `Delivered-ParcelLocker` — and the
`recovered` *sequence* (statuses individually proven, chain unproven) are
offered but labelled, verified in Beat 2, and recorded once proven. The five
CDC slots cap the run at 5 orders naturally; fraud levels map to fraud slots
one-to-one.

## Fraud-risk data

Canned per-level payload fragments (source: `fraud_risk_payloads.json` in
`parcelLab/custom-demo-creator`; ship a copy in the skill's `references/`,
pending comparison with Jamie's current working payload). Each level =
`tags: ["FraudRisk<Level>"]` + `riskAssessment` array of model predictions
(bad_actor, reseller, return_abuser, return_fraudster + sub-signals with
indicators, scores, justifications). At build time the skill freshens
prediction timestamps to look recent and points `shop_url`/ids at the active
context. Direct paths inject at order creation; the Shopify path enriches
after ingestion (Phase 2 step 3).

## The manifest

`$HOME/parcellab-demo-runs/<brand-handle>-<timestamp>/demo-manifest.json` —
the single interface between conductor and sub-skills. Sketch:

```json
{
  "run": { "created_at": "…", "run_dir": "…", "skill_version": "<sha>" },
  "path": "engage | retain | retain-shopify",
  "brand": { "name": "…", "url": "…", "handle": "acme-store",
             "region": "UK", "category": "Fashion" },
  "account": { "id": 1626718, "name": "…", "confirmed_at": "…",
               "edit_mode_verified": true },
  "cdc": { "selected_account_config_id": "<uuid or null>",
           "config_source": "shopify | standard | none",
           "generate_orders": false, "order_types": [] },
  "shopify": { "enabled": true, "store": "x.myshopify.com",
               "location_id": "gid://shopify/Location/…" },
  "destination_country": "GBR",
  "products": [ { "id": "p1", "name": "…", "product_type": "…", "price": "…",
                  "options": [ {"name": "Size", "values": ["S","M","L"]} ],
                  "image_url": "…", "image_verified": true,
                  "pdp_url": "…", "sku": "…" } ],
  "selection": { "core4": ["p1","p2","p3","p4"], "shopify_extra": ["p5","p6"] },
  "brand_tokens": { "…": "branded-template Step 6 token map",
                    "logo": { "type": "url | inline-svg", "value": "…" },
                    "hero": { "url": "…", "alt": "…" } },
  "orders": [ { "label": "recovered-high", "dir": "orders/03-recovered-high",
                "cdc_slot": "fraud_high", "fraud_level": "high",
                "customer": { "name": "…", "email": "…" },
                "products": ["p4"],
                "shipments": [
                  { "label": "A", "scenario": "recovered", "courier": "dpd-uk",
                    "products": ["p4"],
                    "events": ["InTransit","WarehouseDelay","OutForDelivery","Delivered"],
                    "unproven_chain": true } ] } ],
  "gates": { "order_lifecycle": { "gate_b_answered": true,
                                  "gate_c": "send-as-is", "extras": {} } },
  "approvals": { "products_approved_at": "…", "intake_completed_at": "…" }
}
```

`validate_manifest.py` (stdlib, `plugins/pl-tools/scripts/`, unit-tested)
fails loudly before Phase 1 if: <4 core products; any selected image
unverified; Shopify enabled without store/location or ≥2-variant coverage;
>5 orders, no split-shipment order in a 2+-order run, duplicate
customers/order numbers, or duplicate `cdc_slot` claims; a fraud level
missing; a Retain run with no
`Delivered`-ending order; any event outside the proven set (or unproven
chain) not labelled; missing account confirmation or gate answers.

## Sub-skill contracts ("Orchestrated runs" sections)

Additive sections only; without a manifest every skill behaves exactly as
today.

| Skill | Runs as | Manifest replaces | Unchanged |
|---|---|---|---|
| `branded-template` | main session | Step 1b account; Steps 2–6 scraping (via `brand_tokens`) | Steps 7–10 incl. preview checkpoint, publish, 9b assignment |
| `shopify-seed` | background agent (Shopify path) | Step 1 store + Step 2 location (intake), Step 3 collection, Step 5 approval | Steps 0, 4, 6–9 |
| `order-lifecycle` | main session (direct paths; event driver reused on Shopify path) | Gates A/B/C (from `gates` + `orders[]`), product sourcing | payload rules, driver, split rules, reporting, failure lore |
| `demo-request` | main session, Phase 3 | Steps 1–5 (browse/collect/validate), Step 6 approval | Step 7–8 submit + report, extended: `selected_account_config_id`, `generate_orders`, `linked_orders` |

The manifest's approval timestamps are the user's recorded answers to those
gates. **New machinery owned by `demo-environment` itself:** the Shopify
order engine (create order → poll ingestion → enrich → fulfil → events) and
the fraud-fragment injection. `bug-investigation` and `create-order` are not
orchestrated.

## Error handling

- **Lane isolation:** seed failure blocks only Shopify orders (loudly — it
  was the point of the opp). Publish failure blocks only Phase 2, with the
  three-way offer. One order's failure never stops another's driver. The CDC
  call failing (or 500-with-request-created) is reported with the request id
  if one exists; nothing else depends on it.
- **Shopify-path specifics:** ingestion poll timeout → report the order
  number, continue other orders, offer retry; enrichment or fulfilment
  failure → that order is reported as partial, its events are not pushed.
- **Fallback to B:** any failed/gapped agent lane re-runs inline from the
  manifest at the user's choice. No silent continuation; every lane ends in
  a result file or a reported failure.
- **Write safety:** all pL writes in the main session under the confirmed
  account + verified edit-mode guard. Agents touch only the Shopify dev
  store (own CLI auth, store confirmed by name). Shopify order/fulfilment
  writes are to the **dev store only**, named at confirmation.

## Testing

- **Unit (stdlib `unittest`):** `validate_manifest.py` rules above +
  round-trip of the sketch; fraud-fragment freshener (timestamps, shop_url
  rewrite) if it becomes a script. Run:
  `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`.
- **Live, staged:** (1) Engage path, single happy order, end-to-end on
  account 1626718; (2) direct Retain path, default 3 (proves the recovered
  chain and the delay comms); (3) full Shopify path with seed, 3 orders,
  slots 4–5, CDC linking. Beat 2's verification is the pass/fail each time.
- **Standalone regression:** sub-skill edits are additive-only; confirmed by
  diff review and next standalone use.

## Naming, docs, repo mechanics

- Skill `demo-environment`; description spells out **parcelLab**, triggers on
  *"build a parcelLab demo environment for [brand]"*, *"set up the full demo
  for [prospect]"*, *"run the whole demo build"*. `argument-hint:
  <prospect-url>`.
- README gains the skill row; `/pl-setup` gains the two optional
  `CDC_ACCOUNT_CONFIG_*` values; `demo-request/references/api-payload.md`
  refreshed against the Automation API Reference (canonical:
  https://app.notion.com/p/parcellab/Automation-API-Reference-3b8c37dcb4c481789aa8c5e80fcfc730 ).
- No pl-tools version field (SHA-versioned); no marketplace change. All work
  on `feat/demo-environment`.

## Open items

1. **Shopify order-write scope & carrier mapping** — the dev-store auth may
   need re-consenting with an order-write scope; and the fulfilment's
   tracking company must map to a pL courier. Verify both in live test 3.
2. ~~Fraud payload currency~~ **Resolved 2026-08-10**: Jamie's current
   working order payload carries riskAssessment content identical to the
   repo's `fraud_risk_payloads.json` (same prediction ids/timestamps/domain);
   stored orders expose it as `customFields.riskAssessment` + `tags`,
   confirming the `additional_attributes` send shape.
3. **CDC landing-page slot semantics** — ask Max what each `order_type`
   drives on the v2 demo page, so slot claims (esp. linking real orders into
   fraud slots) render as intended. Also collect the two
   `CDC_ACCOUNT_CONFIG_*` UUIDs from the CDC UI.
4. **Unproven event chains** — `recovered` sequence and `Delivered-
   ParcelLocker`: verify live, record in `status-codes.md`.

## Out of scope

- Creating or editing CDC account configurations (UI-only today), and any
  session-JWT CDC endpoints (`generate_existing_request`, per-order
  add/remove) — the skill is token-tier only.
- Auto-registering returns (slot 5 stays manual, v1 behaviour — decided
  2026-08-10).
- Journey/trigger configuration changes; the run assumes the account's
  Journey setup and (Shopify path) the installed parcelLab Shopify app +
  Shopify-linked Returns Portal v2 already exist.
- Login-gated prospect sites (fresh browser context, same rule as the
  sub-skills).
