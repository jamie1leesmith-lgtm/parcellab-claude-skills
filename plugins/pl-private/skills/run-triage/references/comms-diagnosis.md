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

### An empty `filterExpression` does not mean a journey will mail anyone

Filter eligibility is necessary, not sufficient — a recipient role in
`additional_recipients` may still be required, matching the journey's
`advancedRecipients` exactly and case-sensitively.

See the *Known limitation: recipient roles are a second gate* section of
`order-lifecycle`'s SKILL.md.

### A missing comm inside the first 15 minutes is not yet evidence

Comms do not arrive at a uniform lag. `package_delivered_*` is consistently
slowest — measured at over 10 minutes on one parcel of a split order
(2026-08-11, account 1626718).

Checking early shows every checkpoint attached with a comm missing, which looks
exactly like a broken trigger and is not. Wait the full window before forming a
theory.

## Open questions

- **`Delivered` (messageType 30891) on account 1626102** has
  `hasReleasedVersion: true` but has never been exercised. The 2026-08-12 run's
  arc was `TrackingCreated → Dispatch → InTransit → WarehouseDelay`, so
  `Delivered` was never pushed. Whether it sends on that account is untested.

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
