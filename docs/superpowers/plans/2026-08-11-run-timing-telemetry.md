# Run Timing Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every demo-environment run duration a measured difference between two recorded timestamps, so per-agent and per-lane cost is visible and no number is ever estimated by the model.

**Architecture:** `run-state.json` gains an append-only `timeline` array written by a new `run_state.mark()`. A new pure module, `timings.py`, pairs those entries into intervals, combines them by **union** (never sum, because measured work genuinely overlaps), and derives the headline metrics. Driver intervals are read from each order's existing `run.log` rather than marked, because three concurrent drivers writing `run-state.json` would race. `build_telemetry_row.py` consumes `timings.summarise()`.

**Tech Stack:** Python 3 stdlib only. Tests are stdlib `unittest` (no pytest), living in `plugins/pl-tools/scripts/tests/`, run from the `scripts/` directory.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-11-run-timing-telemetry-design.md`.
- **Governing rule:** every duration is the difference between two recorded timestamps. The model never estimates one.
- **Intervals combine by union, never by sum.** Measured work overlaps by design (the scrape agent runs during the intake interview).
- **The four headline metrics are not additive.** `Unattributed` derives from a single union across *all* intervals including gates; `Waiting on user` is an overlapping view reported alongside it.
- **Drivers never write `run-state.json`.** Their intervals come from `orders/*/run.log`.
- Python 3 stdlib only — no new dependencies.
- Tests: stdlib `unittest`, files named `tests/test_<module>.py`, run via `python3 -m unittest tests.test_<module>` from `plugins/pl-tools/scripts/`.
- `set_lane` keeps its existing overwrite behaviour — it drives the run page's status pills. The timeline is the durable record, not a replacement.
- Never write triage columns from a run, with the single exception of `Triage status` = `Untriaged` on creation.
- Do not backfill the Currys run (`currys-20260811-2147`). Its gate stamps never existed.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/run_state.py` (modify) | Gains `mark()` and a `timeline` array in `init()` |
| `plugins/pl-tools/scripts/timings.py` (create) | Pure derivation: interval pairing, union, headline metrics |
| `plugins/pl-tools/scripts/build_telemetry_row.py` (modify) | Emits the new timing columns |
| `plugins/pl-tools/scripts/tests/test_run_state.py` (modify) | Covers `mark()` |
| `plugins/pl-tools/scripts/tests/test_timings.py` (create) | Covers union, unclosed intervals, concurrency, overlap |
| `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py` (modify) | Covers the new columns |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` (modify) | Tells the conductor where to call `mark()` |
| `plugins/pl-tools/skills/demo-environment/references/telemetry.md` (modify) | Documents the new columns |

---

### Task 1: Timeline and `run_state.mark()`

**Files:**
- Modify: `plugins/pl-tools/scripts/run_state.py`
- Test: `plugins/pl-tools/scripts/tests/test_run_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `run_state.mark(run_dir, kind, name, phase) -> dict`. `kind` ∈ `{"lane","agent","gate"}`, `phase` ∈ `{"start","end"}`. Appends `{"kind","name","phase","at"}` to `state["timeline"]`. `init()` now creates `"timeline": []`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_run_state.py`:

```python


class TestTimeline(unittest.TestCase):
    """Durations were unrecoverable because set_lane overwrites: template and
    seed both read 21:31:05 on the live Currys run, the moment each was marked
    done. The timeline is append-only so this cannot recur."""

    def test_init_creates_an_empty_timeline(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        self.assertEqual(run_state.load(d)["timeline"], [])

    def test_mark_appends_without_replacing(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        run_state.mark(d, "lane", "scrape", "start")
        run_state.mark(d, "lane", "scrape", "end")
        timeline = run_state.load(d)["timeline"]
        self.assertEqual(len(timeline), 2)
        self.assertEqual([e["phase"] for e in timeline], ["start", "end"])
        self.assertEqual(timeline[0]["kind"], "lane")
        self.assertEqual(timeline[0]["name"], "scrape")
        self.assertTrue(timeline[0]["at"].endswith("Z"))

    def test_mark_rejects_an_unknown_kind(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        with self.assertRaises(ValueError):
            run_state.mark(d, "sandwich", "scrape", "start")

    def test_mark_rejects_an_unknown_phase(self):
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        with self.assertRaises(ValueError):
            run_state.mark(d, "lane", "scrape", "middle")

    def test_mark_works_on_a_state_predating_the_timeline(self):
        # Runs already on disk have no timeline key.
        d = tempfile.mkdtemp()
        run_state.init(d, "currys-1", None, None)
        state = run_state.load(d)
        del state["timeline"]
        run_state._write(d, state)
        run_state.mark(d, "gate", "plan", "asked")
        self.assertEqual(len(run_state.load(d)["timeline"]), 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run from `plugins/pl-tools/scripts/`:
```bash
python3 -m unittest tests.test_run_state -v
```
Expected: FAIL — `AttributeError: module 'run_state' has no attribute 'mark'`, and `test_init_creates_an_empty_timeline` fails with `KeyError: 'timeline'`.

- [ ] **Step 3: Implement**

In `run_state.py`, add to the module constants beside `LANES` and `STATUSES`:

```python
KINDS = ("lane", "agent", "gate")
PHASES = ("start", "end", "asked", "answered")
```

In `init()`, add `"timeline": []` to the state dict (place it directly after `"lanes"`).

Add this function immediately after `set_meta`:

```python
def mark(run_dir, kind, name, phase):
    """Append one timeline entry. Never replaces an existing one.

    This is the record durations are derived from. `set_lane` keeps only the
    latest transition — correct for the run page's status pills, useless for
    measuring how long anything took.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {PHASES}")

    def apply(state):
        state.setdefault("timeline", []).append(
            {"kind": kind, "name": name, "phase": phase, "at": _now()})

    return _amend(run_dir, apply)
```

`PHASES` includes `asked`/`answered` for gates, so a gate reads naturally as `mark(d, "gate", "plan", "asked")`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_run_state -v
```
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/run_state.py plugins/pl-tools/scripts/tests/test_run_state.py
git commit -m "feat(telemetry): append-only timeline in run-state

set_lane overwrites, so a lane keeps only its latest transition and no
duration survives it. mark() appends instead, and is the record every
derived duration is read from."
```

---

### Task 2: `timings.py` — interval pairing and union

**Files:**
- Create: `plugins/pl-tools/scripts/timings.py`
- Test: `plugins/pl-tools/scripts/tests/test_timings.py`

**Interfaces:**
- Consumes: the `timeline` array from Task 1.
- Produces:
  - `timings.parse_ts(text) -> datetime | None` — tolerates both `...:00Z` and `...:00.000Z`.
  - `timings.pair_intervals(timeline) -> list[dict]` — each `{"kind","name","start","end"}`, `end` is `None` when unclosed.
  - `timings.union_seconds(spans) -> int` — `spans` is an iterable of `(start, end)` datetimes; unclosed spans are ignored.

- [ ] **Step 1: Write the failing tests**

Create `plugins/pl-tools/scripts/tests/test_timings.py`:

```python
"""Unit tests for timings. Stdlib unittest — no pytest."""
import datetime
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import timings  # noqa: E402


def dt(hh, mm, ss=0):
    return datetime.datetime(2026, 8, 11, hh, mm, ss)


class TestParseTs(unittest.TestCase):
    def test_parses_second_precision(self):
        self.assertEqual(timings.parse_ts("2026-08-11T21:35:56Z"), dt(21, 35, 56))

    def test_parses_millisecond_precision(self):
        # events.jsonl stamps carry .000Z; the timeline does not.
        self.assertEqual(timings.parse_ts("2026-08-11T21:38:56.000Z"),
                         dt(21, 38, 56))

    def test_none_passes_through(self):
        self.assertIsNone(timings.parse_ts(None))

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            timings.parse_ts("yesterday")


class TestPairIntervals(unittest.TestCase):
    def test_pairs_start_and_end_by_name(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:52:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:01:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "scrape")
        self.assertEqual(spans[0]["start"], dt(20, 52))
        self.assertEqual(spans[0]["end"], dt(21, 1))

    def test_unclosed_interval_has_no_end(self):
        # An agent that died mid-run. Must not report zero, and must not be
        # silently stretched to the end of the run.
        timeline = [{"kind": "agent", "name": "seed", "phase": "start",
                     "at": "2026-08-11T21:00:00Z"}]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertIsNone(spans[0]["end"])

    def test_gate_asked_answered_pairs(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T21:20:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T21:23:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(spans[0]["start"], dt(21, 20))
        self.assertEqual(spans[0]["end"], dt(21, 23))

    def test_same_name_in_different_kinds_does_not_cross_pair(self):
        timeline = [
            {"kind": "lane", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "agent", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "agent", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:07:00Z"},
            {"kind": "lane", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        spans = {(s["kind"], s["name"]): s for s in timings.pair_intervals(timeline)}
        self.assertEqual(spans[("lane", "seed")]["end"], dt(21, 10))
        self.assertEqual(spans[("agent", "seed")]["end"], dt(21, 7))


class TestUnionSeconds(unittest.TestCase):
    def test_disjoint_spans_add_up(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), dt(11, 5))]), 600)

    def test_overlapping_spans_are_not_double_counted(self):
        # The whole reason union exists: the scrape agent runs during the
        # intake interview, so summing would count the same minutes twice.
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 10)),
                                   (dt(10, 5), dt(10, 15))]), 900)

    def test_fully_contained_span_adds_nothing(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 30)),
                                   (dt(10, 5), dt(10, 10))]), 1800)

    def test_unclosed_spans_are_ignored(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), None)]), 300)

    def test_no_spans_is_zero(self):
        self.assertEqual(timings.union_seconds([]), 0)

    def test_touching_spans_merge(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(10, 5), dt(10, 10))]), 600)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_timings -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'timings'`.

- [ ] **Step 3: Implement**

Create `plugins/pl-tools/scripts/timings.py`:

```python
#!/usr/bin/env python3
"""Derive a run's durations from recorded timestamps. Nothing is estimated.

Every number here is the difference between two stamps written by code at the
moment the thing happened. This module exists because a duration reasoned about
rather than read is wrong: the live Currys run's event window was reported as
~40 minutes by computing 12 events x 200s, when the drivers ran concurrently
and the real window was 15.2 minutes, set by the longest single order.

Intervals combine by UNION, never by sum. Measured work genuinely overlaps —
the scrape agent runs while the intake interview is happening — so summing
durations counts the same wall-clock minutes twice.
"""
import datetime

TS_FORMATS = ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S")
OPEN_PHASES = ("start", "asked")
CLOSE_PHASES = ("end", "answered")


def parse_ts(text):
    """Parse a run timestamp. Tolerates both precisions found on disk.

    The timeline writes second precision; events.jsonl writes .000Z.
    """
    if text is None:
        return None
    cleaned = text.rstrip("Z")
    for fmt in TS_FORMATS:
        try:
            return datetime.datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    raise ValueError(f"unparseable timestamp {text!r}")


def pair_intervals(timeline):
    """Pair timeline entries into {kind, name, start, end} intervals.

    An interval whose close never arrived keeps `end: None` — an agent that
    died must not read as zero, nor be stretched to the end of the run.
    """
    spans = {}
    order = []
    for entry in timeline or []:
        key = (entry.get("kind"), entry.get("name"))
        if key not in spans:
            spans[key] = {"kind": key[0], "name": key[1],
                          "start": None, "end": None}
            order.append(key)
        at = parse_ts(entry.get("at"))
        if entry.get("phase") in OPEN_PHASES and spans[key]["start"] is None:
            spans[key]["start"] = at
        elif entry.get("phase") in CLOSE_PHASES:
            spans[key]["end"] = at
    return [spans[k] for k in order]


def union_seconds(spans):
    """Total wall-clock seconds covered by any span. Unclosed spans ignored."""
    closed = sorted((s, e) for s, e in spans if s is not None and e is not None)
    if not closed:
        return 0
    total = 0
    cur_start, cur_end = closed[0]
    for start, end in closed[1:]:
        if start > cur_end:
            total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = start, end
        else:
            cur_end = max(cur_end, end)
    total += (cur_end - cur_start).total_seconds()
    return int(total)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_timings -v
```
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/timings.py plugins/pl-tools/scripts/tests/test_timings.py
git commit -m "feat(telemetry): interval pairing and union

Union rather than sum, because measured work overlaps by design: the scrape
agent runs during the intake interview, and summing counts those minutes
twice. Unclosed intervals stay unclosed rather than reading as zero."
```

---

### Task 3: `summarise()` — driver intervals and headline metrics

**Files:**
- Modify: `plugins/pl-tools/scripts/timings.py`
- Test: `plugins/pl-tools/scripts/tests/test_timings.py`

**Interfaces:**
- Consumes: `parse_ts`, `pair_intervals`, `union_seconds` from Task 2.
- Produces:
  - `timings.driver_intervals(run_dir) -> list[dict]` — one `{"kind":"driver","name":<order dir>,"start","end"}` per `orders/*/run.log`.
  - `timings.summarise(run_dir) -> dict` with keys `total_elapsed_min`, `measured_min`, `waiting_on_user_min`, `unattributed_min`, `event_window_min`, `per_lane`, `per_agent`, `slowest_lane`, `timeline`. All `*_min` are floats to one decimal place, or `None` when unknowable.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_timings.py`, before the `if __name__` block:

```python

import json  # noqa: E402
import tempfile  # noqa: E402


def a_run_dir(timeline=None, logs=None):
    """A run dir with a timeline and optional per-order run.log files."""
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "orders").mkdir()
    (d / "run-state.json").write_text(json.dumps(
        {"run_id": "currys-1", "timeline": timeline or []}))
    for name, lines in (logs or {}).items():
        (d / "orders" / name).mkdir(parents=True, exist_ok=True)
        (d / "orders" / name / "run.log").write_text("\n".join(lines) + "\n")
    return str(d)


DRIVER_LOGS = {
    # Concurrent: 3, 5 and 4 events, all launched together. The window is the
    # longest order, not the total — this is the 2026-08-11 miscalculation.
    "01-clean-low": ["2026-08-11T21:35:56Z START sequence: 3 events",
                     "2026-08-11T21:45:00Z DONE sequence complete"],
    "02-split-medium": ["2026-08-11T21:36:01Z START sequence: 5 events",
                        "2026-08-11T21:51:06Z DONE sequence complete"],
    "03-recovered-high": ["2026-08-11T21:36:06Z START sequence: 4 events",
                          "2026-08-11T21:48:09Z DONE sequence complete"],
}


class TestDriverIntervals(unittest.TestCase):
    def test_reads_start_and_end_from_run_log(self):
        spans = timings.driver_intervals(a_run_dir(logs=DRIVER_LOGS))
        by_name = {s["name"]: s for s in spans}
        self.assertEqual(by_name["01-clean-low"]["start"], dt(21, 35, 56))
        self.assertEqual(by_name["01-clean-low"]["end"], dt(21, 45, 0))

    def test_unfinished_driver_has_no_end(self):
        logs = {"01-clean-low": ["2026-08-11T21:35:56Z START sequence: 3 events",
                                 "2026-08-11T21:38:56Z EVENT 1/3"]}
        spans = timings.driver_intervals(a_run_dir(logs=logs))
        self.assertIsNone(spans[0]["end"])

    def test_no_orders_gives_no_intervals(self):
        self.assertEqual(timings.driver_intervals(a_run_dir()), [])


class TestSummarise(unittest.TestCase):
    def test_event_window_is_the_longest_order_not_the_total(self):
        # 12 events x 180s sequential would be 36 min. Concurrent: 15.2.
        out = timings.summarise(a_run_dir(logs=DRIVER_LOGS))
        self.assertEqual(out["event_window_min"], 15.2)

    def test_gate_overlapping_an_agent_keeps_unattributed_non_negative(self):
        # The four headline metrics are NOT additive. total - measured -
        # waiting would go negative here; a single union must not.
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T20:52:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T20:58:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["total_elapsed_min"], 10.0)
        self.assertEqual(out["measured_min"], 10.0)
        self.assertEqual(out["waiting_on_user_min"], 6.0)
        self.assertGreaterEqual(out["unattributed_min"], 0)
        self.assertEqual(out["unattributed_min"], 0.0)

    def test_unattributed_counts_time_nothing_covered(self):
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "agent", "name": "scrape", "phase": "end",
             "at": "2026-08-11T20:55:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["total_elapsed_min"], 20.0)
        self.assertEqual(out["measured_min"], 10.0)
        self.assertEqual(out["unattributed_min"], 10.0)

    def test_no_gate_marks_gives_null_waiting(self):
        timeline = [
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertIsNone(out["waiting_on_user_min"])

    def test_slowest_lane_is_named(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:50:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "lane", "name": "cdc", "phase": "end",
             "at": "2026-08-11T21:06:00Z"},
        ]
        out = timings.summarise(a_run_dir(timeline=timeline))
        self.assertEqual(out["slowest_lane"], "scrape")
        self.assertEqual(out["per_lane"]["scrape"], 10.0)
        self.assertEqual(out["per_lane"]["cdc"], 1.0)

    def test_empty_run_reports_nulls_not_zeros(self):
        out = timings.summarise(a_run_dir())
        self.assertIsNone(out["total_elapsed_min"])
        self.assertIsNone(out["event_window_min"])
        self.assertIsNone(out["slowest_lane"])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_timings -v
```
Expected: FAIL — `AttributeError: module 'timings' has no attribute 'driver_intervals'`.

- [ ] **Step 3: Implement**

Add to the top of `timings.py`, beside the existing imports:

```python
import json
import pathlib
```

Append to `timings.py`:

```python
def _minutes(seconds):
    return None if seconds is None else round(seconds / 60.0, 1)


def driver_intervals(run_dir):
    """Driver spans, read from each order's run.log.

    Drivers deliberately do not write run-state.json: three concurrent
    processes doing read-amend-write would lose updates. They already stamp
    their own log, so the interval is read from there.
    """
    spans = []
    orders = pathlib.Path(run_dir) / "orders"
    for log in sorted(orders.glob("*/run.log")):
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        if not lines:
            continue
        start = parse_ts(lines[0].split()[0])
        end = None
        for line in reversed(lines):
            if "DONE sequence complete" in line:
                end = parse_ts(line.split()[0])
                break
        spans.append({"kind": "driver", "name": log.parent.name,
                      "start": start, "end": end})
    return spans


def summarise(run_dir):
    """Every headline metric, derived from recorded stamps only.

    total, measured, waiting and unattributed are NOT additive: a gate can
    overlap measured work, so unattributed comes from one union across every
    interval including gates, and waiting is an overlapping view of it.
    """
    run_dir = pathlib.Path(run_dir)
    state = json.loads((run_dir / "run-state.json").read_text())
    timeline = state.get("timeline", [])

    marked = pair_intervals(timeline)
    drivers = driver_intervals(run_dir)
    everything = marked + drivers

    gates = [s for s in everything if s["kind"] == "gate"]
    work = [s for s in everything if s["kind"] != "gate"]

    stamps = [t for s in everything for t in (s["start"], s["end"]) if t]
    total = (max(stamps) - min(stamps)).total_seconds() if stamps else None

    covered = union_seconds((s["start"], s["end"]) for s in everything)
    measured = union_seconds((s["start"], s["end"]) for s in work)
    waiting = (union_seconds((s["start"], s["end"]) for s in gates)
               if gates else None)

    driver_stamps = [t for s in drivers for t in (s["start"], s["end"]) if t]
    window = ((max(driver_stamps) - min(driver_stamps)).total_seconds()
              if driver_stamps else None)

    def by_kind(kind):
        out = {}
        for s in everything:
            if s["kind"] == kind and s["start"] and s["end"]:
                out[s["name"]] = _minutes(
                    (s["end"] - s["start"]).total_seconds())
        return out

    per_lane = by_kind("lane")
    slowest = max(per_lane, key=per_lane.get) if per_lane else None

    return {
        "total_elapsed_min": _minutes(total),
        "measured_min": _minutes(measured) if stamps else None,
        "waiting_on_user_min": _minutes(waiting),
        "unattributed_min": (_minutes(max(0, total - covered))
                             if total is not None else None),
        "event_window_min": _minutes(window),
        "per_lane": per_lane,
        "per_agent": by_kind("agent"),
        "slowest_lane": slowest,
        "timeline": timeline,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_timings -v
```
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/timings.py plugins/pl-tools/scripts/tests/test_timings.py
git commit -m "feat(telemetry): headline timing metrics

The event window is the longest concurrent order, not the sum of all events —
pinned by a test using the live run's real driver logs. Unattributed derives
from one union across every interval including gates, so a gate overlapping an
agent can never drive it negative."
```

---

### Task 4: Emit the timing columns

**Files:**
- Modify: `plugins/pl-tools/scripts/build_telemetry_row.py`
- Test: `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`

**Interfaces:**
- Consumes: `timings.summarise(run_dir)` from Task 3.
- Produces: `build_row()` gains keys `Total elapsed`, `Measured working time`, `Waiting on user`, `Unattributed`, `Event window`, `Slowest lane`, `Timeline`, `Duration to build`, and `Triage status`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`, before any `if __name__` block:

```python


class TestTimingColumns(unittest.TestCase):
    def _run_dir(self):
        import json
        import pathlib
        import tempfile
        d = pathlib.Path(tempfile.mkdtemp())
        (d / "orders").mkdir()
        (d / "results").mkdir()
        (d / "run-state.json").write_text(json.dumps({
            "run_id": "currys-1",
            "lanes": {},
            "orders": [],
            "failures": [],
            "timeline": [
                {"kind": "lane", "name": "scrape", "phase": "start",
                 "at": "2026-08-11T20:50:00Z"},
                {"kind": "lane", "name": "scrape", "phase": "end",
                 "at": "2026-08-11T21:00:00Z"},
                {"kind": "gate", "name": "plan", "phase": "asked",
                 "at": "2026-08-11T21:02:00Z"},
                {"kind": "gate", "name": "plan", "phase": "answered",
                 "at": "2026-08-11T21:05:00Z"},
            ],
        }))
        (d / "demo-manifest.json").write_text(json.dumps(
            {"brand": {"name": "Currys"}, "orders": []}))
        return str(d)

    def test_timing_columns_are_present_and_derived(self):
        row = btr.build_row(self._run_dir(), "beat1")
        self.assertEqual(row["Total elapsed"], 15.0)
        self.assertEqual(row["Measured working time"], 10.0)
        self.assertEqual(row["Waiting on user"], 3.0)
        self.assertEqual(row["Slowest lane"], "scrape")
        self.assertGreaterEqual(row["Unattributed"], 0)

    def test_timeline_is_serialised_as_json_text(self):
        import json
        row = btr.build_row(self._run_dir(), "beat1")
        self.assertIsInstance(row["Timeline"], str)
        self.assertEqual(len(json.loads(row["Timeline"])), 4)

    def test_triage_status_starts_untriaged(self):
        # Blank makes unreviewed rows findable only by querying for empty.
        row = btr.build_row(self._run_dir(), "committed")
        self.assertEqual(row["Triage status"], "Untriaged")

    def test_no_other_triage_column_is_written(self):
        row = btr.build_row(self._run_dir(), "beat1")
        for column in ("Issue key", "Reviewed at", "Reviewed by",
                       "Action taken", "Fix commit", "Verified in run"):
            self.assertNotIn(column, row)
```

The file already imports the module **as `btr`** (`import build_telemetry_row as btr`) and already
imports `json`, `pathlib`, `tempfile` and `unittest` at the top — so the tests above use `btr.` and
the local imports inside `_run_dir` are redundant but harmless. Do not add a second import of the
module under a different name.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python3 -m unittest tests.test_build_telemetry_row -v
```
Expected: FAIL — `KeyError: 'Total elapsed'`.

- [ ] **Step 3: Implement**

In `build_telemetry_row.py`, add `import timings` to the imports.

In `build_row()`, after the `lanes_failed` assignment, add:

```python
    timing = timings.summarise(run_dir)
```

Then add these entries to the returned dict, after `"Error detail"`:

```python
        "Total elapsed": timing["total_elapsed_min"],
        "Measured working time": timing["measured_min"],
        "Waiting on user": timing["waiting_on_user_min"],
        "Unattributed": timing["unattributed_min"],
        "Event window": timing["event_window_min"],
        "Slowest lane": timing["slowest_lane"],
        "Timeline": json.dumps(timing["timeline"]),
        "Duration to build": timing["total_elapsed_min"],
        "Triage status": "Untriaged",
```

`Duration to build` takes the run's total elapsed here. Its spec definition is gate-approved → Beat 1, which needs a `mark(d, "gate", "beat1", "end")` that Task 5 introduces; until a run records it, total elapsed is the honest available figure and is derived rather than guessed.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python3 -m unittest tests.test_build_telemetry_row -v
```
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

```bash
python3 -m unittest tests.test_inline_assets tests.test_render_run_page \
  tests.test_run_state tests.test_validate_manifest tests.test_check_layout_html \
  tests.test_prepare_fraud_fragment tests.test_shape_product_mix \
  tests.test_build_telemetry_row tests.test_check_images tests.test_timings
```
Expected: OK, no failures. (`tests.test_pl_credentials` is excluded — it prompts for an interactive token paste and is unrelated.)

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/build_telemetry_row.py \
  plugins/pl-tools/scripts/tests/test_build_telemetry_row.py
git commit -m "feat(telemetry): emit derived timing columns

Duration to build was never computed by this script — it was filled in by
hand. Every timing column now comes from timings.summarise. Triage status is
written as Untriaged so unreviewed rows are findable by value rather than by
querying for blank; the remaining triage columns stay owned by review."
```

---

### Task 5: Instruct the conductor and document the columns

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md`
- Modify: `plugins/pl-tools/skills/demo-environment/references/telemetry.md`

**Interfaces:**
- Consumes: `run_state.mark()` from Task 1; the column names from Task 4.
- Produces: no code.

- [ ] **Step 1: Add the marking rule to SKILL.md**

In `SKILL.md`, immediately after the *Write permissions* section, insert:

```markdown
## Timing marks — one line each, and the run is measurable

Durations are only ever the difference between two recorded stamps, so a phase
nobody marked is a phase nobody can measure. Call `run_state.mark()` at each
boundary below; each is one line beside work you are already doing.

| Boundary | Call |
|---|---|
| Dispatching an agent (scrape, seed) | `mark(d, "agent", "<name>", "start")` |
| Its results file lands | `mark(d, "agent", "<name>", "end")` |
| Starting a lane's own work | `mark(d, "lane", "<lane>", "start")` |
| That lane finishing | `mark(d, "lane", "<lane>", "end")` |
| Posing the ★ template question or the ✋ plan gate | `mark(d, "gate", "<template\|plan>", "asked")` |
| Recording the answer | `mark(d, "gate", "<template\|plan>", "answered")` |
| Posting Beat 1 | `mark(d, "gate", "beat1", "end")` |

Drivers are **not** marked — they stamp their own `run.log`, and three
concurrent drivers amending `run-state.json` would lose updates.

A missing mark yields a null, never a wrong number. Never reconstruct a mark
after the fact: a stamp written later records when you remembered, not when it
happened.
```

- [ ] **Step 2: Document the columns in telemetry.md**

In `references/telemetry.md`, add these rows to the columns table, after `Duration to build`:

```markdown
| Total elapsed | Number | minutes, derived |
| Measured working time | Number | minutes, union of all measured intervals |
| Waiting on user | Number | minutes, union of gate ask→answer |
| Unattributed | Number | minutes, total minus everything covered |
| Event window | Number | minutes, first driver start → last driver end |
| Slowest lane | Text | |
| Timeline | Text | the run's timeline as JSON |
```

Then add this subsection immediately below the columns table:

```markdown
### Reading the timing columns

**They are not additive.** A gate can overlap measured work — the scrape agent
runs during the intake interview — so `Total` minus `Measured` minus `Waiting`
double-subtracts. `Unattributed` is computed from a single union across every
interval; `Waiting on user` is an overlapping view of the same timeline.

**`Unattributed` is not user think-time.** It is everything not yet
instrumented. On the run this was designed from it would have been ~37 minutes,
almost all of it the conductor fixing defects rather than the user thinking. It
shrinks as instrumentation improves, so a large value is a signal worth reading.

**`Event window` is concurrent.** Drivers run in parallel, so the window is the
longest single order, never the sum of every event. The live run's window was
15.2 minutes; multiplying 12 events by the 200 s gap suggests 40 and is wrong.
```

- [ ] **Step 3: Note the manual Notion step**

In `references/telemetry.md`, under *The live database*, add:

```markdown
The seven timing columns must exist in the database before a run can write
them. Notion rejects an unknown property name, and a rejected telemetry write
is non-fatal by design — so a missing column shows up as silently absent
timing data, not as an error. Add them once, with the types in the table above.
```

- [ ] **Step 4: Verify the docs match the code**

```bash
cd plugins/pl-tools/scripts
python3 -c "
import build_telemetry_row as b, pathlib, re
doc = pathlib.Path('../skills/demo-environment/references/telemetry.md').read_text()
for col in ('Total elapsed', 'Measured working time', 'Waiting on user',
            'Unattributed', 'Event window', 'Slowest lane', 'Timeline'):
    assert f'| {col} |' in doc, f'{col} missing from telemetry.md'
print('all timing columns documented')
"
```
Expected: `all timing columns documented`.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md \
  plugins/pl-tools/skills/demo-environment/references/telemetry.md
git commit -m "docs(telemetry): where to mark, and how to read the timings

The columns are not additive and Unattributed is not user think-time — both
stated where they will be read, because the failure this work exists to fix
was a plausible number nobody could check."
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Append-only timeline, `mark()` | 1 |
| `set_lane` keeps overwrite behaviour | 1 (untouched) |
| Interval pairing, unclosed intervals | 2 |
| Union not sum | 2 |
| Drivers derived from `run.log`, never marked | 3, 5 |
| Headline metrics incl. concurrent event window | 3 |
| Non-additive metrics, `Unattributed` from one union | 3, 5 |
| Notion columns + JSON timeline blob | 4, 5 |
| `Duration to build` derived, not guessed | 4 |
| `Triage status` = `Untriaged`; no other triage writes | 4 |
| Tests: overlap, unclosed, concurrency, no gates, gate-overlaps-agent | 2, 3 |
| No backfill of the Currys run | Not a task — explicitly out of scope |

**Placeholder scan:** none — every step carries the code it needs.

**Type consistency:** `mark(run_dir, kind, name, phase)` is used identically in Tasks 1, 4 and 5. `summarise()`'s keys are produced in Task 3 and consumed by exactly those names in Task 4. `parse_ts`/`pair_intervals`/`union_seconds` signatures match between Tasks 2 and 3. `PHASES` includes `asked`/`answered`, which `OPEN_PHASES`/`CLOSE_PHASES` in Task 2 pair correctly.

One deliberate inconsistency, resolved: the spec defines `Duration to build` as gate-approved → Beat 1, but that needs the `mark(d, "gate", "beat1", "end")` introduced in Task 5. Task 4 populates it with total elapsed and says so; it is derived either way, never estimated.
