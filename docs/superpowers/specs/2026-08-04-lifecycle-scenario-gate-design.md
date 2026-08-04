# order-lifecycle: three-gate flow with scenario selection and journey introspection — design

**Date:** 2026-08-04
**Status:** approved, ready for planning
**Skill:** `plugins/pl-tools/skills/order-lifecycle/`

## Problem

The skill picks its event sequence for the user. It defaults to the proven happy
path and only diverges if the user thinks to ask, which means:

1. **The user never sees which comms will fire.** A live run of the happy path
   fired four emails — order confirmation, dispatch, out-for-delivery, delivered.
   Nothing told the user that in advance. For a skill whose whole purpose is
   demonstrating post-purchase comms, the comms are invisible until after the fact.
2. **Anything other than the happy path requires knowing the internals.** The
   reference file documents `failed-attempt`, `exception` and `return` sequences,
   all marked untested. Reaching them means reading `references/status-codes.md`.
3. **Nothing checks whether the account will actually respond.** Events are pushed
   blind. If no Journey trigger matches, the run returns a clean set of `204`s,
   the checkpoints attach, and no comms fire — with no signal that anything is
   wrong.
4. **Order enrichment is invisible.** `additional_recipients`, promise dates,
   financials and tags are all supported by the API and documented in
   `create-order`, but a lifecycle run never offers them, so they are effectively
   undiscoverable.

## Goals

- The user chooses the scenario **every run** — no silent default.
- Before anything is sent, the user sees **which events fire and which comms each
  is expected to produce**.
- A custom scenario is derived from **the account's actual Journey config**, not
  from the user's memory of it.
- The user is offered the optional order fields once, concretely, with a one-word
  exit.
- Confidence is stated honestly: a mapping derived from config is a proposal, not
  a guarantee.

## Non-goals

- Changing the happy path. It is proven and stays exactly as it is.
- Changing the driver (`run-lifecycle.sh`), timing, or the timestamp rule.
- Changing split-shipment mechanics.
- Editing Journey config. This skill **reads** Journey config and never writes it.
- Guaranteeing an email. The skill reports `contacted_with_messages`; it never
  promises mail.

## Gate structure

Three gates, replacing the current two.

| Gate | Purpose | Blocking |
|---|---|---|
| **A** | Product(s) sourced from the brand site | yes |
| **B** | Journey + scenario: events and expected comms | yes |
| **C** | Order enrichment, then final approval to send | yes |

The send confirmation folds into Gate C, so the run still has three stops rather
than four. Gate B must precede Gate C, because the journey chosen at B can make
certain order fields **required** at C.

---

## Gate B — scenario selection

Always asked. No default, no inference from context.

### The three options

**1. Happy path** — unchanged, the proven default.

```
InTransit → OutForDelivery → Delivered
```

**2. Unhappy path** — ends delayed, never delivers.

```
InTransit → WarehouseDelay        (then stop)
```

Both statuses are proven. This reuses the documented *partial-delay* pattern: stop
emitting events and the last one stands as the live state indefinitely.

Rejected alternatives, recorded so they are not revisited:

- `InTransit → OutForDelivery → WarehouseDelay` — incoherent. A *warehouse* delay
  cannot follow a parcel already out for delivery.
- `InTransit → OutForDelivery → FailedAttempt-NewAttemptNextDay` — better story
  and matches the happy path's three-event shape, but `FailedAttempt-*` is
  unverified and may `204` without attaching. Available via the custom path, where
  its risk is labelled.
- `WarehouseDelay → InTransit → OutForDelivery → Delivered` — all proven, but ends
  delivered, so it is not an unhappy outcome.

**3. Custom path** — derived from the account's Journey config. See below.

### Split shipments belong at Gate B, not Gate C

A split shipment is a decision about events and comms, not about order fields, so
Gate B owns it. Ask first whether the run is **one shipment or a split**; for a
split, ask a scenario **per shipment** from the same three options, then confirm a
courier per shipment (they may differ).

This is where the three options earn their keep: the canonical split-shipment demo
is one shipment on the happy path and one stuck at a delay, side by side — which is
now expressible as *"shipment A: happy, shipment B: unhappy"* rather than requiring
hand-built sequences.

Interleaving into one numbered sequence stays exactly as documented in the skill's
*Split shipments* section. The driver is unchanged — it marches through
`NN-*.json` regardless of which tracking each file targets.

**Gate C therefore does not offer split shipments.** Had it done so, a split chosen
at C would strand the single scenario chosen at B with nothing to say about the
second shipment.

### What Gate B displays

For options 1 and 2, the event list plus the comm each is expected to fire. These
mappings are empirically confirmed on account 1626718:

| Event | Expected comm | Trigger |
|---|---|---|
| *(order creation)* | `order_confirmation_*` | Order Confirmed |
| `InTransit` | `shipping_confirmation_*` | Package dispatched from warehouse |
| `OutForDelivery` | `out_for_delivery_*` | Package out for delivery |
| `Delivered` | `package_delivered_*` | Delivered (parcel delivered to recipient) |
| `WarehouseDelay` | delay comm | Package delayed in transit |

State that comms depend on the account's Journey config, and that the table above
reflects a standard delivery-notification setup.

---

## Custom path — journey introspection

Requires the Product-API MCP journey tools. **If they are unavailable, skip
introspection entirely, say so in one line, and fall back to asking the user to
describe the sequence in prose.** Never block a run on tool availability.

### Steps

**1. List every journey** — published *and* draft:

`journey_list_journey_configurations(account=[<id>])`

Show name, `releaseStatus`, and a plain-English eligibility line derived from
`filterExpression`. Do not filter the list; the user asked to see all of them.

**2. The user picks one by name.**

**3. Eligibility check — the critical step.** Choosing a journey by name is not
sufficient; the order must match that journey's `filterExpression` or the journey
never processes it. Three ways a chosen journey silently fires nothing:

| Condition | Detect via | Say |
|---|---|---|
| Journey is a draft | `releaseStatus != "published"` | It will not fire until published |
| Returns-only | filter requires `isReturnsPortal: true` | A forward shipment is never a returns portal record; name the journey that would catch this order instead |
| Order ineligible | filter requires fields the planned order lacks, e.g. `delivery_info.client $in [...]` | Name the field, and offer to set it at Gate C |

Where the mismatch is fixable, offer the fix. Where it is not, say which journey
*would* catch this order. Never proceed silently past an ineligible pick.

**4. Fetch that journey's triggers only** —
`journey_get_journey_trigger_configuration(id)` per trigger. One journey is
~5–12 triggers, so ~6–13 calls. Do **not** introspect all journeys: on account
1626718 that would be ~40 trigger calls.

**5. Present trigger → `eventTypes` → proposed `event_status`, with a confidence
label per row.** `eventTypes` is a *different vocabulary* from the `event_status`
enum the events endpoint accepts, so the mapping has three kinds:

| Confidence | Meaning | Example |
|---|---|---|
| **exact** | `eventTypes` contains the `event_status` verbatim | `OutForDelivery` → `OutForDelivery`; `WarehouseDelay` → `WarehouseDelay` |
| **inferred** | Obvious correspondence, different spelling | `ParcelLocker` → `Delivered-ParcelLocker`; `FailedAttemptFirst` → `FailedAttempt-NewAttemptNextDay` |
| **unverified** | Config cannot tell us | `eventTypes: ["*"]` on `onDispatch` — a wildcard matches anything on the slot. `InTransit` is known to reach it only because a live run proved it. |

Mark separately whether each `event_status` is one of the four **proven** values
(`WarehouseDelay`, `InTransit`, `OutForDelivery`, `Delivered`) or one of the ~42
untested ones. Confidence in the *trigger match* and confidence in the *status
attaching* are different axes; show both.

**6. The user selects which triggers to demonstrate, in order.** That selection is
the sequence. Build `NN-<status>.json` files from it exactly as now.

**7. After the run**, verify against `contacted_with_messages` and report which
inferred/unverified mappings actually fired. Offer to record newly confirmed ones
in `references/status-codes.md`, so each custom run reduces the untested surface
instead of the knowledge evaporating.

### Known limitation — recipient roles are a second gate

Filter eligibility is necessary but not sufficient. On account 1626718,
*Gifter Journey* has an empty `filterExpression` (so it matches every order) and
an *Out for Delivery* trigger, yet a live run produced only one
`out_for_delivery_*` comm. It almost certainly depends on `additional_recipients`
carrying a role listed in the Journey's `advancedRecipients` — the mechanism
`create-order` documents under *Dynamic Recipients*.

So a journey can be eligible, published, and still mail nobody. State this as a
limitation; do not attempt to resolve it from config, and never promise mail on the
strength of an eligibility check.

---

## Gate C — order enrichment and final approval

An offer with a fast exit, not a form: *"Anything else to add, or send as-is?"*
Default is send-as-is.

Present a concrete menu — "any other fields?" is unanswerable unless the user has
the API spec memorised. Anything Gate B marked **required** appears pre-filled and
is not optional.

| Extra | Fields | Constraint to state |
|---|---|---|
| Dynamic recipients | `additional_recipients: [{role, email}]`, order and tracking level | Role must match the Journey's `advancedRecipients` **exactly** — case-sensitive. Preserve the user's spelling even if it looks like a typo; the match is literal. Setting the field mails nobody unless the Journey lists that role. |
| Promise dates | `announced_delivery_date`, `_min`, `_max` | **`YYYY-MM-DD` only.** A full ISO datetime is rejected. (`order_date` does accept full ISO.) |
| Client key | `client_key` | Pre-filled when Gate B's journey requires one |
| Order financials | `order_tax_amount`, `order_net_amount`, `order_discount_amount` | For invoice-style comms |
| Extra articles | more `articles_order` entries, each with a unique `line_item_id` | Mirror them into `tracking.articles` or shipment comms render an empty table |
| Tags / custom fields | `tags`, `additional_attributes` | What filter-driven Journey triggers key on |
| Delivery detail | `delivery_method`, `courier_service_level`, `requires_signature` | Cosmetic in comms |

After the menu, display the built payload summary and take the send approval. That
is the last stop before anything reaches production.

---

## Error handling

| Situation | Behaviour |
|---|---|
| Journey MCP tools unavailable | One line saying so; fall back to prose description for custom. Never block. |
| Journey list empty | Report it; offer happy/unhappy only. |
| User picks a draft journey | State it will not fire; ask whether to continue anyway or pick another. |
| User picks a returns-only journey | State a forward shipment cannot match it; name the journey that would. |
| Order ineligible, fixable | Offer to set the field at Gate C. |
| Order ineligible, not fixable | Say so; do not proceed as though comms will fire. |
| Custom sequence contains an untested status | Label it; proceed if the user accepts; verify after. |
| Event returns non-2xx | Surface immediately and pause, as now. |
| Comm missing after a run | **Wait 5+ minutes before investigating** — the delivered comm lags the others. Only then check Journey config. |

## Testing

No unit tests: this is skill prose, not code. Verification is behavioural.

**Must confirm by running:**

1. Happy path still behaves identically — same three events, same four comms. This
   is a regression check on the one proven flow.
2. Unhappy path: two events attach, the delay comm fires, `is_delayed: true`, and
   the tracking stays delayed with no delivery.
3. Custom path with introspection available: journey list appears with statuses,
   an ineligible pick (*Shopify Comms* on a non-Shopify order) is caught and
   explained, and a `Delivered-ParcelLocker` run against *Collected from Locker or
   Shop* either fires or is honestly reported as not firing.
4. Custom path with tools unavailable: falls back to prose without blocking.
5. Gate C: promise dates accepted as `YYYY-MM-DD`; a datetime is rejected before
   sending, not by the API.
6. Skipping Gate C takes one word and changes nothing about the payload.
7. Split shipment: a per-shipment scenario is asked at Gate B, events interleave
   into one sequence, and shipment A reaches `Delivered` while shipment B stays
   stuck at its delay.

**Also confirm the gates cannot be bypassed** — a run with no user input at any
gate must stop, not guess.

## Consequences

- The unhappy path leaves an order permanently mid-delay in the account. Intended,
  mildly untidy if run repeatedly.
- Custom runs cost ~6–13 extra MCP calls for introspection.
- Three gates is more interaction than two. Mitigated by Gate C defaulting to
  send-as-is and Gate B being a single choice for options 1 and 2.
