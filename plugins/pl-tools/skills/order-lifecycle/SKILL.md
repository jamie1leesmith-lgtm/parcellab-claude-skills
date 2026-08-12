---
name: order-lifecycle
description: Simulate a full parcelLab post-purchase journey — source a real product from a brand site, create an untracked order, then push a timed sequence of tracking checkpoints (warehouse → carrier → delivery) so parcelLab fires the comms for each stage. Use for phrases like "simulate the full journey for [brand]", "run a lifecycle order", "push an order and walk it through delivery", "simulate post-purchase events".
---

# parcelLab — Order Lifecycle Simulator

Simulate a full post-purchase journey: source a real product from a brand site,
create an **untracked** order, then push a timed sequence of tracking checkpoints
so parcelLab ingests each stage and fires the configured comms.

Production only. Every run is isolated — fresh product,
fresh order number, no carryover — unless the user explicitly says reuse/resend.

## Workflow

1. **Resolve the account and check the CLI.** See *Account resolution and
   confirmation* below. There is no token — every write goes through the
   `parcellab` CLI's own login. If any part fails, follow *If credentials are
   missing* — don't guess values.

   ```bash
   test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && command -v parcellab >/dev/null && parcellab auth show >/dev/null 2>&1 && echo ok
   ```
2. **Gather inputs:** brand site URL + a rough product idea (e.g. "coffee machine"), destination country, and any overrides (gap, extra items). **Ask for the destination country if the user hasn't named one — never assume it.** It silently sets the language, currency, timezone, courier and address, so a wrong guess yields an entirely wrong-looking journey. `create-order`'s *Defaults & dummy data* table lists the countries with ready-made defaults.
3. **Source the product** (see *Product sourcing*).
4. **Gate A — product and category approval.** Show product(s) with a proposed
   `article_category` for each; wait for approval of both. See *Gate A — product
   and category approval*.
5. **Gate B — journey and scenario selection.** Ask one shipment or a split, then which scenario each shipment runs: happy, unhappy, or custom. Show the events and the comm each is expected to fire. See *Gate B — scenario selection*. **Never skip this and never assume a default.**
6. **Confirm the carrier(s).** State the country default courier; let the user confirm/override. For a split shipment, confirm a courier per shipment (they may differ).
7. **Build payloads** (see *Order + tracking setup* and *Event sequence*). Write the untracked order as `create.json` (no `NN-` prefix so the driver skips it), and each event as `NN-<status>.json` in the same run directory. For split shipments, interleave both shipments' events into one numbered sequence — see *Split shipments*.
8. **Gate C — order enrichment and send approval.** Offer the optional extras, apply anything Gate B marked required, then show the final plan and wait for approval. See *Gate C — order enrichment*.
9. **Launch the driver in the background** (see *Timing & background execution*).
10. **Report** progress from the log (see *Reporting*).

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

## Product sourcing

- Open the site in the Browser pane (`mcp__Claude_Browser__preview_start {url}` then `read_page`).
- Find one real product-detail page matching the idea. Extract `article_name`,
  `article_image_url`, `article_store_url` (the product page URL itself),
  `unit_price`, `sku` (slug of the name if none exposed).
- Verify the image URL loads (navigate to it or check network 200 + image type).
- One product by default; repeat per extra item the user asks for.

## Gate A — product and category approval

Show each sourced product — name, price, image URL, store URL — with a proposed
`article_category`, and get both approved in one exchange. Categories ride along
here because the products are already on screen; they don't need a gate of their
own.

`article_category` is what the returns portal's return-reason filters key on, so
a run built for a returns demo shows the wrong reasons — or none — when it's
missing or cased differently from what the portal expects. Nothing in the API
response signals this.

Propose one category derived from what the products are (four clothing items →
`fashion` for all four), then ask:

> Categories drive which return reasons show in the portal. I'd set **`fashion`**
> for all `<N>` items. Keep it, set a different one for all, or go per-product?
> Standards: `fashion`, `home`, `electronics`, `beauty`, `sports`, `food`,
> `toys`, `media` — or any string you like.

- Blocking, like the rest of Gate A. "Keep it" answers it in one word.
- A proposal is not a default — it has to be shown and accepted.
- The eight standards are a convention; the API takes any string.
- **Use the user's string verbatim, case included.** If the portal filter keys on
  `Fashion`, sending `fashion` matches nothing.
- Per-product categories are expected for a mixed order.
- Full rules, including the untracked-order case, are in `create-order`'s
  *Article categories*.

## Order + tracking setup (before the event loop)

Two order writes, done directly (not by the driver) through the CLI — **never
add `--base-url`**, the default host serves these paths and overriding it breaks
the CLI's own account guard:

```bash
parcellab api request PUT /v4/track/orders/ --data @create.json -o json
```

1. **Untracked order** — build a payload following the `create-order`
   shape: `account` (the resolved account id, `${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`), `order_number` (`<XXX>-<ts>`),
   destination country ISO3, recipient, shipping address, `articles_order`
   (each article including `article_category`, from Gate A's approval),
   currency/timezone from the country. Save as `create.json` with **no
   `mutations`**. Send it → HTTP 201.
2. **Attach tracking** — send an `add_tracking` mutation with a randomised,
   format-correct `tracking_number`, the chosen `courier`, and the article list.
   This associates the courier/tracking so events have something to land on.
   (Do **not** put `checkpoints` in `add_tracking` — that field is output-only
   and the API rejects it.) **For a split shipment, send both `add_tracking`
   mutations in the same `mutations` array of one PUT** — see *Split shipments*.

   **Verify attachment with a read — the PUT response cannot tell you.** The response echoes the
   request payload and carries no `trackings` field, so a successful write looks identical to a
   no-op. Confirm once per tracking number:

   ```bash
   parcellab track tracking list --account <ACCOUNT_ID> --tracking-number <TN> -o json \
     --jmes 'results[].{tn:trackingNumber,c:courier}'
   ```

   One entry per parcel means attached. **Never re-send the `add_tracking` PUT to find out** —
   live 2026-08-11 a conductor did exactly that as a diagnostic, which is an avoidable duplicate
   write against a live account. (It happened not to create a duplicate tracking; that is luck,
   not a guarantee.)

   **Always set `tracking.articles` on every `add_tracking` mutation, even for
   a single-shipment order — not just `articles_order` at the order level.**
   Tracking-triggered comms (Out for Delivery, Delivered, delay updates) render
   their `{{articlesTableWithImages}}` placeholder from the **tracking-level**
   `articles` array, not from `articles_order` — that field only feeds the
   order-level confirmation email. Omitting it is why article name/image/price
   can look fine in the order-confirmation email but come back blank in every
   later shipment comm. Mirror the same items (with matching `line_item_id`s)
   from `articles_order` into `tracking.articles`, **including
   `article_category`** — for the same reason you mirror name/image/price: the
   Returns Order API derives returnable items from `tracking.articles` (see
   `create-order`'s *Payload shape*), so that's the level a reason filter has
   anything to act on.

   **Dual-family article keys — required for the article block to render in
   comms at all** (live-verified 2026-08-11 against a working legacy-ingest
   account): the message templates read the LEGACY camelCase fields from the
   stored document — `articleNo`, `articleName`, `articleImageUrl`,
   `articleCategory`, `price` — and v4 snake_case fields alone leave those
   unset (`imageUrl: null` in the stored doc → empty article table in every
   email). The v4 API passes the camelCase keys through verbatim, so every
   article entry at BOTH levels duplicates its data in both families, and
   `line_item_id` carries the real SKU/article number rather than a sequence
   number (parcelLab's own Custom Demo Creator does the same):

   ```json
   "tracking": {
     "tracking_number": "<randomised>",
     "courier": "<chosen courier>",
     "articles": [
       {
         "line_item_id": "TS-BLK-M",
         "sku": "TS-BLK-M",
         "article_name": "Classic T-Shirt — Black, M",
         "article_category": "fashion",
         "quantity": 1,
         "unit_price": "29.90",
         "article_image_url": "https://picsum.photos/seed/tshirt/400/400",
         "article_store_url": "https://example.com/products/classic-t-shirt",
         "articleNo": "TS-BLK-M",
         "articleName": "Classic T-Shirt — Black, M",
         "articleImageUrl": "https://picsum.photos/seed/tshirt/400/400",
         "articleCategory": "fashion",
         "price": "29.90"
       }
     ]
   }
   ```

   For a split shipment, each tracking's `articles` gets only the line items
   in that parcel (see *Split shipments*).

## Event sequence

Events are pushed via **`POST /v4/track/events/`** through the CLI (trailing
slash required; success = **HTTP 204**, which the CLI shows as empty output and
exit 0), one standalone POST per stage — there is no cumulative array. For each
stage in the chosen sequence (see `references/status-codes.md`), write
`NN-<status>.json` containing:

```json
{
  "event_status": "InTransit",
  "location": "Regional Hub",
  "courier": "dpd-uk",
  "tracking_number": "<the same tracking_number used in add_tracking>"
}
```

**Do not include `event_timestamp` or `account` in this file.** The driver
injects both at the moment it sends each event: `event_timestamp` stamped with
real wall-clock "now" (see *Timing & background execution* — a precomputed
timestamp, future OR past, makes the checkpoint disagree with when its comm
actually sends), and `account` from the resolved account id, because the CLI's
edit-mode guard refuses any raw write whose payload it cannot attribute to an
account. The events API accepts the extra field (verified in production).

**Always identify the event by `courier` + `tracking_number` — never
`account` + `order_number`.** Live testing proved the order-number identifier
does not attach to the tracking timeline; `courier` + `tracking_number` is
what parcelLab's own Custom Demo Creator uses and is confirmed working.

Use the canonical `event_status` values from the reference table; prefer the
proven, genuinely-clean **`InTransit → OutForDelivery → Delivered`** happy
path. **`WarehouseDelay` means "delayed" — do not include it in a happy-path
sequence.** (An earlier version of this skill copied a 4-stage schedule
starting with `WarehouseDelay` from parcelLab's Custom Demo Creator and
mislabeled it "happy"; live testing showed a shipment meant to have no delay
displaying one, because the sequence itself put a delay first. Only add
`WarehouseDelay` when the user actually wants to demonstrate a delay.)
Attachment is asynchronous — after the driver finishes, verify with a lookup
(see *Reporting*) rather than assuming immediate attachment.

## Gate B — scenario selection

**Ask every run. There is no default and no inferring from context.** The point of
this skill is demonstrating post-purchase comms, so the user must see which comms
will fire before any are sent.

Two questions:

1. **One shipment or a split?** A split shipment runs two trackings with
   independent outcomes — see *Split shipments*.
2. **Which scenario per shipment?** Three options:

### 1. Happy path (proven)

```
InTransit → OutForDelivery → Delivered
```

All three statuses are proven to attach and fire. This is the default *offer*, not
a default *choice* — still ask.

### 2. Unhappy path (proven)

```
InTransit → WarehouseDelay      (then stop)
```

Both statuses are proven. The parcel is delayed and never arrives: stop emitting
events and the last one stands as the live state indefinitely, exactly as
*Split shipments* step 5 describes. `is_delayed` becomes `true`.

Do **not** "improve" this to a three-event shape. Two alternatives were considered
and rejected:

- `InTransit → OutForDelivery → WarehouseDelay` is incoherent — a *warehouse* delay
  cannot follow a parcel already out for delivery.
- `InTransit → OutForDelivery → FailedAttempt-NewAttemptNextDay` tells a better
  story, but `FailedAttempt-*` is unverified and may `204` without ever attaching.
  It is reachable through the custom path, where its risk is labelled.

### 3. Custom path

Derived from the account's own Journey configuration — see
*Custom path — journey introspection*.

### What to show the user at this gate

List the events in order, and the comm each is expected to fire. These mappings are
empirically confirmed on account 1626718 with a standard delivery-notification
setup:

| Event | Expected comm | Journey trigger |
|---|---|---|
| *(order creation)* | `order_confirmation_*` | Order Confirmed |
| `InTransit` | `shipping_confirmation_*` | Package dispatched from warehouse |
| `OutForDelivery` | `out_for_delivery_*` | Package out for delivery |
| `Delivered` | `package_delivered_*` | Delivered (parcel delivered to recipient) |
| `WarehouseDelay` | delay comm | Package delayed in transit |

Say plainly that comms depend on the account's Journey config, and that this table
reflects a standard setup rather than a guarantee.

For a split shipment, show this per shipment, labelled A and B.

### Split shipments are chosen here, not at Gate C

A split is a decision about events and comms, so it belongs to Gate B. The
canonical demo is one shipment on the happy path and one stuck at a delay, side by
side — expressible directly as *"A: happy, B: unhappy"*.

**Gate C never offers split shipments.** If it did, a split chosen there would
strand the single scenario chosen here with nothing to say about the second
shipment.

## Split shipments (multiple trackings per order)

An order can have two (or more) trackings, each progressing through its own
independent scenario — e.g. one shipment follows the happy path to `Delivered`
while another stops partway at a delay, to demonstrate different outcomes side
by side. **No driver change is needed for this** — `run-lifecycle.sh` already
just marches through `NN-*.json` files in order with a gap before each; it has
no idea which tracking a file targets. Split shipments are purely a
payload-building pattern:

1. **Order-level flag:** set `"has_multiple_shipments": true` on `create.json`
   (and/or the attach payload — either is fine, it's an order-level field).
2. **Article split:** divide `articles_order`'s `line_item_id`s across the
   shipments — each shipment's `add_tracking.tracking.articles` gets only the
   items in that parcel (same rule as the base `create-order` skill).
3. **Attach both trackings in one PUT:** put two `add_tracking` mutations in
   the same `mutations` array, one per shipment, each with its own randomised
   `tracking_number`, its own `courier` (may differ per shipment), a
   `delivery_number` (`"1"`, `"2"`, ...), and its own article subset.
4. **Interleave the event files into one run directory,** numbered in the
   order you want them to play out in real time. Each file still carries its
   own `courier` + `tracking_number` (whichever shipment it targets), so a
   descriptive filename helps readability — e.g. label each shipment (`A`/`B`):

   ```
   01-A-InTransit.json          (shipment A, happy path, stage 1 — no delay)
   02-B-WarehouseDelay.json     (shipment B, stage 1 — this one IS delayed)
   03-A-OutForDelivery.json     (shipment A, stage 2)
   04-B-Exception-Notified.json (shipment B, stage 2 — its last event)
   05-A-Delivered.json          (shipment A finishes; B stays stuck at Exception)
   ```

   **Don't give a happy-path shipment a `WarehouseDelay` stage** — that status
   means "delayed," so a shipment meant to demonstrate a clean delivery should
   skip it entirely (see *Event sequence* above). Only the shipment(s) meant to
   show a problem should include it.

   The `[0-9][0-9]-*.json` glob only requires the two leading digits; any
   suffix (like `-A-` / `-B-`) is fine and purely for human readability.
5. **To leave a shipment "stuck" in a scenario**, simply stop emitting files
   for it — its last sent event stands as its live status indefinitely. No
   special "end" marker needed.
6. **Gate C and Reporting** should summarise **per shipment** — courier,
   tracking number, and how far its scenario goes — so the user can see both
   outcomes clearly before and during the run.

## Custom path — journey introspection

Builds a sequence from the account's **actual** Journey config, rather than
assuming the user remembers which journeys are live.

**Requires the Product-API MCP journey tools.** If they aren't available in this
session, say so in one line and fall back to asking the user to describe the
sequence in prose, mapping it against *references/status-codes.md*. **Never block a
run on tool availability.**

### 1. List every journey

`journey_list_journey_configurations(account=[<id>])`

**Do not filter by `release_status`** — show drafts too, so the user sees
everything. For each journey give name, `releaseStatus`, and a plain-English
eligibility line derived from `filterExpression`.

### 2. The user picks one by name

### 3. Check the order is actually eligible — do not skip this

Picking a journey by name is **not** sufficient. The order must match that
journey's `filterExpression` or the journey never processes it: no error, just
silence. Three ways a chosen journey fires nothing:

| Condition | Detect | Tell the user |
|---|---|---|
| Draft | `releaseStatus != "published"` | It won't fire until published. Ask whether to continue anyway or pick another. |
| Returns-only | filter requires `isReturnsPortal: true` | A forward shipment is never a returns-portal record. Name the journey that *would* catch this order. |
| Order ineligible | filter needs fields the planned order lacks, e.g. `delivery_info.client: {$in: [...]}` | Name the field and offer to set it at Gate C. |

Where the mismatch is fixable, offer the fix. Where it isn't, say which journey
would catch this order instead. **Never proceed silently past an ineligible pick** —
the whole run would produce checkpoints and no comms, looking like a bug.

### 4. Fetch only that journey's triggers

`journey_get_journey_trigger_configuration(id)` for each trigger on the chosen
journey — roughly 5-12 calls. **Do not introspect every journey**: on a populated
account that is 40+ calls for information the user didn't ask for.

### 5. Present the mapping with a confidence label per row

`eventTypes` in Journey config is a **different vocabulary** from the `event_status`
values the events endpoint accepts. Every proposed mapping is therefore one of:

| Confidence | Meaning | Example |
|---|---|---|
| **exact** | `eventTypes` contains the `event_status` verbatim | `OutForDelivery` -> `OutForDelivery`; `WarehouseDelay` -> `WarehouseDelay` |
| **inferred** | Clear correspondence, different spelling | `ParcelLocker` -> `Delivered-ParcelLocker`; `FailedAttemptFirst` -> `FailedAttempt-NewAttemptNextDay` |
| **unverified** | Config genuinely cannot tell us | `eventTypes: ["*"]` on `onDispatch` — a wildcard matches anything on that slot. `InTransit` is known to reach it only because a live run proved it. |

Show **two independent axes**, because they answer different questions:

- **Trigger confidence** — will this event match this trigger? (the table above)
- **Status confidence** — will this `event_status` attach at all? Only
  `WarehouseDelay`, `InTransit`, `OutForDelivery` and `Delivered` are proven; the
  other ~42 enum values are untested.

A mapping can be *exact* on a status that has never been tested, and *unverified*
on a status proven to work. Don't collapse them into one number.

### 6. The user selects which triggers to demonstrate, in order

That selection **is** the sequence. Build `NN-<status>.json` files from it exactly
as *Event sequence* describes — same identifier rule (`courier` +
`tracking_number`), same no-`event_timestamp` rule.

### 7. After the run, report what actually fired

Verify against `contacted_with_messages` and say which *inferred* and *unverified*
mappings actually produced a comm. Offer to record newly confirmed ones in
`references/status-codes.md`, so each custom run shrinks the untested surface
instead of the finding evaporating.

### Known limitation: recipient roles are a second gate

Filter eligibility is necessary but not sufficient. On account 1626718 the
*Gifter Journey* has an empty `filterExpression` — so it matches every order — and
an *Out for Delivery* trigger, yet a live run produced only one
`out_for_delivery_*` comm. It almost certainly requires `additional_recipients`
carrying a role listed in the Journey's `advancedRecipients`, the mechanism
`create-order` documents under *Additional recipients*.

So a journey can be published, eligible, and still mail nobody. State this as a
limitation. Do not try to resolve it from config, and **never promise mail on the
strength of an eligibility check.**


## Timing & background execution

Launch the driver detached so it survives the session moving on:

```bash
EVENTS_DIR="<run dir>" GAP_SECONDS="<gap, default 200>" \
  bash <skill dir>/references/run-lifecycle.sh
```

The driver waits `GAP_SECONDS` **before every event, including the first**,
then POSTs each `NN-*.json` to `/v4/track/events/` (`create.json` has no `NN-`
prefix so it is skipped), stamping `event_timestamp` with real wall-clock time
at the moment of each send — never precompute it. The leading gap matters:
order creation/`add_tracking` (done just before this script runs) triggers an
order-confirmation comm that also processes asynchronously — without a wait
before event 1, that comm can arrive *after* the first lifecycle event's comm.
Run it with the Bash tool's `run_in_background`. Do a `DRYRUN=1` pass first to
sanity-check the sequence without hitting the API (the log shows the timestamp
each event would be stamped with).

## Gate C — order enrichment

An offer with a fast exit, not a form. **The default is send-as-is** — skipping
takes one word:

> Anything else to add to this order, or send as-is?

Then list the menu below. Do **not** ask an open "any other fields?" — that is
unanswerable unless the user has the Order API spec memorised.

Anything Gate B flagged as **required** (for example a `client_key` needed to make
the chosen journey eligible) appears here pre-filled and is **not** optional.

| Extra | Fields | State this |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]` — write to **both** order and tracking level | Role must match the Journey's `advancedRecipients` **exactly**, case-sensitive. **Preserve the user's spelling even if it looks like a typo** — the match is literal, and "fixing" it breaks a Journey using the same misspelling. Setting the field mails nobody unless the Journey lists that role. |
| Promise dates | `announced_delivery_date`, `announced_delivery_date_min`, `announced_delivery_date_max` | **`YYYY-MM-DD` only.** A full ISO datetime is rejected. (`order_date` *does* take full ISO — the two fields differ.) |
| Client key | `client_key` | Pre-filled when Gate B's journey requires one |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Extra articles | more `articles_order` entries, each with a unique `line_item_id` | Mirror them into every `add_tracking`'s `tracking.articles` or the shipment comms render an empty article table |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |
| Delivery detail | `delivery_method`, `courier_service_level`, `requires_signature` | Mostly cosmetic in comms |
| Article physical data | `weight`, `weight_unit` on each article | Article-level, not order-level — set at **both** levels, `articles_order` and every `add_tracking`'s `tracking.articles`, like every other article field. `weight_unit` is one of `kg` / `g` / `lbs` / `oz` and defaults to `g` (v4 Order API docs, `https://product-api.parcellab.com/v4/docs/markdown/order/`). snake_case only: `weight` has no legacy camelCase twin, so if a comm template renders it blank, check the dual-family rule before adding a value. |

**Split shipments are not offered here** — they are chosen at Gate B, because a
split needs a scenario per shipment.

**Article dimensions are not offered.** The v4 docs describe `width`, `height`
and `length` as millimetres while `length_unit` is a `const` of `cm`. Until one
live order settles which is right, a size rendered in a demo could be wrong by a
factor of ten. Add them once a run proves the unit.

After the menu, show the final plan and wait for approval. It itemises, field by
field:

- order summary, carrier(s), scenario per shipment, event list with expected
  comms, and the gap
- every article with its `article_category`
- **every extra agreed at this gate, with its actual value**

An extra that was discussed but doesn't appear in the summary is a defect. This
is the last stop before anything reaches production, and a wrong promise date or
a mistyped recipient role is invisible in the API's success response.

## Confirmation gates

Three gates. All three are blocking — a run with no user response at any gate
stops and waits. Never infer an answer from earlier context.

- **Gate A:** product(s) **and their `article_category`** approved before
  anything else.
- **Gate B:** journey and scenario chosen — one shipment or split, and which
  scenario each runs. Asked **every run**; there is no default.
- **Gate C:** optional extras offered, then the final plan approved before
  `create.json` is sent.

After Gate C the sequence runs unattended.

## Reporting

Tail `EVENTS_DIR/run.log`. After each event report the pushed `event_status` and
HTTP code (**204 = accepted**, not yet attached). On any non-2xx, surface it and
pause for the user. Once the sequence completes, verify attachment with a public
order-info lookup (account + courier/tracking_number) and report the actual
checkpoint list and `contacted_with_messages` — that is the real proof of
success, not the 204s.

**Wait at least 5 minutes after the final event before treating a missing comm as
a problem, then re-check once before reporting it.** Comms do not arrive at a
uniform lag: in live runs the order confirmation, dispatch and out-for-delivery
comms each appeared within ~3-4 minutes of their event, but
`package_delivered_*` is consistently the slowest — 3-4 minutes on single-parcel
orders, and **over 10 minutes** on one parcel of a split order (measured
2026-08-11, account 1626718, three orders / four parcels). Checking early shows
every checkpoint attached with a comm missing, which looks exactly like a broken
delivered trigger and isn't.

That spread is why the wait was 15 minutes until 2026-08-12, when it came down
to 5 against the operator's own inbox. **The re-check replaces the margin the
longer wait used to provide:** at 5 minutes a slow `package_delivered_*` on a
split parcel may genuinely not have landed yet, so look a second time (a further
~5 minutes) before calling anything missing. One look at 5 minutes is not a
finding.

**This window was 5 minutes and that was too short.** On the 2026-08-11 run a
conductor checked at ~6 minutes, found the delivered comm missing, and reported
it to the user as a possible defect with a plausible-but-wrong hypothesis
attached — that split orders withhold the delivered comm until every parcel
lands. The comm arrived minutes later and disproved it. Wait the full window
before forming a theory, let alone reporting one.

**Do not go digging in Journey config before that window has elapsed.** Doing
so wastes real effort on a non-problem — and in one investigation produced a
plausible-but-wrong diagnosis (the delivered action has
`recipientCustomer: false, recipientPlTest: true`, which looks like the cause
until you notice the out-for-delivery action that *did* fire carries the
identical recipient config).

Once the window has elapsed, check whether the message can send at all before
reading any further config. Resolve the journey channel's `messageType` to its
message with `parcellab journey message list --account <id>` and read
`hasReleasedVersion`: a message that has never been released renders nothing,
while the trigger still matches and the event still names the message it picked.
Proven live 2026-08-12 on account 1626102, where every delivery message was
unreleased and the account had sent zero emails.

`releaseStatus` is not that gate — a `draft` message serves its last released
version, and message 75240 on account 1626718 is `draft` with 51 emails sent.

The fuller ledger of proven causes and non-causes, each with the account it was
proven against, is the run-triage skill's `references/comms-diagnosis.md` if you
have that skill installed.

Two things confirmed live on account 1626718, worth not re-deriving:

- **`delivery_location_type: "Unknown"` is fine.** The `Delivered` trigger's event
  accepts `eventTypes: ["Postbox", "Unknown", "Doorstep", "HomeDeposit"]`, so a
  synthetic `Delivered` event with no explicit location still matches and still
  fires. Treat `Unknown` as expected, not as a fault.
- **`InTransit` attaches as checkpoint `InboundScan`**, displayed as
  "Dispatched" — parcelLab relabels the event status on the timeline. The
  checkpoint you get back will not always be named after the event you sent, so
  match on position and timestamp rather than on `status_code` alone.

## Failure modes

- **Invalid `event_status` → 400** (enum error listing the allowed values). The
  events enum is NOT the status-model names — use only values from
  `references/status-codes.md` (e.g. `WarehouseDelay`, `InTransit`,
  `OutForDelivery`, `Delivered`). There is no `OrderProcessed`/`PickUpScheduled`.
- **Missing trailing slash on the events URL → 301** (body dropped). The driver
  already includes it; keep it.
- **Event accepted (204) but never attaches** → almost always caused by
  identifying the event with `account` + `order_number` instead of `courier` +
  `tracking_number`. Always use the courier/tracking_number identifier.
- **Comms and checkpoints disagree on ordering on the timeline** → a
  precomputed `event_timestamp` (future OR past offset) was baked into the
  payload file instead of letting the driver stamp real send time. Never put
  `event_timestamp` in the `NN-*.json` files; the driver injects it. This was
  reproduced live in both directions (future offsets, then past-anchored
  offsets) before the fix.
- **The very first lifecycle event's comm arrives before the order-confirmation
  comm** → the driver only waited between events, not before the first one, so
  event 1 fired seconds after order creation — not enough lead time for the
  order-confirmation comm (also async) to land first. Fixed: the driver now
  sleeps `GAP_SECONDS` before every event, including the first. Confirmed live
  at 180s that this restores correct ordering.
- **Duplicate tracking number + courier → 400** on the `add_tracking` setup step.
  Always randomise the tracking number.
- **`checkpoints` in `add_tracking` → 400** ("mutations required", misleading).
  `checkpoints` is output-only; never send it. Use `/v4/track/events/` instead.
- **Comms don't fire though the event attached** → `event_status` isn't mapped
  to a status, or no Journey/trigger exists for it in the account. Report the
  attached checkpoint; don't promise an email beyond what
  `contacted_with_messages` shows.
- **Article name/image/price blank in shipment comms (Out for Delivery,
  Delivered, delay updates) even though the order-confirmation email looked
  fine** → `{{articlesTableWithImages}}` in those comms renders from the
  **tracking-level** `add_tracking.tracking.articles` array, not from the
  order-level `articles_order`. If `tracking.articles` was omitted (a
  single-shipment order easily misses this since only *Split shipments*
  called it out before), the table has nothing to render. Always mirror the
  order's articles into `tracking.articles` on every `add_tracking` mutation
  — see *Order + tracking setup*, step 2.

---

## Orchestrated runs (demo-environment)

When the `demo-environment` conductor drives this skill, `demo-manifest.json`
answers the gates — the manifest's recorded approvals ARE the user's answers,
given at the conductor's intake (this is not inference):

- **Gate A** (product approval): `approvals.products_approved_at`.
- **Gate B** (journey/scenario): each manifest order's `shipments[]` carries
  the chosen scenario, courier and exact `events` sequence. Scenarios beyond
  the proven happy/unhappy shapes (e.g. `recovered` =
  `InTransit → WarehouseDelay → OutForDelivery → Delivered`, or locker
  endings) are **custom-path sequences the user explicitly chose at intake**;
  keep this skill's confidence labelling when reporting them, and never
  silently reorder a sequence.
- **Gate C** (enrichment): `gates.order_lifecycle.gate_c` — `"send-as-is"`
  unless `extras` carries fields, which are applied exactly as the Gate C
  table specifies. Each key is the Order API field name, with one exception:
  `extras.article_weights` is a synthetic container. Its entry
  `article_weights[<product id>]` sets `weight` and `weight_unit` on **every
  article whose product is that id**, at both the `articles_order` level and
  every `add_tracking`'s `tracking.articles` — the *Article physical data* row
  above. The manifest keys by product `id` (the goods code) while payload
  articles key by `line_item_id`, which is the SKU, so the lookup goes through
  the product, not the article key. Nothing named `article_weights` is written
  to a payload.
- **Destination country** comes from `destination_country`; the account was
  confirmed by name at intake — do not re-confirm mid-run.
- **Account:** every payload's `account` field and the driver's environment
  come from the manifest's `account.id` — never from `$PARCELLAB_ACCOUNT_ID`,
  which may point at a different account than the one confirmed at intake.
  Launch every driver with the account inline: `PARCELLAB_ACCOUNT_ID=<manifest
  account.id> EVENTS_DIR="orders/<nn>-<label>" GAP_SECONDS="<200 standard |
  60 fast, from the manifest's run.pace>" bash <skill
  dir>/references/run-lifecycle.sh`.
- **Pace:** `GAP_SECONDS` is never hard-coded on an orchestrated run — it
  comes from the manifest's `run.pace` (`standard` → 200, `fast` → 60; an
  absent `run.pace` means standard). At `fast`, comms may arrive out of
  order; say so when reporting.

**Multi-order runs.** Each manifest order gets its own directory
(`orders/<nn>-<label>/` inside the run dir), its own `create.json`,
`NN-<status>.json` files, and its own detached driver — the "every run is
isolated" rule applies per order. Drivers run concurrently; a split-shipment
order follows the *Split shipments* rules unchanged within its own directory.

**Fraud data on direct-path orders.** Before sending `create.json`, generate
the order's fragment and merge it in at the top level:

    python3 ${CLAUDE_PLUGIN_ROOT}/scripts/prepare_fraud_fragment.py \
      --level <order.fraud_level> --shop-url <shopify.store, or the
      brand handle + ".myshopify.com" when no store is configured>

The output's `tags` and `additional_attributes` become `create.json`'s
top-level `tags` and `additional_attributes` fields.

**After the order + add_tracking writes succeed**, write
`orders/<nn>-<label>/order.json`:
`{"order_number", "customer": {"name","email"}, "cdc_slot", "fraud_level",
"trackings": [{"shipment", "courier", "tracking_number"}]}` — the conductor
builds the CDC linking file and the final report from these.

Everything else — payload rules, `tracking.articles` mirroring, the driver,
timing, reporting, failure modes — is unchanged from the sections above.

Standalone behaviour (no manifest): everything above this section, unchanged.