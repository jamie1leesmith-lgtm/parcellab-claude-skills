# Shopify order engine (retain-shopify path)

Runs from Phase 2 of the `demo-environment` conductor when `results/shopify-seed.json`
shows `"status": "ok"`. For each manifest order, in its `orders/<nn>-<label>/` directory,
work through the six parts below in order. The output must land in the same two places the
direct engine writes to — `orders/<nn>-<label>/order.json` and, once every order is
processed, `results/linked-orders.json` — so Phase 3 and Phase 4 never need to know which
engine built an order.

Every relative path in this doc (`orders/<nn>-<label>/`, `results/…`) resolves against the
run directory — `cd` there first, or use absolute paths.

> **LIVE-VERIFIED 2026-08-11** (retain-shopify Run 2, store parcellab-demo-jls, one order
> end-to-end). The substitutions and corrections from that run are folded in below; the
> headline ones:
>
> 1. **`orderCreate` cannot be used from the Shopify CLI at all** — it exists in the
>    schema and passes introspection, but is restricted to apps with OFFLINE tokens and
>    the CLI authenticates with session tokens (`ACCESS_DENIED … only accessible to apps
>    authenticated using offline tokens`). **Always use the draft-order path in Part 2.**
> 2. The draft path needs the **`write_draft_orders`** scope, and Part 5a's
>    fulfillment-order read needs **`write_merchant_managed_fulfillment_orders`** — the
>    full working scope set is in Part 1.
> 3. The order-info lookup parameter is **`order_number`**, not `orderNo` (the API's 400
>    helpfully lists every accepted lookup mode).
> 4. The enrichment PUT **requires core order fields** (`recipient_email`,
>    `destination_country_iso3`, …) but **merges** — it did not blank the
>    integration-written articles (details in Part 4).
> 5. Shopify tracking company `DPD` maps to pL courier **`dpd`** (not `dpd-uk`) — 6b's
>    read-the-courier-back rule is mandatory, the mapping genuinely differs.
>
> Still introspect before the first mutation call of each run (schema drift), but start
> from the shapes below — they are what actually worked.

`$SHOPIFY_DEMO_STORE` in every command below is the manifest's `shopify.store` — already
resolved and confirmed at intake (see the conductor's *Shopify resolution* step). Export it
once at the start of Phase 2:

```bash
export SHOPIFY_DEMO_STORE="<manifest shopify.store>"
```

Do not re-derive it from `~/.claude/parcellab-shopify-seed.env` or `shopify store auth
list` — that lookup belongs to `shopify-seed`'s standalone path, not this orchestrated one.

---

## Part 1 — Scope check (once per run, before the first order)

`shopify store auth list` prints which stores are connected, not which scopes the
connection was granted — so a scope gap shows up only when a write is attempted, as an
access error partway through an order. Check for it up front with a cheap read instead:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ orders(first: 1) { nodes { id } } }'
```

Read-only, so **no `--allow-mutations`**.

- **Succeeds** → scopes are sufficient, continue to Part 2.
- **Access error** → the store's auth needs re-consenting with the full scope set this
  engine needs across all six parts:

  ```bash
  shopify store auth -s "$SHOPIFY_DEMO_STORE" \
    --scopes write_products,write_inventory,read_orders,write_orders,write_fulfillments,write_draft_orders,write_merchant_managed_fulfillment_orders
  ```

  **This opens a browser consent window — warn the user before running it**, the same way
  `shopify-seed` Step 1 warns before its own first-time auth.

**Live-verified scope set (2026-08-11):** the five scopes above are NOT sufficient. The
full working set for this engine is:

```
write_products,write_inventory,read_orders,write_orders,write_fulfillments,write_draft_orders,write_merchant_managed_fulfillment_orders
```

- `write_draft_orders` — required by Part 2's draft-order path (the only path that works
  from the CLI; the access error names a "manage draft orders" requirement).
- `write_merchant_managed_fulfillment_orders` — required just to READ
  `order.fulfillmentOrders` in Part 5a; `write_fulfillments` alone gets `ACCESS_DENIED`.

Expect up to two extra browser re-consents when upgrading an existing seed-only auth —
run the full string above once instead.

---

## Part 2 — Create order (draft-order path — live-verified 2026-08-11)

**Do not use `orderCreate` from the CLI.** It introspects as present and the scope can be
granted, but the call fails with `ACCESS_DENIED: … This mutation is only accessible to
apps authenticated using offline tokens` — and `shopify store execute` always uses a
session token. The working path is a draft order completed into a real order (two calls;
everything downstream only needs the final `order.id` / `order.name`).

**Call 1 — create the draft:**

```graphql
mutation CreateDemoDraft($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder { id name }
    userErrors { field message }
  }
}
```

Variables, one order (map the order's `products` entries to seeded variant gids from
`results/shopify-seed.json` — match by **title only**: the manifest's product `id`
(`p1`, `p2`, …) and Shopify's product/variant gids are disjoint namespaces, one never
resolves to the other, so match the manifest product's `name` against
`results/shopify-seed.json`'s `products[].title` and take that product's `variants`
from there. Then pick the variant whose `selectedOptions` match what the order asked
for, or the first listed variant if the order didn't specify size/colour):

```json
{
  "input": {
    "email": "<customer.email>",
    "lineItems": [{ "variantId": "<gid from results/shopify-seed.json>", "quantity": 1 }],
    "shippingAddress": {
      "firstName": "<first>", "lastName": "<last>",
      "address1": "<region-appropriate street>", "city": "<city>",
      "zip": "<zip>", "countryCode": "<GB|US|DE from destination_country>"
    },
    "tags": ["<XXX>"]
  }
}
```

**`tags` carries the same brand code the direct engine puts in its `order_number`
prefix** — derive `<XXX>` with `create-order/SKILL.md`'s existing rule (first three
letters of `brand.name`, uppercased, stripping a leading "www."/article and any
non-letters first; fall back to `ORD` if no brand name is available). Shopify's
`DraftOrderInput`/`OrderInput` have no writable `name` field (confirmed via live
schema introspection 2026-08-19), so the order's display number is entirely the
store's own sequential counter and can't carry a per-brand prefix the way the
direct engine's `order_number` does. Tagging is the equivalent for this path: it
makes the order searchable/filterable by brand in the portal, the same reason the
direct engine's prefix exists, even though it can't sit in the order number itself.

**Call 2 — complete it into a real, paid order:**

```graphql
mutation CompleteDraft($id: ID!, $paymentPending: Boolean) {
  draftOrderComplete(id: $id, paymentPending: $paymentPending) {
    draftOrder { order { id name email } }
    userErrors { field message }
  }
}
```

with `{"id": "<draftOrder.id from call 1>", "paymentPending": false}` —
`paymentPending: false` marks the order paid, replacing the old shape's
`financialStatus: "PAID"` (there is no receipt option on this path; drafts don't send
Shopify receipts).

Write each mutation to a scratch `.graphql` file and the variables to
`orders/<nn>-<label>/draft-create-vars.json`, then run each with:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file <mutation>.graphql \
  --variable-file <vars>.json \
  --allow-mutations
```

**`--allow-mutations` is required** — the CLI refuses the write without it.

**Check `userErrors` on both calls, and on every call in this reference** — an empty array
is the only success signal; a non-empty one means the order was not created and this
order's remaining steps must not run.

**Record `order.name` from call 2** — **this is the `order_number` pL will know.** Note
the store's order-name prefix applies (live run produced `pl-1020`, not `#1001`). It is
also what `orders/<nn>-<label>/order.json` reports as `order_number` for this engine (the
direct engine instead uses `<XXX>-<ts>`; both are the same field, different shapes, and
Phase 3/4 treat them identically).

---

## Part 3 — Poll pL ingestion

Shopify orders reach parcelLab through the live integration sync, not through this
engine's own writes, so there is a real (if usually short) delay before the order document
exists on the pL side. Poll for it rather than assuming it landed:

```bash
for i in $(seq 1 12); do
  sleep 10
  parcellab api request GET "/v4/track/orders/info/?account=<account-id>&order_number=<order.name>" -o json \
    | tee /tmp/order-info.json \
    | grep -q "<order.name>" && break
done
```

`<account-id>` is the manifest's `account.id`; `<order.name>` is the value Part 2 recorded.

**Parameter names live-verified 2026-08-11:** the lookup is `order_number` + `account`
(`orderNo` gets a 400 whose error message helpfully lists every accepted lookup mode:
`order_number + account`, `external_reference + account`, `tracking_number + courier`, …).
Ingestion was near-instant on the live run (first 10 s poll hit). Note for anything
beyond this poll: **integration-ingested orders do NOT appear in `GET /v4/track/orders/`**
(the list endpoint only returns API-created orders) — order-info is the only read that
sees them.

**Success** = the response body actually contains the order document — grepped for the
order number, mirroring Part 6a's pattern below — not merely that the CLI call exited 0. A
GET against a not-yet-ingested order can still exit 0 with an empty or 404-shaped JSON body,
which `&& break` alone would treat as done; grep for content instead.
**On timeout** (12 attempts exhausted): report this order as **not-ingested**, skip Parts
4–6 for it, and continue with the next order — one order's ingestion failure must never
stop another order's run. This is the `"failed_at": "ingestion"` case in `order.json` (see
the Phase 2 Shopify section in `SKILL.md`).

---

## Part 4 — Enrich with fraud data

Generate the order's fraud fragment exactly as the direct engine does, pointed at this
store:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_fraud_fragment.py \
  --level <order.fraud_level> --shop-url "$SHOPIFY_DEMO_STORE" \
  > orders/<nn>-<label>/fraud.json
```

Build `orders/<nn>-<label>/enrich.json` from it — the fragment's `tags` and
`additional_attributes` (already in the API's list-of-`{key,value}` shape) are copied
verbatim as top-level fields, alongside the identifiers **and the required core fields**:

```json
{
  "account": <account-id>,
  "order_number": "<order.name>",
  "destination_country_iso3": "<from manifest>",
  "recipient_email": "<customer.email>",
  "recipient_name": "<customer.name>",
  "tags": ["<from fraud.json>"],
  "additional_attributes": ["<from fraud.json — list of {key, value}>"]
}
```

Send it:

```bash
parcellab api request PUT /v4/track/orders/ --data @orders/<nn>-<label>/enrich.json -o json
```

**Live-verified 2026-08-11:** the PUT is *not* a bare patch — omitting
`recipient_email`/`destination_country_iso3` gets a 400 naming them required, so include
the core fields above (the conductor knows them all from the manifest; no read-back
needed). With those present the call **merges**: the integration-written articles,
address, and tracking placeholder all survived untouched, with `tags` +
`additional_attributes` added on top. One cosmetic note: the write echo shows
`client_key: ""` while the integration order belongs to the Shopify store's client —
eyeball the portal's order view on a first run against a new store.

**Verify from the PUT's own response, not from order-info** (live-verified
2026-08-11): `/v4/track/orders/info/` is the customer-facing projection — it
redacts PII to `<name>`/`<email>` and carries **no order-level `tags` and no
`riskAssessment`**; its `additional_attributes` is a *dict* holding only
`ShopifyOrderTagsAtCreation`, not the API's list-of-`{key,value}`. Checking there
makes a successful enrichment look like a silent failure. The PUT response echoes
the merged document — assert `tags` and the `additional_attributes` keys on it.
Any `tags`/`additional_attributes` found under `trackings[].articles[]` in
order-info are the seeded **product** tags (`pl-demo-seed`,
`pl-prospect-<handle>`), unrelated to the fraud fragment.

**On enrichment failure** (non-2xx, or `userErrors`-equivalent rejection): report this order
as **enrichment-failed**, skip Parts 5–6 for it, continue with the next order. This is the
`"failed_at": "enrichment"` case.

---

## Part 5 — Fulfil with tracking (candidate mutation)

### 5a. Look up the fulfillment order

Read-only, so **no `--allow-mutations`**:

```graphql
query GetFO($id: ID!) {
  order(id: $id) {
    fulfillmentOrders(first: 5) {
      nodes { id lineItems(first: 20) { nodes { id remainingQuantity } } }
    }
  }
}
```

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/get-fo.graphql --variable-file /tmp/get-fo-vars.json
```

`$id` is the `order.id` gid Part 2 recorded. The `fulfillmentOrders` and their
`lineItems` ids are what Part 5b's `fulfillmentOrderLineItems` needs — Shopify assigns
these itself; do not construct them.

### 5b. Fulfil — live-verified 2026-08-11

`fulfillmentCreate` exists and works exactly as below (no V2 substitution needed on the
`2026-07`-era schema). Two live gotchas already folded into Part 1's scope set: Part 5a's
read needs `write_merchant_managed_fulfillment_orders`, and the `company` string sent here
is NOT what pL stores (see 6b — live run: sent `DPD`, pL stored courier `dpd`).

```graphql
mutation Fulfil($fulfillment: FulfillmentInput!) {
  fulfillmentCreate(fulfillment: $fulfillment) {
    fulfillment { id trackingInfo { number company } }
    userErrors { field message }
  }
}
```

Variables (one shipment):

```json
{
  "fulfillment": {
    "lineItemsByFulfillmentOrder": [
      {
        "fulfillmentOrderId": "<gid from 5a>",
        "fulfillmentOrderLineItems": [{ "id": "<gid from 5a>", "quantity": 1 }]
      }
    ],
    "trackingInfo": {
      "number": "<randomised, format-correct, UNIQUE ACROSS THE WHOLE RUN>",
      "company": "<carrier pL recognises — the shipment's courier from the manifest, e.g. UPS/DPD>"
    },
    "notifyCustomer": false
  }
}
```

**Tracking numbers must be unique across every shipment in the run, not merely
random.** parcelLab keys a tracking record by `courier` + `tracking_number`, so
two shipments sharing a number collide: events pushed for one land on the other,
and the run reports success while one arc silently overwrites another. Seeding a
PRNG deterministically is the trap — a resumed or re-run Part 5 replays the same
sequence and re-issues a number an earlier order already holds (hit live
2026-08-11: orders 1 and 2A both drew `01524417519594`). Keep a set of the run's
issued numbers, generate against it, and audit before Part 6.

To repair a collision found after fulfilment, update the tracking rather than
re-fulfilling:

```graphql
mutation TIU($fulfillmentId: ID!, $trackingInfoInput: FulfillmentTrackingInput!, $notifyCustomer: Boolean) {
  fulfillmentTrackingInfoUpdate(fulfillmentId: $fulfillmentId, trackingInfoInput: $trackingInfoInput, notifyCustomer: $notifyCustomer) {
    fulfillment { id trackingInfo { number company } }
    userErrors { field message }
  }
}
```

**`trackingInfo` reads back as a LIST**, both here and on `fulfillmentCreate` —
the selection set above looks like a single object but is not. Index it.

Write the mutation to `/tmp/fulfil.graphql` and the variables to (per shipment)
`orders/<nn>-<label>/fulfil-<shipment>-vars.json`, then:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/fulfil.graphql \
  --variable-file orders/<nn>-<label>/fulfil-<shipment>-vars.json \
  --allow-mutations
```

`notifyCustomer: false` on every call — Shopify's own fulfillment email is not part of this
demo's comms story; the pL Journey comms triggered in Part 6 are.

**For a split order, make two separate `fulfillmentCreate` calls**, one per shipment, each
with its own randomised tracking number and its own `fulfillmentOrderLineItems` covering
only that shipment's line items — the same division `order-lifecycle`'s *Split shipments*
section uses for `add_tracking`, applied here to fulfilments instead.

**Check `userErrors` on every call.** **On fulfilment failure**: report this order as
**fulfilment-failed**, skip Part 6 for it, continue with the next order. This is the
`"failed_at": "fulfilment"` case.

---

## Part 6 — Wait for tracking in pL, then push events

### 6a. Poll for the tracking

Same polling pattern as Part 3 (up to 12 × 10s), now against the same order-info lookup,
waiting until the tracking record carrying this shipment's tracking number appears in the
response rather than until the order document merely exists:

```bash
for i in $(seq 1 12); do
  sleep 10
  parcellab api request GET "/v4/track/orders/info/?account=<account-id>&order_number=<order.name>" -o json \
    | tee /tmp/order-info.json \
    | grep -q "<tracking number from Part 5b>" && break
done
```

(Live run: the tracking appeared on the first 10 s poll.)

On timeout: same as Part 3 — report not-ingested-for-tracking, skip pushing events for this
shipment, continue with the run's other orders/shipments.

### 6b. Read the pL courier from that same response — never guess it

The `company` string Part 5b sent (e.g. `UPS`) is the Shopify carrier name, not necessarily
the courier code parcelLab's integration stores against the tracking. **Read the actual
`courier` value out of the order-info response fetched in 6a** and use that exact string —
this is the identifier order-lifecycle's own `status-codes.md` requires (`courier` +
`tracking_number`, never `account` + `order_number`) for every event push.

**Live-verified mapping (2026-08-11):** company `DPD` → pL courier **`dpd`** — NOT the
`dpd-uk` code the direct engine uses for the same carrier. Guessing would have pushed
every event at a tracking that doesn't exist; this step is not optional.

### 6c. Build and push events exactly as the direct engine's driver does

**These files are always written fresh here — never pre-built and never reused.** The
conductor's Phase 0 pre-build deliberately excludes this path: `tracking_number` does not
exist until Part 5b's `fulfillmentCreate` assigns it, and `courier` is only knowable after
6b reads it back. Both are fields in every event file.

Write `orders/<nn>-<label>/NN-<status>.json` files for the chosen scenario, one per stage,
using the `courier` from 6b and the `tracking_number` from Part 5b — same rules as
`order-lifecycle`'s *Event sequence* (no `event_timestamp`, no `account` in the file; the
driver injects both at send time) and, for split orders, the same interleaving as its
*Split shipments* section, using `${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md`
for the valid `event_status` enum and the proven happy/unhappy sequences.

Then launch the driver, one per order, exactly as the direct engine does:

```bash
PARCELLAB_ACCOUNT_ID="<manifest account.id>" EVENTS_DIR="orders/<nn>-<label>" GAP_SECONDS="<300 standard | 60 fast, from the manifest's run.pace>" \
  bash ${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/run-lifecycle.sh
```

`PARCELLAB_ACCOUNT_ID` is set inline from the manifest's `account.id` — the
confirmed target account, not whatever the ambient env var happens to hold.
`GAP_SECONDS` likewise comes from the manifest's `run.pace`: `standard` (or an
absent `run.pace`) → 300, `fast` → 60. At `fast`, Beat 2's report must note
that comm ordering was not guaranteed.

**Watching the drivers:** match on `bash .*run-lifecycle.sh`, not on
`run-lifecycle.sh` alone — a `pgrep -f run-lifecycle.sh` in a waiter loop also matches
the waiter's own shell command line, so it counts itself and never reaches zero
(observed 2026-08-11: the wait never returned). Note also that a driver started in a
Bash-tool foreground call can outlive that call's timeout and keep running detached —
a timed-out driver is not necessarily a stopped one; check before relaunching.

Run it with the Bash tool's `run_in_background`; do a `DRYRUN=1` pass first — **with
`GAP_SECONDS=0`**. The driver sleeps before *every* event including the first, and honours
that sleep in dry-run too, so a dry pass at standard pace costs the same wall clock as the
real run (a 5-event order = 15 minutes; it timed out live on 2026-08-11). `GAP_SECONDS=0`
here does not violate the standard-pace rule: a dry run sends nothing, so comm ordering is
not in play. All orders'
drivers run concurrently once each has reached this point — a failure earlier in one
order's Parts 2–5 must never block another order's driver from launching.

### 6d. Write `order.json`

Once the driver is launched (or the order was marked partial at whichever part failed),
write `orders/<nn>-<label>/order.json` in the same shape the direct engine writes:
`{"order_number", "customer": {"name","email"}, "cdc_slot", "fraud_level", "trackings":
[{"shipment", "courier", "tracking_number"}]}`, with `order_number` = the Shopify
`order.name` from Part 2 (e.g. `"#1001"`). A partial order additionally carries `"status":
"partial", "failed_at": "<ingestion|enrichment|fulfilment>"` and has no `trackings` entry
for the shipment(s) that never got events pushed.
