---
name: demo-environment
description: Build a complete parcelLab customer demo environment from one intake interview — branded email template, 1–5 realistic orders with fraud-risk data walking through good and bad delivery journeys, optional Shopify dev-store build over the real parcelLab integration, and a CDC demo request linking the real orders. Trigger on phrases like "build a parcelLab demo environment for [brand]", "set up the full demo for [prospect]", "run the whole demo build", "prep the demo environment for [brand]". Orchestrates the branded-template, shopify-seed, order-lifecycle and demo-request skills; requires the parcellab CLI, the Browser pane, and (for Shopify opps) the Shopify CLI.
argument-hint: <prospect-url>
---

# parcelLab — Unified Demo Environment Builder

One interview, a background scrape lane, and at most one template
checkpoint (none when a repeat brand's layout verifies live) → a complete demo:
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

## Write permissions — settle these BEFORE the gate

A run is read-only until the ✋ gate, then fires a dense burst of writes. If write
permissions are not settled first, the run stalls at its first write with the
environment half-built and the operator answering prompts one at a time.

**Check during Phase 0 step 4**, in the same round that verifies `edit-mode` —
it is the natural place, and it is still cheap to fix there. Read the user's
`~/.claude/settings.json`; if `permissions.allow` does not cover the writes
below, say so at the gate and let the user add them (they must edit that file
themselves — an agent cannot widen its own permissions, and any attempt is
correctly refused).

| Write | Rule |
|---|---|
| Push the layout | `mcp__<parcellab-mcp-server>__journey_write_layout` |
| Publish the layout | `Bash(parcellab --env prod journey layout publish *)` |
| Shopify seed + orders | `Bash(shopify store execute *)` |

`<parcellab-mcp-server>` is **per-install** — the parcelLab connector registers
under a different id for every user, so these rules cannot be copied between
teammates verbatim. Resolve it by reading the name of any parcelLab MCP tool
available in the session (the segment between `mcp__` and the tool name) and
substitute it before offering the snippet.

Order creation and the CDC submit run through scripts, not these tools, and are
covered by whatever Bash rules the user already has. Do not propose
`Bash(parcellab *)`: `pl-setup` installs a `PreToolUse` hook that auto-approves
read-only `parcellab` commands and refuses every write verb, and a blanket rule
would retire that distinction.

## The run page

Every run keeps one progress artifact — see
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md` for
the states and skeleton. Publish state 1 right after creating the run dir;
republish at each numbered state; keep the URL the first publish returns and
carry it into `run.page_url` when step 8 writes the manifest. Values the run
dir does not yet carry (path, account name) render as `—` and fill in at the
next republish. Publishing is never load-bearing.

## Phase 0 — Intake (front-loaded)

1. **Create the run directory** `$HOME/parcellab-demo-runs/<handle>-<ts>/`
   (handle derived from the prospect URL exactly as shopify-seed Step 3
   derives `prospect_handle`; ts = YYYYMMDD-HHMM). Create `results/`,
   `orders/` and `scrape/` inside it. Update `run-page.html` (state 1 per
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
   and republish — non-fatal.
2. **Path + brand round:** take the prospect URL and ask ONLY the path
   questions (returns in scope? · Shopify opp? — per *Paths*) plus, when one
   applies, the reuse offer below — the minimum needed to know what to
   collect, and everything that has to be settled before the scrape agent is
   dispatched.
   **Prior-pool detection:** scan `$HOME/parcellab-demo-runs/` for a
   directory whose `<handle>-<ts>` handle equals this run's handle and which
   contains both `scrape/brand-tokens.json` and `scrape/product-pool.json`;
   the most recent such run is the candidate. If one exists, offer it in this
   same round ("reuse the pool scraped for <brand> on <date>, or scrape
   fresh?"). No candidate → no offer, and step 3 dispatches as normal.
3. **Dispatch the scrape agent immediately.** Use the Agent tool
   (general-purpose subagent, background) with exactly this brief, filling
   the placeholders. **Resolve `${CLAUDE_PLUGIN_ROOT}` to its absolute path
   and paste the three real file paths into the dispatched brief** — a
   subagent does not reliably inherit that variable, and an unexpanded one
   hands it three unusable paths:

   > Execute the demo-environment scrape pass for the run directory
   > `<run dir>`, prospect `<url>`, path `<engage|retain|retain-shopify>`.
   > Follow `${CLAUDE_PLUGIN_ROOT}/skills/branded-template/SKILL.md` Steps
   > 3–6 for brand tokens (write the full `__BRAND_X__` token map + logo +
   > hero to `<run dir>/scrape/brand-tokens.json`) and
   > `${CLAUDE_PLUGIN_ROOT}/skills/shopify-seed/references/product-scrape.md`
   > for the product pool (≥8 candidates in the superset shape
   > `{id, name, product_type, price, options, image_url, pdp_url, sku}`;
   > variant axes required only on retain-shopify — elsewhere capture what
   > the PDP shows without extra navigation; write to
   > `<run dir>/scrape/product-pool.json`). Validate every candidate image
   > by running
   > `node ${CLAUDE_PLUGIN_ROOT}/skills/demo-request/scripts/check_images.mjs`
   > over the whole pool (accepts 1–N products; 200 + image/*, ranged-GET
   > retry) and set `image_verified` per product from its per-product `ok`
   > flags. Ground rules, non-negotiable: never ask the user anything — a
   > gap is a failure report; decline non-essential cookies; when done (or
   > failed) write `<run dir>/results/scrape.json` as
   > `{"status": "ok"|"failed", "error": null|"<why>"}` and return a
   > one-paragraph summary.

   **Browser pane ownership:** the agent owns the pane from dispatch until
   `results/scrape.json` exists. Do not navigate the pane in that window —
   the ★ template preview naturally starts after it, since it needs the
   scraped tokens. **Reused pool:** when the user accepted the reuse offer
   made in step 2, skip the dispatch entirely — copy the prior run's
   `scrape/brand-tokens.json` and `scrape/product-pool.json` into this run's
   `scrape/`, then write `results/scrape.json` yourself as
   `{"status": "ok", "error": null}`. Without that file the pre-build at
   step 6 waits on a precondition nothing else will ever satisfy. Once
   `results/scrape.json` shows
   `ok`: Update `run-page.html` (state 2 per
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
   and republish — non-fatal.
4. **Interview concurrently, in chat** (batch with AskUserQuestion where
   possible) — the remaining rounds, while the scrape agent runs:
   - destination country — **never assume it**
   - order plan: how many orders (1–5, default 3), and per order a fraud
     level + scenario. Offer the default matrix first: #1 low/happy,
     #2 medium/split (A happy, B stuck-delay), #3 high/recovered. On
     retain paths offer #4 manual_return and #5 return_tracking (both
     happy → Delivered). Scenario vocabulary: happy · stuck-delay ·
     recovered (`InTransit → WarehouseDelay → OutForDelivery → Delivered`,
     proven live 2026-08-11 — no unproven label) · locker (`… → Delivered-ParcelLocker`, label:
     status unproven) · custom (user-specified sequence, label per
     order-lifecycle's confidence rules). Runs of 2+ orders need at least
     one split-shipment order. Every order gets a distinct synthetic
     customer (region-appropriate name + email) — generate and show them.
   - **pace:** `standard` (180 s gaps, comm-ordering safe — the default) or
     `fast` (60 s gaps, comms may arrive out of order — say so when
     offering it). Record as the manifest's `run.pace`.
   - CDC region (US|UK|DE) and category (Home|Electronics|Fashion) —
     inferred from the site later, confirmed at the approval gate.
   - **Shopify resolution (retain-shopify only):** First `command -v shopify` — if the CLI is missing, stop and point the user at `/pl-setup`'s optional Shopify CLI section (install + full-scope store auth) rather than improvising an install mid-intake; the auth must carry the order/fulfilment scopes or the order engine hits a re-consent wall later. Confirm the dev store by
     name from `~/.claude/parcellab-shopify-seed.env` (else
     `shopify store auth list`), then resolve the location GID immediately —
     follow shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
     preference rules. Record both in the manifest.
   - **Target account + confirmation (every run):** the demo's target is a
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
     same account, offering the fix if not. **If the guard was repointed for
     this run** (e.g. at parcelfashion), note it — Beat 1 offers to restore it
     to the user's own account. In the same round, check write permissions per
     *Write permissions* above — a missing rule is cheap to fix here and stalls
     the run mid-build if it surfaces after the gate.
   - **CDC config:** read the key matching the target (process env, then
     `~/.claude/parcellab-demo-request.env`): own account →
     `CDC_ACCOUNT_CONFIG_DEFAULT` · parcelfashion →
     `CDC_ACCOUNT_CONFIG_PARCELFASHION` · retain-shopify →
     `CDC_ACCOUNT_CONFIG_SHOPIFY`. **The value is a UUID** — the API rejects a
     bare parcelLab account id with 400 "invalid input syntax for type uuid"
     (live-verified 2026-08-11). **The practical default needs no key at all:**
     when the user's CDC default config targets their own demo account (set in
     the CDC UI), omitting the field links correctly — that combination worked
     on both live runs. **First-run capture:** if the needed key is missing,
     ask once for the config UUID if the user has one (it is an id, not a
     credential), offer to append it to `~/.claude/parcellab-demo-request.env`,
     and proceed. If they don't:
     `selected_account_config_id: null`, `config_source: "none"` (the CDC will
     use the caller's default — say so in the final report, and note linking
     then resolves in whatever account that default config targets).
     `config_source` values: `default | parcelfashion | shopify | none`.
     `generate_orders` is **false** unless the user asks the CDC to also
     generate synthetic orders alongside the run's real ones — in that case
     compose `cdc.orders` (`{name?, items?: [{product_index, quantity?}]}`,
     0-based into the submitted products; the API has no order-type enum, only
     free-form names). When `linked_orders` will be sent, the config matters:
     the CDC resolves linked order numbers in the config's target account, so
     a mismatched config fails linking with "No parcelLab order found"
     (live-verified 2026-08-11).
5. **Repeat-brand template shortcut:** look for an existing layout for this
   brand on the target account and, if one verifies live, offer to skip the
   template lane.
   - **Find it:**
     `parcellab --env prod journey layout list --account <account.id> --all -o json --jmes 'results[].{id:id,name:prettyName,auto:autoLayout}'`.
     **Match rule:** a layout whose `prettyName`, lowercased with punctuation
     and whitespace stripped, contains the brand name or the run's `<handle>`
     similarly normalised. No match → no shortcut. Several matches → offer the
     most recently created one, or run the template lane normally if the user
     is unsure. Never guess an id.
   - **Verify it:** `parcellab --env prod journey layout show <id> -o json`
     must show `releaseStatus: published` AND an `autoLayout` entry whose
     `client` is the store this path's orders will land on. Anything less →
     no shortcut.
   - **If the user accepts,** write `results/branded-template.json` with
     exactly the four keys branded-template's orchestrated contract defines.
     **The CLI's field names are not those keys — copy the values across, do
     not paste the CLI's shape:**
     `layout_id` ← the response's `id` · `release_status` ← the value of
     `releaseStatus` (the publish gate reads `"release_status": "published"`;
     a verbatim `releaseStatus` key leaves `release_status` absent and stalls
     the gate on every order) · `store_assignment` ← the name of the store
     behind the matching `autoLayout` entry's `client` id (resolve it with
     `parcellab --env prod config client list --account <account.id> -o json`)
     · `account` ← the manifest's `account.id`. Add
     `"note": "template lane skipped — verified live at intake"`. Then skip
     the ★ checkpoint; Phase 1 has no template work.
6. **Pre-build everything sendable**, once the interview and
   `results/scrape.json` (status ok) are both in:
   - **The template HTML** from the tokens — branded-template Step 7, build
     only, no push, written to Step 7's own canonical path
     `$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html`
     (that path, not the run dir: Step 8's preview server serves from there
     and cannot read `~/Documents`). Skip when the repeat-brand shortcut was
     taken.
   - **The fraud fragment** for every order, on every path — it depends on
     nothing the engines produce.
   - **Direct engine only** (engage and retain paths): every order's
     `create.json` + `track.json` + `NN-<status>.json` event files
     (order-lifecycle's payload rules verbatim, no POSTs and no PUTs).
     **Never pre-build these on retain-shopify.** That path's tracking number
     is assigned by Shopify at `fulfillmentCreate` time and its `courier` must
     be read back out of the live pL order-info response (shopify-order-engine
     Parts 5b and 6b — live run: Shopify company `DPD` → pL courier `dpd`, not
     the `dpd-uk` the direct engine uses). Both values are fields in the event
     files, so anything built now would carry a locally invented tracking
     number and a guessed courier, and every event would push at a tracking
     that does not exist. On retain-shopify these files are built fresh at
     6c, after the read-back.
   - **The proposed plan** itself.
   **Scrape failure fallback:** if `results/scrape.json` says `failed` (or
   the agent dies), run the browser pass inline now — brand tokens, product
   pool, image validation, exactly as the scrape brief specifies — and carry
   on. The agent is an accelerator, never load-bearing.
7. **Propose the plan** and gate on approval (✋ — the intake's one gate;
   one yes releases the sends, and nothing before this step has *sent
   anything to* parcelLab, Shopify or the CDC — the only prior calls are
   read-only lookups plus the edit-mode guard):
   core 4 (four distinct product types) · per-order product distribution ·
   (retain-shopify) the seed set = core 4 + extras at distinct price points ·
   the order/scenario/fraud matrix with expected comm per event (mark
   unproven items) · CDC region/category/config source · CDC synthetic
   generation on/off (+ which slots) · the account by name. One explicit yes
   covers all of it; any tweak loops back here. When the gate opens: Update
   `run-page.html` (state 3 per
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
   and republish — non-fatal. Once approved: Update `run-page.html` (state 4
   per `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
   and republish — non-fatal.
8. **Write the manifest** to `demo-manifest.json` (schema:
   `run{…, pace: "standard"|"fast" — absent means standard, page_url —
   recorded after the first run-page publish}`, `path`,
   `brand{name,url,handle,region,category}`, `account{id,name,confirmed_at,
   edit_mode_verified}`, `cdc{selected_account_config_id,config_source,
   generate_orders,orders}`, `shopify{enabled,store?,location_id?}`,
   `destination_country`, `products[]`, `selection{core4,shopify_extra}`,
   `brand_tokens{tokens,logo,hero}`, `orders[]` with per-order
   `{label,dir,cdc_slot,fraud_level,customer{name,email},products,
   shipments[{label,scenario,courier,products,events,unproven_events?,
   unproven_chain?}]}`, `gates{order_lifecycle{gate_b_answered,gate_c,
   extras}}`, `approvals{products_approved_at,intake_completed_at}`).
   On retain-shopify also write `seed/seed-products.json`
   (`{products: core4 ∪ shopify_extra in scrape shape, location_id,
   prospect_handle}`). The scrape lane's raw output stays on disk under the
   run dir's `scrape/` (`brand-tokens.json`, `product-pool.json`) with its
   outcome in `results/scrape.json`; the manifest carries the selected
   subset.
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

**Store assignment is reassigned, never negotiated.** branded-template Step 9b
asks which store should use the template when an account has several, and 9b.3
treats another layout's `country: []` entry for that store as stale. On an
orchestrated run neither is a question: the path already determines the store
(retain-shopify → the Shopify-integrated client; otherwise the account's
default), and a prior brand's mapping on that store is always cleared in favour
of this run's layout. A store can hold only one default auto-template, so the
two are mutually exclusive and leaving the old one means every comm in this run
goes out under the previous brand. Say in Beat 1 which layout lost the mapping,
so the change is visible and reversible.

**Then run branded-template inline** (main session): invoke the
pl-tools:branded-template skill; its "Orchestrated runs (demo-environment)"
contract consumes the manifest's `brand_tokens` and account, and reuses the
HTML pre-built at Phase 0 step 6 at Step 7's own path
`$HOME/parcellab-previews/{brand-name-lowercase}-parcellab-layout.html`
rather than building it again. Its Step 8 preview question is ★ the run's one
checkpoint — wait for the user there as that skill specifies. It finishes by
writing `results/branded-template.json`.

**Unless the repeat-brand shortcut was taken** at Phase 0 step 5 — then
`results/branded-template.json` already exists from the live-verified
layout, this lane has no work, and the publish gate below reads that same
file.

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
order-lifecycle's "Orchestrated runs (demo-environment)" contract. Steps 1–3
were pre-built at Phase 0 step 6 on this engine's paths — reuse those files as
they stand; rebuild only if the approved plan changed at the gate. (The
Shopify engine below shares only steps 3–4's *shape*, never these pre-built
files.)

1. Fraud fragment: run `prepare_fraud_fragment.py` for the order's level and
   merge `tags` + `additional_attributes` into `create.json`.
2. Build `create.json` + the single PUT with all `add_tracking` mutations
   (order-lifecycle's payload rules verbatim: randomised format-correct
   tracking numbers, courier per shipment, `tracking.articles` mirrored,
   split rules for 2-shipment orders).
3. Write the `NN-<status>.json` event files from the shipment's `events`.
4. `DRYRUN=1` pass; then launch `run-lifecycle.sh` detached
   (`run_in_background`) — one driver per order, all orders concurrent.
   `GAP_SECONDS` comes from the manifest's `run.pace`: 180 for standard (the
   default), 60 for fast. When pace is fast, Beat 2's report must note that
   comm ordering was not guaranteed at this pace. Pass `PARCELLAB_ACCOUNT_ID=<manifest account.id>`
   inline on every launch: `create.json`'s `account` field and the driver's
   account both come from the manifest, never from the ambient
   `$PARCELLAB_ACCOUNT_ID`, which may point at a different account than the
   one confirmed at intake. Once drivers are launched: Update
   `run-page.html` (state 5 per
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`)
   and republish — non-fatal.
5. Write `order.json` per the contract.

When every order's `order.json` exists, build
`results/linked-orders.json`: every order with a non-null `cdc_slot` becomes
`{"order_number": <order.json order_number>, "name": <human label>}` — the
label derived from the slot (`fraud_low` → "Fraud risk: low", `manual_return`
→ "Manual return", `return_tracking` → "Return tracking"); `cdc_slot` itself
never goes to the API (its enum was removed 2026-08-11).
An order whose creation failed is excluded (and reported); one order's
failure never stops another's driver.

## Phase 2 — Orders (Shopify engine: retain-shopify path)

Gate: publish gate passed AND `results/shopify-seed.json` status ok.
For each manifest order, in its `orders/<nn>-<label>/` directory, follow
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/shopify-order-engine.md`:
create the order in Shopify (line items = the order's `products` mapped to
seeded variant gids) → poll pL ingestion → enrich with the fraud fragment →
fulfil per shipment with tracking → poll the pL tracking → build the
`NN-<status>.json` files and launch the driver, following the same rules as
the direct engine's steps 3–4 — but **the event files are always written
fresh at Part 6c, never reused from Phase 0**: only after 6b has read the
`courier` back out of the live order-info response are the file's `courier`
and `tracking_number` knowable at all. This includes that `GAP_SECONDS` comes from the manifest's
`run.pace`: 180 for standard (the default), 60 for fast. When pace is fast,
Beat 2's report must note that comm ordering was not guaranteed at this
pace. Once drivers are launched: Update `run-page.html` (state 5 per
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`) and
republish — non-fatal. Then write `order.json` (order_number = the Shopify
order name, e.g. "#1001") and, once all orders are processed, build
`results/linked-orders.json` the same way as the direct engine.

Per-order failure isolation: ingestion timeout, enrichment failure or
fulfilment failure marks THAT order partial in `order.json`
(`"status": "partial", "failed_at": "<step>"`) — its events are not pushed,
other orders continue, and the report says exactly which step failed.

## Phase 3 — The one CDC call

Exactly one CDC interaction per run, after Phase 2 — with a `cdc_live_`
token, linking existing orders is only possible on the creation call.
Invoke the pl-tools:demo-request skill's "Orchestrated runs
(demo-environment)" contract against the run dir: it builds the payload
from the manifest + `results/linked-orders.json` and submits once. Do not
retry a 500 (the request already exists — the results file records it).

## Phase 4 — Report

**Beat 1 — environment built** (immediately after Phase 3): layout id +
release status + store assignment (+ any 9b country-override warning,
repeated verbatim) · per order: number, customer, fraud level, slot,
courier(s) + tracking number(s), scenario, and the expected comm per event
with confidence labels · (retain-shopify) the seed table + demos +
adjustments from `results/shopify-seed.json` · CDC request id/URL, which
orders were submitted for linking, the config source (say "caller's default
config" when `config_source` is `none`), and `generate_orders`/`orders`
(say plainly whether the CDC was also asked to generate synthetic orders,
and for which slots). No currency symbols. **If the edit-mode guard was
repointed for this run** (per Phase 0 step 4's note), offer here to restore
it to the user's own account. Once Beat 1 is posted: Update `run-page.html`
(state 6 per
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`) and
republish — non-fatal.

**Beat 2 — verified** (after each order's driver finishes AND ≥5 minutes
after its final event — comms lag, delivered comms the longest): per order,
public order-info lookup by courier + tracking_number; report checkpoints
attached vs planned and `contacted_with_messages` vs the expected comms —
explicitly covering the good AND bad arcs the run promised. For every
unproven event or chain that fired correctly, offer to record it in
`${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md`.
Once Beat 2 is posted: Update `run-page.html` (state 7 per
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`) and
republish — non-fatal.

## Failure handling

| Lane fails | Blocks | Response |
|---|---|---|
| scrape agent | nothing | run the browser pass inline (Phase 0 step 6's fallback) |
| seed agent | Shopify orders only | report, offer inline re-run from the same manifest |
| template publish | Phase 2 (all orders) | the three-way publish-gate offer |
| one order (any engine) | nothing else | mark partial in its order.json; report the exact step |
| CDC call | nothing | report; 500 = request exists, retry manually in-app |

On any failure above: Update `run-page.html` (state 8 per
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md`) and
republish — non-fatal.

Fallback rule (Approach B): any agent lane can be re-run inline in the main
session from the same manifest — the brief and the contract are identical.
Never silently continue past a failed lane; every lane ends in a results
file or a reported failure, and Beat 1 lists any lane still outstanding.
