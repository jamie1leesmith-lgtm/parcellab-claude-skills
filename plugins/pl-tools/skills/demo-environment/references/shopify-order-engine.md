# Shopify order engine (retain-shopify path)

Runs from Phase 2 of the `demo-environment` conductor when `results/shopify-seed.json`
shows `"status": "ok"`. For each manifest order, in its `orders/<nn>-<label>/` directory,
work through the six parts below in order. The output must land in the same two places the
direct engine writes to — `orders/<nn>-<label>/order.json` and, once every order is
processed, `results/linked-orders.json` — so Phase 3 and Phase 4 never need to know which
engine built an order.

Every relative path in this doc (`orders/<nn>-<label>/`, `results/…`) resolves against the
run directory — `cd` there first, or use absolute paths.

> **Both GraphQL mutations below are CANDIDATES, not confirmed shapes.** Shopify's Admin
> GraphQL schema is versioned and drifts store to store (see `shopify-seed`'s
> `references/mutation-template.md`, verified against a specific `2026-07` schema — this
> file has not had that live pass yet). **Introspect the target store's schema before the
> first `orderCreate` call and before the first `fulfillmentCreate` call in every run** —
> never assume either mutation exists just because it is documented here. If introspection
> shows the field is missing, fall back per the note in that part and **write the
> substitution into this file** so the next run starts from what actually worked, not from
> what was guessed.

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
    --scopes write_products,write_inventory,read_orders,write_orders,write_fulfillments
  ```

  **This opens a browser consent window — warn the user before running it**, the same way
  `shopify-seed` Step 1 warns before its own first-time auth.

**Record a finding here once this has run live**: which of the five scopes above the
store's auth actually needed (a store already seeded via `shopify-seed` already has
`write_products,write_inventory` — this run may only add `read_orders,write_orders,
write_fulfillments`). Unverified as of this writing; confirm on the retain-shopify run in
the staged live verification pass and replace this paragraph with the real answer.

---

## Part 2 — Create order (candidate mutation)

**Verify before first use.** Introspect the store's `Mutation` type and check `orderCreate`
is in the field list:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query '{ __type(name: "Mutation") { fields { name } } }'
```

- **`orderCreate` present** → use it, below.
- **`orderCreate` absent** → fall back to `draftOrderCreate` (build the draft with the same
  line items and addresses) followed by `draftOrderComplete` (which converts it to a real
  order and returns the same `order { id name email }` shape). **Record this substitution
  in this file** — it changes the mutation name and adds a second call, but the rest of
  this reference (polling, enrichment, fulfilment) is unaffected since it only depends on
  `order.id` and `order.name`.

```graphql
mutation CreateDemoOrder($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
  orderCreate(order: $order, options: $options) {
    order { id name email }
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
  "order": {
    "email": "<customer.email>",
    "lineItems": [{ "variantId": "<gid from results/shopify-seed.json>", "quantity": 1 }],
    "shippingAddress": {
      "firstName": "<first>", "lastName": "<last>",
      "address1": "<region-appropriate street>", "city": "<city>",
      "zip": "<zip>", "countryCode": "<GB|US|DE from destination_country>"
    },
    "financialStatus": "PAID"
  },
  "options": { "sendReceipt": false, "sendFulfillmentReceipt": false }
}
```

Write the mutation above to `/tmp/create-order.graphql` and the variables to
`orders/<nn>-<label>/create-order-vars.json`, then:

```bash
shopify store execute -s "$SHOPIFY_DEMO_STORE" \
  --query-file /tmp/create-order.graphql \
  --variable-file orders/<nn>-<label>/create-order-vars.json \
  --allow-mutations
```

**`--allow-mutations` is required** — the CLI refuses the write without it.

**Check `userErrors` on this call, and on every call in this reference** — an empty array
is the only success signal; a non-empty one means the order was not created and this
order's remaining steps must not run.

**Record `order.name`** (e.g. `#1001`) — **this is the `order_number` pL will know.** It is
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
  parcellab api request GET "/v4/track/orders/info/?account=<account-id>&orderNo=<order.name>" -o json \
    | tee /tmp/order-info.json \
    | grep -q "<order.name, digits only e.g. 1001>" && break
done
```

`<account-id>` is the manifest's `account.id`; `<order.name>` is the value Part 2 recorded
(URL-encode the leading `#` as `%23` if the CLI does not do this automatically — check the
literal request the CLI sends before assuming it needs manual encoding).

This is the same identifier pattern (account + order number) order-lifecycle's own
Reporting section describes for a public order-info lookup — **it does not pin an exact
query-parameter spelling**, so treat the parameter names above as the current best guess,
not a confirmed contract. Confirm them on the first live retain-shopify run and correct this
paragraph (and the command above) to match whatever the CLI actually accepts if it differs.

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
`additional_attributes` become top-level fields alongside the account and order identifier:

```json
{
  "account": <account-id>,
  "order_number": "<order.name>",
  "tags": ["<from fraud.json>"],
  "additional_attributes": { "riskAssessment": ["<from fraud.json>"] }
}
```

Send it:

```bash
parcellab api request PUT /v4/track/orders/ --data @orders/<nn>-<label>/enrich.json -o json
```

**This call is assumed to be an upsert** — merging `tags`/`additional_attributes` onto the
order pL already ingested in Part 3, leaving every other field (address, line items,
tracking) untouched. That assumption is **unverified as of this writing**; it is scheduled
to be confirmed on Run 3 of the staged live verification pass. **If it turns out to replace
rather than merge**: before sending, read the order back (the same GET as Part 3) and fold
its existing fields into this payload so the PUT doesn't blank them out — then record
which behaviour was actually observed, here, so this stops being an open question.

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

### 5b. Fulfil — verify before first use

Introspect (same query as Part 2) and check `fulfillmentCreate` is present. **If it is
absent**, introspect for `fulfillmentCreateV2` instead, use it in its place, and **record
the substitution in this file** — the field name changes but the variable shape below is
expected to carry over unchanged.

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
      "number": "<randomised, format-correct>",
      "company": "<carrier pL recognises — the shipment's courier from the manifest, e.g. UPS/DPD>"
    },
    "notifyCustomer": false
  }
}
```

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
  parcellab api request GET "/v4/track/orders/info/?account=<account-id>&orderNo=<order.name>" -o json \
    | tee /tmp/order-info.json \
    | grep -q "<tracking number from Part 5b>" && break
done
```

On timeout: same as Part 3 — report not-ingested-for-tracking, skip pushing events for this
shipment, continue with the run's other orders/shipments.

### 6b. Read the pL courier from that same response — never guess it

The `company` string Part 5b sent (e.g. `UPS`) is the Shopify carrier name, not necessarily
the courier code parcelLab's integration stores against the tracking. **Read the actual
`courier` value out of the order-info response fetched in 6a** and use that exact string —
this is the identifier order-lifecycle's own `status-codes.md` requires (`courier` +
`tracking_number`, never `account` + `order_number`) for every event push.

### 6c. Build and push events exactly as the direct engine's driver does

Write `orders/<nn>-<label>/NN-<status>.json` files for the chosen scenario, one per stage,
using the `courier` from 6b and the `tracking_number` from Part 5b — same rules as
`order-lifecycle`'s *Event sequence* (no `event_timestamp`, no `account` in the file; the
driver injects both at send time) and, for split orders, the same interleaving as its
*Split shipments* section, using `${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/status-codes.md`
for the valid `event_status` enum and the proven happy/unhappy sequences.

Then launch the driver, one per order, exactly as the direct engine does:

```bash
PARCELLAB_ACCOUNT_ID="<manifest account.id>" EVENTS_DIR="orders/<nn>-<label>" GAP_SECONDS="<gap, default 180>" \
  bash ${CLAUDE_PLUGIN_ROOT}/skills/order-lifecycle/references/run-lifecycle.sh
```

`PARCELLAB_ACCOUNT_ID` is set inline from the manifest's `account.id` — the
confirmed target account, not whatever the ambient env var happens to hold.

Run it with the Bash tool's `run_in_background`; do a `DRYRUN=1` pass first. All orders'
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
