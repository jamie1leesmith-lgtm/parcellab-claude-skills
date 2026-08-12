# run-triage timing phase — design

**Date:** 2026-08-12
**Status:** approved in brainstorming, not yet planned
**Supersedes:** nothing. Fills a gap in
[2026-08-12-run-telemetry-triage-design.md](2026-08-12-run-telemetry-triage-design.md),
which built `run-triage`'s correctness track (Phase 2, `comms-diagnosis.md`) but
never built its speed track, despite Jamie naming optimization a primary goal
when the skill was first brainstormed.

## Why

Running the skill for real surfaced the gap. `rank()` in `triage_sweep.py`
reads `Largest gap` only as a tie-breaker — the last term checked, after
severity — to decide *which* row to open. Once Phase 2 starts, it investigates
exclusively through `comms-diagnosis.md`, which is scoped to *why comms don't
fire*. There is no phase for *why a run is slow*, and no ledger to record a
time-sink finding in.

The cost of that gap was concrete: working the Kapten & Son row's timing data
by hand (101 min total, 41.6 min / 41% unattributed, an 18.5-minute largest gap
tied to the same defect Phase 2 diagnosed) produced a real finding that was
never written anywhere durable. It existed only as chat prose and would have
evaporated exactly the way the comms diagnosis would have if `comms-diagnosis.md`
didn't exist.

## The constraint that shapes everything here

`demo-environment/references/telemetry.md` already warns: **`Unattributed` is
not user think-time.** On the run it was designed from, ~37 of ~41 minutes were
the conductor fixing its own defects, not genuine waiting. With two rows in the
database — one of which has no timing data at all — a phase that tried to
*classify* a gap's cause (bottleneck vs. defect-fixing vs. missing
instrumentation) would be guessing, and a confident wrong guess is worse than
no guess: it would misdirect the next reader and erode trust in every other
claim the skill makes.

So the phase reports **size and location only.** It never claims a cause.

## Design

### Phase 2b, always on

Added to `run-triage`'s deep-dive, running on every triaged top row **alongside**
the existing comms Phase 2 — not a separate trigger, not conditional on
severity. This matches how the finding was actually discovered this session:
while diagnosing the comms cause, the timing breakdown was sitting in the same
row.

### The note

A fixed two-sentence structure, built only from columns already in the schema,
with no causal language:

```
Total {X} min. Largest gap {Y} min after {label} ({Z}% of total).
Unattributed {W} min ({N}% of total) — size and location only, not a diagnosis.
```

Kapten's row would read: *"Total 101 min. Largest gap 18.5 min after
`orders:end` (18% of total). Unattributed 41.6 min (41% of total) — size and
location only, not a diagnosis."*

`{label}` is the row's existing `Largest gap after` value, used verbatim —
never re-derived from the timeline. Minutes are reported to one decimal place,
matching how `largest_gap()` already rounds them; percentages are whole numbers,
rounded normally (`round(x)`), since a fractional percentage implies more
precision than two data points support.

The percentage math and template fill live in a script,
`plugins/pl-private/scripts/timing_note.py`, mirroring why `triage_sweep.py`
exists rather than living as prose: a conductor computing a percentage and
choosing wording differently each run is the exact failure mode that script was
built to prevent.

### Where it's written

A new Notion column, **`Timing note`** (Text), separate from `Action taken`.
`Action taken` already holds causal, fix-oriented comms prose; mixing a
deliberately non-causal timing observation into the same field would create
pressure to match that voice and drift toward exactly the diagnosis this phase
must not make. It also means timing findings become independently queryable
later, once enough rows exist to look for patterns.

Like the other triage columns, this is written unattended at Phase 3 — it is
review's own record, following the same rule `comms-diagnosis.md` already
established for triage writes.

### No ledger, yet

`comms-diagnosis.md` works because comms causes generalize: `hasReleasedVersion`
gates sending on every account, always. A slow scrape lane or a long plan-gate
wait is local to one run's brand, account, and human — it is not obviously true
elsewhere. Building a `time-sinks.md` ledger from one or two data points would
assume a pattern that hasn't been shown to repeat.

**Revisit once the same bottleneck (by name — e.g. `scrape` lane, or the
template-gate wait) appears on two or more independent rows.** At that point a
ledger entry is earned rather than assumed, and it should follow
`comms-diagnosis.md`'s own shape: a claim, the runs it was proven against, and
how to re-check it.

### Error handling

| Condition | Behaviour |
|---|---|
| No timing data at all (Currys' shape: `Total elapsed` and everything else null) | Write nothing to `Timing note`. Report the skip in the triage output, in the same style as Phase 2's ledger-match skip. |
| `Total elapsed` present, `Largest gap` null | Report total and unattributed only; omit the gap sentence rather than inventing a placeholder. |
| Everything present | Full two-sentence note. |

An absent value is silence, never a zero or a guess — the same rule
`largest_gap()` already follows for unmeasured runs.

### Testing

`plugins/pl-private/scripts/tests/test_timing_note.py`, stdlib `unittest`,
mirroring `triage_sweep.py`'s test shape: Kapten's real row as the primary
fixture (asserting the exact note text, not just that a string was produced),
a null-data fixture matching Currys' shape proving the skip path, and a
partial-data fixture (elapsed present, gap null) proving the gap sentence is
omitted rather than rendered with a placeholder.

## Deliberately out of scope

- **Any causal classification** of what a gap or a large `Unattributed` value
  means. Explicitly deferred until enough rows exist to support it —
  `triage_sweep.py`'s own docstring already uses "revisit once ten rows exist"
  as its bar for a related judgment call; the same bar applies here.
- **A cross-run pattern ledger.** Deferred until the same named bottleneck
  repeats on two or more rows.
- **Any change to `rank()`'s tie-break logic.** This design adds a report, not
  a new ranking signal.
