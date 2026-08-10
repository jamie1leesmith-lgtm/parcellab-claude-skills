# `demo-environment` — unified demo-build skill (design)

**Date:** 2026-08-07 · **Status:** approved pending Jamie's spec review · **Branch:** `feat/demo-environment`

## Purpose

One skill that builds a complete parcelLab customer demo from a single sitting:
today that means running `branded-template`, `demo-request`, optionally
`shopify-seed`, and `order-lifecycle` by hand, in order, answering each skill's
questions and doing each skill's browsing separately. The unified skill gathers
**all** decisions up front in one intake, browses the prospect site **once**,
then executes the sub-skills — concurrently where dependencies allow — so a
demo environment that took the best part of an hour of supervised work becomes
one interview, one template checkpoint, and a report.

**Success criteria**

- One invocation (`build a parcelLab demo environment for <brand url>`) produces:
  a submitted CDC request, a published branded layout assigned to a store,
  (if Shopify) a seeded dev store supporting all four exchange demos, and the
  configured set of live orders walking through their scenarios.
- The user answers questions **only** at intake and at the single template
  checkpoint. Agents never ask anything.
- A failed lane never silently sinks the run: it reports, everything
  independent continues, and the lane can be re-run inline from the manifest.
- Every sub-skill remains fully usable standalone, unchanged.

## Approach

**Approach A (chosen): conductor skill + shared manifest + brief-driven
agents, with the sequential path (Approach B) as the built-in fallback.**
The conductor never re-implements a sub-skill; it prepares complete answers
(the manifest), then runs each sub-skill either in a background agent or
inline in the main session. If an agent fails, the same manifest drives an
inline re-run — B is A minus the concurrency, not a separate code path.

Rejected: a merged mega-skill (forks every hard-won rule in the four
SKILL.mds — the `autoLayout` merge logic alone is ~100 lines of scar tissue —
and every future sub-skill fix would need making twice).

## Architecture

Four phases. The conductor is a new skill at
`plugins/pl-tools/skills/demo-environment/` (no new plugin, no marketplace
entry, no `pl-` directory prefix).

### Phase 0 — Intake (main session, all interaction lives here)

1. **Batched interview** (one `AskUserQuestion` round wherever possible):
   - Brand/prospect URL (usually given as the invocation argument).
   - **Shopify opp?** If yes: confirm the dev store by name (from
     `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`),
     then resolve the location GID immediately (the `shopify-seed` Step 2
     query and selection rules) so the manifest carries it.
   - **Destination country** (never assumed — sets language, currency,
     timezone, courier, addresses).
   - **Orders & scenarios** — see *Order model* below. Default offer is the
     canonical two-order demo; the user can reshape it.
   - **CDC region + category** (US/UK/DE, Home/Electronics/Fashion) —
     inferred from the site, confirmed here.
2. **parcelLab account confirmation** — resolve `$PARCELLAB_ACCOUNT_ID`
   (fallback `$PARCELLAB_USER_ID`), show the account **by name** via
   `parcellab account account show`, get a yes, and verify
   `parcellab settings edit-mode show` says `account-restricted` for that same
   account. This single confirmation covers every parcelLab write in the run
   (all of which happen in the main session).
3. **CDC account config selection** — automatic, driven by the Shopify
   answer: the CDC has different account configurations for Shopify and
   non-Shopify demos. The conductor reads two optional values from
   `~/.claude/parcellab-demo-request.env` (the file `demo-request`'s
   credentials already live in):
   - `CDC_ACCOUNT_CONFIG_SHOPIFY=<uuid>`
   - `CDC_ACCOUNT_CONFIG_STANDARD=<uuid>`
   Shopify opp → the Shopify UUID; otherwise the standard UUID. If the needed
   value is missing, the demo request is submitted **without**
   `selected_account_config_id` (the CDC's default behaviour) and the report
   says so. The UUIDs come from the CDC UI today; see *Open items*.
4. **One browser pass** on the prospect site (the only browsing in the run):
   - Brand style extraction: the `branded-template` Step 3–6 snippets
     (styles, buttons, logo, hero) → `brand_tokens`.
   - Product pool collection: **more than 4 candidates** (aim ≥8 PDPs), each
     scraped in the superset shape (see *Manifest*), following
     `shopify-seed`'s `references/product-scrape.md` discipline (landing
     guard, variant-axis harvesting including colour-sibling pages). Variant
     axes are **required** only when `shopify.enabled`; on non-Shopify runs
     capture whatever the PDP already shows, but spend no extra navigation
     on variants.
   - Image validation for every candidate that survives selection
     (`check_images.mjs` semantics: 200 + `image/*`, ranged-GET retry).
5. **Product selection & the single approval gate.** The conductor proposes:
   - **Core 4** — four products of different types → the CDC request *and*
     the orders.
   - **Order distribution** — which core products land in which order/shipment
     (e.g. split order carries 3 across shipments A+B, locker order carries
     the 4th).
   - **Shopify set** (only if Shopify) — the core products with their full
     variant spread, plus extra products at distinct price points so
     `shape_product_mix.py` can guarantee even, uneven-upward and (when
     available) uneven-downward exchanges.
   One approval covers: products, images, distribution, Shopify pricing
   adjustments (`was → now`), scenario/comm expectations per order, the CDC
   fields, and the account. On yes, the manifest is written and validated.

### Phase 1 — Concurrent build

Launched in a single message so they run in parallel:

- **Agent 1 — `demo-request` (background, always):** follows the skill's
  *Orchestrated runs* contract: read manifest → build payload (core 4, brand
  fields, `selected_account_config_id` if present) → submit via
  `submit_demo_request.mjs` → write `results/demo-request.json` in the run
  dir and return a summary (request id, URL, status).
- **Agent 2 — `shopify-seed` (background, only if `shopify.enabled`):**
  preflight → location already resolved at intake → shape mix from the
  manifest's Shopify set → archive previous `pl-demo-seed` products → push →
  verify by returned IDs (media READY, ≥2 variants, stock, `availableForSale`)
  → write `results/shopify-seed.json` + summary (product table, demo list,
  adjustments, warnings).
- **Main session — `branded-template`:** build the HTML from
  `brand_tokens` + bundled `template.html` (no re-scrape) → serve preview →
  **★ the run's one checkpoint: user approves the template ★** → push via
  `journey_write_layout` → publish via CLI (Step 9a rules) → assign to the
  store per Step 9b (full autoLayout merge discipline; if Shopify opp, the
  conductor pre-selects the Shopify-linked client from intake, still
  confirmed in the 9b.2 flow when several stores exist).

Agent ground rules (verbatim in every brief): **never open the Browser pane**
(everything browser-derived is already in the manifest; a genuine gap — e.g.
Shopify rejects an image server-side — is reported back, fixed by the
conductor in the main session, and the lane re-dispatched or run inline);
**never ask the user anything** (a brief is complete by construction; a gap is
a failure report, not a question); **write results to the run dir** so the
conductor's report never depends on parsing prose.

### Phase 2 — Orders (main session, hard-gated on publish)

Blocked until Step 9a confirms `releaseStatus: published` — order creation
fires the order-confirmation comm immediately, and an unpublished template
means the demo's first email goes out unbranded. On publish failure the
conductor offers: fix & re-publish / publish manually in the portal then
continue / explicitly proceed accepting unbranded comms.

For each order in `orders[]`:

1. Build `create.json` (no mutations) + one PUT with all `add_tracking`
   mutations for that order's shipments (randomised format-correct tracking
   numbers, courier per shipment, `tracking.articles` mirrored from
   `articles_order` — the blank-article-table rule), split-shipment flag and
   article split per the `order-lifecycle` rules.
2. Write the order's event files `NN-<status>.json` into its own directory
   `orders/<nn>-<label>/` (courier + tracking_number identifiers, no
   timestamps, no account — the driver injects both).
3. `DRYRUN=1` pass, then launch `run-lifecycle.sh` detached
   (`run_in_background`), `GAP_SECONDS` default 180, one driver per order —
   drivers run concurrently, so N orders cost the wall-clock of the longest.

### Phase 3 — Report (two beats)

- **Beat 1 — environment built:** CDC request id/URL/status · Shopify product
  table + available exchange demos + price adjustments · layout id, account,
  `releaseStatus`, store assignment (+ any country-override warning) · per
  order: order number, shipment/tracking numbers, couriers, scenario, and the
  expected comm per event (labelled with status confidence).
- **Beat 2 — verified:** after each driver finishes **and ≥5 minutes** after
  its final event (the delivered comm demonstrably lags), verify per order via
  public order-info lookup: checkpoints attached + `contacted_with_messages`.
  Report actual vs expected; offer to record newly proven statuses in
  `order-lifecycle`'s `references/status-codes.md`.

## Order model (multi-order runs)

`orders[]` in the manifest; each order has its own run subdirectory, driver
instance, and isolated payloads (fresh order number, fresh tracking numbers).
The intake's default offer is the **canonical two-order demo**:

| Order | Shipments | Sequence | Note |
|---|---|---|---|
| 1 "Split shipment" | A: happy | `InTransit → OutForDelivery → Delivered` | all proven |
| | B: unhappy | `InTransit → WarehouseDelay` (stays stuck) | all proven |
| 2 "Locker delivery" | single | `InTransit → OutForDelivery → Delivered-ParcelLocker` | final status **inferred, unproven** |

Statuses outside the proven set (`InTransit`, `OutForDelivery`, `Delivered`,
`WarehouseDelay`) are offered but labelled unproven at intake, and Beat 2
reports whether they actually attached/fired. The user can add, remove, or
reshape orders freely; each shipment's scenario and courier is confirmed at
intake (Gate B semantics, answered once).

## The manifest

`$HOME/parcellab-demo-runs/<brand-handle>-<timestamp>/demo-manifest.json` —
the single interface between conductor and sub-skills. Sketch:

```json
{
  "run": { "created_at": "…", "run_dir": "…", "skill_version": "<sha>" },
  "brand": { "name": "…", "url": "…", "handle": "acme-store",
             "region": "UK", "category": "Fashion" },
  "account": { "id": 1626718, "name": "…", "confirmed_at": "…",
               "edit_mode_verified": true },
  "cdc": { "selected_account_config_id": "<uuid or null>",
           "config_source": "shopify | standard | none" },
  "shopify": { "enabled": true, "store": "x.myshopify.com",
               "location_id": "gid://shopify/Location/…" },
  "destination_country": "GBR",
  "products": [ { "id": "p1", "name": "…", "product_type": "…",
                  "price": "…", "options": [ {"name": "Size", "values": ["S","M","L"]} ],
                  "image_url": "…", "image_verified": true,
                  "pdp_url": "…", "sku": "…" } ],
  "selection": { "core4": ["p1","p2","p3","p4"],
                 "shopify_extra": ["p5","p6"] },
  "brand_tokens": { "…": "branded-template Step 6 token map",
                    "logo": { "type": "url | inline-svg", "value": "…" },
                    "hero": { "url": "…", "alt": "…" } },
  "orders": [ { "label": "split-shipment", "dir": "orders/01-split-shipment",
                "products": ["p1","p2","p3"],
                "shipments": [
                  { "label": "A", "scenario": "happy", "courier": "dpd-uk",
                    "products": ["p1","p2"],
                    "events": ["InTransit","OutForDelivery","Delivered"] },
                  { "label": "B", "scenario": "unhappy", "courier": "dpd-uk",
                    "products": ["p3"],
                    "events": ["InTransit","WarehouseDelay"] } ] },
              { "label": "locker", "dir": "orders/02-locker",
                "products": ["p4"],
                "shipments": [
                  { "label": "A", "scenario": "custom", "courier": "dpd-uk",
                    "products": ["p4"],
                    "events": ["InTransit","OutForDelivery","Delivered-ParcelLocker"],
                    "unproven_events": ["Delivered-ParcelLocker"] } ] } ],
  "gates": { "order_lifecycle": { "gate_b_answered": true,
                                  "gate_c": "send-as-is",
                                  "extras": {} } },
  "approvals": { "products_approved_at": "…", "intake_completed_at": "…" }
}
```

`validate_manifest.py` (stdlib, in `plugins/pl-tools/scripts/`, unit-tested)
fails loudly before Phase 1 if: fewer than 4 core products; any selected image
unverified; `shopify.enabled` without store/location or without ≥2-variant
coverage on the Shopify set; any order with no shipments, any shipment with no
events, or an event outside the proven set (`InTransit`, `OutForDelivery`,
`Delivered`, `WarehouseDelay`) not listed in that shipment's
`unproven_events`; missing account confirmation or gate answers.

## Sub-skill contracts ("Orchestrated runs" sections)

Each of the four sub-skills gains one **additive** section defining what a
complete manifest replaces. No existing step changes; without a manifest the
skills behave exactly as today.

| Skill | Runs as | Manifest replaces | Unchanged |
|---|---|---|---|
| `demo-request` | background agent | Steps 1–5 (browse/collect/validate), Step 6 approval | Steps 7–8 submit + report |
| `shopify-seed` | background agent | Step 1 store resolution + Step 2 location (done at intake), Step 3 collection, Step 5 approval | Steps 0, 4, 6–9 |
| `branded-template` | main session | Step 1b account, Steps 2–6 scraping (via `brand_tokens`) | Steps 7–10 incl. preview checkpoint, publish, 9b assignment |
| `order-lifecycle` | main session | Gates A/B/C (answered from `gates` + `orders[]`), product sourcing | Payload rules, driver, split-shipment rules, reporting, failure lore |

The manifest's approval timestamps are the user's answers to those gates —
explicit choices recorded at intake, not inference. `bug-investigation` and
`create-order` are not orchestrated (`order-lifecycle` builds its own orders).

## Error handling

- **Lane isolation:** CDC failure blocks nothing. Shopify failure blocks
  nothing (flagged loudly when `shopify.enabled` — it was the point of the
  opp). Template publish failure blocks **only** Phase 2, with the three-way
  offer above. One order's failure never stops another order's driver.
- **Fallback to B:** any failed/gapped agent lane can be re-run inline in the
  main session from the same manifest, at the user's choice. The conductor
  states what failed, what the agent reported, and what continuing means.
- **No silent continuation:** every lane ends in a written result file or a
  reported failure. Beat 1 lists any lane still outstanding.
- **Write safety:** all parcelLab-account writes (layout, orders) run in the
  main session under the intake's confirmed account + verified edit-mode
  guard. Agents touch only the CDC API (its own token) and the Shopify dev
  store (its own CLI auth, store confirmed by name at intake).

## Testing

- **Unit (stdlib `unittest`, no pytest):** `validate_manifest.py` — the rules
  above, plus round-trip of the sketch manifest. Run with the existing
  harness: `cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v`.
- **Live, staged:** (1) no-Shopify, single happy-path order, end-to-end on
  account 1626718 against a real brand; (2) full canonical run — two orders +
  Shopify + CDC config selection. Beat 2's verification is the pass/fail.
- **Standalone regression:** the four sub-skill edits are additive-only;
  confirmed by diff review and the next normal standalone use of each skill.

## Naming, docs, repo mechanics

- Skill `demo-environment`; description spells out **parcelLab** and triggers
  on e.g. *"build a parcelLab demo environment for [brand]"*, *"set up the
  full demo for [prospect]"*, *"run the whole demo build"*. `argument-hint:
  <prospect-url>`.
- README gains the skill row; `/pl-setup` gains the two optional
  `CDC_ACCOUNT_CONFIG_*` values (documented as "from the CDC UI, optional").
- No pl-tools version field (SHA-versioned); no marketplace change. All work
  on `feat/demo-environment`.

## Open items

1. ~~CDC account-config endpoints~~ **Resolved 2026-08-10** by the canonical
   [Automation API Reference](https://app.notion.com/p/parcellab/Automation-API-Reference-3b8c37dcb4c481789aa8c5e80fcfc730):
   configs are UUID-selected only (no list/create/update endpoints), and
   **omitting `selected_account_config_id` uses the caller's default config**
   — so the env-var design above degrades to the default, not to "no config".
   The same doc adds fields this spec predates: `generate_orders` (default
   true), `order_types` (subset of `fraud_high|fraud_medium|fraud_low|
   manual_return|return_tracking`), `linked_orders` (attach pre-existing
   parcelLab orders at creation time; token auth allows this **only** on the
   creation call), `products[].category_override`, and 500-still-creates-the-
   request semantics. `demo-request/references/api-payload.md` is stale
   against it and needs refreshing during implementation.
2. **OPEN DESIGN FORK — CDC orders vs lifecycle orders** (decide at resume):
   should the demo request (a) keep generating synthetic CDC orders
   concurrently in Phase 1 as specced, (b) always submit after Phase 2 and
   `linked_orders` our lifecycle orders so the demo page features the orders
   that actually move during the demo, or (c) let intake choose per run
   (linking chosen → CDC submit shifts after Phase 2; else concurrent)?
   Leaning (c). Prerequisite question for Max: which landing-page slot each
   `order_type` drives in CDC v2, i.e. which type a linked tracking/engage
   order should claim.
3. **The two `CDC_ACCOUNT_CONFIG_*` UUIDs** need collecting from the CDC UI
   once, then storing via `/pl-setup` (possibly only the non-default one,
   given the caller-default behaviour above).
4. **`Delivered-ParcelLocker`** (and any other locker-style status) is
   unproven; first successful live run should be recorded in
   `order-lifecycle`'s `references/status-codes.md`.

## Out of scope

- Creating or editing CDC account configurations (UI-only today).
- `bug-investigation` (not a demo-build skill) and direct `create-order`
  orchestration (orders are `order-lifecycle`'s job).
- Journey/trigger configuration changes in the parcelLab account — the run
  assumes the account's Journey setup exists (standard delivery-notification
  set on 1626718).
- Login-gated prospect sites (Browser pane runs a fresh context; same rule as
  the sub-skills).
