# demo-environment — canonical intake fields

Every field below is answered once, by the intake questionnaire
(`render_intake_questionnaire.py`), before the scrape agent is dispatched
— see `SKILL.md`'s "Intake questionnaire" section for the publish/wait/
extract mechanics. This file documents *what* the questionnaire asks and
what it deliberately doesn't; it no longer describes a sequential chat
round structure, since there isn't one.

## Fields the questionnaire asks

| Field | Options | Condition |
|---|---|---|
| Shopify opp? | No · Yes | always |
| Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |
| Order matrix | see below | always |
| Anything else to add to every order, or send as-is? | Send as-is · Extras (detail asked in chat after the form) | always |
| Mode | Babysit · Auto | always |

`shopify_opp` → `path` (No → **retain**, Yes → **retain-shopify**).
Returns are always in scope for this demo — there is no separate question
about that; every run is either **retain** or **retain-shopify**.

### The default order matrix

The questionnaire pre-fills this; the operator edits from it. 1–5 orders,
default 5 (every row starts checked; uncheck rows to reduce the count).

| Order | Fraud | Scenario |
|---|---|---|
| #1 | low | happy |
| #2 | medium | split — parcel A happy, parcel B stuck-delay |
| #3 | high | recovered |
| #4 | low | manual_return (retain paths only) |
| #5 | low | return_tracking (retain paths only) |

Scenario vocabulary: `happy` · `stuck-delay` · `recovered`
(`InTransit → WarehouseDelay → OutForDelivery → Delivered`, proven live
2026-08-11) · `locker` (`… → Delivered-ParcelLocker`, status unproven) ·
`custom` (user-specified sequence, labelled per order-lifecycle's confidence
rules). Runs of 2+ orders need at least one split-shipment order. Every order
gets a distinct synthetic customer (region-appropriate name + email) —
generate them and show them.

### The send-as-is / extras toggle

The default is send-as-is, and picking it takes one click. When the
operator picks **extras**, the field-by-field detail — promise dates,
order financials, article physical data, delivery detail, tags/custom
fields, dynamic recipients, extra articles — is collected in **chat, after
the questionnaire**, from order-lifecycle's own Gate C menu. The
questionnaire only ever asks the toggle: those per-field values depend on
schema owned by order-lifecycle, not this skill.

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

When the chat follow-up turns on article physical data, do not ask for a
value per product. Derive one per article from its `product_type` and show
every derived value at the ✋ gate, article by article, so it can be
corrected before anything is sent.

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

## Fields the questionnaire deliberately does not ask

Each of these was a live question once. Resolving them silently is what
makes a clean run unattended after the ✋ gate, and what makes mode
irrelevant to every question except the two hard gates.

| Not asked | Instead |
|---|---|
| Are returns in scope for this demo? | Always yes. The old "engage" (no-returns) path is retired; every run is `retain` or `retain-shopify`. |
| Which country are these orders delivering to? | Always inferred via `resolve_auto_defaults.infer_country` (TLD, else path locale segment, else scraped currency symbol, else `US`) — in every mode. Written to `destination_country`. |
| Which region should the CDC request use? | Always set equal to the resolved `destination_country` above, written to `brand.region`. |
| Which category should the CDC request use? | Always inferred via `resolve_auto_defaults.infer_category` from the scraped product pool, once it exists — in every mode. Written to `brand.category`. |
| What pace should the journeys run at? | Always `"standard"` (200 s gaps). `GAP_SECONDS=60` ("fast") is no longer offered as a live choice. |
| Which account should this demo build in? | Always the user's own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`) — the shared **parcelfashion** account is no longer offered as a choice here. |
| Using **\<name\>** (\<id\>) — correct? | No longer asked — the account above is resolved and used silently. Its name is still looked up (`parcellab account account show <id>`) and stated in Beat 1, so it stays visible after the fact even though nothing gates on it beforehand. |
| What is the CDC account config name (or UUID) for this target? | Always `selected_account_config_id: null`, `config_source: "none"` — the CDC uses the caller's default config. |
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → asked (SKILL.md Phase 0 step 4's Shopify resolution bullet). |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |

## Mode

**Babysit** and **auto** answer every field above identically — mode is
purely a questionnaire field now, not inferred from wording, and it
changes exactly one thing downstream: whether the ★ template preview and
✋ plan approval pause for a chat yes or auto-approve. See `SKILL.md`'s
"Intake questionnaire" and "Both hard gates are auto-approved in auto
mode" sections.
