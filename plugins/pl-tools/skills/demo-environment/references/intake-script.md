# demo-environment — canonical intake fields

Every field below is answered once, by the intake form `run_server.py`
serves — see `SKILL.md`'s "Intake questionnaire" and Phase 0 step 2 for the
start-server/wait-for-file mechanics. This file documents *what* the form
asks and what it deliberately doesn't; it no longer describes a sequential
chat round structure, since there isn't one. The handoff is the file
`<run dir>/intake.json` appearing on disk — a valid submission writes it,
an invalid one doesn't, and there is nothing to publish, poll, or extract
around that.

## Fields the form asks

| Field | Options | Condition |
|---|---|---|
| Shopify opp? | No · Yes | always |
| Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |
| Region | US · UK · DE | always — pre-filled from `resolve_auto_defaults.infer_country`, editable |
| Default courier | free text | always — pre-filled per region (`usps` / `royal-mail` / `dhl-germany`) |
| Order matrix | count (1–5) + per-order fraud/split/scenario/courier, per-parcel scenario/courier when split | always |
| Customisation | Send as-is · the seven extras, field by field | always |
| Mode | Babysit · Auto | always |

`shopify_opp` → `path` (No → **retain**, Yes → **retain-shopify**).
Returns are always in scope for this demo — there is no separate question
about that; every run is either **retain** or **retain-shopify**.

### The default order matrix

`intake_schema.default_answers()` is the source of truth for the form's
pre-fill — the operator edits from it, 1–5 orders. It ships three rows
(trimmed from the historical five, since the two return-flow rows depend
on the retain path, which this same form now decides in the same
submission):

| Order | Fraud | Split | Detail |
|---|---|---|---|
| #1 | low | no | scenario `happy`, courier `null` (falls back to the run's default) |
| #2 | medium | yes | parcel A: scenario `happy` · parcel B: scenario `stuck-delay`, both courier `null` |
| #3 | high | no | scenario `recovered`, courier `null` |

`split` is per order; a split order carries exactly two parcels, each with
its own `scenario` and `courier`, in place of the non-split order's single
`scenario`/`courier` pair. A `null` courier on any order or parcel means
"use the form's default courier field" — the courier is per-shipment only
when the operator overrides it.

**Mapping onto the manifest:** each order's parcels (or, for a non-split
order, the order itself) become that order's manifest `shipments[]`
entries — one shipment per parcel, or one shipment for a non-split order.
Each shipment's `scenario` is the parcel's (or order's) `scenario`
verbatim. Each shipment's `courier` is the parcel's (or order's) `courier`
when non-null, otherwise the form's default courier field.

Scenario vocabulary: `happy` · `stuck-delay` · `recovered`
(`InTransit → WarehouseDelay → OutForDelivery → Delivered`, proven live
2026-08-11) · `locker` (`… → Delivered-ParcelLocker`, status unproven) ·
`custom` (user-specified sequence, labelled per order-lifecycle's confidence
rules). `manual_return` and `return_tracking` are **not** scenarios — they are
`cdc_slot` values, and no event sequence is documented for either, so
return-flow demos are requested via `custom` (with the sequence spelled out)
until their sequences are proven live, at which point they can be restored to
`intake_schema.SCENARIOS`.

Runs of 2+ orders need at least one split-shipment order, and at least one
shipment must end in the literal event `Delivered` — which only `happy` and
`recovered` do (`intake_schema.DELIVERED_TERMINATING_SCENARIOS`; `locker`
ends `Delivered-ParcelLocker`, a different string). Both rules are enforced
by `parse_answers`, so the form rejects a matrix that would fail
`validate_manifest.py` later. Every order gets a distinct synthetic customer
(region-appropriate name + email) — generate them and show them.

### Customisation (send-as-is / the seven extras)

The default is send-as-is, and picking it takes one click — the form's
`gate_c` field is `"send-as-is"` and `extras` is empty. Picking the extras
option opens the field-by-field detail **in the same form** — there is no
chat follow-up any more; every field below is collected before submission.
The manifest keys are the literal Order API field names (`intake_schema.
EXTRA_KEYS` is the source of truth):

| Extra | Manifest key(s) |
|---|---|
| Promise dates | `announced_delivery_date`, `announced_delivery_date_min`, `announced_delivery_date_max` (each `YYYY-MM-DD`) |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` |
| Article physical data | `article_weights` (synthetic container — see "Deriving article weights" below) |
| Delivery detail | `delivery_method`, `courier_service_level`, `requires_signature` |
| Tags / custom fields | `tags`, `additional_attributes` |
| Dynamic recipients | `additional_recipients` |
| Extra articles | `extra_articles` (synthetic container) |

Three rules specific to an orchestrated run, unchanged from before:

- **One answer covers every order.** Extras are per-run, not per-order.
- **Tags merge, they do not replace.** `prepare_fraud_fragment.py` already
  writes each order's top-level `tags` and `additional_attributes`. Union the
  intake's tags with the fraud fragment's output per order; neither side
  overwrites the other. Overwriting discards the fraud data the whole run is
  built to demonstrate.
- **The `client_key` pre-fill does not apply.** Standalone Gate C pre-fills a
  `client_key` when Gate B introspected a journey needing one. Here Gate B is
  answered by the manifest and no introspection runs, so nothing is pre-filled.

Record the answer as `gates.order_lifecycle.gate_c` (`"send-as-is"` or
`"extras"`) plus `extras`. Promise dates are resolved to absolute `YYYY-MM-DD`
at manifest-write time — a full ISO datetime is rejected by the API.

### Deriving article weights

Two mechanisms, and which one applies depends entirely on whether the
operator typed a weight. Never ask for a value per product on top of what
the form collected; either way, show every resolved value at the ✋ gate,
article by article, so it can be corrected before anything is sent.

**1 — The operator supplied a weight (the form emitted
`article_weights`).** That single value is the **run-wide** weight: the form
has no product ids to key by, because the scrape lane only runs after intake
is submitted, so it arrives under the sentinel key
`__run_default__` (`intake_schema.RUN_DEFAULT_WEIGHT_KEY`). **Fan it out** at
manifest-write time to

```json
{"<product id 1>": {"weight": …, "weight_unit": …},
 "<product id 2>": {"weight": …, "weight_unit": …}}
```

— one entry per product id in the run (the `core4`, plus any
`shopify_extra`), all carrying the same value the operator typed. The
`product_type` table below is **not** consulted in this case; using it would
discard the number the operator just entered. The sentinel key must never
reach the manifest — `validate_manifest.py` rejects any
`article_weights` key that is not a product `id`
(`MANIFEST INVALID: extras.article_weights: unknown product …`).

**2 — The operator supplied no weight**, so `article_weights` is absent from
the submitted extras. Then no weights are written for the run — an absent
key is an answer, not a gap to fill. The table below is the fallback for the
one remaining case: a weight is needed later in the run (the operator asks
for one after the ✋ gate, or an order-lifecycle Gate C follow-up wants one)
and no operator value exists to fan out. Derive one weight per article from
its `product_type`, keyed by product `id` exactly as above.

Match case-insensitively on the `product_type` string; first match wins.

| `product_type` contains | Weight |
|---|---|
| shoe, boot, sneaker, trainer | 900 g |
| coat, jacket, knit, jumper, hoodie | 700 g |
| shirt, tee, top, dress, trouser, sock, apparel | 300 g |
| bag, hat, belt, scarf, accessor | 500 g |
| phone, laptop, tablet, electronic, device, audio | 1200 g |
| home, kitchen, decor, furnish | 800 g |
| (no match) | 500 g |

**`weight_unit` is always written, never left out** — `validate_manifest.py`
rejects a missing one (`{weight: 300}` → "must be one of [...] (got None)").
Write `g` unless the user says otherwise, in which case it must be one of
`kg`, `g`, `lbs`, `oz`; any other value is rejected too. Weights are numbers
greater than zero. Write them to
`extras.article_weights`, keyed by product **`id`** (the goods code) and never
by SKU — `validate_manifest.py` rejects SKU keys.

## Fields the form deliberately does not ask

Each of these was a live question once. Resolving them silently is what
makes a clean run unattended after the ✋ gate, and what makes mode
irrelevant to every question except the two hard gates.

| Not asked | Instead |
|---|---|
| Are returns in scope for this demo? | Always yes. The old "engage" (no-returns) path is retired; every run is `retain` or `retain-shopify`. |
| Which category should the CDC request use? | Always inferred via `resolve_auto_defaults.infer_category` from the scraped product pool, once it exists — in every mode. Written to `brand.category`. A known separate gap: this is one category for the whole run, not per product — a prospect whose order matrix spans genuinely different product categories still gets a single inferred value. |
| What pace should the journeys run at? | Always `"standard"` (300 s gaps). `GAP_SECONDS=60` ("fast") is no longer offered as a live choice in any mode. |
| Which account should this demo build in? | Always the user's own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`) — the shared **parcelfashion** account is no longer offered as a choice here. |
| Using **\<name\>** (\<id\>) — correct? | No longer asked — the account above is resolved and used silently. Its name is still looked up (`parcellab account account show <id>`) and stated in Beat 1, so it stays visible after the fact even though nothing gates on it beforehand. |
| What is the CDC account config name (or UUID) for this target? | Always `selected_account_config_id: null`, `config_source: "none"` — the CDC uses the caller's default config. |
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → asked (SKILL.md Phase 0 step 4's Shopify resolution bullet). |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |

**Region is now asked, not resolved silently** — see the field table above.
`resolve_auto_defaults.infer_country` (TLD, else path locale segment, else
scraped currency symbol, else `US`) still runs, but only to pre-fill the
form's region field; the operator's submitted value is what gets written,
to both `brand.region` and `destination_country`. The form limits the
choice to `US`, `UK`, `DE` because `validate_manifest.py` accepts no other
`brand.region`.

## Mode

**Babysit** and **auto** answer every field above identically — mode is
purely a form field now, not inferred from wording, and it
changes exactly one thing downstream: whether the ★ template preview and
✋ plan approval pause for a chat yes or auto-approve. See `SKILL.md`'s
"Intake questionnaire" and "Both hard gates are auto-approved in auto
mode" sections.
