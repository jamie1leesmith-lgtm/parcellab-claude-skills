# Run timing telemetry — design

**Date:** 2026-08-11
**Status:** approved, not yet implemented
**Scope:** `demo-environment` and `order-lifecycle` run telemetry only. No other skill is instrumented.

## Problem

Run duration is a primary optimisation target, and today it is unmeasurable.

Three specific failures, all observed on the live Currys run (`currys-20260811-2147`):

1. **`build_telemetry_row.py` never computes `Duration to build`.** The column exists in the
   shared Notion database and is populated by hand. The value written for that run — `9` — was
   an estimate, not a measurement.
2. **`run_state.set_lane` overwrites.** Each lane keeps only its most recent transition, so
   `template` and `seed` both read `21:31:05`, the moment they were marked done. No lane duration
   is derivable after the fact.
3. **Durations reasoned about rather than read are wrong.** The conductor reported the run's event
   window as ~40 minutes by computing `12 events × 200s`. The drivers run concurrently, so the real
   window was **15.2 minutes**, bounded by the longest single order (5 events), not by the total.
   The error inflated the unoptimisable share of the run from 24% to 63% and would have pointed
   optimisation effort at the one part of the run that is fixed by design.

Failure 3 is the governing one. It is not a bug in a script; it is what happens whenever a duration
is derived by reasoning instead of subtraction.

## Governing rule

> Every duration is the difference between two timestamps written by code at the moment the thing
> happened. The model never estimates one.

Any figure that cannot be traced to two recorded stamps does not get written.

## Design

### 1. Append-only timeline

`run-state.json` gains a `timeline` array. Entries are appended, never replaced:

```json
{"kind": "lane|agent|gate", "name": "scrape", "phase": "start|end", "at": "2026-08-11T20:52:03Z"}
```

One new function, `run_state.mark(run_dir, kind, name, phase)`, appends one entry.

Append-only is the fix for failure 2. `set_lane` keeps its current overwrite behaviour — it drives
the run page's status pills, where only the latest state matters — but it is no longer the record
durations are read from.

### 2. What is instrumented

| Source | Mechanism | Accuracy |
|---|---|---|
| Lanes — scrape, template, seed, orders, cdc | `mark()` at start and end | Exact |
| Sub-agents | Conductor `mark()`s at dispatch and at results-file ingest | Exact |
| Gates — template approval, plan gate | `mark()` on ask and on answer | Exact |
| Drivers | Derived at report time from each order's `run.log` | Exact |

**Drivers do not write to `run-state.json`.** Three concurrent drivers doing read-amend-write would
race; the atomic tmp-and-replace in `_write` makes a torn file impossible but does not make a
lost update impossible. The drivers already timestamp `run.log` (`START`, per-event, `DONE`) and
`events.jsonl`, so their intervals are read from there instead. No new driver code.

**Gate marks** are what make user think-time measurable rather than inferred. There are two real
gates, each of which already has a recording step, so there are two places to remember rather than
many. A missing mark yields a null, never a wrong number.

### 3. Derivation — `scripts/timings.py`

A new module, pure functions over recorded stamps, no I/O beyond reading the run dir. It returns:

| Metric | Definition |
|---|---|
| Total elapsed | First stamp in the run → last stamp |
| Measured working time | **Union** of lane, agent and driver intervals |
| Waiting on user | **Union** of gate `ask → answer` intervals |
| Covered | **Union** of everything above, gates included |
| Unattributed | Total − covered |
| Event window | First driver start → last driver end |
| Per-lane / per-agent durations | Paired start/end per name |
| Slowest lane | The lane with the largest duration |

**These four are not additive, and the implementation must not assume they are.** A gate can
overlap measured work — the scrape agent runs concurrently with the intake interview, so the plan
gate's ask→answer window may sit inside the scrape agent's interval. Computing
`total − measured − waiting` would then subtract the same minutes twice and can produce a negative
residual. `Unattributed` is therefore derived from a single union across *all* intervals, and
`Waiting on user` is reported alongside it as an overlapping view, not as a disjoint slice.

**Union, not sum.** Measured work overlaps by design — the scrape agent runs concurrently with the
intake interview. Summing durations double-counts the same wall-clock minutes and can produce a
negative residual. Union is the only correct operator here, and it is why every interval needs both
a start and an end rather than a duration.

**`Unattributed` is named for what it is.** It is not user think-time; it is everything not yet
instrumented. On the Currys run it would have been ~37 minutes, the bulk of which was the conductor
fixing run-page defects, not the user thinking. Reporting that as "waiting on user" would repeat
failure 3 in a new column. The residual shrinks as instrumentation improves, which makes a large
value a useful signal in itself.

### 4. Notion columns

Added, all in minutes except where noted: `Total elapsed`, `Measured working time`,
`Waiting on user`, `Unattributed`, `Event window`, `Slowest lane` (text), `Timeline` (text, the
timeline serialised as JSON so nothing is lost without one column per phase).

Two existing columns are repaired:

- **`Duration to build`** keeps its name and gains a real definition — gate approved → Beat 1
  posted — derived rather than guessed.
- **`Triage status`** is written as `Untriaged` on row creation. It is currently left blank, so
  finding unreviewed rows means querying for empty rather than for a value. This is the one
  triage-column write that is permitted; the rest remain owned by review, per `telemetry.md`.

### 5. Tests

`timings.py` gets unit tests for the cases that would otherwise yield confident nonsense:

- Overlapping intervals — union is not the sum.
- An interval that never closed (agent died mid-run) — reported as unclosed, not as zero and not
  as running to the end of time.
- Concurrent drivers — the window is the longest order, not the total. This is failure 3, pinned.
- A run with no gate marks — `Waiting on user` is null, and `Unattributed` absorbs it.
- **A gate overlapping an agent** — `Unattributed` stays non-negative, proving the four headline
  metrics are not treated as additive.
- A run where union exceeds total — impossible, so it raises rather than reporting a negative.

## Explicitly out of scope

- **Backfilling the Currys run.** Driver and agent intervals could be reconstructed from logs, but
  gate stamps never existed. Reconstructed numbers would be estimates written into a shared table,
  which is the practice this spec exists to end. That row keeps its hand-entered `9`.
- **Separating conductor reasoning time from tool-execution time.** Not observable from outside the
  turn. It falls into `Unattributed`, correctly labelled.
- **Instrumenting other skills.** `demo-environment` and `order-lifecycle` only.

## Consequences

Per-agent and per-lane cost becomes visible, which is what makes "who is taking the most time"
answerable. The event window stops being confused with the optimisable part of the run: on the
Currys run the optimisable share was 76%, not the 37% the sequential miscalculation implied.
