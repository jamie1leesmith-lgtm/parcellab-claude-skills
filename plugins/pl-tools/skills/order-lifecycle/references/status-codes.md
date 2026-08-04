# parcelLab lifecycle event statuses

Events are pushed via `POST https://api.parcellab.com/v4/track/events/`
(trailing slash required; success = HTTP 204). Each POST is one standalone
event body — NOT a cumulative array.

> **Identifier: always use `courier` + `tracking_number`.** `account` +
> `order_number` is documented as a valid alternative, but live testing on
> account 1626718 showed it never attaches to the tracking timeline (tested
> twice, 40+ minutes apart, no attachment). `courier` + `tracking_number` is
> what parcelLab's own production Custom Demo Creator tool uses exclusively
> for this endpoint, and it reliably attached and fired comms in testing.
> Never use `account` + `order_number` for this skill.

Required fields per event:
- `event_status` — MUST be one of parcelLab's fixed enum (below). This is the
  events-endpoint enum, which is NOT the same as the status-model names
  (e.g. there is no `OrderProcessed`/`PickUpScheduled` here).
- `event_timestamp` — ISO 8601. **Do not set this when building the payload
  file.** See *Timestamp rule* below — the driver injects it at send time.
- `courier` + `tracking_number` — the same values used in the `add_tracking`
  setup mutation.
- `location` — optional free text.

## Timestamp rule (critical)

**The driver stamps `event_timestamp` with the real wall-clock time at the
moment it actually sends each event.** Do not put `event_timestamp` in the
`NN-<status>.json` files at all — `run-lifecycle.sh` injects it via a `python3`
JSON merge immediately before each POST.

Why: comms always send at real wall-clock time — that's outside anyone's
control, it's just when the API happens to process the request. The
checkpoint's displayed time is whatever `event_timestamp` you send. If those
two disagree, the timeline looks broken. Two failed attempts proved this
concretely:
- `event_timestamp = now + Nh` (future offsets computed at build time) → every
  checkpoint sorted *after* the comm that was triggered by it.
- `event_timestamp = now - 48h + Nh` (anchored in the past, matching
  parcelLab's own Custom Demo Creator script) → checkpoints sorted *before the
  order itself was created*, since the whole run happens within minutes of
  real "now" but the timestamps claimed to be up to two days earlier.

Both are wrong because they precompute the timestamp once, at build time, and
the real send happens minutes to hours later (across the `GAP_SECONDS`
delays). The only value that stays correct through a multi-minute run is the
one captured **at the instant of sending** — which is real time by
definition, and matches whatever time the comm actually sends at. One event,
sent now, produces a checkpoint stamped now and a comm sent now: they agree.

Comms fire only if the account maps `event_status` to a status and has a
matching Journey/trigger; a 204 confirms ingestion, not that mail sent.
Attachment is **asynchronous** — allow several minutes before checking whether
a checkpoint landed; don't conclude failure from an immediate re-read.

## Proven default sequence — genuine happy path (no delay)

```
InTransit → OutForDelivery → Delivered
```

**Use this as the default "happy path."** All three stages are independently
proven to attach and fire the correct comm (confirmed across multiple live
runs). This deliberately **excludes `WarehouseDelay`** — see the note below.

| event_status    | location (example)  |
|-----------------|----------------------|
| InTransit       | Regional Hub         |
| OutForDelivery  | Local Depot          |
| Delivered       | Recipient address    |

> **`WarehouseDelay` is not part of the happy path — it means "delayed."**
> parcelLab's own Custom Demo Creator script (`main.py`) uses a four-stage
> "full" schedule of `WarehouseDelay → InTransit → OutForDelivery →
> Delivered`, which this skill originally copied and mislabeled as "happy."
> It isn't — a shipment starting with `WarehouseDelay` shows a delay
> checkpoint, which is wrong for a scenario meant to represent a clean
> delivery with no issues (confirmed live: it showed up on a shipment
> explicitly meant to have no delay, in a split-shipment test). Only use
> `WarehouseDelay` when you actually want to demonstrate a delay — e.g. as
> the first stage of the *partial-delay* scenario below, or prepended to the
> happy sequence if the user explicitly asks for "happy path, but delayed at
> first."

## Full valid `event_status` enum (from the live API's validation error)

`WarehousePending`, `WarehousePrepared`, `WarehouseDelay`, `Loaded`,
`InboundScan`, `InTransit`, `ExportHub`, `ImportHub`, `CustomsIn`,
`CustomsReleased`, `Exception-AddressIssue`, `Exception-CustomerRefusal`,
`Exception-Customs`, `Exception-Damaged`, `Exception-DeliveryPayment`,
`Exception-IdentFailed`, `Exception-ItemMissing`, `Exception-Notified`,
`Exception-Strike`, `ScheduledDelivery ###`, `ScheduledTomorrow`,
`DestinationDeliveryCenter`, `OutForDelivery`, `FailedAttempt-NewAttemptNextDay`,
`FailedAttempt-NewAttemptToday`, `FailedAttempt-PickUpReady`,
`FailedAttempt-Scheduled ###`, `PickupReady`, `PickupReady, collect at ###`,
`Delivered`, `Delivered-Doorstep`, `Delivered-HomeDeposit`,
`Delivered-Neighbor`, `Delivered-Notified`, `Delivered-ParcelLocker`,
`Delivered-ParcelShop`, `Delivered-Postbox`, `ReturnToSender-Damaged`,
`ReturnToSender-DeliveryPayment`, `ReturnToSender-NotCollected`,
`ReturnToSender-Recall`, `ReturnDroppedOff`, `ReturnInProcess`,
`ReturnDelivered`, `ReturnRefunded`, `RMAProcessed`.

These extras are **untested** for this skill (only the four-stage sequence
above has been confirmed to attach) — use them for alternate scenarios but
verify attachment via a lookup before trusting a new sequence.

## Sequences

- **happy** (default, proven, no delay): InTransit, OutForDelivery, Delivered
- **happy-with-delay** (only if the user explicitly wants an initial delay on
  an otherwise-successful shipment): WarehouseDelay, InTransit, OutForDelivery, Delivered
- **failed-attempt** (untested): InTransit, OutForDelivery, FailedAttempt-NewAttemptNextDay, OutForDelivery, Delivered
- **exception** (untested): InTransit, Exception-Notified, InTransit, OutForDelivery, Delivered
- **return** (untested): InTransit, OutForDelivery, FailedAttempt-NewAttemptNextDay, ReturnToSender-NotCollected, ReturnDelivered
- **partial-delay** (for the "stuck" shipment in a split-shipment demo): send
  only the first 1-2 stages, then stop emitting events for that tracking —
  it stays live at whatever status it last reached.
  - Single-stage (proven): `WarehouseDelay` only.
  - Two-stage (partly untested): `WarehouseDelay` (proven), then
    `Exception-Notified` (untested — verify via lookup after running).
