# demo-environment — canonical intake script

Ask these questions in this order, with this wording. Conditional questions are
marked; skip one when its condition is false, never reorder the rest. Batch a
round with AskUserQuestion where the questions are independent.

Standard wording matters because the answers become manifest fields: a question
asked three different ways across three runs produces three differently-shaped
answers, and the run page and telemetry compare runs to each other.

## Round 1 — before the scrape agent is dispatched

Everything that has to be settled before the scrape brief can be written.

| # | Question | Options | Condition |
|---|---|---|---|
| 1 | Are returns in scope for this demo? | No · Yes | always |
| 2 | Is this a Shopify opp? | No · Yes | Q1 = yes |
| 3 | Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |

Q1 no → **engage**. Q1 yes + Q2 no → **retain**. Q1 yes + Q2 yes →
**retain-shopify**. An Engage-only run never asks Q2; Retain covers the Engage
story automatically.

## Round 2 — batched, while the scrape agent runs

| # | Question | Options | Condition |
|---|---|---|---|
| 4 | Which country are these orders delivering to? | US · UK · DE · Other | always — never assume it |
| 5 | How many orders, and which scenario and fraud level for each? | the default matrix below | always |
| 6 | What pace should the journeys run at? | Standard (200 s gaps, comm ordering safe) · Fast (60 s gaps, comms may arrive out of order) | always |
| 7 | Anything else to add to every order, or send as-is? | the Gate C menu below | always |
| 8 | Which region and category should the CDC request use? | US/UK/DE × Home/Electronics/Fashion | always |
| 9 | Which account should this demo build in? | \<user's own demo account\> · parcelfashion | always — parcelfashion is offered only when `CDC_ACCOUNT_CONFIG_PARCELFASHION` is stored, and never on retain-shopify |
| 10 | Using **\<name\>** (\<id\>) — correct? | Yes · Pick another | always |
| 11 | The edit-mode guard is not restricted to this account. Fix it? | Fix it · Leave it | `parcellab settings edit-mode show` is not `account-restricted` for the target |
| 12 | These write permissions are missing — add them to `~/.claude/settings.json`? | (the user edits the file themselves) | `permissions.allow` does not cover the run's writes |
| 13 | What is the CDC account config UUID for this target? | (a UUID, or skip) | the target's config key is missing from the env |
| 14 | Which Shopify store should this seed into? | (the authed stores) | retain-shopify **and** 2+ stores authed |

### Q5 — the default matrix

Offer this first; the user adjusts from it. 1–5 orders, default 3.

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

### Q7 — the Gate C menu

The default is send-as-is, and skipping takes one word. Offer the menu from
order-lifecycle's Gate C table verbatim: promise dates · order financials ·
article physical data · delivery detail · tags/custom fields · dynamic
recipients · extra articles.

Do **not** ask an open "any other fields?" — that is unanswerable unless the
user has the Order API spec memorised.

Three rules specific to an orchestrated run:

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

### Q7 — deriving article weights

When the user turns on article physical data, do not ask for a value per
product. Derive one per article from its `product_type` and show every derived
value at the ✋ gate, article by article, so it can be corrected before anything
is sent.

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

Unit is `g` unless the user says otherwise. Write them to
`extras.article_weights`, keyed by product **`id`** (the goods code) and never
by SKU — `validate_manifest.py` rejects SKU keys.

## Questions this script deliberately does not contain

Each of these was a question once. Removing them is what makes a clean run
unattended after the ✋ gate.

| Not asked | Instead |
|---|---|
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → Q14. |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |
