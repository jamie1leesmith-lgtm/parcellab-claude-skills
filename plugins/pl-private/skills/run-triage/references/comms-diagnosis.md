# Why comms did not fire

Proven live. Each entry names the account and object it was proven against, so
it can be re-checked rather than taken on trust.

Non-causes are recorded as prominently as causes. A disproven hypothesis that
stays unrecorded gets re-derived — that is how the 2026-08-12 Kapten & Son run
lost about twenty minutes to a theory already known to be wrong.

## Proven causes

### A message with no released version renders nothing

`hasReleasedVersion: false` on the message behind a journey action means no email
is produced. The trigger still matches and the tracking event still names the
message it selected, so the event log looks healthy — which is what makes this
one expensive to find.

**Proven 2026-08-12**, account 1626102, journey 13736, messageTypes 30889 and
30890. The `Dispatch` event on tracking `6a7c4fbfd8c75e6486173d31` carries
`message: "shipping_confirmation_9c8f"`, and:

```bash
parcellab track email list --account 1626102
```

returns 0 rows for the entire account — not just for that tracking.

**How to check:** resolve each journey channel's `messageType` to its message and
read `hasReleasedVersion`:

```bash
parcellab journey message list --account <id> --page-size 200 -o json
```

### `order_confirmation` does not fire for Shopify-integration orders — by design, not a defect

On the retain-shopify path, orders arrive at parcelLab through the live Shopify
integration sync, not through the direct engine's `PUT /v4/track/orders/`. The
`order_confirmation` journey (trigger `onOrderCreated`) is not configured to
fire for these orders, because Shopify itself sends the customer its own
native order-confirmation email — parcelLab sending a second one would
duplicate it. This is expected account setup, not a misconfigured trigger or
an unreleased message.

**Proven 2026-08-14**, account 1626718, run `hotelchocolat-20260814-1128`,
message 33876 (`order_confirmation_1093`, journey 15924). The message is
`releaseStatus: published` and `active: true` for `en` — ruling out the
"message not released" cause before it's even considered. `order_confirmation`
fired zero times across all three retain-shopify orders (`pl-1035`, `pl-1036`,
`pl-1037`), while `shipping_confirmation`, `out_for_delivery`,
`package_delivered`, and `delay_update` all fired exactly as expected. Earlier
runs on the same account that used the **direct** engine (not Shopify) did
receive `order_confirmation_1093` sends — confirming the split is by engine
path, not a broken trigger.

**How to check:** if `order_confirmation` (or any order-level, pre-tracking
comm) is missing only on a retain-shopify run, check the path before treating
it as a defect — this is expected on that path and needs no fix.

### A `WarehouseDelay` checkpoint does not reach a "Delivery delayed" journey without an account-specific `onDeliveryStatus` trigger-event

`WarehouseDelay` is pushed via the events API on the `onDeliveryStatus` slot,
the same slot `InTransit`/`OutForDelivery` use. The **global** `🟡 Delay: Any
reason` trigger-event (id `3808`) that most "Delivery delayed" journeys are
wired to listens on the `onDelay` slot instead, matching semantic delay-*reason*
event types (`OperationalError`, `AddressIssue`, `TrafficProblems`, ...) — not
the raw checkpoint status. A journey trigger built only on event `3808` never
fires for a `WarehouseDelay` push, no matter how the message/journey itself is
configured.

**Proven 2026-08-14**, comparing account **1626102** (failing, run
`grailed-20260814-1256`) against account **1626718** (control, run
`hotelchocolat-20260814-1128`, where the equivalent comm fired twice
successfully). 1626718 carries an **account-specific** trigger-event, `🟡
Delivery status: warehouse delay or exception` (id `17372`), explicitly mapping
`eventTypes: ["WarehouseDelay","Exception"]` onto `slotTypes: ["onDeliveryStatus"]`
— that mapping is what lets its delay journey react to a raw `WarehouseDelay`
checkpoint at all. Account 1626102's full trigger-event list (63 rows, all
global `account: 1`) has no such mapping; its "Delivery delayed" journey
(config `17475`, trigger `54666`) is wired only to event `3808`. Message 35988
(`parcel_delayed_all_b612`) is `published`/`active` — ruling out the
release-status cause before it's even considered. Result: `WarehouseDelay`
checkpoints attached correctly on both shipments (order `#1090` parcel-b/fedex,
order `#1091`/usps), the message could send, but the trigger never matched, so
zero of two eligible sends went out.

**How to check:** if a delay/exception-style comm is missing and the message
is confirmed released, check whether the account has an account-specific
trigger-event mapping the raw checkpoint status (`WarehouseDelay`, `Exception`,
etc.) onto `onDeliveryStatus` — do not assume the global `onDelay` "Delay: Any
reason" event covers it, because it doesn't.

```bash
parcellab api request GET "/v4/journey/trigger-events/?account=<id>" -o json \
  --jmes "results[?account==<id>]"
```

An empty result means the account has no custom mapping and relies entirely on
global trigger-events — which do not cover raw delivery-status delay
checkpoints.

## Proven non-causes — spend no calls re-deriving these

### `releaseStatus: draft` does not block sending

A draft message serves its last released version.

**Proven 2026-08-12**: account 1626718 message 75240 is `draft` with
`hasReleasedVersion: true`, and has sent 51 emails.

`hasReleasedVersion` is the gate; `releaseStatus` is not. Checking the wrong one
of these two produces a confident wrong answer, since most drafts on a healthy
account do have a released version.

### `recipientCustomer: false` with `recipientPlTest: true` does not block sending

This is normal demo-account configuration. It targets the parcelLab test
recipient and records the email with `live: false`.

**Proven 2026-08-12**: account 1626718 sent 100 emails with channel config
byte-identical to the failing account's — `recipientCustomer: false`,
`recipientPlTest: true`, `recipientSendTo: []`.

This is the hypothesis the Kapten & Son row proposed. It had already been
disproven once before that.

### A message-level `layout` pin does not override the client auto-template

A message can carry an explicit `layout` id (not `null`), left over from an
earlier run that built it. This looks like it would win over the account's
`autoLayout` mapping — it doesn't. The client auto-template still governs what
actually renders.

**Proven 2026-08-13**, account 1626718, message 75240
(`out_for_delivery_00d7`), run `adidas-20260813-1033`. Message 75240 carries
`layout: 19453` (a Moonpig layout, left from an earlier run). The client
auto-template for the store this run used was set to the adidas layout
(20736). A triage inferred from the pin alone that the fired emails would
render as Moonpig — **wrong**: visual inspection in the app confirmed every
email rendered as adidas.

**There is no read-only API check for this.** `track email list` /
`track email show` expose only a storage path to the rendered HTML, and
`track notification`'s `body` field returns the messageType key, not content.
**A message's `layout` field is not evidence of what actually renders — treat
it as unverifiable without opening the email in the portal, and say so rather
than inferring an outcome.**

### An empty `filterExpression` does not mean a journey will mail anyone

Filter eligibility is necessary, not sufficient — a recipient role in
`additional_recipients` may still be required, matching the journey's
`advancedRecipients` exactly and case-sensitively.

See the *Known limitation: recipient roles are a second gate* section of
`order-lifecycle`'s SKILL.md.

### A missing comm on a single look is not yet evidence

Comms do not arrive at a uniform lag. `package_delivered_*` is consistently
slowest — measured at over 10 minutes on one parcel of a split order
(2026-08-11, account 1626718).

Checking early shows every checkpoint attached with a comm missing, which looks
exactly like a broken trigger and is not.

The run window was 15 minutes until 2026-08-12, when it came down to 5. **A
triage therefore cannot assume a run's own Beat 2 waited long enough for a slow
split parcel.** Before treating a row's "comm missing" as real, check the gap
between the final event and the verification, and re-look yourself — a comm that
has since landed turns the finding into a timing artefact, not a defect.

### `contacted_with_messages` undercounts sends — never count comms from it

`trackings[].reporting_info.contacted_with_messages` is **per tracking and
deduplicated**, so an order-level comm appears once in each tracking's array and
reads as a single send. On a split-shipment order that hides a real duplicate.

**Proven 2026-08-13**, account 1626718, run `adidas-20260813-1033`. Order
`ADI-1786614815` has two trackings, each listing `order_confirmation_1093` once.
The run's own Beat 2 therefore reported 15 comms. The account actually sent 16:

```bash
parcellab track email list --account 1626718 --page-size 30 -o json \
  --jmes 'results[].{mt:messageType,at:createdAt}'
```

Four `order_confirmation_1093` sends, two of them for `ADI-1786614815`
(09:55:16 and 09:55:47) — one per tracking. The customer receives the same
order-confirmation email twice for one order number.

`contacted_with_messages` is still the right source for *which* comm a tracking
selected. It is the wrong source for *how many* were sent — use
`track email list` for counts, and expect an extra order-level comm per extra
tracking.

## Open questions

- (Resolved 2026-08-12, closed rather than deleted so the history is visible.)
  ~~`Delivered` (messageType 30891) on account 1626102 has `hasReleasedVersion:
  true` but has never been exercised...~~ Moot: journey `13736` and messageType
  30891 no longer exist. The account was rebuilt into two new journeys
  (`Outbound Email Flow` 17475, `Return Experience Flow` 17476), published
  `2026-08-12T12:24`, with every message `hasReleasedVersion: true`. Two test
  sends at `13:21` confirm delivery-stage comms now work on this account.

## Adding an entry

Give each entry the account and object it was proven against, and the command
that shows it. An entry a later reader cannot re-check is one they will end up
re-deriving, which defeats the file.

A hypothesis that turned out wrong belongs under *Proven non-causes*, not
deleted. Knowing what has already been ruled out is most of the value here.

Findings about the sweep or ledger tooling itself — not about why a comm did or
did not fire — do not belong in this file. See `scripts/triage_sweep.py`'s
`multi_select()` docstring and its commit `0a72a3a` for an example: the Notion
connector returns multi-select columns as JSON strings, which inflated every
severity score until the sweep coerced them.
