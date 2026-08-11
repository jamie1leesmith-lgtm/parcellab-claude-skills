---
name: demo-environment
description: Build a complete parcelLab customer demo environment from one intake interview — branded email template, 1–5 realistic orders with fraud-risk data walking through good and bad delivery journeys, optional Shopify dev-store build over the real parcelLab integration, and a CDC demo request linking the real orders. Trigger on phrases like "build a parcelLab demo environment for [brand]", "set up the full demo for [prospect]", "run the whole demo build", "prep the demo environment for [brand]". Orchestrates the branded-template, shopify-seed, order-lifecycle and demo-request skills; requires the parcellab CLI, the Browser pane, and (for Shopify opps) the Shopify CLI.
argument-hint: <prospect-url>
---

# parcelLab — Unified Demo Environment Builder

One interview, one browser pass, one template checkpoint → a complete demo:
published branded layout, 1–5 fraud-tagged orders running their journeys,
(if Shopify) a seeded dev store with real orders on the real integration,
and one CDC demo request linking those orders.

Read `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/flows.md` if
you need the phase/gate picture; the four sub-skills' own SKILL.md files are
the single source of truth for their mechanics — this skill only prepares
their answers and sequences them (each has an "Orchestrated runs" section
defining its contract).

## Paths

Ask **"Are returns in scope for this demo?"** first.
- No → **engage** path.
- Yes → ask **"Is this a Shopify opp?"** → no → **retain** · yes →
  **retain-shopify**. An Engage-only run never asks the Shopify question;
  Retain covers the Engage story automatically.

## Phase 0 — Intake

1. **Create the run directory** `$HOME/parcellab-demo-runs/<handle>-<ts>/`
   (handle derived from the prospect URL exactly as shopify-seed Step 3
   derives `prospect_handle`; ts = YYYYMMDD-HHMM). Create `results/` and
   `orders/` inside it.
2. **Interview** (batch with AskUserQuestion where possible; one round for
   path + country + order count, a second for the order plan):
   - returns in scope? · Shopify opp? (per *Paths*)
   - destination country — **never assume it**
   - order plan: how many orders (1–5, default 3), and per order a fraud
     level + scenario. Offer the default matrix first: #1 low/happy,
     #2 medium/split (A happy, B stuck-delay), #3 high/recovered. On
     retain paths offer #4 manual_return and #5 return_tracking (both
     happy → Delivered). Scenario vocabulary: happy · stuck-delay ·
     recovered (`InTransit → WarehouseDelay → OutForDelivery → Delivered`,
     label: chain unproven) · locker (`… → Delivered-ParcelLocker`, label:
     status unproven) · custom (user-specified sequence, label per
     order-lifecycle's confidence rules). Runs of 2+ orders need at least
     one split-shipment order. Every order gets a distinct synthetic
     customer (region-appropriate name + email) — generate and show them.
   - CDC region (US|UK|DE) and category (Home|Electronics|Fashion) —
     inferred from the site later, confirmed at the approval gate.
3. **Shopify resolution (retain-shopify only):** confirm the dev store by
   name from `~/.claude/parcellab-shopify-seed.env` (else
   `shopify store auth list`), then resolve the location GID immediately —
   follow shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
   preference rules. Record both in the manifest.
4. **Target account + confirmation (every run):** the demo's target is a
   run-level choice — the user's own demo account
   (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`, the default) or the
   shared **parcelfashion** account (offer it only when
   `CDC_ACCOUNT_CONFIG_PARCELFASHION` is stored; on retain-shopify never
   offer it — the Shopify integration lives in the user's own account). The
   choice drives every pL write in the run AND the CDC config key (the CDC
   looks up linked orders in the config's target account, so they must
   agree). Then: `parcellab account account show <id>` for the human name;
   ask "Using **<name>** (<id>) — correct?"; verify
   `parcellab settings edit-mode show` says `account-restricted` for that
   same account, offering the fix if not.
5. **CDC config:** read the key matching the target (process env, then
   `~/.claude/parcellab-demo-request.env`): own account →
   `CDC_ACCOUNT_CONFIG_DEFAULT` · parcelfashion →
   `CDC_ACCOUNT_CONFIG_PARCELFASHION` · retain-shopify →
   `CDC_ACCOUNT_CONFIG_SHOPIFY`. **First-run capture:** if the needed key is
   missing, ask the user for the UUID once (it is visible in the CDC UI —
   there is no list API; it is an id, not a credential), offer to append it
   to `~/.claude/parcellab-demo-request.env`, and proceed. If they don't
   have it: `selected_account_config_id: null`, `config_source: "none"`
   (the CDC will use the caller's default — say so in the final report).
   `config_source` values: `default | parcelfashion | shopify | none`.
6. **One browser pass** (the run's only browsing):
   - Brand tokens: run branded-template's Step 3–6 extraction snippets
     (`${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md`) and build
     the full `__BRAND_X__` token map + logo + hero.
   - Product pool: collect ≥8 PDP candidates in the superset shape
     (`{id, name, product_type, price, options, image_url, pdp_url, sku}`)
     following `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
     — variant axes are required only on retain-shopify; elsewhere capture
     what the PDP shows without extra navigation.
   - Validate every candidate image:
     `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
     semantics (200 + image/*; ranged-GET retry). Mark `image_verified`.
7. **Propose the plan** and gate on approval (✋ — the intake's one gate):
   core 4 (four distinct product types) · per-order product distribution ·
   (retain-shopify) the seed set = core 4 + extras at distinct price points ·
   the order/scenario/fraud matrix with expected comm per event (mark
   unproven items) · CDC region/category/config source · the account by
   name. One explicit yes covers all of it; any tweak loops back here.
8. **Write the manifest** to `demo-manifest.json` (schema: `run`, `path`,
   `brand{name,url,handle,region,category}`, `account{id,name,confirmed_at,
   edit_mode_verified}`, `cdc{selected_account_config_id,config_source,
   generate_orders,order_types}`, `shopify{enabled,store?,location_id?}`,
   `destination_country`, `products[]`, `selection{core4,shopify_extra}`,
   `brand_tokens{tokens,logo,hero}`, `orders[]` with per-order
   `{label,dir,cdc_slot,fraud_level,customer{name,email},products,
   shipments[{label,scenario,courier,products,events,unproven_events?,
   unproven_chain?}]}`, `gates{order_lifecycle{gate_b_answered,gate_c,
   extras}}`, `approvals{products_approved_at,intake_completed_at}`).
   On retain-shopify also write `seed/seed-products.json`
   (`{products: core4 ∪ shopify_extra in scrape shape, location_id,
   prospect_handle}`).
9. **Validate:**
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`
   — on `MANIFEST INVALID`, fix the named gaps (re-asking if needed) and
   re-validate. **Never start Phase 1 on an invalid manifest.**

## Phase 1 — Template ∥ seed

**Dispatch the seed agent first (retain-shopify only)**, so it runs while
you build the template. Use the Agent tool (general-purpose subagent,
background) with exactly this brief, filling the placeholders:

> Invoke the pl-tools:shopify-seed skill and execute its "Orchestrated runs
> (demo-environment)" contract for the run directory `<run dir>`. The
> manifest and `seed/seed-products.json` are already there. Ground rules,
> non-negotiable: never open the Browser pane; never ask the user anything —
> a gap is a failure report; write your outcome to
> `<run dir>/results/shopify-seed.json` exactly as the contract specifies,
> and return a one-paragraph summary plus the product/demo tables.

**Then run branded-template inline** (main session): invoke the
pl-tools:branded-template skill; its "Orchestrated runs (demo-environment)"
contract consumes the manifest's `brand_tokens` and account. Its Step 8
preview question is ★ the run's one checkpoint — wait for the user there as
that skill specifies. It finishes by writing
`results/branded-template.json`.

## The publish gate

Phase 2 must not start until `results/branded-template.json` shows
`"release_status": "published"` — order creation fires the
order-confirmation comm immediately on every path, and an unpublished
template means that first email goes out unbranded. If it says
`not published`, offer exactly three ways forward and wait:
1. fix and re-publish (follow branded-template Step 9a's failure table);
2. the user publishes manually in the portal, then confirms here;
3. explicitly proceed accepting unbranded comms (record the choice in the
   report).

**retain-shopify additionally waits for the seed**: `results/shopify-seed.json`
must show `"status": "ok"` before Shopify orders are created (their line
items reference seeded variants). A failed seed lane stops only the order
stage of the Shopify path: report it, offer to re-run the seed inline from
the same manifest (the fallback), and leave every other lane alone.

## Phase 2 — Orders (direct engine: engage and retain paths)

For each manifest order, in its `orders/<nn>-<label>/` directory, follow
order-lifecycle's "Orchestrated runs (demo-environment)" contract:

1. Fraud fragment: run `prepare_fraud_fragment.py` for the order's level and
   merge `tags` + `additional_attributes` into `create.json`.
2. Build `create.json` + the single PUT with all `add_tracking` mutations
   (order-lifecycle's payload rules verbatim: randomised format-correct
   tracking numbers, courier per shipment, `tracking.articles` mirrored,
   split rules for 2-shipment orders).
3. Write the `NN-<status>.json` event files from the shipment's `events`.
4. `DRYRUN=1` pass; then launch `run-lifecycle.sh` detached
   (`run_in_background`, `GAP_SECONDS` default 180) — one driver per order,
   all orders concurrent.
5. Write `order.json` per the contract.

When every order's `order.json` exists, build
`results/linked-orders.json`: every order with a non-null `cdc_slot` becomes
`{"order_number": <order.json order_number>, "order_type": <cdc_slot>}`.
An order whose creation failed is excluded (and reported); one order's
failure never stops another's driver.

## Phase 2 — Orders (Shopify engine: retain-shopify path)

Gate: publish gate passed AND `results/shopify-seed.json` status ok.
For each manifest order, in its `orders/<nn>-<label>/` directory, follow
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/shopify-order-engine.md`:
create the order in Shopify (line items = the order's `products` mapped to
seeded variant gids) → poll pL ingestion → enrich with the fraud fragment →
fulfil per shipment with tracking → poll the pL tracking → build the
`NN-<status>.json` files and launch the driver, exactly as the direct
engine's steps 3–4. Then write `order.json` (order_number = the Shopify
order name, e.g. "#1001") and, once all orders are processed, build
`results/linked-orders.json` the same way as the direct engine.

Per-order failure isolation: ingestion timeout, enrichment failure or
fulfilment failure marks THAT order partial in `order.json`
(`"status": "partial", "failed_at": "<step>"`) — its events are not pushed,
other orders continue, and the report says exactly which step failed.
