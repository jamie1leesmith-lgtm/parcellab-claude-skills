# Run-page publish telemetry

**Date:** 2026-08-12
**Skill:** `plugins/pl-tools/skills/demo-environment/`
**Status:** approved. **The five Notion columns are already live** (added
2026-08-12 via the connector against data source
`6061c7ca-bbe2-484c-a072-c0a77d9394d3`); the code changes are not yet
implemented.

## Problem

Teammates are testing the skills and report that the run-page artifact "isn't
updating". The claim cannot currently be checked. `run_state.py` has no concept
of a page publish, so a run that never republished and a run that republished
twelve times deposit **identical** telemetry rows. Every diagnosis is anecdote.

Two distinctions matter and neither is currently visible:

- **Render ≠ publish.** The skill's hook is *record fact → `render_run_page.py`
  → Artifact call*. A conductor can do the first two and skip the third; the
  HTML on disk still looks current.
- **Conductor-side ≠ viewer-side.** If the conductor is republishing correctly
  and teammates still see a frozen page, the problem is that an already-open
  tab does not pick up a redeploy — a completely different fix. No column
  today separates those two cases.

## Design

### 1. Recording — a `page` section in `run-state.json`

`run_state.py` gains two functions and one state key:

```json
"page": {
  "renders":   [{"at": "2026-08-12T10:04:11Z"}],
  "publishes": [{"at": "2026-08-12T10:04:14Z", "url": "https://…"}]
}
```

- `record_render(run_dir)` — called by `render_run_page.py` **itself**, at the
  end of a successful render. A render therefore cannot happen unrecorded; this
  half of the data is not self-reported and needs no conductor honesty.
- `record_publish(run_dir, url)` — called by the conductor after each Artifact
  call, carrying the URL the call returned.

`run-state.json` stays owned by `run_state.py`. The renderer calls the
recording function rather than writing the file directly, preserving the single
writer.

The publish half is self-reported by necessity — only the conductor knows an
Artifact call happened. That is acceptable because the failure being hunted
(a skipped publish) shows up as a *missing* record, and the automatic render
count provides the baseline to compare against. `telemetry.md`'s existing
warning about self-reported deviations applies: treat publishes as a signal,
and renders as the ground truth.

### 2. Five new Notion columns

| Column | Type | Meaning |
|---|---|---|
| Page publishes | Number | Count of Artifact calls. Healthy run ≈ 8–12 |
| Page renders | Number | Count of renders. **publishes < renders means a skipped Artifact call** |
| Max page gap | Number | Minutes; longest gap between consecutive publishes, measured only between drivers-launched and last-driver-finished |
| Page URL changes | Number | Distinct published URLs − 1. `0` = stable |
| Page cadence | Text | Publish offsets in seconds from run start, comma-separated: `0,45,320,610,815` |

All five are derived in `build_telemetry_row.py` from `run-state.json`, the
same place the existing timing columns are derived.

**Why `Max page gap` is scoped to the driver window.** That is the only window
with a known expected cadence — one event wave per `GAP_SECONDS`, so a healthy
standard-pace run reads ≈3.5 minutes and anything past ~5 is a real signal.
Measured across the whole run it would be dominated by legitimate waiting at
the ✋ gate, which can be ten minutes and is not a defect. Null when drivers
never launched, or when fewer than two publishes fall inside the window.

**Why `Page cadence` exists rather than putting publish events in `Timeline`.**
See the sizing constraint below.

### 3. `Timeline` truncation guard

`build_telemetry_row.py:122` currently does `json.dumps(timing["timeline"])`
with no length guard. Notion's rich-text property limit is **2000 characters**,
and a rejected property rejects the whole write — which `telemetry.md` records
as non-fatal, so it surfaces as *silently absent data*, not as an error.

A current run's timeline is roughly 22 entries at ~75 chars ≈ 1,650 characters:
already close to the ceiling. This is a **pre-existing latent bug** — a long
enough run today loses its entire telemetry row, including every column
unrelated to the timeline.

Adding ~24 render/publish entries would have pushed a typical run past 3,400
characters and detonated it on every run. Hence two decisions:

- Page events go to the compact `Page cadence` column (~40 chars) instead of
  `Timeline`, preserving per-publish reconstructability at 2% of the size.
- `Timeline` gains a guard: serialise, and if the result exceeds 1,900
  characters, drop oldest entries and append a `{"truncated": N}` marker so the
  loss is visible rather than silent.

### 4. Sequencing — columns before code

Notion rejects an unknown property name and the rejection takes the whole
write. If the skill change ships before the columns exist, **every teammate's
telemetry write fails entirely** — losing all telemetry, not just the new
fields.

Order:

1. ~~Add all five columns via the connector's `update_data_source` against data
   source `6061c7ca-bbe2-484c-a072-c0a77d9394d3`~~ — **done 2026-08-12**, per
   `telemetry.md`'s rule that schema changes go through the connector rather
   than the UI. Verified present in the returned schema as `Page publishes`,
   `Page renders`, `Max page gap`, `Page URL changes` (all number) and
   `Page cadence` (text).
2. Then ship the skill and script changes.

Adding columns is additive: existing rows are undisturbed, and in-flight runs
on the old code simply never write them.

### 5. Known limitation — the final publish is uncountable

Beat 2's order is: post Beat 2 → record → re-render → republish, and separately
update the telemetry row. Whichever ordering is chosen, the last publish of the
run either lands after the telemetry write or the telemetry write lands after
the last publish. `Page publishes` is therefore expected to run one short of
the true total at `beat2`. Document it rather than engineer around it — a
consistent off-by-one is readable; a special case is not.

## What the data answers

| Row reads | Diagnosis |
|---|---|
| publishes ≈ renders ≈ 10, max gap ~3.5 min | Working as designed |
| renders 10, publishes 2 | Conductor renders but skips the Artifact call |
| renders 2, publishes 2 | Conductor skips the whole hook — skill adherence |
| publishes 10, max gap 9 min | Publishing too slowly; watcher loop not re-triggering |
| URL changes ≥ 1 | Teammates were watching a URL that stopped receiving updates |
| publishes ~10, max gap fine, still reported frozen | Viewer-side: an open tab not picking up redeploys |

The last row is the case that cannot be distinguished today, and it is the most
likely explanation for the current reports.

## Out of scope

- Any change to how often the page publishes. This spec measures the current
  design; it does not tune it.
- The roadmap item in `run-page.md` about a genuinely live view (local polling
  page, or driver-written Notion state polled via `watchTool`). Measurement
  first — that decision should be made on data.
- Viewer-side refresh behaviour. If the data points there, that is a separate
  investigation.

## Files touched

| File | Change |
|---|---|
| Notion data source `6061c7ca-…` | Five new columns, added first |
| `plugins/pl-tools/scripts/run_state.py` | `page` key, `record_render`, `record_publish` |
| `plugins/pl-tools/scripts/render_run_page.py` | Calls `record_render` on success |
| `plugins/pl-tools/scripts/build_telemetry_row.py` | Derives the five columns; adds the `Timeline` truncation guard |
| `plugins/pl-tools/scripts/tests/` | Coverage for the derivations, the guard, and the driver-window scoping |
| `skills/demo-environment/references/telemetry.md` | Documents the five columns and the off-by-one |
| `skills/demo-environment/references/run-page.md` | The publish hook gains `record_publish` |
| `skills/demo-environment/SKILL.md` | The milestone hook sentence, used at ~10 sites |
