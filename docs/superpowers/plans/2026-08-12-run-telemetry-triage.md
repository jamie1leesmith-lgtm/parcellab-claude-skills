# Run-Telemetry Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private `run-triage` skill that turns rows in the shared runs
database into proven rules and fix-backlog items, and close the timeline blind
spot that would hide the slowest runs.

**Architecture:** A new unlisted plugin `plugins/pl-private/` holds the skill,
a ranking script, and a diagnosis ledger. Speed metrics move from read-time
derivation (which depends on a field designed to be droppable) to write-time
derivation in the existing `timings.py`, surfaced as two new Notion columns.
Run detail moves out of the private run-page artifact and into the shared Notion
row, because an artifact cannot be shared from code and a teammate's link will
never open.

**Tech Stack:** Python 3 stdlib only · `unittest` · `parcellab-cli` (read-only)
· the user's own Notion connector.

**Spec:** [2026-08-12-run-telemetry-triage-design.md](../specs/2026-08-12-run-telemetry-triage-design.md)

## Global Constraints

- **Tests are stdlib `unittest`.** `pytest` is not installed; never `pip install`.
- **Frontmatter `name:` must equal the directory name** — a mismatch removes the
  skill from the plugin inventory with no error.
- **Keep the word "parcelLab" spelled out** in any skill `description:` — that is
  the trigger text Claude matches against.
- **Reference files via `${CLAUDE_PLUGIN_ROOT}`** — never `~/.claude/skills/…`
  and never a path relative to this repo.
- **`plugins/pl-private/` is never added to `.claude-plugin/marketplace.json`.**
  That omission is the entire privacy mechanism.
- **The triage skill never writes to a parcelLab account.** Diagnosis is
  read-only; `parcellab` calls are `list`/`show` only.
- **Work on a branch**, not `main`. Each task ends with a commit; Jamie confirms
  at the review gate between tasks before anything is pushed.
- **GitHub is the personal account** `jamie1leesmith-lgtm`, never the `parcelLab`
  org. Check `git remote -v` before pushing.

---

## Correction to the spec

The spec proposed three new columns: `Uncovered gaps`, `Largest gap`, and
`Largest gap after`. `timings.summarise()` already computes `Unattributed` as
total-minus-covered, which is the same quantity as `Uncovered gaps` — on the
Kapten & Son run, 41.6 against a hand-computed 42.6, the difference being driver
intervals. **Only two columns are new.** `Largest gap` and `Largest gap after`
carry the information `Unattributed` cannot: which single stretch to look at.

The spec also proposed re-serialising the timeline as spans rather than paired
events. **This plan does not do that.** The two rows already in the database are
in event format, and a format change would mean the sweep script parses both.
Task 4 does the format-compatible half — dropping duplicate entries — which is
most of the saving at none of the churn.

---

## File Structure

| Path | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/timings.py` | **Modify.** Add `largest_gap()`; surface it from `summarise()`. |
| `plugins/pl-tools/scripts/tests/test_timings.py` | **Modify.** Cover `largest_gap`. |
| `plugins/pl-tools/scripts/build_telemetry_row.py` | **Modify.** Emit the two new columns; dedupe the timeline payload. |
| `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py` | **Modify.** Cover both. |
| `plugins/pl-tools/scripts/build_run_digest.py` | **Create.** Render a run's spans and full timeline as markdown for the Notion row body. |
| `plugins/pl-tools/scripts/tests/test_build_run_digest.py` | **Create.** stdlib `unittest`. |
| `plugins/pl-private/.claude-plugin/plugin.json` | **Create.** The unlisted plugin manifest. |
| `plugins/pl-private/scripts/triage_sweep.py` | **Create.** Severity + time ranking. Pure arithmetic. |
| `plugins/pl-private/scripts/tests/test_triage_sweep.py` | **Create.** stdlib `unittest`. |
| `plugins/pl-private/skills/run-triage/SKILL.md` | **Create.** The three-phase procedure. |
| `plugins/pl-private/skills/run-triage/references/comms-diagnosis.md` | **Create.** Ledger of proven causes and non-causes. |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` | **Modify.** Pointer to the ledger at Beat 2. |
| `plugins/pl-tools/skills/order-lifecycle/SKILL.md` | **Modify.** Pointer to the ledger at Reporting. |

---

### Task 1: Add the two columns to the shared Notion database

Nothing writes these yet. They go first because Notion rejects an unknown
property and takes **the whole row** with it, and a rejected telemetry write is
non-fatal by design — so shipping the code first turns every run's telemetry
into silently absent data rather than an error.

**Files:** none — this is a change to the shared database.

**Interfaces:**
- Produces: two properties on data source `6061c7ca-bbe2-484c-a072-c0a77d9394d3`
  named exactly `Largest gap` (Number) and `Largest gap after` (Text), relied on
  by Task 3.

- [ ] **Step 1: Confirm the current schema**

Fetch the data source and list its properties, so the add is against a known
state:

```
notion-fetch id="collection://6061c7ca-bbe2-484c-a072-c0a77d9394d3"
```

Expected: the 40 columns documented in
`plugins/pl-tools/skills/demo-environment/references/telemetry.md`, with no
`Largest gap` present.

- [ ] **Step 2: Add both columns through the connector**

Use `update_data_source`, not the Notion UI — the schema is shared and doing it
through the connector keeps it reproducible:

```
ADD COLUMN "Largest gap" NUMBER
ADD COLUMN "Largest gap after" TEXT
```

- [ ] **Step 3: Verify both exist**

Re-fetch the data source. Expected: both properties present, `Largest gap` typed
Number and `Largest gap after` typed Text. A name mismatch of any kind — case,
spacing — means Task 3's writes are silently dropped, so compare the strings
character by character.

- [ ] **Step 4: Document them**

Add both rows to the column table in
`plugins/pl-tools/skills/demo-environment/references/telemetry.md`, after
`Page cadence`:

```markdown
| Largest gap | Number | minutes; the longest stretch covered by no instrumented span. Null when fewer than two stamps |
| Largest gap after | Text | the mark that gap follows, e.g. `orders:end` |
```

Then extend the "Reading the timing columns" section with:

```markdown
**`Largest gap` points at one stretch; `Unattributed` totals them all.** They
measure the same uninstrumented time from different ends, so they are not
additive and the largest gap is always the smaller number. On the 2026-08-12
Kapten & Son run the largest gap was 18.5 minutes after `orders:end` — the wait
for comms that could not arrive, which was also that run's correctness defect.
```

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/references/telemetry.md
git commit -m "docs(telemetry): document the largest-gap columns"
```

---

### Task 2: Derive the largest gap in `timings.py`

**Files:**
- Modify: `plugins/pl-tools/scripts/timings.py`
- Test: `plugins/pl-tools/scripts/tests/test_timings.py`

**Interfaces:**
- Consumes: the existing `pair_intervals(timeline)`, which returns a list of
  `{"kind", "name", "start", "end"}` dicts where `start`/`end` are `datetime` or
  `None`.
- Produces: `largest_gap(spans) -> (seconds: float | None, label: str | None)`
  and two new keys in the `summarise()` return dict: `largest_gap` (minutes,
  rounded to 1dp, or `None`) and `largest_gap_after` (str or `None`). Task 3
  consumes both.

- [ ] **Step 1: Write the failing tests**

Add to `plugins/pl-tools/scripts/tests/test_timings.py`. The Kapten case is the
important one — its expected answer was computed by hand from the real row, and
it is the case that motivated the whole column:

```python
class LargestGapTests(unittest.TestCase):
    def _span(self, name, start, end):
        return {"kind": "lane", "name": name,
                "start": timings.parse_ts(start) if start else None,
                "end": timings.parse_ts(end) if end else None}

    def test_none_when_fewer_than_two_stamps(self):
        spans = [self._span("scrape", "2026-08-12T09:47:05", None)]
        self.assertEqual(timings.largest_gap(spans), (None, None))

    def test_gap_between_two_spans(self):
        spans = [self._span("scrape", "2026-08-12T09:00:00",
                            "2026-08-12T09:10:00"),
                 self._span("orders", "2026-08-12T09:25:00",
                            "2026-08-12T09:30:00")]
        seconds, label = timings.largest_gap(spans)
        self.assertEqual(seconds, 900.0)
        self.assertEqual(label, "scrape:end")

    def test_overlapping_spans_do_not_create_a_gap(self):
        spans = [self._span("seed", "2026-08-12T10:36:26",
                            "2026-08-12T10:40:36"),
                 self._span("template", "2026-08-12T10:36:26",
                            "2026-08-12T10:41:26")]
        self.assertEqual(timings.largest_gap(spans), (None, None))

    def test_trailing_gap_to_an_unclosed_mark_counts(self):
        """The Kapten & Son shape: the worst gap ends at a bare `end` mark.

        Beat 2 records only an end, so a gap measured span-to-span misses the
        18.5-minute wait entirely and reports 11.9 instead.
        """
        spans = [self._span("orders", "2026-08-12T10:53:22",
                            "2026-08-12T11:09:34"),
                 {"kind": "gate", "name": "beat2", "start": None,
                  "end": timings.parse_ts("2026-08-12T11:28:06")}]
        seconds, label = timings.largest_gap(spans)
        self.assertEqual(round(seconds / 60.0, 1), 18.5)
        self.assertEqual(label, "orders:end")

    def test_kapten_timeline_end_to_end(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-12T10:04:29"},
            {"kind": "gate", "name": "template", "phase": "asked",
             "at": "2026-08-12T10:11:08"},
            {"kind": "gate", "name": "template", "phase": "answered",
             "at": "2026-08-12T10:29:32"},
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-12T10:31:26"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-12T10:32:49"},
            {"kind": "lane", "name": "template", "phase": "start",
             "at": "2026-08-12T10:36:26"},
            {"kind": "lane", "name": "template", "phase": "end",
             "at": "2026-08-12T10:41:26"},
            {"kind": "lane", "name": "orders", "phase": "start",
             "at": "2026-08-12T10:53:22"},
            {"kind": "lane", "name": "orders", "phase": "end",
             "at": "2026-08-12T11:09:34"},
            {"kind": "gate", "name": "beat2", "phase": "end",
             "at": "2026-08-12T11:28:06"},
        ]
        seconds, label = timings.largest_gap(timings.pair_intervals(timeline))
        self.assertEqual(round(seconds / 60.0, 1), 18.5)
        self.assertEqual(label, "orders:end")
```

- [ ] **Step 2: Run them and verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_timings.LargestGapTests -v
```

Expected: FAIL — `module 'timings' has no attribute 'largest_gap'`.

- [ ] **Step 3: Implement `largest_gap`**

Add to `plugins/pl-tools/scripts/timings.py`, after `union_seconds`:

```python
def largest_gap(spans):
    """Longest stretch inside the run covered by no instrumented span.

    `Unattributed` already reports the *total* uncovered time. This reports the
    single worst stretch and the mark it follows, which is what points at a
    specific defect rather than at a budget.

    The horizon is the last stamp of any kind, not the last closed span: Beat 2
    records only an `end`, so measuring span-to-span would have missed the
    2026-08-12 Kapten & Son run's worst gap (18.5 min after `orders:end`, the
    wait for comms that could not arrive) and reported 11.9 instead.

    Returns (seconds, label) or (None, None) when nothing is measurable.
    """
    closed = sorted((s["start"], s["end"], s["name"]) for s in spans
                    if s["start"] and s["end"])
    stamps = [t for s in spans for t in (s["start"], s["end"]) if t]
    if not closed or len(stamps) < 2:
        return None, None

    best_seconds, best_label = 0, None
    frontier, frontier_name = closed[0][1], closed[0][2]
    for start, end, name in closed[1:]:
        if start > frontier:
            gap = (start - frontier).total_seconds()
            if gap > best_seconds:
                best_seconds, best_label = gap, f"{frontier_name}:end"
        if end > frontier:
            frontier, frontier_name = end, name

    horizon = max(stamps)
    if horizon > frontier:
        gap = (horizon - frontier).total_seconds()
        if gap > best_seconds:
            best_seconds, best_label = gap, f"{frontier_name}:end"

    return (best_seconds, best_label) if best_seconds > 0 else (None, None)
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_timings -v
```

Expected: PASS, including the pre-existing `timings` tests.

- [ ] **Step 5: Surface it from `summarise()`**

In `summarise()`, inside the `try` block that already computes `covered` and
`measured`, add:

```python
        gap_seconds, gap_label = largest_gap(everything)
        largest_gap_min = _minutes(gap_seconds)
```

In the `except ValueError` branch that nulls the durations, add:

```python
        largest_gap_min = None
        gap_label = None
```

Then add both to the returned dict, alongside the existing keys:

```python
        "largest_gap": largest_gap_min,
        "largest_gap_after": gap_label,
```

An impossible span already nulls every duration rather than escaping, because
telemetry is an observer and letting it raise costs the ~20 columns that are not
durations. These two follow that same rule.

- [ ] **Step 6: Test `summarise` carries them**

Add to `test_timings.py`, following the existing `summarise` tests' fixture
pattern for building a temporary run dir with a `run-state.json`:

```python
    def test_summarise_reports_the_largest_gap(self):
        run_dir = self._run_dir_with_timeline([
            {"kind": "lane", "name": "orders", "phase": "start",
             "at": "2026-08-12T10:53:22"},
            {"kind": "lane", "name": "orders", "phase": "end",
             "at": "2026-08-12T11:09:34"},
            {"kind": "gate", "name": "beat2", "phase": "end",
             "at": "2026-08-12T11:28:06"},
        ])
        summary = timings.summarise(run_dir)
        self.assertEqual(summary["largest_gap"], 18.5)
        self.assertEqual(summary["largest_gap_after"], "orders:end")
```

If no `_run_dir_with_timeline` helper exists in the file, write one that creates
a `tempfile.TemporaryDirectory`, writes `{"timeline": [...]}` to
`run-state.json`, and returns the path.

- [ ] **Step 7: Run the full script suite**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS. Any failure outside `test_timings` is pre-existing — confirm by
stashing and re-running before touching it.

- [ ] **Step 8: Commit**

```bash
git add plugins/pl-tools/scripts/timings.py plugins/pl-tools/scripts/tests/test_timings.py
git commit -m "feat(telemetry): derive the largest uninstrumented gap"
```

---

### Task 3: Emit the two columns from `build_telemetry_row.py`

**Files:**
- Modify: `plugins/pl-tools/scripts/build_telemetry_row.py`
- Test: `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`

**Interfaces:**
- Consumes: `timings.summarise()`'s `largest_gap` and `largest_gap_after` keys
  from Task 2.
- Produces: `Largest gap` and `Largest gap after` keys in the row payload,
  matching the Notion properties created in Task 1.

- [ ] **Step 1: Write the failing test**

Add to `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`, following
the existing tests' pattern for building a row:

```python
    def test_row_carries_the_largest_gap_columns(self):
        row = build_telemetry_row.build_row(
            self.run_dir, "beat2", skill_version="abc1234")
        self.assertEqual(row["Largest gap"], 18.5)
        self.assertEqual(row["Largest gap after"], "orders:end")

    def test_largest_gap_is_null_when_unmeasurable(self):
        """A one-stamp run is unmeasured, not instantaneous."""
        row = build_telemetry_row.build_row(
            self.single_stamp_run_dir, "committed", skill_version="abc1234")
        self.assertIsNone(row["Largest gap"])
        self.assertIsNone(row["Largest gap after"])
```

Build `self.run_dir` with the Kapten timeline from Task 2 Step 6, and
`self.single_stamp_run_dir` with a timeline holding one entry. Match whatever
factory the existing tests in this file already use — read them first rather
than inventing a second pattern.

- [ ] **Step 2: Run and verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row -v
```

Expected: FAIL with `KeyError: 'Largest gap'`.

- [ ] **Step 3: Add the columns**

In `build_telemetry_row.py`, next to the existing timing columns (near line 194,
where `"Timeline"` is set):

```python
        "Largest gap": timing["largest_gap"],
        "Largest gap after": timing["largest_gap_after"],
```

- [ ] **Step 4: Run and verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/build_telemetry_row.py plugins/pl-tools/scripts/tests/test_build_telemetry_row.py
git commit -m "feat(telemetry): report the largest gap and what it follows"
```

---

### Task 4: Shrink the timeline payload

The guard at `TIMELINE_LIMIT = 1900` is correct and stays — an over-length
property rejects the whole row. This task reduces how often it bites. The
Kapten row's timeline was ~1,650 characters, and every `agent` entry in it
duplicates a `lane` entry with a byte-identical timestamp.

Dedupe at serialisation only. `pair_intervals` keys on `(kind, name)`, so
dropping `agent` entries anywhere else would change the computed spans.

**Files:**
- Modify: `plugins/pl-tools/scripts/build_telemetry_row.py`
- Test: `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`

**Interfaces:**
- Produces: `timeline_json(timeline, limit=TIMELINE_LIMIT)` keeps its signature
  and return type (a JSON string). Only the content shrinks.

- [ ] **Step 1: Write the failing tests**

```python
    def test_agent_entries_duplicating_a_lane_are_dropped(self):
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
        ]
        payload = json.loads(build_telemetry_row.timeline_json(timeline))
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["kind"], "lane")

    def test_agent_entry_with_its_own_timestamp_is_kept(self):
        """Only exact duplicates go. A distinct stamp is real information."""
        timeline = [
            {"kind": "agent", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:48:30"},
        ]
        payload = json.loads(build_telemetry_row.timeline_json(timeline))
        self.assertEqual(len(payload), 2)

    def test_compact_separators(self):
        timeline = [{"kind": "lane", "name": "seed", "phase": "start",
                     "at": "2026-08-12T10:36:26"}]
        self.assertNotIn(", ", build_telemetry_row.timeline_json(timeline))

    def test_truncation_marker_still_applies(self):
        timeline = [{"kind": "lane", "name": f"lane{i}", "phase": "start",
                     "at": "2026-08-12T10:36:26"} for i in range(200)]
        payload = json.loads(build_telemetry_row.timeline_json(timeline))
        self.assertIn("truncated", payload[0])
        self.assertLessEqual(
            len(build_telemetry_row.timeline_json(timeline)), 1900)
```

- [ ] **Step 2: Run and verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row -v
```

Expected: FAIL on the dedupe and separator tests; the truncation test passes
already.

- [ ] **Step 3: Implement**

Replace `timeline_json` in `build_telemetry_row.py`:

```python
def timeline_json(timeline, limit=TIMELINE_LIMIT):
    """Serialise the timeline within Notion's 2000-char rich-text limit.

    An over-length property rejects the WHOLE row, and a rejected telemetry
    write is non-fatal by design — so without this guard a long run loses
    every column silently, not just its timeline. Oldest entries go first;
    the marker makes the loss visible rather than silent.

    An `agent` entry sharing a `lane` entry's name, phase and timestamp carries
    no information the lane entry does not — the 2026-08-12 Kapten & Son run had
    four such pairs. They are dropped here, at serialisation, and nowhere else:
    `pair_intervals` keys on (kind, name), so dropping them upstream would
    change the spans it computes.
    """
    lane_keys = {(e.get("name"), e.get("phase"), e.get("at"))
                 for e in (timeline or []) if e.get("kind") == "lane"}
    entries = [e for e in (timeline or [])
               if not (e.get("kind") == "agent"
                       and (e.get("name"), e.get("phase"),
                            e.get("at")) in lane_keys)]

    dropped = 0
    while True:
        payload = ([{"truncated": dropped}] + entries) if dropped else entries
        text = json.dumps(payload, separators=(",", ":"))
        if len(text) <= limit or not entries:
            return text
        entries.pop(0)
        dropped += 1
```

The `lane_keys` pre-pass is why this is order-independent. In a real timeline
the `agent` entry precedes its `lane` twin, so a single backwards-looking pass
would drop nothing at all — and the tests would still pass if written only
against a lane-first fixture.

- [ ] **Step 4: Run and verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS across the whole suite.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/build_telemetry_row.py plugins/pl-tools/scripts/tests/test_build_telemetry_row.py
git commit -m "feat(telemetry): drop duplicate agent entries from the timeline"
```

---

### Task 5: Create the unlisted plugin and the sweep script

**Files:**
- Create: `plugins/pl-private/.claude-plugin/plugin.json`
- Create: `plugins/pl-private/scripts/triage_sweep.py`
- Create: `plugins/pl-private/scripts/tests/test_triage_sweep.py`

**Interfaces:**
- Produces: `severity(row) -> int`, `rank(rows) -> list` (descending by severity
  then largest gap), and a `__main__` that reads a JSON array of rows on stdin
  and prints a ranked table. Task 6's SKILL.md invokes the `__main__`.
- Row dicts use the Notion column names verbatim as keys: `Run ID`, `Outcome`,
  `Comms expected`, `Comms fired`, `Lanes failed`, `Deviations`, `Largest gap`,
  `Total elapsed`.

- [ ] **Step 1: Write the plugin manifest**

`plugins/pl-private/.claude-plugin/plugin.json`:

```json
{
  "name": "pl-private",
  "description": "Jamie's private parcelLab tooling. Not listed in the marketplace and not distributed to the team.",
  "author": {
    "name": "Jamie Lee-Smith",
    "email": "jamie.lee-smith@parcellab.com"
  },
  "keywords": ["parcellab", "pl", "triage", "telemetry", "private"]
}
```

Do not add an entry for this plugin to `.claude-plugin/marketplace.json`.

- [ ] **Step 2: Write the failing tests**

`plugins/pl-private/scripts/tests/test_triage_sweep.py`:

```python
import unittest

import triage_sweep


def row(**kw):
    base = {"Run ID": "r", "Outcome": "Verified", "Reached": "Beat 2",
            "Comms expected": 12, "Comms fired": 12, "Lanes failed": [],
            "Deviations": [], "Largest gap": 1.0, "Total elapsed": 60.0}
    base.update(kw)
    return base


class SeverityTests(unittest.TestCase):
    def test_clean_run_scores_zero(self):
        self.assertEqual(triage_sweep.severity(row()), 0)

    def test_stalled_outcome_scores(self):
        self.assertEqual(triage_sweep.severity(row(Outcome="Stalled")), 4)

    def test_missing_comms_score(self):
        self.assertEqual(triage_sweep.severity(row(**{"Comms fired": 0})), 3)

    def test_kapten_row(self):
        """Stalled, 0 of 12 comms, two deviations, no failed lane."""
        scored = triage_sweep.severity(row(
            Outcome="Stalled", Deviations=["comm_missing",
                                           "workaround_invented"],
            **{"Comms fired": 0}))
        self.assertEqual(scored, 9)

    def test_a_run_that_never_reached_beat_2_scores(self):
        """No Beat 2 is a stall signal, not missing data.

        The 2026-08-11 Currys run stopped at Beat 1 with Outcome "Built", which
        no other rule catches.
        """
        self.assertEqual(triage_sweep.severity(row(Reached="Beat 1")), 2)

    def test_failed_lanes_score_two_each(self):
        self.assertEqual(
            triage_sweep.severity(row(**{"Lanes failed": ["orders", "cdc"]})),
            4)

    def test_zero_expected_comms_is_not_a_shortfall(self):
        """An engage run planning no comms has not missed any."""
        self.assertEqual(
            triage_sweep.severity(row(**{"Comms expected": 0,
                                         "Comms fired": 0})), 0)

    def test_null_counts_are_not_a_shortfall(self):
        self.assertEqual(
            triage_sweep.severity(row(**{"Comms expected": None,
                                         "Comms fired": None})), 0)


class RankTests(unittest.TestCase):
    def test_severity_outranks_time(self):
        mild = row(**{"Run ID": "mild", "Largest gap": 40.0})
        severe = row(**{"Run ID": "severe", "Outcome": "Failed",
                        "Largest gap": 1.0})
        self.assertEqual([r["Run ID"] for r in triage_sweep.rank([mild,
                                                                  severe])],
                         ["severe", "mild"])

    def test_time_breaks_a_severity_tie(self):
        slow = row(**{"Run ID": "slow", "Largest gap": 18.5})
        quick = row(**{"Run ID": "quick", "Largest gap": 2.0})
        self.assertEqual([r["Run ID"] for r in triage_sweep.rank([quick,
                                                                  slow])],
                         ["slow", "quick"])

    def test_missing_largest_gap_sorts_last_not_first(self):
        """A null gap is unmeasured, and must not outrank a measured one."""
        unmeasured = row(**{"Run ID": "unmeasured", "Largest gap": None})
        measured = row(**{"Run ID": "measured", "Largest gap": 5.0})
        self.assertEqual(
            [r["Run ID"] for r in triage_sweep.rank([unmeasured, measured])],
            ["measured", "unmeasured"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run and verify they fail**

```bash
cd plugins/pl-private/scripts && python3 -m unittest discover -s tests -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'triage_sweep'`.

- [ ] **Step 4: Implement**

`plugins/pl-private/scripts/triage_sweep.py`:

```python
#!/usr/bin/env python3
"""Rank untriaged telemetry rows so the worst one gets looked at first.

Arithmetic only, deliberately: a conductor asked to weigh severity in prose
weighs it differently each run, and the whole point of the runs database is
that defects are found by query rather than by anecdote.
"""
import json
import sys

SEVERE_OUTCOMES = ("Stalled", "Failed")


def severity(row):
    """Higher is worse.

    The weights say a run that stopped (4) matters more than one that ran but
    mailed nobody (3), which matters more than a failed lane (2 each) or a run
    that never reached Beat 2 (2), which matters more than a recorded deviation
    (1 each). They are a starting order, not a measurement — revisit once ten
    rows exist.

    A run with no Beat 2 scores for it rather than being read as missing data:
    it stopped before anything was verified, which is a finding.
    """
    score = 0
    if row.get("Outcome") in SEVERE_OUTCOMES:
        score += 4

    expected = row.get("Comms expected") or 0
    fired = row.get("Comms fired") or 0
    if expected and fired < expected:
        score += 3

    if row.get("Reached") != "Beat 2":
        score += 2

    score += 2 * len(row.get("Lanes failed") or [])
    score += len(row.get("Deviations") or [])
    return score


def rank(rows):
    """Worst first: severity, then the largest uninstrumented gap.

    A null `Largest gap` sorts last rather than first — it means the run was
    not measured, which is not evidence that it was fast.
    """
    return sorted(rows,
                  key=lambda r: (severity(r), r.get("Largest gap") or -1.0),
                  reverse=True)


def main():
    rows = json.load(sys.stdin)
    ranked = rank(rows)
    print(f"{'Run ID':32s} {'Sev':>3s} {'Gap':>6s} {'Total':>6s}  Outcome")
    for r in ranked:
        gap = r.get("Largest gap")
        total = r.get("Total elapsed")
        print(f"{str(r.get('Run ID'))[:32]:32s} {severity(r):3d} "
              f"{'-' if gap is None else format(gap, '.1f'):>6s} "
              f"{'-' if total is None else format(total, '.1f'):>6s}  "
              f"{r.get('Outcome')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run and verify they pass**

```bash
cd plugins/pl-private/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS, 10 tests.

- [ ] **Step 6: Check it against the two real rows**

```bash
cd plugins/pl-private/scripts && echo '[{"Run ID":"kapten-son-20260812-1145","Outcome":"Stalled","Reached":"Beat 2","Comms expected":12,"Comms fired":0,"Lanes failed":[],"Deviations":["comm_missing","workaround_invented"],"Largest gap":18.5,"Total elapsed":101.0},{"Run ID":"currys-20260811-2147","Outcome":"Built","Reached":"Beat 1","Comms expected":null,"Comms fired":null,"Lanes failed":[],"Deviations":["manual_intervention","instruction_unfollowable","workaround_invented","gate_reasked"],"Largest gap":null,"Total elapsed":null}]' | python3 triage_sweep.py
```

Expected: Kapten first with severity 9 (stalled 4 + no comms 3 + two deviations),
Currys second with severity 6 (four deviations + no Beat 2). Both are real rows,
so a different ordering means the weights need revisiting before the skill ships.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-private/
git commit -m "feat(pl-private): add the unlisted plugin and the triage sweep"
```

---

### Task 6: Write the skill and seed the diagnosis ledger

**Files:**
- Create: `plugins/pl-private/skills/run-triage/SKILL.md`
- Create: `plugins/pl-private/skills/run-triage/references/comms-diagnosis.md`

**Interfaces:**
- Consumes: `triage_sweep.py`'s `__main__` from Task 5, invoked as
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/triage_sweep.py`.
- Produces: the ledger file that Task 7's pointers reference.

- [ ] **Step 1: Create the skill with skill-creator**

Per `CLAUDE.md`, do not hand-roll a `SKILL.md`. Invoke
`/anthropic-skills:skill-creator` and give it the content below to place.

The frontmatter `name:` must be exactly `run-triage`, matching the directory.
The description must spell out "parcelLab":

```yaml
name: run-triage
description: Triage parcelLab demo-environment run telemetry — sweep the shared Notion runs database for untriaged runs, rank them by severity and time cost, investigate the worst one read-only through parcellab-cli, and record the proven cause as a durable rule. Trigger on "triage the runs", "what broke in the last demo runs", "why did that run stall", "review the run telemetry".
```

- [ ] **Step 2: Write the three phases into the skill body**

**Phase 1 — Sweep.** Query the runs database (id
`67609211a22643bfaa6bf94ccbd3f391`, data source
`6061c7ca-bbe2-484c-a072-c0a77d9394d3`) for rows where `Triage status` is
`Untriaged`. Pipe them as JSON to
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/triage_sweep.py`. Present the ranked
table and stop.

**Phase 2 — Deep-dive the top row.** In this order, and the order matters:

1. **Read `references/comms-diagnosis.md` first.** If the row's stated
   hypothesis appears there as a proven non-cause, say so and skip straight to
   the alternatives it lists. This step exists because the 2026-08-12 Kapten &
   Son row proposed a hypothesis that had already been disproven and written
   down; the note was in a file that run never loaded.
2. **Investigate read-only** with `parcellab`, always fetching the same objects
   from a known-good control account for comparison. State the control account
   used. The Kapten diagnosis became conclusive only when the failing and
   working accounts turned out to have byte-identical recipient config.
3. **Read the row's page body, not the `Run page` URL.** Run-page artifacts are
   private to whoever published them and cannot be shared from code, so a
   teammate's link will not open. Task 8 writes the spans and full timeline into
   the row body for exactly this reason; rows written before that lands have only
   their columns, and that limit gets stated in the triage rather than worked
   around.
4. **Budget: 20 `parcellab` calls.** On exhaustion, stop, record what is known,
   mark the rest `unknown`, and write the row. Write `unknown` rather than
   reaching — that triage left `Delivered` explicitly untested rather than
   inferring it from the other two events.

**Phase 3 — Land it.** Write without asking: the Notion triage columns
(`Triage status`, `Reviewed at`, `Reviewed by`, `Action taken`, and `Issue key`
/ `Fix commit` when they exist), and an append to `references/comms-diagnosis.md`.
Ask first for: any `SKILL.md` edit, any GitHub issue, anything touching a
parcelLab account.

Escalate proportionately — most triages are quick:

| Finding | Route |
|---|---|
| Mechanical — a rule to record, a wrong line, a missing check | Fix in-session |
| A code change across files | GitHub issue on `jamie1leesmith-lgtm`; fix inline if small |
| A genuinely new subsystem | `superpowers:brainstorming` → `writing-plans` |

- [ ] **Step 3: Seed the ledger**

`plugins/pl-private/skills/run-triage/references/comms-diagnosis.md`. Record
non-causes as prominently as causes — a disproven hypothesis that stays
unrecorded gets re-derived, which is how the Kapten run lost time.

Each entry carries its evidence so a later reader can re-check it rather than
having to trust it:

```markdown
# Why comms did not fire

Proven live. Each entry names the account and object it was proven against, so
it can be re-checked rather than taken on trust.

## Proven causes

### A message with no released version renders nothing

`hasReleasedVersion: false` on the message behind a journey action means no
email is produced. The trigger still matches and the tracking event still names
the message it selected, so the event log looks healthy.

**Proven 2026-08-12**, account 1626102, journey 13736. The `Dispatch` event on
tracking `6a7c4fbfd8c75e6486173d31` carries
`message: "shipping_confirmation_9c8f"`, and `parcellab track email list
--account 1626102` returns 0 rows for the entire account.

**How to check:** resolve each channel's `messageType` to its message via
`parcellab journey message list --account <id>`, and read `hasReleasedVersion`.

## Proven non-causes — do not spend calls re-deriving these

### `releaseStatus: draft` does not block sending

A draft message serves its last released version. **Proven 2026-08-12**:
account 1626718 message 75240 is `draft` with `hasReleasedVersion: true` and has
sent 51 emails.

`hasReleasedVersion` is the gate, not `releaseStatus`.

### `recipientCustomer: false` with `recipientPlTest: true` does not block sending

This is normal demo-account config; it targets the parcelLab test recipient and
records the email with `live: false`. **Proven 2026-08-12**: account 1626718
sent 100 emails with channel config byte-identical to the failing account's.

### An empty `filterExpression` does not mean a journey will mail anyone

Filter eligibility is necessary, not sufficient — a recipient role in
`additional_recipients` may still be required. See the *Known limitation:
recipient roles are a second gate* section of `order-lifecycle`'s SKILL.md.

## Open questions

- **`Delivered` (messageType 30891) on account 1626102** has
  `hasReleasedVersion: true` but was never exercised: the 2026-08-12 run's arc
  was `TrackingCreated → Dispatch → InTransit → WarehouseDelay`. Whether it
  sends there is untested.
```

- [ ] **Step 4: Write the failure behaviour into the skill**

Add a table to the SKILL.md so these are decided once rather than improvised:

```markdown
| Condition | Behaviour |
|---|---|
| No Notion connector | Stop and say so. The skill has nothing to read without it. |
| `parcellab` unauthenticated | Stop before Phase 2. Do not fall back to guessing from the row. |
| `Timeline` missing or truncated | Use `Largest gap` and `Largest gap after`; report per-span detail as unavailable. Never interpolate the missing entries. |
| Call budget exhausted | Record findings, mark the rest `unknown`, write the row. A partial triage beats an abandoned one. |
| Row's hypothesis already a proven non-cause | Say so, cite the ledger entry, and move to the alternatives without spending calls. |
```

- [ ] **Step 5: Verify the skill is inventoried**

```bash
ls plugins/pl-private/skills/run-triage/ && head -4 plugins/pl-private/skills/run-triage/SKILL.md
```

Expected: `SKILL.md` and `references/`, with frontmatter `name: run-triage`
matching the directory name exactly. A mismatch removes the skill from the
inventory with no error.

- [ ] **Step 6: Confirm it is still unlisted**

```bash
grep -c "pl-private" .claude-plugin/marketplace.json || echo "correctly absent"
```

Expected: `correctly absent`. A match here means the skill would ship to the
whole team on their next `/pl-update`.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-private/skills/
git commit -m "feat(run-triage): add the skill and seed the diagnosis ledger"
```

---

### Task 7: Point the run skills at the ledger

Placement is the fix. A rule in a file the conductor never loads is the defect
this whole plan exists to close, so these pointers are the deliverable, not
decoration.

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md`
- Modify: `plugins/pl-tools/skills/order-lifecycle/SKILL.md`

**Interfaces:**
- Consumes: `comms-diagnosis.md` from Task 6.

- [ ] **Step 1: Find the Beat 2 verification section**

```bash
grep -n "Beat 2" plugins/pl-tools/skills/demo-environment/SKILL.md | head
```

- [ ] **Step 2: Add the pointer at Beat 2**

Where Beat 2 checks `contacted_with_messages`, add:

```markdown
**Before diagnosing a missing comm, check whether the message can send at all.**
Resolve the journey channel's `messageType` to its message and read
`hasReleasedVersion` — a message that has never been released renders nothing,
while the trigger still matches and the event still names it. Proven causes and
proven non-causes are listed in the run-triage skill's
`references/comms-diagnosis.md`; several plausible hypotheses there are already
disproven, and re-deriving one costs a run about twenty minutes.
```

These skills ship to the team while `pl-private` does not, so the pointer names
the file rather than linking a path teammates cannot resolve.

- [ ] **Step 3: Add the pointer in order-lifecycle**

In the *Reporting* section, after the paragraph beginning "**Do not go digging
in Journey config before that window has elapsed.**":

```markdown
Once the window has elapsed, start from the recorded non-causes rather than from
config: the run-triage skill's `references/comms-diagnosis.md` lists what has
already been proven not to block sending, with the account and object each was
proven against.
```

- [ ] **Step 4: Verify both landed**

```bash
grep -c "comms-diagnosis" plugins/pl-tools/skills/demo-environment/SKILL.md plugins/pl-tools/skills/order-lifecycle/SKILL.md
```

Expected: `1` for each file.

- [ ] **Step 5: Run the full suite once more**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
cd ../../pl-private/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS in both.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md plugins/pl-tools/skills/order-lifecycle/SKILL.md
git commit -m "docs(skills): point comm diagnosis at the proven-causes ledger"
```

---

### Task 8: Write the run detail into the Notion row body

A run page is a **private** artifact. Its owner can share it by hand in the
claude.ai UI, but there is no publish-time setting and no default: listing every
artifact visible to Jamie on 2026-08-12 returned 11, all his own, while the
Kapten & Son row's `Run page` URL — a teammate's — was absent. So triage can
never open a teammate's run page, and every detail it needs must live elsewhere.

The row itself is that elsewhere. It is a Notion page in a database already
shared with the team, and page *bodies* are not subject to the 2000-character
property limit that forces `Timeline` to truncate. This makes each row
self-contained and retires the truncation blind spot for the detail view.

**Files:**
- Create: `plugins/pl-tools/scripts/build_run_digest.py`
- Create: `plugins/pl-tools/scripts/tests/test_build_run_digest.py`
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md`

**Interfaces:**
- Consumes: `timings.pair_intervals` and `timings.parse_ts` from Task 2's module.
- Produces: `run_digest_markdown(run_dir) -> str`, invoked by the skill at
  Beat 2 and appended to the row page through the user's Notion connector.

- [ ] **Step 1: Write the failing tests**

`plugins/pl-tools/scripts/tests/test_build_run_digest.py`:

```python
import json
import pathlib
import tempfile
import unittest

import build_run_digest


class DigestTests(unittest.TestCase):
    def _run_dir(self, timeline):
        tmp = tempfile.mkdtemp()
        (pathlib.Path(tmp) / "run-state.json").write_text(
            json.dumps({"timeline": timeline}))
        return tmp

    def test_missing_run_state_returns_a_note_not_an_exception(self):
        """Telemetry is an observer. A missing file is not a crash."""
        with tempfile.TemporaryDirectory() as empty:
            out = build_run_digest.run_digest_markdown(empty)
        self.assertIn("No timeline recorded", out)

    def test_spans_table_reports_duration(self):
        run_dir = self._run_dir([
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-12T10:04:29"},
        ])
        out = build_run_digest.run_digest_markdown(run_dir)
        self.assertIn("| lane | scrape |", out)
        self.assertIn("17.4", out)

    def test_unclosed_span_shows_a_dash_not_a_zero(self):
        """An agent that died must not read as instantaneous."""
        run_dir = self._run_dir([
            {"kind": "agent", "name": "seed", "phase": "start",
             "at": "2026-08-12T10:36:26"},
        ])
        out = build_run_digest.run_digest_markdown(run_dir)
        self.assertIn("| agent | seed |", out)
        self.assertNotIn("0.0", out)

    def test_every_timeline_entry_appears(self):
        entries = [{"kind": "lane", "name": f"l{i}", "phase": "start",
                    "at": "2026-08-12T10:36:26"} for i in range(60)]
        out = build_run_digest.run_digest_markdown(self._run_dir(entries))
        for i in range(60):
            self.assertIn(f"l{i}", out)

    def test_no_line_exceeds_the_notion_block_limit(self):
        """Rows are separate blocks; a single over-length line is rejected."""
        entries = [{"kind": "lane", "name": f"l{i}", "phase": "start",
                    "at": "2026-08-12T10:36:26"} for i in range(200)]
        out = build_run_digest.run_digest_markdown(self._run_dir(entries))
        for line in out.splitlines():
            self.assertLessEqual(len(line), 2000)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_run_digest -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'build_run_digest'`.

- [ ] **Step 3: Implement**

`plugins/pl-tools/scripts/build_run_digest.py`:

```python
#!/usr/bin/env python3
"""Render a run's detail as markdown for the body of its Notion row.

A run page is a private artifact: its owner can share it by hand, but there is
no publish-time setting and no default, so nobody else can open it. The Notion
row is in a database the team already shares, and its page body has no
equivalent of the 2000-character property limit that truncates `Timeline`.
Writing the detail here is what makes a teammate's run readable at all.

Tables, not code blocks: each table row becomes its own Notion block, so a long
timeline cannot produce one over-length block.
"""
import json
import pathlib
import sys

import timings


def _fmt(stamp):
    return stamp.strftime("%H:%M:%S") if stamp else "—"


def run_digest_markdown(run_dir):
    """Markdown for one run: its spans, then every timeline entry."""
    path = pathlib.Path(run_dir) / "run-state.json"
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return "## Run detail\n\nNo timeline recorded for this run.\n"

    timeline = state.get("timeline") or []
    if not timeline:
        return "## Run detail\n\nNo timeline recorded for this run.\n"

    lines = ["## Run detail", "", "### Spans", "",
             "| Kind | Name | Start | End | Minutes |",
             "|---|---|---|---|---|"]
    for span in timings.pair_intervals(timeline):
        if span["start"] and span["end"]:
            minutes = f"{(span['end'] - span['start']).total_seconds() / 60:.1f}"
        else:
            # Unclosed: an agent that died must not read as zero.
            minutes = "—"
        lines.append(f"| {span['kind']} | {span['name']} | "
                     f"{_fmt(span['start'])} | {_fmt(span['end'])} | "
                     f"{minutes} |")

    lines += ["", "### Timeline (full, untruncated)", "",
              "| At | Kind | Name | Phase |", "|---|---|---|---|"]
    for entry in timeline:
        lines.append(f"| {entry.get('at')} | {entry.get('kind')} | "
                     f"{entry.get('name')} | {entry.get('phase')} |")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(run_digest_markdown(sys.argv[1]))
```

- [ ] **Step 4: Run and verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS across the whole suite.

- [ ] **Step 5: Instruct the skill to write it at Beat 2**

In `plugins/pl-tools/skills/demo-environment/SKILL.md`, in the Beat 2 telemetry
step, after the row update:

```markdown
**Then append the run detail to the row's own page**, so the run is readable by
anyone on the team:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_run_digest.py <run dir>
```

Append the output to the Notion **row page** — the page the `beat2` update just
wrote to — not to the database and not to a new page. The run page artifact is
private to whoever ran it and cannot be shared from here, so this is the only
copy a teammate can open. A failed append is recorded and mentioned once in the
final report, exactly like a failed row write: telemetry is an observer, never a
dependency.
```

- [ ] **Step 6: Verify the instruction landed**

```bash
grep -c "build_run_digest" plugins/pl-tools/skills/demo-environment/SKILL.md
```

Expected: `1`.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/scripts/build_run_digest.py plugins/pl-tools/scripts/tests/test_build_run_digest.py plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(telemetry): write run detail into the shared Notion row"
```

---

## After the plan

Two follow-ups the spec records as out of scope, to raise as GitHub issues once
the skill exists — the first triage should produce them:

- The `hasReleasedVersion` preflight in `demo-environment`, so a run refuses to
  promise comms it cannot deliver. Worth ~18 minutes per affected run.
- Account 1626102's unpublished delivery messages. Max's account and his call;
  this plan writes nothing to it.

Installing the plugin locally is a one-off: add `plugins/pl-private` as a local
plugin directory in Claude Code, then restart. It never reaches
`marketplace.json`, so `/pl-update` will not offer it to anyone.
