---
name: create-order
description: Create a real order in the user's ParcelLab account via the production Order API. Use whenever the user wants to create, push, send, or POST an order to ParcelLab — including phrases like "create a parcellab order", "push a test order to PL", "send an order to parcellab for [country/scenario]", "create a PL shipment", or any request to generate a tracked or untracked order in their parcelLab account. The skill fills in realistic dummy data when the user only provides partial context, so trigger it even when the user has not specified every field.
---

# parcelLab — Create Order

Create or update an order in the user's ParcelLab account by sending a single `PUT` to the production Order API. The user normally gives a small amount of context (a country, a scenario, "make it look like a returns case", etc.) and you fill the rest with plausible dummy data.

The full API spec lives at <https://docs.parcellab.com/docs/developers/orders/full-order-api-spec> — consult it if the user asks for a field you don't recognise. Don't try to mirror the entire spec inline; this file only covers the happy path.

## Workflow

1. **Resolve the account and check the CLI.** See *Account resolution and confirmation* below for which account to use and how to confirm it. There is no token — writes go through the `parcellab` CLI's own login.

   ```bash
   test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && command -v parcellab >/dev/null && parcellab auth show >/dev/null 2>&1 && echo ok
   ```

   If any part fails, follow *If credentials are missing* below — don't guess values and don't proceed.

2. **Gather context from the user's message.** Look for: destination country, courier, scenario (e.g. "delivered", "in transit", "return"), number of items, tracking vs untracked, language. Anything they don't mention, you make up — see *Defaults & dummy data* below — **except the destination country, which you always ask for if they haven't named one.**

2a. **Always confirm the carrier before building a tracked order.** Even if the user's message implies a country (and therefore a sensible default courier), explicitly ask which courier they want — state the default you'd otherwise use and let them confirm or override. Skip this only for untracked orders (no `mutations`). Never silently pick a courier for a tracked order.

2b. **Confirm the articles and their categories together, before building the
   payload.** `article_category` is what returns-portal reason filters key on,
   so never leave it off and never pick it silently — but the articles
   themselves don't exist yet at this point in the workflow either (step 3,
   *Build the payload*, is where they'd otherwise first appear), so propose
   both the specific articles and a baseline category in the same exchange.
   See *Article categories* below.

2c. **Offer the extras gate before building anything.** Ask once whether anything
   else should go on the order, then apply what the user picks — see *Extra order
   information* below. The default is send-as-is; skipping takes one word.

3. **Build the payload.** Construct a single JSON object following the structure in *Payload shape*. Save it to a temp file so the CLI can use `--data @file` and you avoid shell-quoting pain:

   ```bash
   PAYLOAD_FILE=$(mktemp -t pl-order.XXXXXX.json)
   # write JSON to $PAYLOAD_FILE using the Write tool
   ```

4. **Show the payload and ask the user to confirm.** Display a summary that
   itemises, field by field:
   - order_number, recipient, destination country, courier, tracking number
   - every article with its `article_category`
   - **every extra agreed at step 2c, with its actual value**

   An extra that was discussed but doesn't appear here is a defect: this summary
   is the last point where a wrong promise date or a mistyped recipient role is
   catchable, and both are invisible in the API's success response. Offer the
   full JSON on request. Then ask "send this to ParcelLab?" and wait for an
   affirmative reply before step 5 — every successful PUT writes a real order to
   their production account.

5. **Send it** through the CLI. The path is served by the CLI's default host — **never add `--base-url`**; overriding the host breaks the CLI's own edit-mode account check and every write fails with a misleading `HTTP 404` about child accounts.

   ```bash
   parcellab api request PUT /v4/track/orders/ --data @"$PAYLOAD_FILE" -o json
   ```

   The CLI is already authenticated (OAuth) and its edit-mode guard checks
   `payload.account` before anything is sent — a payload naming any account other
   than the restricted one is refused locally. That is expected behaviour, not an
   error to work around: fix the account, don't loosen the guard.

6. **Report back.** Tell the user:
   - Whether it succeeded (the CLI prints the saved order as JSON on success and a clear `Error:` line on failure)
   - The returned `external_id` and `order_number`
   - Any `mutations[].result.warnings` or `errors` — these come back as 200 but mean the tracking didn't fully apply
   - A link to the order in the parcelLab dashboard if helpful: `https://portal.parcellab.com/` (you don't know the exact deep link format; just point them at the portal)

   Then delete the temp payload file.

## Account resolution and confirmation

**Resolve the account, in this order:**

1. An account the user named explicitly in this conversation.
2. `$PARCELLAB_ACCOUNT_ID`.
3. `$PARCELLAB_USER_ID` (legacy alias — accept it, never write it).

If none resolve, set the default up now: ask which account they want, find it
with `parcellab account account search --name "<term>"`, and offer to write it
to the `env` block of `~/.claude/settings.json` as `PARCELLAB_ACCOUNT_ID`. Then
tell them to quit and reopen the app — environment variables are only read at
startup.

Point the CLI's write guard at that same account too:
`parcellab settings edit-mode set account-restricted --account <id>`, then confirm
it took with `parcellab settings edit-mode show`. Use their own leaf account — a
parent account does not work. Without this the CLI may permit writes to a
colleague's demo account and block their own, and that stays invisible until a
write fails.

**Confirm before the first write of the conversation.** Resolve the account's
human name with `parcellab account account show <id>` and ask:

> Using **<account name>** (`<id>`) — your default. Correct, or use a different
> account?

A bare account number means nothing to a human reader; a wrong *name* is
obvious. Do not skip the name lookup.

Rules:

- Confirm once per conversation, before the first write — not before every call.
- An account the user names explicitly still gets confirmed, the same way.
- Read-only inspection needs no confirmation. Every write does.
- **Also before the first write:** run `parcellab settings edit-mode show`. It
  must say `account-restricted` scoped to this same account. If it says
  anything else — unrestricted, read-only, or a different account — stop and
  offer to fix it (`parcellab settings edit-mode set account-restricted
  --account <id>`) before writing anything. This guard is the only thing that
  physically stops a write landing in a colleague's account; a write must never
  proceed while it is off or aimed elsewhere.

### If credentials are missing

Stop. Do not guess values and do not proceed. Everything this skill needs comes
from the parcelLab CLI — there is no token.

1. `command -v parcellab` — if missing, the CLI needs installing (internal users:
   the `parcellab-cli` repo). Stop and say so.
2. `parcellab auth show` — if not authenticated, run `parcellab auth login`
   **in the background** (it blocks while the browser waits for approval) and
   tell the user their browser will open.
3. No default account? Run the account setup above, or suggest `/pl-setup`,
   which does all of this in one pass.

> **If you have just run setup, quit and reopen the app** — environment
> variables are only read at startup. (CLI login and edit-mode take effect
> immediately; only the `settings.json` env block needs the restart.)

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
      "line_item_id": "TS-BLK-M",
      "sku": "TS-BLK-M",
      "article_name": "Classic T-Shirt — Black, M",
      "article_category": "fashion",
      "quantity": 1,
      "unit_price": "89.90",
      "article_image_url": "https://picsum.photos/seed/tshirt/400/400",
      "articleNo": "TS-BLK-M",
      "articleName": "Classic T-Shirt — Black, M",
      "articleImageUrl": "https://picsum.photos/seed/tshirt/400/400",
      "articleCategory": "fashion",
      "price": "89.90"
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
            "line_item_id": "TS-BLK-M",
            "sku": "TS-BLK-M",
            "article_name": "Classic T-Shirt — Black, M",
            "article_category": "fashion",
            "quantity": 1,
            "unit_price": "89.90",
            "articleNo": "TS-BLK-M",
            "articleName": "Classic T-Shirt — Black, M",
            "articleCategory": "fashion",
            "price": "89.90"
          }
        ]
      }
    }
  ]
}
```

Notes:
- **Dual-family article keys are required for comms to render articles**
  (live-verified 2026-08-11): the message templates read the legacy camelCase
  fields (`articleNo`, `articleName`, `articleImageUrl`, `articleCategory`,
  `price`) from the stored document, and the v4 snake_case fields alone leave
  them unset — the article block in every email comes out empty. The v4 API
  passes the camelCase keys through verbatim, so duplicate each article's
  data in both families at BOTH levels, and put the real SKU/article number
  in `line_item_id` (not a sequence number) — parcelLab's own Custom Demo
  Creator does the same.
- `account` is the numeric account id resolved in *Account resolution and confirmation* — `${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`.
- `order_number` must be unique per account. **Prefix it with the first three letters of the business/brand name, uppercased, then a timestamp** — `<XXX>-$(date +%s)` — so orders are easy to find in the portal (e.g. Moonpig → `MOO-1784828280`, Nike → `NIK-…`). Strip leading "www."/articles and non-letters before taking the three letters; if no brand is given, fall back to `ORD-$(date +%s)`. Unless the user gives an explicit order number, always follow this scheme.
- `line_item_id` must be unique within `articles_order`.
- **Always populate each `add_tracking` mutation's `tracking.articles` with the items that ship in that parcel** (each entry needs at least `line_item_id`, `sku`, `article_name`, `quantity`, `unit_price`; `line_item_id` must match the corresponding `articles_order` entry). `articles_order` is the full order; `tracking.articles` is what's in the box. The parcelLab Returns Order API derives returnable items from `tracking.articles`, so leaving it empty means the returns portal shows **no selectable items** even though the products are present in `articles_order`.
- **`article_category` belongs on every article at both levels** — see *Article
  categories*. It drives the returns portal's return-reason filters.
- For an untracked order, omit `mutations` entirely.
- For an order with multiple articles or shipments, repeat the structure — keep `line_item_id`s aligned between `articles_order` and `tracking.articles`. For a split shipment, each `add_tracking` mutation's `tracking.articles` holds only the items in that parcel.

## Article categories

`article_category` is a free-text string on each article. The returns portal's
return-reason filters key on it, so an order built for a returns demo shows the
wrong reasons — or none — when the category is missing or spelled differently
from what the portal expects. Nothing in the API response signals this.

**Propose the articles and a baseline category together, in one exchange.**
The articles haven't been named anywhere yet at this point in the workflow —
*Build the payload* is where they'd otherwise first appear — so name them here
rather than asking the user to approve a category for products they haven't
seen. Derive one category from what the products actually are (four clothing
items → `fashion` for all four):

> Categories drive which return reasons show in the portal. I'd add **`<N>`
> items** — `<article 1>`, `<article 2>`, ... — all as category **`fashion`**.
> Keep it, set a different one for all, or go per-product? Standards:
> `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`, `toys`, `media`
> — or any string you like.

- Blocking: don't send a payload on an unanswered category prompt. "Keep it"
  answers it in one word.
- A proposal is not a default — show it and get it accepted.
- The eight standards are this skill's convention. The API accepts any string.
- **Use the user's string verbatim, case included.** If the portal filter keys on
  `Fashion`, sending `fashion` matches nothing. Normalising the input breaks the
  match.
- Per-product categories are expected for a mixed order (jacket + kettle).
- **Write it at both levels**: `articles_order[].article_category` *and* every
  `add_tracking.tracking.articles[].article_category`, for the same reason you
  mirror `article_name`/`unit_price`/`article_image_url`: the Returns Order
  API derives returnable items from `tracking.articles` (see *Payload shape*
  above), so that's the level a reason filter has anything to act on.
  Untracked orders (no `mutations`) only ever write the order level — there is
  no tracking record, so there is no returns flow to filter in the first
  place.

## Extra order information

Ask this once, after categories and before the payload summary. It is an offer
with a fast exit, not a form:

> Anything else to add to this order, or send as-is?

Then show this menu. Don't ask an open "any other fields?" — that's unanswerable
unless the user has the Order API spec memorised.

| Extra | Fields | State this |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]` at **both** order and tracking level | Role matches the Journey's `advancedRecipients` literally, case-sensitive. Preserve the user's spelling even if it looks like a typo. See *Additional recipients*. |
| Promise dates | `announced_delivery_date`, `announced_delivery_date_min`, `announced_delivery_date_max` | **`YYYY-MM-DD` only** — a full ISO datetime is rejected. (`order_date` does take full ISO; the fields differ.) |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |

Anything the user asks for that isn't listed is still fair game — check the
[full spec](https://docs.parcellab.com/docs/developers/orders/full-order-api-spec)
rather than refusing.

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

**Never pick the destination country yourself — always ask.** If the user hasn't
named a country, stop and ask which destination they want before building anything,
offering the ones below as the ready-made options:

> Which destination country? I have defaults ready for **DEU**, **GBR**, **USA**,
> **FRA**, **NLD** and **AUT** — or name any other and I'll pick a plausible
> address and courier for it.

Destination is the one field never invented, because it silently determines the
language, currency, timezone, courier and address of the whole order — so a wrong
guess produces an entirely wrong-looking order rather than an obviously wrong
field. Everything *else* the user doesn't mention, you still make up from the table
below.

Once the country is known, infer the rest from it.

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
- **"Send to test/staging"** — there's no separate test env on this skill. Tell the user this skill only targets production and ask if they really want to proceed.

## Failure modes to watch for

- **HTTP 400 with `client_error`** — usually a missing required field, bad country code (must be 3-letter ISO), or an invalid `recipient_email`. Read the `errors` array and fix the offending field rather than retrying blind.
- **`Unauthorized response: Run 'parcellab --env prod auth login' and retry.`** — the CLI's OAuth session expired. Run `parcellab auth login` in the background (it blocks on browser approval) and retry after the user approves.
- **`Blocked by edit mode 'account-restricted' … does not match restricted account …`** — the CLI's write guard is aimed at a different account than the payload. Working as designed. Either the payload's `account` is wrong, or the user's guard is misconfigured — show them `parcellab settings edit-mode show` and fix whichever is wrong. Never suggest `unrestricted`.
- **`Raw write requests require payload.account in account-restricted mode.`** — the payload is missing its `account` field. Add it; don't loosen the guard.
- **Success with `mutations[0].result.success: false`** — the order saved but tracking didn't attach. Common causes: courier code not recognised, tracking number conflicts with an existing order on the account. Report the warning verbatim.

If the CLI itself fails (no network, command not found), surface the error; don't retry silently.
