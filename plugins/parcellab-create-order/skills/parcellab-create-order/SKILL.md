---
name: parcellab-create-order
description: Create a real order in the user's ParcelLab account via the production Order API. Use whenever the user wants to create, push, send, or POST an order to ParcelLab — including phrases like "create a parcellab order", "push a test order to PL", "send an order to parcellab for [country/scenario]", "create a PL shipment", or any request to generate a tracked or untracked order in their parcelLab account. The skill fills in realistic dummy data when the user only provides partial context, so trigger it even when the user has not specified every field.
---

# parcelLab — Create Order

Create or update an order in the user's ParcelLab account by sending a single `PUT` to the production Order API. The user normally gives a small amount of context (a country, a scenario, "make it look like a returns case", etc.) and you fill the rest with plausible dummy data.

The full API spec lives at <https://docs.parcellab.com/docs/developers/orders/full-order-api-spec> — consult it if the user asks for a field you don't recognise. Don't try to mirror the entire spec inline; this file only covers the happy path.

## Workflow

1. **Confirm credentials are present.** Check `PARCELLAB_USER_ID` and `PARCELLAB_TOKEN` are set in the environment. If either is missing, stop and tell the user — don't try to guess them or proceed.

   ```bash
   test -n "$PARCELLAB_USER_ID" && test -n "$PARCELLAB_TOKEN" && echo ok
   ```

2. **Gather context from the user's message.** Look for: destination country, courier, scenario (e.g. "delivered", "in transit", "return"), number of items, tracking vs untracked, language. Anything they don't mention, you make up — see *Defaults & dummy data* below.

2a. **Always confirm the carrier before building a tracked order.** Even if the user's message implies a country (and therefore a sensible default courier), explicitly ask which courier they want — state the default you'd otherwise use and let them confirm or override. Skip this only for untracked orders (no `mutations`). Never silently pick a courier for a tracked order.

3. **Build the payload.** Construct a single JSON object following the structure in *Payload shape*. Save it to a temp file so `curl` can use `--data-binary @file` and you avoid shell-quoting pain:

   ```bash
   PAYLOAD_FILE=$(mktemp -t pl-order.XXXXXX.json)
   # write JSON to $PAYLOAD_FILE using the Write tool
   ```

4. **Show the payload and ask the user to confirm.** Display the JSON (or a tight summary of the key fields — order_number, recipient, country, courier, tracking number, article count) and ask "send this to ParcelLab?" Wait for an affirmative reply before step 5. This matters because every successful PUT writes a real order to their production account.

5. **Send it.** PUT to `https://api.parcellab.com/v4/track/orders/` with the encoded auth header. Capture status and body:

   ```bash
   AUTH=$(printf '%s:%s' "$PARCELLAB_USER_ID" "$PARCELLAB_TOKEN" | base64)
   curl -sS -X PUT "https://api.parcellab.com/v4/track/orders/" \
     -H "Authorization: Parcellab-API-Token $AUTH" \
     -H "Content-Type: application/json" \
     -w "\n---HTTP %{http_code}---\n" \
     --data-binary @"$PAYLOAD_FILE"
   ```

   `base64` on macOS produces single-line output by default, which is what the API wants. If you ever need to be safe, pipe through `tr -d '\n'`.

6. **Report back.** Tell the user:
   - HTTP status (200 update / 201 create / 4xx error)
   - The returned `external_id` and `order_number`
   - Any `mutations[].result.warnings` or `errors` — these come back as 200 but mean the tracking didn't fully apply
   - A link to the order in the parcelLab dashboard if helpful: `https://portal.parcellab.com/` (you don't know the exact deep link format; just point them at the portal)

   Then delete the temp payload file.

## Payload shape

Minimum viable order — required by the spec:

```json
{
  "account": 12345,
  "order_number": "CLAUDE-1718553600",
  "destination_country_iso3": "DEU",
  "recipient_email": "anna.schmidt@example.com"
}
```

A realistic tracked order with one article:

```json
{
  "account": 12345,
  "order_number": "CLAUDE-1718553600",
  "external_reference": "CLAUDE-1718553600",
  "destination_country_iso3": "DEU",
  "recipient_email": "anna.schmidt@example.com",
  "recipient_name": "Anna Schmidt",
  "language_iso2": "de",
  "timezone": "Europe/Berlin",
  "order_date": "2026-06-16T10:30:00Z",
  "order_total_amount": "89.90",
  "order_currency": "EUR",
  "channel": "webshop",
  "shipping_address": {
    "first_name": "Anna",
    "last_name": "Schmidt",
    "address_line": "Friedrichstraße 123",
    "postal_code": "10117",
    "city": "Berlin",
    "country_iso3": "DEU"
  },
  "articles_order": [
    {
      "line_item_id": "1",
      "sku": "TS-BLK-M",
      "article_name": "Classic T-Shirt — Black, M",
      "quantity": 1,
      "unit_price": "89.90",
      "article_image_url": "https://picsum.photos/seed/tshirt/400/400"
    }
  ],
  "mutations": [
    {
      "type": "add_tracking",
      "tracking": {
        "tracking_number": "00340434292135100186",
        "courier": "dhl-germany",
        "recipient_postal_code": "10117",
        "destination_country_iso3": "DEU",
        "language_iso2": "de",
        "articles": [
          {
            "line_item_id": "1",
            "sku": "TS-BLK-M",
            "article_name": "Classic T-Shirt — Black, M",
            "quantity": 1,
            "unit_price": "89.90"
          }
        ]
      }
    }
  ]
}
```

Notes:
- `account` is the numeric `PARCELLAB_USER_ID`.
- `order_number` must be unique per account. **Prefix it with the first three letters of the business/brand name, uppercased, then a timestamp** — `<XXX>-$(date +%s)` — so orders are easy to find in the portal (e.g. Moonpig → `MOO-1784828280`, Nike → `NIK-…`). Strip leading "www."/articles and non-letters before taking the three letters; if no brand is given, fall back to `ORD-$(date +%s)`. Unless the user gives an explicit order number, always follow this scheme.
- `line_item_id` must be unique within `articles_order`.
- **Always populate each `add_tracking` mutation's `tracking.articles` with the items that ship in that parcel** (each entry needs at least `line_item_id`, `sku`, `article_name`, `quantity`, `unit_price`; `line_item_id` must match the corresponding `articles_order` entry). `articles_order` is the full order; `tracking.articles` is what's in the box. The parcelLab Returns Order API derives returnable items from `tracking.articles`, so leaving it empty means the returns portal shows **no selectable items** even though the products are present in `articles_order`.
- For an untracked order, omit `mutations` entirely.
- For an order with multiple articles or shipments, repeat the structure — keep `line_item_id`s aligned between `articles_order` and `tracking.articles`. For a split shipment, each `add_tracking` mutation's `tracking.articles` holds only the items in that parcel.

## Additional recipients (Dynamic Recipients)

parcelLab calls this feature "Dynamic Recipients" in their portal/docs, but the API field is `additional_recipients`. See <https://docs.parcellab.com/docs/engage/messages-and-journeys/configuration/dynamic-recipients> for the canonical reference.

How it works end-to-end:

1. **You send `additional_recipients`** at order level and/or tracking level via the v4 Order API. Each entry is `{ "role": "<key>", "email": "<address>" }`.
2. **A Journey in the parcelLab portal** must be configured with `advancedRecipients` listing the same role key. Without a matching Journey, the field saves on the API but no notifications fire — it's inert data.
3. **When the Journey trigger fires** (e.g. shipment delivered), parcelLab looks up additional recipients on the relevant record whose `role` matches the Journey's `advancedRecipients` list, and sends to those emails alongside the customer.

**Critical rule about `role`:** it must match exactly — case-sensitive, no spelling variation. If the portal Journey expects `giftRecipient` and the payload sends `gift_recipient` or `GiftRecipient`, no recipient is selected. Roles are commonly camelCase in parcelLab's examples (`warehouseContact`, `giftRecipient`, `supplierContact`).

**Which level to send at:** "Use the location that matches the record used by your notification flow. If the notification is triggered by a shipment or return tracking, include the roles on that tracking." In practice, write to both order and tracking levels — it's cheap, and you don't always know which level the Journey targets.

```json
"additional_recipients": [
  { "role": "giftRecipient", "email": "extra@example.com" }
],
"mutations": [
  {
    "type": "add_tracking",
    "tracking": {
      "tracking_number": "...",
      "courier": "...",
      "additional_recipients": [
        { "role": "giftRecipient", "email": "extra@example.com" }
      ]
    }
  }
]
```

**Before sending, when the user asks for an additional recipient:**

- **Ask for or confirm the role key** the user's account Journey is configured with. Don't invent one. If they don't know, point them at the portal Journey config or suggest `giftRecipient` / `warehouseContact` / similar camelCase from the docs as a starting suggestion.
- **Preserve the user's exact spelling and case** — even if it looks misspelled (e.g. `GiftReciever`). The match is literal; "fixing" it will break things if the Journey uses the same misspelling.
- **Flag the dependency on Journey config**: tell the user "this only fires notifications if a Journey in your account is configured with `advancedRecipients: ["<the role>"]`." Don't promise an email will go out.

If the order has no `mutations` (untracked), the order-level field is the only place to put it — but the Journey must be one that triggers off order events rather than tracking events.

## Defaults & dummy data

When the user gives partial context, infer the rest from the destination country. If they give nothing at all, default to a German order.

| Country | Language | Currency | Timezone        | Courier         | Example postcode/city |
|---------|----------|----------|-----------------|-----------------|------------------------|
| DEU     | de       | EUR      | Europe/Berlin   | dhl-germany     | 10117 Berlin           |
| GBR     | en       | GBP      | Europe/London   | royal-mail      | SW1A 1AA London        |
| USA     | en       | USD      | America/New_York| usps            | 10001 New York, NY     |
| FRA     | fr       | EUR      | Europe/Paris    | colissimo       | 75001 Paris            |
| NLD     | nl       | EUR      | Europe/Amsterdam| postnl          | 1011 AB Amsterdam      |
| AUT     | de       | EUR      | Europe/Vienna   | dhl-austria     | 1010 Vienna            |

For other countries: pick a courier that actually operates there (don't invent codes — `dhl`, `ups`, `fedex`, `dpd`, `gls` are safe fallbacks) and use a realistic capital-city address. If unsure, ask before sending rather than guess.

**Tracking numbers** should look like the real thing for the courier — e.g. DHL Germany uses 20-digit numeric, Royal Mail uses `XX#########GB`, USPS uses 22-digit numeric, UPS starts with `1Z`. **Always randomise the tracking number** — never reuse a fixed/hardcoded value. A `tracking_number` + `courier` pair that already exists on the account causes a `400 validation_error` ("tracking_number + courier already belongs to order …"). Generate a fresh random-but-format-correct number every time, e.g.:

```bash
# Royal Mail: RM#########GB
printf 'RM%09dGB\n' $(( (RANDOM*RANDOM) % 1000000000 ))
# DHL Germany: 20-digit numeric
printf '00%018d\n' $(( (RANDOM*RANDOM*RANDOM) % 1000000000000000000 ))
```

They don't need to be live — just unique and correctly formatted for the chosen courier.

**Recipient names** should match the country (Anna Schmidt for DE, James Wilson for GB, etc.) and the email should look domain-plausible (`example.com` is acceptable).

**Article images** — `https://picsum.photos/seed/<slug>/400/400` works reliably and gives a different image per slug.

## Common variations the user might ask for

- **"Make it look like a returns case"** — add `"is_return": true` inside the `tracking` object, set `cancelled_reason` on the order if they want it cancelled too.
- **"Multiple items"** — add more entries to `articles_order`, each with a unique `line_item_id`.
- **"Split shipment"** — emit two `add_tracking` mutations, each with a `tracking.articles` array referencing the relevant `line_item_id`s; set `has_multiple_shipments: true` on the order.
- **"No tracking, just the order"** — omit `mutations`.
- **"Use order number X"** — use exactly what they gave; don't append a timestamp.
- **"Send to test/staging"** — there's no separate test env on this skill. Tell the user this skill only targets production (`api.parcellab.com`) and ask if they really want to proceed.

## Failure modes to watch for

- **HTTP 400 with `client_error`** — usually a missing required field, bad country code (must be 3-letter ISO), or an invalid `recipient_email`. Read the `errors` array and fix the offending field rather than retrying blind.
- **HTTP 401/403** — credentials are wrong or the token lacks order-write scope. Don't retry; surface the error.
- **HTTP 200 with `mutations[0].result.success: false`** — the order saved but tracking didn't attach. Common causes: courier code not recognised, tracking number conflicts with an existing order on the account. Report the warning verbatim.

If `curl` itself fails (no network, DNS), surface the error; don't retry silently.
