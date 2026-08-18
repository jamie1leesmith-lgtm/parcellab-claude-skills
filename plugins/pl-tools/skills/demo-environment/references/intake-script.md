# demo-environment — canonical intake script

Ask these questions in this order, with this wording. Conditional questions are
marked; skip one when its condition is false, never reorder the rest. Batch a
round with AskUserQuestion where the questions are independent.

Standard wording matters because the answers become manifest fields: a question
asked three different ways across three runs produces three differently-shaped
answers, and the run page and telemetry compare runs to each other.

## Round 1 — before the scrape agent is dispatched

**Auto mode never changes Q1.** Q1 (Shopify opp) decides the build path and
is always asked live, exactly as below, in both babysit and auto mode — it is
never defaulted or read from an answers doc. Q2, below, is a different case:
it is also part of Round 1, but auto mode *does* auto-resolve it — see the
note under the table.

Everything that has to be settled before the scrape brief can be written.
Returns are always in scope for this demo — there is no separate question
about that; every run is either **retain** or **retain-shopify**.

| # | Question | Options | Condition |
|---|---|---|---|
| 1 | Is this a Shopify opp? | No · Yes | always |
| 2 | Reuse the pool scraped for **\<brand\>** on \<date\>, or scrape fresh? | Reuse · Scrape fresh | a prior run dir with the same handle holds both `scrape/brand-tokens.json` and `scrape/product-pool.json` |

**Q2 in auto mode:** auto-resolves, it is not asked. Reuse the pool
automatically whenever the same candidate exists (the condition column
above), and scrape fresh only when there is no candidate to reuse — the
same reuse-if-a-candidate-exists rule babysit mode's offer encodes,
just accepted without a chat round-trip.

Q1 no → **retain**. Q1 yes → **retain-shopify**.

## Round 2 — batched, while the scrape agent runs

| # | Question | Options | Condition | Auto mode |
|---|---|---|---|---|
| 3 | How many orders, and which scenario and fraud level for each? | the default matrix below | always | Existing default matrix, unchanged |
| 4 | Anything else to add to every order, or send as-is? | the Gate C menu below | always | `send-as-is` |
| 5 | Which category should the CDC request use? | Home · Electronics · Fashion | always | `resolve_auto_defaults.infer_category` |
| 6 | The edit-mode guard is not restricted to this account. Fix it? | Fix it · Leave it | `parcellab settings edit-mode show` is not `account-restricted` for the target | Fix it |
| 7 | These write permissions are missing — add them to `~/.claude/settings.json`? | (the user edits the file themselves) | `permissions.allow` does not cover the run's writes | **Blocker** — never defaulted |
| 8 | Which Shopify store should this seed into? | (the authed stores) | retain-shopify **and** 2+ stores authed | **Blocker** — never defaulted |

### Q3 — the default matrix

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

### Q4 — the Gate C menu

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

### Q4 follow-up — deriving article weights

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

**`weight_unit` is always written, never left out** — `validate_manifest.py`
rejects a missing one (`{weight: 300}` → "must be one of [...] (got None)").
Write `g` unless the user says otherwise, in which case it must be one of
`kg`, `g`, `lbs`, `oz`; any other value is rejected too. Weights are numbers
greater than zero. Write them to
`extras.article_weights`, keyed by product **`id`** (the goods code) and never
by SKU — `validate_manifest.py` rejects SKU keys.

## Questions this script deliberately does not contain

Each of these was a question once. Removing them is what makes a clean run
unattended after the ✋ gate.

| Not asked | Instead |
|---|---|
| Are returns in scope for this demo? | Always yes. The old "engage" (no-returns) path is retired; every run is `retain` or `retain-shopify`. |
| Which country are these orders delivering to? | Always inferred via `resolve_auto_defaults.infer_country` (TLD, else path locale segment, else scraped currency symbol, else `US`) — in every mode, not just auto. Written to `destination_country`. |
| Which region should the CDC request use? | Always set equal to the resolved `destination_country` above, written to `brand.region`. |
| What pace should the journeys run at? | Always `"standard"` (200 s gaps). `GAP_SECONDS=60` ("fast") is no longer offered as a live choice in any mode. |
| Which account should this demo build in? | Always the user's own default demo account (`${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`) — the shared **parcelfashion** account is no longer offered as a choice here. |
| Using **\<name\>** (\<id\>) — correct? | No longer asked — the account above is resolved and used silently. Its name is still looked up (`parcellab account account show <id>`) and stated in Beat 1, so it stays visible after the fact even though nothing gates on it beforehand. |
| What is the CDC account config name (or UUID) for this target? | Always `selected_account_config_id: null`, `config_source: "none"` — the CDC uses the caller's default config. This is safe now that the target account is always the fixed default account above and the practical default already targets it. |
| Should the CDC also generate synthetic orders? | `generate_orders` is always `false` and `cdc.orders` always `[]`. The ✋ gate states `CDC synthetic generation: off` so it stays visible. |
| Which Shopify store? (when only one) | Resolved from `~/.claude/parcellab-shopify-seed.env`, else `shopify store auth list`. Exactly one → use it and state it at the gate. Zero → stop and point at `/pl-setup`. 2+ → Q8. |
| Restore the edit-mode guard? | Restored automatically after Beat 2, once every driver has exited. |
| Record this proven event in `status-codes.md`? | Recorded automatically by Beat 2, which reports what it wrote. |

## Auto mode

An optional answers doc (flat JSON, keyed by manifest field) may override any
Auto-mode value above except Q1, which is never doc-supplied.
`resolve_auto_defaults.resolve_auto_fields` computes the merged result; an
unknown doc key is collected, never applied, and reported once in Beat 1.
Both hard gates (★ template, ✋ plan) are auto-approved in auto mode — see
`SKILL.md`'s "Mode selection" and "Blockers" sections for the trigger phrase
and the full blocker list.

**What actually differs from babysit mode now is small.** Country, region,
pace, the target account, and the CDC config were all live babysit-mode
questions once; all five are now always resolved the same way regardless of
mode (see the table above), so they no longer distinguish auto mode from
babysit mode at all. What auto mode still changes, on top of the shared
Round 1/2 script above:

- **Q2** (reuse the prior scrape pool) resolves automatically instead of
  being asked.
- **Both hard gates** (★ template preview, ✋ plan approval) are
  auto-approved instead of waiting for a chat yes.
- **Blockers stop the run** (see `SKILL.md`'s "Blockers (auto mode)" table)
  in the same situations babysit mode would otherwise ask a live question
  and wait — write permissions missing (Q7) and 2+ Shopify stores with no
  env pin (Q8) are the two that can still require input either way.
