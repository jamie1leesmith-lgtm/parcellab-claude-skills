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

## Timing marks — one line each, and the run is measurable

Durations are only ever the difference between two recorded stamps, so a phase
nobody marked is a phase nobody can measure. Call `run_state.mark()` at each
boundary below; each is one line beside work you are already doing, and each
is named again at the step where it happens.

| Boundary | Call |
|---|---|
| Dispatching an agent (scrape, seed) | `mark(d, "agent", "<name>", "start")` |
| Its results file lands | `mark(d, "agent", "<name>", "end")` |
| Starting a lane's own work | `mark(d, "lane", "<lane>", "start")` |
| That lane finishing | `mark(d, "lane", "<lane>", "end")` |
| Posing the ★ template question or the ✋ plan gate | `mark(d, "gate", "<template\|plan>", "asked")` |
| Recording the answer | `mark(d, "gate", "<template\|plan>", "answered")` |
| Posting Beat 1 | `mark(d, "gate", "beat1", "end")` |

Drivers are **not** marked — they stamp their own `run.log`, and three
concurrent drivers amending `run-state.json` would lose updates.

A missing mark yields a null, never a wrong number. Never reconstruct a mark
after the fact: a stamp written later records when you remembered, not when it
happened.

**A lane mark also moves that lane's status pill** on the run page — `start` →
running, `end` → ok. One call does both. When a lane ends as something richer
than ok, say so explicitly with `set_lane` and the mark will not flatten it:

| Lane outcome | Call |
|---|---|
| template published | `set_lane(d, "template", "published", layout_id=<id>, store="<name>")` |
| seed skipped (non-Shopify path) | `set_lane(d, "seed", "skipped")` |
| any lane failed | `set_lane(d, "<lane>", "failed")` (or `add_failure`) |

These two used to be independent, and only `mark` was documented — so every
run left all five pills on "pending" while the tests, which call `set_lane`
directly, stayed green (found 2026-08-12; Currys and UNIQLO show the mirror
image, correct pills and an empty timeline).

## The run page

Every run keeps one progress artifact — see
`${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/run-page.md` for
the states and skeleton. Publish state 1 right after creating the run dir;
republish at each numbered state; keep the URL the first publish returns and
carry it into `run.page_url` when step 7 writes the manifest. Values the run
dir does not yet carry (path, account name) render as `—` and fill in at the
next republish. Publishing is never load-bearing.

**Republishing includes recording it.** After each Artifact call, record it with
`run_state.record_publish(<run dir>, <the URL the call returned>)`. Renders
record themselves; publishes cannot, so an unrecorded publish is
indistinguishable from one that never happened — and telling those apart is
what the `Page publishes` / `Page renders` telemetry columns exist for. Passing
the returned URL is what lets `Page URL changes` show a reader stranded on a
URL that stopped updating.

## Phase 0 — Intake (front-loaded)

1. **Create the run directory** `$HOME/parcellab-demo-runs/<handle>-<ts>/`
   (handle derived from the prospect URL exactly as shopify-seed Step 3
   derives `prospect_handle`; ts = YYYYMMDD-HHMM). Create `results/`,
   `orders/` and `scrape/` inside it. Initialise run state:

   ```bash
   python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}/scripts'); \
   import run_state; run_state.init('<run dir>', '<run id>', '<path>', '<account name>')"
   ```

   then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_run_page.py <run dir>` and
   republish the artifact — non-fatal. Path and account are still unanswered
   here and render as `—`; they fill in at the next render.

   **Never hand-edit `run-page.html`.** It is derived from `run-state.json`, so
   an edit is overwritten by the next render. Record facts through
   `run_state.py` and re-render — that is what makes republishing cheap enough
   to do a dozen times per run.
2. **Path + brand round:** take the prospect URL and ask **Round 1** of
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/intake-script.md`
   — the path questions plus, when one applies, the reuse offer. Ask them in
   that file's order, with that file's wording. That is the minimum needed to
   know what to collect, and everything that has to be settled before the
   scrape agent is dispatched.
   **Prior-pool detection:** scan `$HOME/parcellab-demo-runs/` for a
   directory whose `<handle>-<ts>` handle equals this run's handle and which
   contains both `scrape/brand-tokens.json` and `scrape/product-pool.json`;
   the most recent such run is the candidate. If one exists, offer it in this
   same round ("reuse the pool scraped for <brand> on <date>, or scrape
   fresh?"). No candidate → no offer, and step 3 dispatches as normal.
3. **Dispatch the scrape agent immediately** — `mark(d, "agent", "scrape", "start")` and `mark(d, "lane", "scrape", "start")` as you dispatch. Use the Agent tool
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
   scraped tokens. **This binds more than deliberate navigation:** a
   `PostToolUse` hook can open a file in the pane as a side effect of a plain
   Write (observed 2026-08-11 — writing `run-page.html` took the pane while the
   scrape agent held it). Writing run files is unavoidable, so treat pane
   contention as expected rather than forbidden: if the pane is taken from the
   agent, do not also drive it, and re-check `results/scrape.json` rather than
   assuming the agent died. **Reused pool:** when the user accepted the reuse offer
   made in step 2, skip the dispatch entirely — copy the prior run's
   `scrape/brand-tokens.json` and `scrape/product-pool.json` into this run's
   `scrape/`, then write `results/scrape.json` yourself as
   `{"status": "ok", "error": null}`. Without that file the pre-build at
   step 6 waits on a precondition nothing else will ever satisfy. Once
   `results/scrape.json` shows
   `ok`: record the fact via `${CLAUDE_PLUGIN_ROOT}/scripts/run_state.py` — `mark(d, "agent", "scrape", "end")` the moment the file lands, plus `mark(d, "lane", "scrape", "end")` — then `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/render_run_page.py <run dir>` and republish the artifact — non-fatal. **Never hand-edit `run-page.html`;** it is derived, and the next render overwrites it.
4. **Interview concurrently, in chat** — ask **Round 2** of
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/intake-script.md`
   while the scrape agent runs, batching with AskUserQuestion where the
   questions are independent. Ask them in that file's order, with that file's
   wording; it also carries the default order matrix, the Gate C menu rules and
   the article-weight derivation table. The mechanics below are not questions —
   they are the lookups and verifications those answers depend on.
   - **Shopify resolution (retain-shopify only):** First `command -v shopify` —
     if the CLI is missing, stop and point the user at `/pl-setup`'s optional
     Shopify CLI section (install + full-scope store auth) rather than
     improvising an install mid-intake; the auth must carry the
     order/fulfilment scopes or the order engine hits a re-consent wall later.
     Then resolve the store **without asking**: read
     `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`.
     Exactly one store → use it and state it at the ✋ gate. None → stop and
     point at `/pl-setup`. Two or more → this is the only case that asks
     (intake-script Q14). Then resolve the location GID immediately — follow
     shopify-seed Steps 1–2 exactly, including the fulfils-online-orders
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
     this run** (e.g. at parcelfashion), note it — it is restored automatically
     after Beat 2, once the drivers have stopped pushing events against it. In
     the same round, check write permissions per
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
     `generate_orders` is always `false` and `cdc.orders` always `[]` — the run
     never asks the CDC to generate synthetic orders alongside its real ones,
     and the ✋ gate states this as a fixed line so it stays visible. The
     config still matters for linking: the CDC resolves linked order numbers in
     the config's target account, so a mismatched config fails linking with
     "No parcelLab order found" (live-verified 2026-08-11).
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
   - **The run's images, inlined** so the page can actually show them:
     `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/inline_assets.py <run dir>`. The
     artifact CSP blocks external requests, so a remote `<img src>` renders as
     a broken-image icon — this is what makes product shots, the brand logo and
     the hero visible on the run page at all.
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

   **Verify the page is not blank before you show it to anyone.** After
   `inline_assets.py`, `scrape/assets.json` must exist. `render_run_page.py`
   warns on stderr when `results/scrape.json` says ok and that file is missing;
   treat the warning as a stop. Both `_brand_header` and `_products` open with
   `if not assets: return ""`, so skipping the inline step renders an empty
   showcase that still publishes successfully — live 2026-08-12 the user
   approved a template against a page showing nothing at all.
7. **Write and validate the manifest — before either gate.** The manifest is
   the plan, so it has to exist before the page can render the plan. Write it
   per the schema in step 9 below, then validate it **with `--pre-gate`**:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py --pre-gate <run>/demo-manifest.json
   ```

   Fix any `MANIFEST INVALID` gaps now, while nothing has been asked or sent.

   `--pre-gate` defers exactly one check: `approvals.products_approved_at`,
   which cannot honestly exist until the ✋ gate stamps it. Write that field as
   `null` here — **never back-date it to make a validator pass**. Step 9
   re-validates without the flag once the yes arrives, and Phase 1 still
   demands a fully valid manifest.

   Validating here rather than after the gate means a schema error is caught
   before the user is asked to approve anything, instead of forcing an
   approve → validate → fix → re-approve loop.

   **This does not reveal the plan.** The run page shows the plan card only
   once `mark(d, "gate", "plan", "asked")` is in the timeline, so state 2b
   below still shows the template and swatches alone. Ordering is enforced by
   the timeline, not by which files happen to exist.
8. ★ **Show the template and get it approved — before anything else is
   proposed.** The HTML exists on disk from step 6, so serve it and put it in
   front of the user now: follow branded-template Step 8 (launch config →
   `preview_start` → navigate → screenshot), ask *"Does this look right before
   I push it to parcelLab?"* — `mark(d, "gate", "template", "asked")` as you
   ask, `"answered"` when they reply — and iterate on the file until they say yes. This
   is the run's first deliverable and it gates every comm the environment will
   send, so it is approved on its own, ahead of the plan.
   - **Re-render and republish the page before asking.** The template preview
     is rendered from
     `$HOME/parcellab-previews/{brand}-parcellab-layout.html`, which the
     renderer resolves from the manifest's brand or the run id's handle. Asking
     for approval against a page that does not show the thing being approved is
     the defect this ordering exists to prevent.
   - **Hold the run page here.** Publish a template-only state — the preview,
     the brand-token swatches, and nothing downstream. Do not show the plan,
     the order matrix or the seed set yet: putting detail on screen that the
     user cannot act on, before the first deliverable is even visible, is what
     made the 2026-08-11 smoke run confusing.
   - **Skip this step entirely when the repeat-brand shortcut was taken** at
     step 5 — the layout is already live and verified, so there is nothing to
     preview and `results/branded-template.json` already exists.
   - **Approval here covers the push.** Phase 1's branded-template run does not
     ask again; its own Step 8 checkpoint is already satisfied.
9. **Propose the plan** and gate on approval (✋ — the sends gate;
   one yes releases the sends, and nothing before this step has *sent
   anything to* parcelLab, Shopify or the CDC — the only prior calls are
   read-only lookups plus the edit-mode guard).

   **The plan is shown on the run page, not typed into the question.** Mark the
   gate asked, re-render, republish — that publishes the plan card, which
   renders every item below from the manifest written at step 7. Then ask in
   chat for a short approve-or-change, and link the page. A plan pasted into an
   AskUserQuestion option label is unreadable, and it was pasted there on
   2026-08-12 *because* the page could not render it — fixing the page is what
   makes the short question honest.

   The page's plan card covers:
   core 4 (four distinct product types) · per-order product distribution ·
   (retain-shopify) the seed set = core 4 + extras at distinct price points ·
   the order/scenario/fraud matrix with expected comm per event (mark
   unproven items) · CDC region/category/config source ·
   `CDC synthetic generation: off` (a fixed line, never a question) ·
   **every extra agreed at Q7, field by field with its actual value** —
   including each auto-derived article weight listed per article, because an
   auto-derived value the user never saw is worse than one they rejected ·
   the account by name. One explicit yes
   covers all of it; any tweak loops back here. When the gate opens: record it
   via `run_state.py` — `mark(d, "gate", "plan", "asked")` as you pose it, and
   again on every re-ask — re-render with `render_run_page.py <run dir>` and
   republish — non-fatal.

   **If the page failed to publish, the plan still has to be readable** — post
   it in chat as a markdown table then, and say the page is unavailable. The
   page being non-fatal never means the user approves something unseen.

   **Once approved**, do these four things before any build work starts:

   1. `mark(d, "gate", "plan", "answered")` at the moment the yes arrives —
      this is where `Duration to build` starts.
   2. Re-validate **without** `--pre-gate` (the approval stamp exists now):
      `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`.
   3. Re-render and republish — non-fatal.
   4. **Open the telemetry row.** Skip only when `PL_RUN_TELEMETRY_DB` is
      unset — check it, do not assume:

      ```bash
      python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_telemetry_row.py <run dir> committed \
        --skill-version "$(git -C ${CLAUDE_PLUGIN_ROOT}/../.. rev-parse --short HEAD)"
      ```

      Create the page in the telemetry database via the Notion connector,
      setting `Date` to today and `Ran by` to the current user, then write the
      returned page id to `results/telemetry.json` so Beats 1 and 2 update that
      same row. See
      `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/telemetry.md`.

      **`results/telemetry.json` existing is the proof this happened** — Beats
      1 and 2 both branch on that file, so skipping here silently disables
      telemetry for the whole run. Live 2026-08-12 the row was never opened
      despite `PL_RUN_TELEMETRY_DB` being set, and the omission only surfaced
      at Beat 2, when the row had to be back-filled from the timeline.

   This is the first outward-facing write of the run, and it happens only after
   the gate — never before.
   **The manifest schema** (written at step 7, above — kept here because this
   is where its fields were settled). `demo-manifest.json`:
   `run{…, pace: "standard"|"fast" — absent means standard, page_url —
   recorded after the first run-page publish}`, `path`,
   `brand{name,url,handle,region,category}`, `account{id,name,confirmed_at,
   edit_mode_verified}`, `cdc{selected_account_config_id,config_source,
   generate_orders,orders}`, `shopify{enabled,store?,location_id?}`,
   `destination_country`, `products[]` (each in scrape shape, carrying both its
   own `id` and `sku`), `selection{core4,shopify_extra}` — **these hold product
   `id` values, not SKUs, and so do every order's `products` and every
   shipment's `products`.** A product's `id` is its goods code (`E491096-000`);
   its `sku` is the variant (`E491096-000-57`). Payload files use SKUs for
   `line_item_id`; the manifest never does. `validate_manifest.py` rejects SKUs
   with `unknown product <sku>` — live 2026-08-11 that cost a full
   validate-fix-revalidate cycle because the rule existed only in the validator
   and nowhere a conductor would read first,
   `brand_tokens{tokens,logo,hero}`, `orders[]` with per-order
   `{label,dir,cdc_slot,fraud_level,customer{name,email},products,
   shipments[{label,scenario,courier,products,events,unproven_events?,
   unproven_chain?}]}`,
   `gates{order_lifecycle{gate_b_answered, gate_c: "send-as-is"|"extras",
   extras}}` — `extras` is empty when `gate_c` is `send-as-is`, and non-empty
   otherwise. Promise dates in `extras` are `YYYY-MM-DD` (a full ISO datetime
   is rejected by the API). `extras.article_weights` is keyed by product `id`,
   never SKU — the same rule as everywhere else in the manifest —
   `{<product id>: {weight: <number greater than 0>, weight_unit:
   "kg"|"g"|"lbs"|"oz"}}` — `weight_unit` is always written explicitly; a
   missing one is rejected.
   `validate_manifest.py` enforces all of this,
   `approvals{products_approved_at,intake_completed_at}` — the approval stamps
   are the one part written after their gates, since that is when they happen).
   On retain-shopify also write `seed/seed-products.json`
   (`{products: core4 ∪ shopify_extra in scrape shape, location_id,
   prospect_handle}`). The scrape lane's raw output stays on disk under the
   run dir's `scrape/` (`brand-tokens.json`, `product-pool.json`) with its
   outcome in `results/scrape.json`; the manifest carries the selected
   subset.

   **The validate command** (run at step 7, before the gates):
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/validate_manifest.py <run>/demo-manifest.json`
   — on `MANIFEST INVALID`, fix the named gaps (re-asking if needed) and
   re-validate. **Never start Phase 1 on an invalid manifest.**

## Phase 1 — Template ∥ seed

**Dispatch the seed agent first (retain-shopify only)**, so it runs while
you build the template — `mark(d, "agent", "seed", "start")` as you dispatch,
and `mark(d, "agent", "seed", "end")` when `results/shopify-seed.json` lands.
Open each lane's own work with `mark(d, "lane", "<template|seed>", "start")`
and close it with `"end"`. Use the Agent tool (general-purpose subagent,
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
rather than building it again. **Its Step 8 preview question is already
answered** — the ★ checkpoint ran at Phase 0 step 8, before the plan gate, and
the user approved that exact file. Do not ask again: go straight to Step 9's
push and publish. It finishes by writing `results/branded-template.json`.

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

   **Union, never replace.** When `gates.order_lifecycle.extras` also carries
   `tags` or `additional_attributes`, the order's value is the union of the
   intake's and the fragment's — neither side overwrites the other. Taking the
   intake value alone strips the fraud data from every order, and the
   fraud-driven Journey triggers then never fire; the API's success response
   looks identical either way.
2. Build `create.json` + the single PUT with all `add_tracking` mutations
   (order-lifecycle's payload rules verbatim: randomised format-correct
   tracking numbers, courier per shipment, `tracking.articles` mirrored,
   split rules for 2-shipment orders).

   **`extras.article_weights` is a lookup, not a field to copy.** Every other
   extra's manifest key is already the Order API field name; this one is a
   synthetic container. `extras.article_weights[<product id>]` sets `weight`
   and `weight_unit` on **every article whose product is that id**, at both the
   `articles_order` level and every `add_tracking`'s `tracking.articles` — the
   same dual-level rule as any other article field. The manifest keys by
   product `id` (the goods code) while payload articles key by `line_item_id`,
   which is the SKU, so resolve through the order's product, not the article
   key. No top-level `article_weights` is ever written to a payload.
3. Write the `NN-<status>.json` event files from the shipment's `events`.
4. `DRYRUN=1` pass; then launch `run-lifecycle.sh` as a **tracked background
   task — one Bash call per order with `run_in_background: true`, and NO
   `nohup`, `&`, or `disown`** — all orders concurrent.

   **Those are two different mechanisms and mixing them defeats both.**
   `run_in_background` keeps the process attached to a task the user can see,
   and notifies you when it exits. `nohup … &` detaches it from that task
   entirely: live 2026-08-11 a conductor wrapped the launch in `nohup`, so the
   tracked task was the *launcher* — it exited in about two seconds while three
   drivers ran for fifteen minutes with nothing in the user's task list. The
   user had to ask "I don't see any background tasks running?" to find out the
   run was fine.

   Set `STATE_FILE="<run dir>/orders/<nn>-<label>/events.jsonl"` on every launch
   so the watcher in step 5 can see progress.

   `GAP_SECONDS` comes from the manifest's `run.pace`: 200 for standard (the
   default), 60 for fast. When pace is fast, Beat 2's report must note that
   comm ordering was not guaranteed at this pace. Pass `PARCELLAB_ACCOUNT_ID=<manifest account.id>`
   inline on every launch: `create.json`'s `account` field and the driver's
   account both come from the manifest, never from the ambient
   `$PARCELLAB_ACCOUNT_ID`, which may point at a different account than the
   one confirmed at intake. Once drivers are launched: record it via
   `run_state.py` — `mark(d, "lane", "orders", "start")`, and
   `set_schedule`, which the page's clock needs —
   re-render with `render_run_page.py <run dir>` and republish — non-fatal.
5. **Watch and republish.** After launching every driver, run
   `${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_event.sh <run dir>` as a tracked
   background task. When it returns, ingest each order's new `events.jsonl`
   lines with `run_state.confirm_event(...)`, re-render, republish, and start
   the watcher again. Repeat until every driver's task has reported completion,
   then `mark(d, "lane", "orders", "end")`.

   This is what makes the page live rather than frozen for the fifteen minutes
   that matter most. Expect roughly 8–12 republishes per run; that cost was
   chosen deliberately over a cheaper animation-only page. If it proves too
   expensive, widen the watcher's settle window rather than abandoning the loop.
6. Write `order.json` per the contract.

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
`run.pace`: 200 for standard (the default), 60 for fast. When pace is fast,
Beat 2's report must note that comm ordering was not guaranteed at this
pace. It also includes the launch mechanics in full: a **tracked background task
per order (`run_in_background: true`, never `nohup`)** with `STATE_FILE` set,
followed by the same `wait_for_event.sh` watch-and-republish loop as the direct
engine's step 5. Once drivers are launched: record it via `run_state.py`
(`mark(d, "lane", "orders", "start")` and `set_schedule`, with the matching
`"end"` when the watch loop finishes), re-render with `render_run_page.py <run dir>` and
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
from the manifest + `results/linked-orders.json` and submits once — bracket
the invocation with `mark(d, "lane", "cdc", "start")` and `"end"`. Do not
retry a 500 (the request already exists — the results file records it).

## Phase 4 — Report

**Beat 1 — environment built** (immediately after Phase 3): layout id +
release status + store assignment (+ any 9b country-override warning,
repeated verbatim) · per order: number, customer, fraud level, slot,
courier(s) + tracking number(s), scenario, and the expected comm per event
with confidence labels · (retain-shopify) the seed table + demos +
adjustments from `results/shopify-seed.json` · CDC request id/URL, which
orders were submitted for linking, and the config source (say "caller's
default config" when `config_source` is `none`). No currency symbols. **If the edit-mode guard was
repointed for this run** (per Phase 0 step 4's note), say so here as a line of fact and state that it is restored after Beat 2
— not now. The drivers are still pushing events against that account.
Once Beat 1 is posted: record it via `run_state.py` — `mark(d, "gate", "beat1", "end")`, which is where `Duration to build` ends — re-render with `render_run_page.py <run dir>` and republish — non-fatal.
Update the telemetry row (stage `beat1`) with the build results, if
`results/telemetry.json` exists.

**Then arm Beat 2's wake-up, in the same turn.** Nothing else will:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/wait_for_beat2.py <run dir>
```

Launch it as a **tracked background task** (`run_in_background: true`, no
`nohup`). It sleeps until 5 minutes past the newest event across every order's
`events.jsonl`, then exits — and that exit notification is what re-invokes you
to run Beat 2.

**A conductor only acts when something invokes it.** By Beat 1 every driver and
watcher has finished, so unless this task is running there is no pending event
left to wake anyone, and the run simply stops one beat short. Live 2026-08-12
that left a completed environment sitting unverified for 19 minutes until the
user asked why Beat 2 had not fired — the run page said `cdc ok` and nothing
further. Arming this is not optional bookkeeping; it is the only thing that
makes Beat 2 happen at all.

If the task is somehow lost, say so plainly and run Beat 2 as soon as you next
act — a late Beat 2 beats a silent one.

**Beat 2 — verified** (after each order's driver finishes AND **≥5 minutes**
after its final event): per order,
order-info lookup; report checkpoints
attached vs planned, and — for *which* comm each tracking selected —
`contacted_with_messages` vs the expected comms, explicitly covering the good
AND bad arcs the run promised.

**Read these from the response's real paths** — none of the three sit where the
obvious name suggests, and guessing produces an empty report that reads as a
failed run:

| What | Path on the order-info response |
|---|---|
| Checkpoint status | `trackings[].checkpoints[].status_code` (not `status`) |
| Which comm a tracking selected | `trackings[].reporting_info.contacted_with_messages` |
| pL courier | `trackings[].courier_info.courier` |

**Never count total sends from `contacted_with_messages`.** It lives per
tracking and is deduplicated within that tracking's own array, so an
order-level comm (`order_confirmation`, `shipping_confirmation`) that fires
once per tracking on a multi-tracking order reads as one accounted-for entry
in each tracking's list — not as the same physical send referenced twice. A
split-shipment order therefore always undercounts by one send per extra
tracking if this field is treated as the count.

**Proven live 2026-08-13**, account 1626718, run `adidas-20260813-1033`: split
order `ADI-1786614815` actually sent `order_confirmation_1093` twice — once
per tracking, at 09:55:16 and 09:55:47, both to the same recipient. Beat 2
reported 15 comms for the run from `contacted_with_messages`; the account had
actually sent 16. Get the real count from raw send records instead:

```bash
parcellab track email list --account <id> --page-size 50 -o json \
  --jmes 'results[?createdAt>=`<run start>`].{mt:messageType,at:createdAt}'
```

Count sends per `messageType` across the run window and report that as
"comms fired" — a split order will legitimately show two sends of the same
order-level `messageType`, and that is the true count, not a bug to explain
away.

Look the order up by **`order_number` + `account`**. The
`courier` + `tracking_number` form this step used to specify returns
`Unauthorized` on a conductor's credentials (live 2026-08-12, same token that
served the `order_number` form seconds earlier).

**A comm still missing at 5 minutes is not yet a defect — re-check before you
call it one.** Wait a further 5 minutes and look again; only report a comm as
missing once a second look agrees. This floor was 15 minutes precisely because
an early report is worse than a late one: measured 2026-08-11, comms landed in
3-4 minutes on single-parcel orders but took over 10 on a split order's parcel,
and reporting at 6 minutes put a wrong defect hypothesis in front of the user.
The floor came down to 5 on 2026-08-12 (verified against the operator's own
inbox), so **the re-check now carries the protection the longer wait used to** —
it is what makes 5 minutes safe, not an optional extra. A run that reports
"comm missing" without a second look has skipped the step, and the split
parcel is where that will bite first.

**Before diagnosing a missing comm, check whether the message can send at all.**
Resolve the journey channel's `messageType` to its message and read
`hasReleasedVersion` — a message that has never been released renders nothing,
while the trigger still matches and the event still names it.

Two things that look like causes and are not, both proven live on 2026-08-12:

- **`releaseStatus: draft` does not block sending.** A draft serves its last
  released version — account 1626718 message 75240 is `draft` and has sent 51
  emails. `hasReleasedVersion` is the gate, not `releaseStatus`.
- **`recipientCustomer: false` with `recipientPlTest: true` does not block
  sending.** That is normal demo-account config. Account 1626718 sent 100 emails
  with channel config byte-identical to a failing account's.

Re-deriving either one costs a run about twenty minutes. The fuller ledger, with
the command for each check, is the run-triage skill's
`references/comms-diagnosis.md` if you have that skill installed.

**Restore the edit-mode guard.** Once every driver has exited and the
verification above is done, if the guard was repointed for this run, restore it
to the user's own account — no question, and report it in one line. If the
restore fails, say so explicitly with the error; a guard left pointing at
another account is exactly the state the next run's Phase 0 check will trip on.

For every unproven event or chain that fired correctly, record it in
`${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md` —
automatically, then report what was written. Each entry carries the date, the
order number and the account, so a later reader can check it. A run edits a
skill reference file here on purpose: the alternative is proven status codes
staying labelled unproven because nobody answered a prompt at the end of a
fifteen-minute run.
Once Beat 2 is posted: record it via `run_state.py`, re-render with `render_run_page.py <run dir>` and republish — non-fatal.

Update the telemetry row (stage `beat2`), filling `Comms expected` and
`Comms fired` from the verification just performed. `Duration to build` is
derived from the marks — never compute a duration by hand.

**Then append the run detail to the row's own page**, so the run is readable by
anyone on the team:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_run_digest.py <run dir>
```

Append the output to the Notion **row page** — the page the `beat2` update just
wrote to — not to the database and not to a new page. The run page artifact is
private to whoever ran it and cannot be shared from here, so this is the only
copy a teammate can open. A failed append is recorded and mentioned once in the
final report, exactly like a failed row write: telemetry is an observer, never
a dependency.

**Then answer these three questions explicitly before writing the row** — they
are the only source for the self-reported deviations, and an open "did
anything go wrong?" reliably returns "no":

1. Did any instruction fail to work as written? If so, which file and line?
   → `instruction_unfollowable`
2. Did you do anything the skill does not describe, including a workaround for
   a tool that behaved unexpectedly? → `workaround_invented`
3. Did the user have to intervene, correct you, or ask why something had not
   happened? → `manual_intervention`

Answer them from the actual run, not from intent. Live 2026-08-11 all three
would have been answered "no" by a conductor that had in fact wrapped its
drivers in `nohup` against the skill's instruction, leaving the user staring
at an empty task list — question 3 is the one that would have caught it.

## Failure handling

| Lane fails | Blocks | Response |
|---|---|---|
| scrape agent | nothing | run the browser pass inline (Phase 0 step 6's fallback) |
| seed agent | Shopify orders only | report, offer inline re-run from the same manifest |
| template publish | Phase 2 (all orders) | the three-way publish-gate offer |
| one order (any engine) | nothing else | mark partial in its order.json; report the exact step |
| CDC call | nothing | report; 500 = request exists, retry manually in-app |

On any failure above: record it via `run_state.py`, re-render with `render_run_page.py <run dir>` and republish — non-fatal.

Fallback rule (Approach B): any agent lane can be re-run inline in the main
session from the same manifest — the brief and the contract are identical.
Never silently continue past a failed lane; every lane ends in a results
file or a reported failure, and Beat 1 lists any lane still outstanding.
