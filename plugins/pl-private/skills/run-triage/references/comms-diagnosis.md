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
parcellab journey event list --account <id> --page-size 200 -o json
```

An empty account-specific result (every row `account: 1`) means the account has
no custom mapping and relies entirely on global trigger-events — which do not
cover raw delivery-status delay checkpoints.

> **Command corrected 2026-08-17.** This entry originally documented
> `parcellab api request GET "/v4/journey/trigger-events/?account=<id>"`. That
> path returns a **404 Resolver404** — the resource is `journey event`, not
> `journey trigger-events`. The ledger's own rule is that an entry a later
> reader cannot re-check is one they will re-derive; a 404 in the "How to check"
> block is exactly that, so the working command replaces it above.

### The same slot mismatch also affects account 1622356 — confirmed on two runs

**Proven 2026-08-19** (triaging rows written 2026-08-19 for runs on 2026-08-18),
account 1622356, runs `lovehoney-20260818-1306` (order `#1002`) and
`sportsshoes-20260818-1705` (order `#1005`). Both rows independently reported
`delay_update` never firing for a `WarehouseDelay` checkpoint, confirmed on
each run by two checks 5-10+ minutes apart.

`journey event list --account 1622356` (71 rows) has no account-specific event
mapping `WarehouseDelay`/`Exception` onto `onDeliveryStatus` — only the global
wildcard "All events" (id 15308, `account: 1`) covers that slot, and it is not
wired into the relevant trigger. The "Delay Update" messageType (33912,
message 75557) is `releaseStatus: published` / `hasReleasedVersion: true` /
`active: true` on `en` — ruling out message release before it's even
considered. Its journey (`Standard Delivery Notifications`, config 15958)
trigger 52398 ("Package delayed in transit") is wired only to global event
**3808** (`onDelay` slot) — identical wiring shape to 1626102's trigger 54636.

Checked against control **1626718** (Jamie's own account): its account-specific
event **17372** (`WarehouseDelay`, `Exception` → `onDeliveryStatus`) still
resolves as of 2026-08-19.

Checkpoints did attach correctly: `track tracking list --account 1622356`
shows both order `#1005` and order `#1002` at
`activityMonitorCurrentDeliveryStatus: WarehouseDelay` — so this is the
trigger-wiring gap, not a missing checkpoint, exactly as on 1626102.

**The rule this adds:** the slot-mismatch gap is not unique to 1626102. Any
demo-shell account without an account-specific `onDeliveryStatus` event
mapping for `WarehouseDelay`/`Exception` will silently drop delay comms the
same way. Check `journey event list --account <id>` for this mapping on
**any** account before assuming a delay comm's absence is run-specific —
across the pool seen so far (1622356, 1626102), both instances found the gap,
none found a working per-account mapping other than 1626718 (which is not a
demo shell). Not yet written: whether the wider demo-shell pool (1622522,
1622456) shares the same gap — check before reusing them for a delay-comm
demo.

### The same slot mismatch recurred on 1626102 three days later — unfixed accounts re-offend

**Re-proven 2026-08-17**, account 1626102, run `windsor-20260817-0956`. Identical
symptom (`WarehouseDelay` pushed on orders #1094-B and #1095, "Parcel delayed -
all" never fired, rechecked twice), identical cause, same account as the
2026-08-14 `grailed` proof above. Nothing had changed: `journey event list`
still returns 63 rows, all global `account: 1`, while the control 1626718 still
carries account-specific event 17372.

The trigger is **54636** `Emails | Delay: Parcel delayed - all`, wired only to
global event 3808 (`onDelay`). Message check: messageType 35988
(`parcel_delayed_all_b612`), message 82254, `releaseStatus: published` /
`hasReleasedVersion: true` / `active: true`.

**The rule this adds:** a demo-environment run on an account with a known,
unremediated trigger-event gap will reproduce the same missing comm every time.
Before triaging a delay comm on account 1626102, check this ledger first — the
answer is already here, and the account write that would fix it has not been
made.

### The 1626102 slot mismatch is now a three-time repeat offender, and it can disguise itself as a "wrong account" message

**Proven 2026-08-20**, account 1626102, run `canyon-20260820-1348`, order `#1098`
shipment B (`WarehouseDelay`, order-level comm `delay_update`). The row's own
stated hypothesis — *"message 35988 belongs to a different account (1620732),
wrong language/type"* — is **disproven**: `journey message list --account
1626102` shows message **82254** (messageType 35988, `en`, `releaseStatus:
published`, `hasReleasedVersion: true`) live on **1626102 itself**. The
confusion is `messageType` (a shared numeric identifier, 35988) vs `message`
(the account-specific instance carrying that type, 82254) — reading the
`messageType` id alone and expecting it to name one owning account is the
trap.

The actual cause is unchanged since 2026-08-14: `journey event list --account
1626102` is still 63 rows, all global (`account: 1`); trigger **54666**
"Delivery delayed" (journey config 17475) is still wired only to global event
**3808** (`onDelay` slot). `WarehouseDelay` checkpoint confirmed attached
(order `#1098` shipment B reads `activityMonitorCurrentDeliveryStatus:
WarehouseDelay`). This is the same account, same trigger id, same wiring gap
as `grailed-20260814-1256` and `windsor-20260817-0956` — a full week later,
still unremediated.

**The rule this adds:** on account 1626102 specifically, treat any "wrong
account" or "message doesn't belong here" hypothesis about a delay comm with
suspicion — check `journey event list --account 1626102` for the known slot
gap before accepting a different story, because the same numeric
`messageType` id existing correctly-released on the *right* account is easy to
misread as evidence of the opposite.

### A shop not set up to process messages sends nothing, while journey, messages and triggers all read healthy

The whole comms chain can check out — journey `published`, every message
`hasReleasedVersion: true`, triggers wired to the right events, checkpoints
attached, delivery status reaching `Delivered` — and the account still sends
zero emails, because the **shop/client** the orders belong to was not configured
to process messages. Every object this file tells you to check is downstream of
that, so all of them look correct.

**Account 1622522, run `footlocker-20260814-1256`.** Reported by the account
owner on 2026-08-17: *"the shop was incorrectly setup to process messages"*, and
fixed by them that morning, confirmed by a test send
(`package_delivered_f4dd`, 2026-08-17T09:48) — the account's only email up to
that point.

**Recorded as owner-reported, not triage-proven.** The repair landed hours
before the triage read the account, so the broken state was never inspected
read-only and no command here demonstrates it. It is written down because the
*shape* is what costs time: this triage spent calls confirming journey, message
release state and trigger wiring were all fine, which was true and irrelevant.

**How to check:** when comms are zero **account-wide** — not one comm missing,
but nothing at all — check the shop/client object before working down the
journey chain:

```bash
parcellab config client list --account <id> -o json
```

A per-message or per-trigger fault cannot explain an account that has never sent
anything; that pattern points at shop/client setup or ownership, not at the
journey. See also *An account you do not own* in **Open questions** — if the
account is not yours, stop at the observation.

### An account with zero Journey Configurations sends nothing — check config count before anything else

Not a wiring gap on an existing journey (see the trigger-event slot mismatch
above) and not a shop/client setup fault (see *A shop not set up to process
messages* above) — this is simpler and more fundamental: the account has **no
Journey Configuration objects at all**. `journey configuration list --account
<id>` returns `count: 0`, and the account's own message-type(s) show
`messages: []` and `triggers: []` — there is nothing to wire because nothing
was ever built.

**Proven 2026-08-17**, account 1622524 ("Demo - Armand Castro", a demo shell
under "Demo SolCon" parent 1621786), run `lightformshop-20260817-1155`.
`journey configuration list --account 1622524` → `count: 0`. Compared against
4 sibling demo shells under the same parent: 1622522 → 2 configs, 1622456 → 2,
1626102 → 2, 1622356 → 4. Account 1622524 is the outlier, not the norm for
this pool — sibling shells routinely carry pre-built journeys.

**How to check:**

```bash
parcellab journey configuration list --account <id> -o json
```

A `count` of 0 explains a zero-send account on its own; no journey, trigger,
message, or shop/client check downstream of it can add information once this
is confirmed.

**Ownership note:** this account was not the run's own persistent demo
account — it belongs to a named colleague's demo shell ("Demo - Armand
Castro"), reused for this LightForm build. Per *An account you do not own*
below, the account's own config is not this triage's to fix; the durable fix
is a demo-environment pre-flight check (tracked in [issue #9](https://github.com/jamie1leesmith-lgtm/parcellab-claude-skills/issues/9))
so a run on an unprepared shell fails in under a minute instead of after
~90 minutes of scrape/template/orders work.

## Proven non-causes — spend no calls re-deriving these

### An empty `filterExpression` on the trigger is not why a delay comm was skipped

When a delay comm does not fire, the intuitive next look is the trigger's filter.
On the accounts seen so far the filter is simply **empty** — so it cannot be
what blocked anything, and looking there burns calls without narrowing.

**Proven 2026-08-17**, account 1626102, trigger 54636: `filterExpression: {}`.
This was the `windsor-20260817-0956` row's own stated hypothesis ("worth a
follow-up on the trigger's filter config") and it was wrong; the cause was the
event slot mismatch above. Check the trigger's **`events[]` slot mapping**
before its filter.

Not to be confused with *An empty `filterExpression` does not mean a journey
will mail anyone* below. That entry says an empty filter is not **sufficient**
for a send; this one says an empty filter is not the **blocker**. Both hold at
once — an empty filter tells you nothing in either direction, so it is never
the object to spend calls on first.

### A trigger can embed an event record that no longer resolves

Reading a trigger's inline `events[]` can show an account-specific event that
looks like the custom mapping you are hunting for. It may be dead.

**Proven 2026-08-17**, account 1626102: trigger 54641 (`Emails | Delay: Parcel
delayed - other`) embeds event **17719** (`account: 1626102`, eventTypes
`["Exception"]`, slotTypes `["onDelay"]`). That event is absent from
`journey event list` and `parcellab journey event show 17719` returns all-null
fields, while the control's live event 17372 both appears in its list and
resolves. So `journey event list` is the trustworthy source; a trigger's
embedded copy is not.

Do **not** read an embedded account-specific event as proof the account has a
custom mapping — resolve it with `journey event show` first.

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

### `checkpoints: 0` from `track tracking show` is not evidence that events never attached

`track tracking show` does not return a `checkpoints` (or `history`) array at
all, so reading its length gives `0` on a perfectly healthy tracking. Treating
that as "the run's events never landed" turns a comms question into a
non-existent orders-lane bug.

**Proven 2026-08-17.** Tracking `6a7f81247ce68cc93c30cbe7` (account 1622522) read
`checkpoints: 0` — and so did the control tracking `6a82e4406d4f4d2f38c2e8cb` on
1626102, whose events are known to have attached. The same call also returns
`reporting_info: {}`, so `contacted_with_messages` reads `None` here regardless
of truth.

**Read these fields instead**, which do carry real state:

```bash
parcellab track tracking show <id> -o json
# activityMonitorCurrentDeliveryStatus, reportingPickupDate,
# reportingInTransitDate, reportingCourierDropoffDate, reportingDeliveryDate
```

On the tracking above those showed `Delivered` with all four dates set to
2026-08-14 — the events had attached all along.

This is the general lesson behind this file's control-comparison rule: **an
absent or zero field is only evidence once the same call on a known-good account
returns something different.**

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

- (Opened and closed 2026-08-17, kept so the reasoning is visible.)
  ~~Account 1622522 (Foot Locker) sends almost nothing and no known cause
  explains it.~~ **Closed as out of scope, not as a defect.** From run
  `footlocker-20260814-1256`: the account had sent exactly one email in its
  lifetime (`package_delivered_f4dd`, 2026-08-17T09:48), while everything
  checkable read healthy — journey 14173 `published`, all 15 messages
  `hasReleasedVersion: true`, 15 triggers on sensible events, and the run's own
  tracking at `Delivered`. **Cause since supplied by the account owner: the shop
  was not correctly set up to process messages**, fixed by them on 2026-08-17
  before this triage ran — that lone email was their test send. Written up as a
  proven cause above (*A shop not set up to process messages…*); it is account
  configuration owned by that account's user, not a demo-environment defect.

  **The rule, and it is the reusable part:** an account you do not own can
  produce zero comms for reasons triage can neither see nor fix. Before treating
  a zero-send as a run defect, establish who owns the account. If it is not the
  runner's, record the observation and stop — do not diagnose it, and do not
  propose changing its live config. See also the note in *Adding an entry* about
  reading a live account in its **present** state: config inspected today is not
  evidence about a run three days ago, because someone may have changed it in
  between — as happened here.

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

**Date every claim about live config, because you are reading the account as it
is now, not as it was during the run.** Accounts get changed between a run and
its triage — sometimes by the run's own owner, sometimes by someone else. A
healthy-looking config is therefore not evidence that the config was healthy
when the comms failed, and an entry that omits the read date cannot be
re-checked against that risk. **Proven 2026-08-17**: the
`footlocker-20260814-1256` triage read account 1622522 as fully configured and
briefly recorded its zero-send as unexplained — the owner had in fact repaired
the account and test-sent that same morning, hours before the triage looked.
Where it matters, say both dates: what the run did, and when you read the
account.

Findings about the sweep or ledger tooling itself — not about why a comm did or
did not fire — do not belong in this file. See `scripts/triage_sweep.py`'s
`multi_select()` docstring and its commit `0a72a3a` for an example: the Notion
connector returns multi-select columns as JSON strings, which inflated every
severity score until the sweep coerced them.
