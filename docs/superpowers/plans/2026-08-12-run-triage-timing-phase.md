# Run-Triage Timing Phase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `run-triage` a speed track to match its correctness track — a
Phase 2b that reports a row's timing shape (size and location of the biggest
gap, never a cause) alongside the existing comms diagnosis.

**Architecture:** One new Notion column (`Timing note`, Text) on the shared
runs database. One new script, `timing_note.py`, mirroring `triage_sweep.py`'s
shape: a pure function the tests exercise directly, plus a thin stdin/stdout
wrapper the skill invokes. One section added to `run-triage`'s `SKILL.md`.

**Tech Stack:** Python 3 stdlib only · `unittest` · the user's own Notion
connector.

**Spec:** [2026-08-12-run-triage-timing-phase-design.md](../specs/2026-08-12-run-triage-timing-phase-design.md)

## Global Constraints

- **Tests are stdlib `unittest`.** `pytest` is not installed; never `pip install`.
- **The note reports size and location only, never a cause.** No sentence may
  imply why a gap or an `Unattributed` value is what it is.
- **No cross-run ledger yet.** Do not create or modify
  `plugins/pl-private/skills/run-triage/references/comms-diagnosis.md` as part
  of this plan — that file is scoped to comms causes, and a `time-sinks.md`
  equivalent is explicitly deferred until the same named bottleneck repeats on
  two or more independent rows.
- **A bug found in this script's own logic gets documented in the script's own
  docstring and commit message, not in `comms-diagnosis.md`.** That separation
  is already established by commit `c3007f3` and the note at the bottom of
  `comms-diagnosis.md`; this plan continues it rather than special-casing a new
  file.
- **The Notion column must exist before any code writes to it.** Notion rejects
  an unknown property and takes the whole row with it, and a rejected
  telemetry write is non-fatal by design — so the failure would look like
  silently absent data, not an error.
- **Work on a branch**, not `main`. Branch `pl-run-triage-timing` off `main`.
  Commit locally; push and open a PR only once the plan is complete, per
  Jamie's standing rule that he confirms before anything reaches GitHub.
- **GitHub is the personal account** `jamie1leesmith-lgtm`, never the
  `parcelLab` org.

---

## File Structure

| Path | Responsibility |
|---|---|
| `plugins/pl-private/scripts/timing_note.py` | **Create.** `format_note(row) -> str \| None`, plus a `main()` reading one row as JSON from stdin. |
| `plugins/pl-private/scripts/tests/test_timing_note.py` | **Create.** stdlib `unittest`, mirroring `test_triage_sweep.py`'s shape. |
| `plugins/pl-tools/skills/demo-environment/references/telemetry.md` | **Modify.** One new row in the column table. |
| `plugins/pl-private/skills/run-triage/SKILL.md` | **Modify.** New `## Phase 2b` section; `Timing note` added to the Phase 3 write-without-asking list; a `Reference` bullet noting no ledger exists yet. |

---

### Task 1: Add the `Timing note` column to the shared Notion database

**This task is executed directly — by Jamie or by the controller acting on his
instruction — never delegated to an implementer subagent.** It is a write to a
schema shared with the whole team, the same class of action as the earlier
`Largest gap` columns, and it must land before any code in Task 2 depends on
it.

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/references/telemetry.md`

**Interfaces:**
- Produces: a Notion property named exactly `Timing note` (Text) on data
  source `6061c7ca-bbe2-484c-a072-c0a77d9394d3`, relied on by Task 2's `main()`
  and by the SKILL.md text in Task 3.

- [ ] **Step 1: Confirm the current schema has no `Timing note` column**

Fetch the data source and check its properties before adding anything:

```
notion-fetch id="collection://6061c7ca-bbe2-484c-a072-c0a77d9394d3"
```

Expected: `Timing note` is absent from the returned schema.

- [ ] **Step 2: Add the column through the connector**

Use `update_data_source`, not the Notion UI — the schema is shared and the
connector keeps the change reproducible:

```
data_source_id: 6061c7ca-bbe2-484c-a072-c0a77d9394d3
statements: ADD COLUMN "Timing note" RICH_TEXT
```

- [ ] **Step 3: Verify it exists with the right type and exact name**

Re-fetch the data source. Expected: `Timing note` present, typed as `text`
(Notion's RICH_TEXT DDL type surfaces as `text` in the schema). Compare the
property name character for character against `Timing note` — a mismatch of
case or spacing means every future write to it is silently dropped rather than
erroring, exactly the failure mode the two `Largest gap` columns were built to
avoid.

- [ ] **Step 4: Document it in the shared schema reference**

Add one row to the column table in
`plugins/pl-tools/skills/demo-environment/references/telemetry.md`, directly
after the existing `Verified in run` row (the last of the triage-owned
columns):

```markdown
| Verified in run | Text | |
| Timing note | Text | a factual, non-causal size-and-location summary from run-triage's Phase 2b (`Largest gap`, `Unattributed`) — never a claim about why. Written by review, like the other triage columns above it. See `pl-private`'s `run-triage` skill if installed. |
```

This table documents the DB's full schema regardless of who writes each
column — the triage columns above it (`Issue key`, `Triage status`,
`Action taken`, and so on) are already documented there even though a *run*
never writes them, and `Timing note` follows the same convention.

- [ ] **Step 5: Commit**

```bash
git checkout -b pl-run-triage-timing
git add plugins/pl-tools/skills/demo-environment/references/telemetry.md
git commit -m "docs(telemetry): document the Timing note column"
```

---

### Task 2: Write `timing_note.py` and its tests

**Files:**
- Create: `plugins/pl-private/scripts/timing_note.py`
- Create: `plugins/pl-private/scripts/tests/test_timing_note.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — this is a pure function over a plain
  dict, same as `triage_sweep.severity()`.
- Produces: `format_note(row) -> str | None`, invoked by Task 3's SKILL.md text
  via `main()`, which reads one row as a JSON object from stdin and prints the
  note (or nothing).

- [ ] **Step 1: Write the failing tests**

`plugins/pl-private/scripts/tests/test_timing_note.py`:

```python
import unittest

import timing_note


def timing_row(**kw):
    base = {"Total elapsed": 101.0, "Largest gap": 18.5,
            "Largest gap after": "orders:end", "Unattributed": 41.6}
    base.update(kw)
    return base


class FormatNoteTests(unittest.TestCase):
    def test_kapten_row_produces_the_exact_note(self):
        expected = ("Total 101.0 min. Largest gap 18.5 min after orders:end "
                    "(18% of total). Unattributed 41.6 min (41% of total) — "
                    "size and location only, not a diagnosis.")
        self.assertEqual(timing_note.format_note(timing_row()), expected)

    def test_no_timing_data_returns_none(self):
        """Currys' shape: everything null because it predates instrumentation.

        None here means silence, not a zero — the same rule `largest_gap()`
        already follows for an unmeasured run.
        """
        row = {"Total elapsed": None, "Largest gap": None,
               "Largest gap after": None, "Unattributed": None}
        self.assertIsNone(timing_note.format_note(row))

    def test_missing_gap_omits_the_gap_sentence(self):
        row = timing_row(**{"Largest gap": None, "Largest gap after": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Largest gap", note)
        self.assertIn("Total 101.0 min.", note)
        self.assertIn("Unattributed 41.6 min", note)

    def test_missing_unattributed_omits_that_sentence(self):
        row = timing_row(**{"Unattributed": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Unattributed", note)
        self.assertIn("Largest gap 18.5 min", note)

    def test_gap_without_a_label_is_omitted_defensively(self):
        """`largest_gap()` always returns the pair together in current code,
        but a gap with no label would otherwise render an incomplete
        sentence — omit rather than guess at wording.
        """
        row = timing_row(**{"Largest gap after": None})
        note = timing_note.format_note(row)
        self.assertNotIn("Largest gap", note)

    def test_percentages_round_to_whole_numbers(self):
        row = timing_row(**{"Total elapsed": 60.0, "Largest gap": 10.0,
                            "Largest gap after": "beat2:end",
                            "Unattributed": 20.0})
        note = timing_note.format_note(row)
        self.assertIn("(17% of total)", note)
        self.assertIn("(33% of total)", note)

    def test_never_claims_a_cause(self):
        """The load-bearing rule from the design doc: report, don't diagnose."""
        note = timing_note.format_note(timing_row())
        for banned in ("because", "caused by", "bottleneck", "the reason"):
            self.assertNotIn(banned, note.lower())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

```bash
cd plugins/pl-private/scripts && python3 -m unittest tests.test_timing_note -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'timing_note'`.

- [ ] **Step 3: Implement `format_note` and `main`**

`plugins/pl-private/scripts/timing_note.py`:

```python
#!/usr/bin/env python3
"""Report a run's timing shape without claiming a cause.

`demo-environment/references/telemetry.md` already warns that a large
`Unattributed` value can mean "the conductor was fixing its own defects"
rather than a genuine bottleneck. With two rows in the runs database — one of
which predates timing instrumentation entirely — a confident guess at cause
would likely be wrong, and a wrong guess here would undercut every other claim
this skill makes. So this reports size and location only: how big a gap is,
and where it falls, never why.

There is deliberately no cross-run ledger for this. A comms cause generalizes
(`hasReleasedVersion` gates sending on every account, always); a slow lane on
one run has not been shown to generalize the same way. See
docs/superpowers/specs/2026-08-12-run-triage-timing-phase-design.md.
"""
import json
import sys


def format_note(row):
    """A factual, non-causal summary of one row's timing data.

    Returns None when there is nothing to report — a row like Currys' that
    predates the timing columns has `Total elapsed: None`, and silence is the
    honest answer, not a zero.

    Each sentence is independently optional: a field that is null is omitted
    rather than rendered as a placeholder, matching the rule `largest_gap()`
    already follows for an unmeasured run. The gap sentence needs both
    `Largest gap` and `Largest gap after` — they are always produced together
    by `largest_gap()` in current code, but a gap with no label would
    otherwise render an incomplete sentence.
    """
    total = row.get("Total elapsed")
    if not total:
        return None

    parts = [f"Total {total:.1f} min."]

    gap = row.get("Largest gap")
    label = row.get("Largest gap after")
    if gap is not None and label is not None:
        pct = round(gap / total * 100)
        parts.append(
            f"Largest gap {gap:.1f} min after {label} ({pct}% of total).")

    unattributed = row.get("Unattributed")
    if unattributed is not None:
        pct = round(unattributed / total * 100)
        parts.append(
            f"Unattributed {unattributed:.1f} min ({pct}% of total) — "
            f"size and location only, not a diagnosis.")

    return " ".join(parts)


def main():
    row = json.load(sys.stdin)
    note = format_note(row)
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and verify they pass**

```bash
cd plugins/pl-private/scripts && python3 -m unittest tests.test_timing_note -v
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Check it against the Kapten row through the CLI path**

```bash
cd plugins/pl-private/scripts && echo '{"Total elapsed":101.0,"Largest gap":18.5,"Largest gap after":"orders:end","Unattributed":41.6}' | python3 timing_note.py
```

Expected:

```
Total 101.0 min. Largest gap 18.5 min after orders:end (18% of total). Unattributed 41.6 min (41% of total) — size and location only, not a diagnosis.
```

- [ ] **Step 6: Check the skip path through the CLI**

```bash
cd plugins/pl-private/scripts && echo '{"Total elapsed":null,"Largest gap":null,"Largest gap after":null,"Unattributed":null}' | python3 timing_note.py
```

Expected: no output, exit code `0`.

- [ ] **Step 7: Run the full `pl-private` suite**

```bash
cd plugins/pl-private/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS, including the pre-existing `triage_sweep` tests.

- [ ] **Step 8: Commit**

```bash
git add plugins/pl-private/scripts/timing_note.py plugins/pl-private/scripts/tests/test_timing_note.py
git commit -m "feat(run-triage): report a row's timing shape without claiming a cause"
```

---

### Task 3: Add Phase 2b to the skill

**Files:**
- Modify: `plugins/pl-private/skills/run-triage/SKILL.md`

**Interfaces:**
- Consumes: `timing_note.py`'s `main()` from Task 2, invoked as
  `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/timing_note.py < row.json`.

- [ ] **Step 1: Insert the Phase 2b section**

In `plugins/pl-private/skills/run-triage/SKILL.md`, insert a new section
immediately after Phase 2's final paragraph (the one ending "...more useful to
the next reader than a confident guess would have been.") and before the
`## Phase 3 — Land it` heading.

Insert exactly the block below — everything between the `<<<BEGIN` and
`<<<END` markers, which are delimiters for this plan step and are **not** part
of the text to insert. The inner `bash` fence is a real fence and belongs in
the SKILL.md; do not mistake it for the end of the insertion.

<<<BEGIN
## Phase 2b — Report the timing shape

Runs alongside Phase 2, on the same top row, every time. Report size and
location only — never a cause. `demo-environment/references/telemetry.md`
already warns that a large `Unattributed` value can mean "the conductor was
fixing its own defects" rather than a genuine bottleneck, and with two rows in
the database a confident guess at which one this is would likely be wrong —
and would undercut every other claim this skill makes.

Run the script against the row's own timing columns:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/timing_note.py < row.json
```

It reads `Total elapsed`, `Largest gap`, `Largest gap after`, and
`Unattributed`, using the Notion column names verbatim, and prints a fixed
two-sentence note — or nothing, when the row predates timing instrumentation
(Currys' shape: `Total elapsed` is null).

If it prints nothing, say so in the triage output and write nothing to
`Timing note`. Never write a placeholder.

**There is no cross-run ledger for timing findings, yet.** A comms cause
generalizes — `hasReleasedVersion` gates sending on every account, always. A
slow lane on one run has not been shown to generalize the same way. Build a
ledger only once the same named bottleneck (by lane or gate name) appears on
two or more independent rows — at that point a pattern is earned rather than
assumed.
<<<END

- [ ] **Step 2: Add `Timing note` to the Phase 3 write-without-asking list**

Find the bullet list under `### Write without asking` and change:

```markdown
- The Notion triage columns: `Triage status`, `Reviewed at`, `Reviewed by`,
  `Action taken`, plus `Issue key` and `Fix commit` when they exist.
```

to:

```markdown
- The Notion triage columns: `Triage status`, `Reviewed at`, `Reviewed by`,
  `Action taken`, plus `Issue key` and `Fix commit` when they exist, and
  `Timing note` from Phase 2b.
```

- [ ] **Step 3: Add a `Reference` bullet for the new column**

Under the `## Reference` heading, add a second bullet after the existing one
for `comms-diagnosis.md`:

```markdown
- `Timing note` (Notion column) — a factual, non-causal size-and-location
  summary from Phase 2b. No cross-run ledger exists yet; one is built only
  once the same named bottleneck repeats on two or more independent rows. See
  `docs/superpowers/specs/2026-08-12-run-triage-timing-phase-design.md`.
```

- [ ] **Step 4: Verify the section landed correctly**

```bash
grep -n "^## Phase" plugins/pl-private/skills/run-triage/SKILL.md
```

Expected: `Phase 1`, `Phase 2`, `Phase 2b`, `Phase 3`, in that order.

```bash
grep -c "timing_note.py" plugins/pl-private/skills/run-triage/SKILL.md
```

Expected: `1`.

- [ ] **Step 5: Confirm the fences balance**

```bash
python3 -c "
import re, pathlib
t = pathlib.Path('plugins/pl-private/skills/run-triage/SKILL.md').read_text()
n = len(re.findall(r'^\`\`\`', t, flags=re.M))
print('fence count:', n, '->', 'balanced' if n % 2 == 0 else 'UNBALANCED')
"
```

Expected: `balanced`.

Also confirm the delimiters themselves never made it into the file — they are
markers for this plan step, not skill content:

```bash
grep -c "<<<BEGIN\|<<<END" plugins/pl-private/skills/run-triage/SKILL.md
```

Expected: `0`. A previous round of this same kind of edit shipped a stray
closing fence from exactly this pattern — check both, not just the fence count
alone.

- [ ] **Step 6: Run the full suite once more**

```bash
cd plugins/pl-private/scripts && python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-private/skills/run-triage/SKILL.md
git commit -m "docs(run-triage): add Phase 2b, the timing-shape report"
```

---

## After the plan

Nothing to raise as a follow-up issue — this plan is self-contained. The two
things it deliberately defers are already recorded in the spec's "Deliberately
out of scope" section: causal classification of a gap's origin, and a
cross-run pattern ledger. Both wait on more rows existing in the database, not
on more code.
