---
name: order-lifecycle
description: Simulate a full parcelLab post-purchase journey — source a real product from a brand site, create an untracked order, then push a timed sequence of tracking checkpoints (warehouse → carrier → delivery) so parcelLab fires the comms for each stage. Use for phrases like "simulate the full journey for [brand]", "run a lifecycle order", "push an order and walk it through delivery", "simulate post-purchase events".
---

# parcelLab — Order Lifecycle Simulator

Simulate a full post-purchase journey: source a real product from a brand site,
create an **untracked** order, then push a timed sequence of tracking checkpoints
so parcelLab ingests each stage and fires the configured comms.

Production only (`api.parcellab.com`). Every run is isolated — fresh product,
fresh order number, no carryover — unless the user explicitly says reuse/resend.

## Workflow

1. **Resolve the account and confirm credentials.** See *Account resolution and
   confirmation* below. If either value is missing, follow *If credentials are
   missing* — don't guess them.

   ```bash
   test -n "${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}" && test -n "$PARCELLAB_TOKEN" && echo ok
   ```
2. **Gather inputs:** brand site URL + a rough product idea (e.g. "coffee machine"), destination country, and any overrides (scenario, gap, extra items, **split shipment** — see *Split shipments*). **Ask for the destination country if the user hasn't named one — never assume it.** It silently sets the language, currency, timezone, courier and address, so a wrong guess yields an entirely wrong-looking journey. `create-order`'s *Defaults & dummy data* table lists the countries with ready-made defaults.
3. **Source the product** (see *Product sourcing*).
4. **Gate A — product approval.** Show product(s); wait for approval.
5. **Confirm the carrier(s).** State the country default courier; let the user confirm/override. For a split shipment, confirm a courier per shipment (they may differ).
6. **Build payloads** (see *Order creation* and *Event sequence*). Write the untracked order as `create.json` (no `NN-` prefix so the driver skips it), and each event as `NN-<status>.json` in the same run directory. For split shipments, interleave both shipments' events into one numbered sequence — see *Split shipments*.
6a. **Journey pre-check (optional — see *Journey pre-check*).** Offer it whenever the sequence isn't the proven default, or whenever the user asks. Skip silently if the required tool isn't available.
7. **Gate B — plan approval.** Show order summary + carrier + scenario + gap. Wait for approval.
8. **Launch the driver in the background** (see *Timing & background execution*).
9. **Report** progress from the log (see *Reporting*).

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

### If credentials are missing

Stop. Do not guess values and do not proceed. Say this:

> **If you have just set these up, quit and reopen the app** — environment
> variables are only read at startup.
>
> Otherwise, let's set them up now. I need your parcelLab Order API credential.
> In the portal it's shown as a base64 value — paste that and I'll handle the
> rest. (A raw token works too; I'll just need your account ID as well.)

On receiving a base64 value: decode it, split on the first `:` — the part before
is the account ID, the part after is the token. This is why the base64 form is
preferred: one paste gives both, and it removes the commonest setup error, which
is pasting the whole encoded blob in as the token and getting an unexplained
`401`.

Write both to the `env` block of `~/.claude/settings.json`, merging into any
existing `env` block rather than replacing it. Then tell the user to quit and
reopen the app.

Never print the token back to the user or repeat it anywhere in your reply.

## Product sourcing

- Open the site in the Browser pane (`mcp__Claude_Browser__preview_start {url}` then `read_page`).
- Find one real product-detail page matching the idea. Extract `article_name`,
  `article_image_url`, `article_store_url` (the product page URL itself),
  `unit_price`, `sku` (slug of the name if none exposed).
- Verify the image URL loads (navigate to it or check network 200 + image type).
- One product by default; repeat per extra item the user asks for.

## Order + tracking setup (before the event loop)

Two `PUT https://api.parcellab.com/v4/track/orders/` calls, done directly (not by
the driver):

1. **Untracked order** — build a payload following the `create-order`
   shape: `account` (the resolved account id, `${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}`), `order_number` (`<XXX>-<ts>`),
   destination country ISO3, recipient, shipping address, `articles_order`,
   currency/timezone from the country. Save as `create.json` with **no
   `mutations`**. Send it → HTTP 201.
2. **Attach tracking** — send an `add_tracking` mutation with a randomised,
   format-correct `tracking_number`, the chosen `courier`, and the article list.
   This associates the courier/tracking so events have something to land on.
   (Do **not** put `checkpoints` in `add_tracking` — that field is output-only
   and the API rejects it.) **For a split shipment, send both `add_tracking`
   mutations in the same `mutations` array of one PUT** — see *Split shipments*.

   **Always set `tracking.articles` on every `add_tracking` mutation, even for
   a single-shipment order — not just `articles_order` at the order level.**
   Tracking-triggered comms (Out for Delivery, Delivered, delay updates) render
   their `{{articlesTableWithImages}}` placeholder from the **tracking-level**
   `articles` array, not from `articles_order` — that field only feeds the
   order-level confirmation email. Omitting it is why article name/image/price
   can look fine in the order-confirmation email but come back blank in every
   later shipment comm. Mirror the same items (with matching `line_item_id`s)
   from `articles_order` into `tracking.articles`:

   ```json
   "tracking": {
     "tracking_number": "<randomised>",
     "courier": "<chosen courier>",
     "articles": [
       {
         "line_item_id": "1",
         "article_name": "Classic T-Shirt — Black, M",
         "quantity": 1,
         "article_image_url": "https://picsum.photos/seed/tshirt/400/400",
         "article_store_url": "https://example.com/products/classic-t-shirt"
       }
     ]
   }
   ```

   For a split shipment, each tracking's `articles` gets only the line items
   in that parcel (see *Split shipments*).

## Event sequence

Events are pushed via **`POST https://api.parcellab.com/v4/track/events/`**
(trailing slash required; success = **HTTP 204**), one standalone POST per stage —
there is no cumulative array. For each stage in the chosen sequence (see
`references/status-codes.md`), write `NN-<status>.json` containing:

```json
{
  "event_status": "InTransit",
  "location": "Regional Hub",
  "courier": "dpd-uk",
  "tracking_number": "<the same tracking_number used in add_tracking>"
}
```

**Do not include `event_timestamp` in this file.** The driver injects it at
the moment it sends each event, stamped with real wall-clock "now" — see
*Timing & background execution*. A precomputed timestamp (future OR past)
makes the checkpoint disagree with when its comm actually sends, since comms
always fire at real send time regardless of what the payload claims.

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
6. **Gate B and Reporting** should summarise **per shipment** — courier,
   tracking number, and how far its scenario goes — so the user can see both
   outcomes clearly before and during the run.

## Journey pre-check (optional, Tier 1)

Before running a sequence — especially a **custom one that diverges from the
proven default** — you can sanity-check that the account actually has a
published Journey trigger for each stage, so a failure to fire a comm isn't a
surprise after the fact.

**This is informational only, not a blocking gate, and requires tooling not
every session has:**

1. Try `journey_list_journey_configurations` (account Product-API MCP tools)
   with `account=[${PARCELLAB_ACCOUNT_ID:-$PARCELLAB_USER_ID}]`, `release_status="published"`. **If
   this tool isn't available in the current session, skip this step
   entirely** — say so briefly and move on to Gate B. Never block the run on
   its absence.
2. If available, for each Journey's triggers, fetch
   `journey_get_journey_trigger_configuration` and note each trigger's
   `events[].eventTypes` and `slotTypes`.
3. Present a short table to the user: Journey name → trigger name →
   eventTypes/slotTypes, filtered to the slots relevant to lifecycle
   simulation (`onDeliveryStatus`, `onDispatch`, `onDelivered`, `onDelay`,
   `onOrderCreated`, `onTrackingCreated`). Flag which stages in the chosen
   sequence look covered.
4. **Matching is not always a literal string match** — some triggers key on a
   `slotType` with a wildcard (`eventTypes: ["*"]`), and parcelLab sometimes
   resolves an `event_status` to a different internal label before matching
   (e.g. `Delivered` resolved to `Unknown` in `delivery_location_type` when
   matching an `onDelivered` trigger). Only the four proven stages
   (`WarehouseDelay`, `InTransit`, `OutForDelivery`, `Delivered`) plus the
   automatic order-confirmation trigger have been empirically confirmed to
   match. For any other `event_status`, treat the table as "looks plausible"
   rather than a guarantee — the only real proof is running it and checking
   `contacted_with_messages` afterward.

## Timing & background execution

Launch the driver detached so it survives the session moving on:

```bash
EVENTS_DIR="<run dir>" GAP_SECONDS="<gap, default 120; 180 recommended>" \
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

## Confirmation gates

- **Gate A:** product(s) approved before building payloads.
- **Gate B:** full plan approved before `00-create.json` is sent.
After Gate B the sequence runs unattended.

## Reporting

Tail `EVENTS_DIR/run.log`. After each event report the pushed `event_status` and
HTTP code (**204 = accepted**, not yet attached). On any non-2xx, surface it and
pause for the user. Once the sequence completes, verify attachment with a public
order-info lookup (account + courier/tracking_number) and report the actual
checkpoint list and `contacted_with_messages` — that is the real proof of
success, not the 204s.

**Wait at least 5 minutes after the final event before treating a missing comm as
a problem.** Comms do not arrive at a uniform lag: in a live run the order
confirmation, dispatch and out-for-delivery comms each appeared within ~3-4
minutes of their event, but `package_delivered_*` took **over 5 minutes** —
noticeably longer than the rest. Checking at ~3 minutes showed all four
checkpoints attached with only three comms, which looks exactly like a broken
delivered trigger and isn't.

**Do not go digging in Journey config before that 5 minutes has elapsed.** Doing
so wastes real effort on a non-problem — and in one investigation produced a
plausible-but-wrong diagnosis (the delivered action has
`recipientCustomer: false, recipientPlTest: true`, which looks like the cause
until you notice the out-for-delivery action that *did* fire carries the
identical recipient config).

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