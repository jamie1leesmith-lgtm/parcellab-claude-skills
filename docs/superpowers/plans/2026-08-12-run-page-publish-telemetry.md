# Run-Page Publish Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it possible to tell, from a Notion telemetry row alone, whether a demo-environment run's page artifact actually republished as designed.

**Architecture:** `run_state.py` gains a `page` section recording renders and publishes. `render_run_page.py` records its own render, so that half of the data cannot be skipped. The conductor records each Artifact call. `build_telemetry_row.py` derives five new columns from those two lists, and gains a truncation guard on the existing `Timeline` column that is already at risk of exceeding Notion's limit.

**Tech Stack:** Python 3 stdlib, `unittest`, Markdown skill files.

## Global Constraints

- **Tests are stdlib `unittest`. `pytest` is NOT installed — never `pip install`.** Run from `plugins/pl-tools/scripts`: `python3 -m unittest discover -s tests -v`
- **The five Notion columns are already live** (added 2026-08-12): `Page publishes`, `Page renders`, `Max page gap`, `Page URL changes` (all number) and `Page cadence` (text). Do not add, rename, or re-create them. Column names in code must match those strings exactly — Notion rejects an unknown property name and the rejection takes the whole write.
- **Notion rich-text limit is 2000 characters.** The `Timeline` guard uses a 1900 budget.
- **`run-state.json` has exactly one writer: `run_state.py`.** Other modules call its functions; nothing else opens the file for writing.
- **Telemetry is an observer, never a dependency** — no change here may make a run fail.
- **Never write credentials, tokens, or customer data** into telemetry.
- Frontmatter `name:`/`description:` must not change; "parcelLab" stays spelled out in `description:`.
- Reference files via `${CLAUDE_PLUGIN_ROOT}`; never rename a `parcellab-` string.
- No anti-correction language in skill files — claims carry a date, a live-run reference, or a doc URL.
- **Do not `git push`.** Commit only.

## Data contract (locked here, used by Tasks 1–3)

`run-state.json` gains:

```json
"page": {
  "renders":   [{"at": "2026-08-12T10:04:11Z"}],
  "publishes": [{"at": "2026-08-12T10:04:14Z", "url": "https://claude.site/artifacts/abc"}]
}
```

Timestamps use `run_state._now()`'s format: `%Y-%m-%dT%H:%M:%SZ`.

Derived columns:

| Column | Derivation | Null when |
|---|---|---|
| `Page renders` | `len(page.renders)` | never (0 if absent) |
| `Page publishes` | `len(page.publishes)` | never (0 if absent) |
| `Page URL changes` | count of distinct non-empty `url` values, minus 1 | no publishes |
| `Page cadence` | comma-joined whole seconds from the baseline to each publish | no publishes |
| `Max page gap` | largest gap in minutes between consecutive publishes falling inside the driver window | fewer than 2 such publishes, or any driver unfinished |

**Baseline for `Page cadence`** is the first `page.renders` entry, falling back to the first publish when there are no renders. State 1 renders at run-dir creation, so that is effectively run start.

**Driver window** comes from `timings.driver_intervals(run_dir)`: start = `min(s["start"])`, end = `max(s["end"])`, and only when every span has both — mirroring how `event_window_min` refuses to guess at an unfinished run.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/run_state.py` | Owns `run-state.json`; gains `page` + two recorders |
| `plugins/pl-tools/scripts/render_run_page.py` | Renders the page; records its own render |
| `plugins/pl-tools/scripts/build_telemetry_row.py` | Derives the row; gains 5 columns + the Timeline guard |
| `plugins/pl-tools/skills/demo-environment/references/telemetry.md` | Documents the columns and the off-by-one |
| `plugins/pl-tools/skills/demo-environment/references/run-page.md` | The publish hook gains `record_publish` |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` | "The run page" section defines what republishing includes |

---

### Task 1: `run_state.py` — the `page` section

**Files:**
- Modify: `plugins/pl-tools/scripts/run_state.py`
- Test: `plugins/pl-tools/scripts/tests/test_run_state.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `run_state.record_render(run_dir)` and `run_state.record_publish(run_dir, url)`, both returning the amended state dict like every other function in this module. `init()` seeds `state["page"] = {"renders": [], "publishes": []}`. Task 2 calls `record_render`; Task 3 reads `state["page"]`.

Runs started before this change have no `page` key, so both recorders use `setdefault` — the same pattern `mark()` already uses for `timeline` at `run_state.py:96`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_run_state.py`, inside the existing test class:

```python
    def test_init_seeds_an_empty_page_section(self):
        state = run_state.init(self.run_dir, "r1", "engage", "Acme")
        self.assertEqual(state["page"], {"renders": [], "publishes": []})

    def test_record_render_appends_a_stamp(self):
        run_state.init(self.run_dir, "r1", "engage", "Acme")
        state = run_state.record_render(self.run_dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        self.assertRegex(state["page"]["renders"][0]["at"],
                         r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_record_publish_keeps_the_url(self):
        run_state.init(self.run_dir, "r1", "engage", "Acme")
        state = run_state.record_publish(self.run_dir, "https://x.test/a")
        self.assertEqual(state["page"]["publishes"][0]["url"],
                         "https://x.test/a")

    def test_recorders_append_never_replace(self):
        run_state.init(self.run_dir, "r1", "engage", "Acme")
        run_state.record_render(self.run_dir)
        run_state.record_render(self.run_dir)
        state = run_state.record_publish(self.run_dir, "https://x.test/a")
        state = run_state.record_publish(self.run_dir, "https://x.test/b")
        self.assertEqual(len(state["page"]["renders"]), 2)
        self.assertEqual([p["url"] for p in state["page"]["publishes"]],
                         ["https://x.test/a", "https://x.test/b"])

    def test_recorders_survive_a_state_written_before_page_existed(self):
        run_state.init(self.run_dir, "r1", "engage", "Acme")
        state = run_state.load(self.run_dir)
        del state["page"]
        run_state._write(self.run_dir, state)
        state = run_state.record_render(self.run_dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        state = run_state.record_publish(self.run_dir, "https://x.test/a")
        self.assertEqual(len(state["page"]["publishes"]), 1)
```

If the existing test class sets up `self.run_dir` under a different name, match the file's convention rather than introducing a second one.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_state -v
```

Expected: the five new tests FAIL — `KeyError: 'page'` on the first, `AttributeError: module 'run_state' has no attribute 'record_render'` on the rest.

- [ ] **Step 3: Seed `page` in `init()`**

In `run_state.py`, in the `init()` state dict, add after `"schedule": {},`:

```python
        "page": {"renders": [], "publishes": []},
```

- [ ] **Step 4: Add the two recorders**

Add after `set_schedule()`:

```python
def _page(state):
    return state.setdefault("page", {"renders": [], "publishes": []})


def record_render(run_dir):
    """Stamp a completed render. Called by render_run_page.py itself, so a
    render cannot happen unrecorded — this is the trustworthy half of the
    page telemetry, against which self-reported publishes are compared.
    """
    def apply(state):
        _page(state).setdefault("renders", []).append({"at": _now()})

    return _amend(run_dir, apply)


def record_publish(run_dir, url):
    """Stamp an Artifact call and the URL it returned.

    Self-reported: only the conductor knows a publish happened. A publish
    count below the render count is therefore the signal that the Artifact
    call was skipped.
    """
    def apply(state):
        _page(state).setdefault("publishes", []).append(
            {"at": _now(), "url": url})

    return _amend(run_dir, apply)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_run_state -v
```

Expected: PASS, including every pre-existing test.

- [ ] **Step 6: Commit**

```bash
git add plugins/pl-tools/scripts/run_state.py plugins/pl-tools/scripts/tests/test_run_state.py
git commit -m "feat(run-state): record page renders and publishes"
```

---

### Task 2: `render_run_page.py` records its own render

**Files:**
- Modify: `plugins/pl-tools/scripts/render_run_page.py:481-484` (the tail of `main()`)
- Test: `plugins/pl-tools/scripts/tests/test_render_run_page.py`

**Interfaces:**
- Consumes: `run_state.record_render(run_dir)` from Task 1.
- Produces: every successful CLI render appends one entry to `page.renders`. Task 3 counts them.

The recording happens **after** the HTML is written, so a render that crashed mid-write is not counted as having happened. The page itself never displays these counts, so the one-behind lag inside the rendered HTML does not matter.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_run_page.py`:

```python
    def test_main_records_the_render_in_run_state(self):
        import run_state
        run_state.init(self.run_dir, "r1", "engage", "Acme")
        argv = sys.argv
        sys.argv = ["render_run_page.py", str(self.run_dir)]
        try:
            self.assertEqual(render_run_page.main(), 0)
        finally:
            sys.argv = argv
        state = run_state.load(self.run_dir)
        self.assertEqual(len(state["page"]["renders"]), 1)
        self.assertTrue((pathlib.Path(self.run_dir) / "run-page.html").exists())
```

Match the file's existing conventions for `self.run_dir`, and add `import sys` / `import pathlib` at the top only if they are not already there.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page -v
```

Expected: FAIL — `KeyError: 'page'` or `renders` length 0, because nothing records the render yet.

- [ ] **Step 3: Import and call the recorder**

In `render_run_page.py`, add `import run_state` alongside the other imports at the top of the file.

Then in `main()`, replace:

```python
    (run_dir / "run-page.html").write_text(
        render(state, manifest, assets, template_html))
    print(f"rendered {run_dir / 'run-page.html'}")
    return 0
```

with:

```python
    (run_dir / "run-page.html").write_text(
        render(state, manifest, assets, template_html))
    # Recorded after the write, so a render that died mid-write is not
    # counted. This is the half of page telemetry that cannot be skipped.
    run_state.record_render(run_dir)
    print(f"rendered {run_dir / 'run-page.html'}")
    return 0
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_render_run_page -v
```

Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit**

```bash
git add plugins/pl-tools/scripts/render_run_page.py plugins/pl-tools/scripts/tests/test_render_run_page.py
git commit -m "feat(run-page): record each render from the renderer itself"
```

---

### Task 3: Five derived columns and the `Timeline` guard

**Files:**
- Modify: `plugins/pl-tools/scripts/build_telemetry_row.py:122` and the payload dict around `:100-124`
- Test: `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`

**Interfaces:**
- Consumes: `state["page"]` from Task 1; `timings.driver_intervals(run_dir)` and `timings.parse_ts(text)`, both already available (`build_telemetry_row.py` imports `timings` at line 13).
- Produces: the five column values in the row dict, and `timeline_json(timeline, limit=1900)` as a module-level function.

`timings.driver_intervals(run_dir)` returns a list of `{"kind", "name", "start", "end"}` where `start`/`end` are `datetime` objects or `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build_telemetry_row.py`:

```python
    def test_timeline_json_passes_short_timelines_through(self):
        timeline = [{"kind": "gate", "name": "plan", "phase": "asked",
                     "at": "2026-08-12T10:00:00Z"}]
        text = build_telemetry_row.timeline_json(timeline)
        self.assertEqual(json.loads(text), timeline)

    def test_timeline_json_truncates_oldest_and_marks_the_loss(self):
        timeline = [{"kind": "lane", "name": f"lane{i}", "phase": "start",
                     "at": "2026-08-12T10:00:00Z"} for i in range(200)]
        text = build_telemetry_row.timeline_json(timeline)
        self.assertLessEqual(len(text), 1900)
        payload = json.loads(text)
        self.assertIn("truncated", payload[0])
        self.assertGreater(payload[0]["truncated"], 0)
        # the newest entry survives; the oldest is what gets dropped
        self.assertEqual(payload[-1]["name"], "lane199")

    def test_page_counts_and_url_stability(self):
        page = {"renders": [{"at": "2026-08-12T10:00:00Z"}] * 3,
                "publishes": [
                    {"at": "2026-08-12T10:00:01Z", "url": "https://x.test/a"},
                    {"at": "2026-08-12T10:00:02Z", "url": "https://x.test/a"}]}
        cols = build_telemetry_row.page_columns(page, [])
        self.assertEqual(cols["Page renders"], 3)
        self.assertEqual(cols["Page publishes"], 2)
        self.assertEqual(cols["Page URL changes"], 0)

    def test_page_url_change_is_counted(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:00:01Z", "url": "https://x.test/a"},
            {"at": "2026-08-12T10:00:02Z", "url": "https://x.test/b"}]}
        cols = build_telemetry_row.page_columns(page, [])
        self.assertEqual(cols["Page URL changes"], 1)

    def test_page_columns_are_null_without_publishes(self):
        cols = build_telemetry_row.page_columns(
            {"renders": [{"at": "2026-08-12T10:00:00Z"}], "publishes": []}, [])
        self.assertEqual(cols["Page renders"], 1)
        self.assertEqual(cols["Page publishes"], 0)
        self.assertIsNone(cols["Page URL changes"])
        self.assertIsNone(cols["Page cadence"])
        self.assertIsNone(cols["Max page gap"])

    def test_page_cadence_counts_seconds_from_the_first_render(self):
        page = {"renders": [{"at": "2026-08-12T10:00:00Z"}],
                "publishes": [{"at": "2026-08-12T10:00:05Z", "url": "u"},
                              {"at": "2026-08-12T10:01:00Z", "url": "u"}]}
        cols = build_telemetry_row.page_columns(page, [])
        self.assertEqual(cols["Page cadence"], "5,60")

    def test_max_page_gap_uses_only_publishes_inside_the_driver_window(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:00:00Z", "url": "u"},   # before window
            {"at": "2026-08-12T10:10:00Z", "url": "u"},
            {"at": "2026-08-12T10:14:00Z", "url": "u"},   # 4 min gap
            {"at": "2026-08-12T10:15:00Z", "url": "u"},   # 1 min gap
            {"at": "2026-08-12T11:00:00Z", "url": "u"}]}  # after window
        drivers = [{"kind": "driver", "name": "01",
                    "start": timings.parse_ts("2026-08-12T10:05:00Z"),
                    "end": timings.parse_ts("2026-08-12T10:20:00Z")}]
        cols = build_telemetry_row.page_columns(page, drivers)
        self.assertEqual(cols["Max page gap"], 4.0)

    def test_max_page_gap_is_null_while_a_driver_is_unfinished(self):
        page = {"renders": [], "publishes": [
            {"at": "2026-08-12T10:10:00Z", "url": "u"},
            {"at": "2026-08-12T10:14:00Z", "url": "u"}]}
        drivers = [{"kind": "driver", "name": "01",
                    "start": timings.parse_ts("2026-08-12T10:05:00Z"),
                    "end": None}]
        cols = build_telemetry_row.page_columns(page, drivers)
        self.assertIsNone(cols["Max page gap"])
```

Add `import json` and `import timings` at the top of the test file if they are not already present.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row -v
```

Expected: FAIL with `AttributeError: module 'build_telemetry_row' has no attribute 'timeline_json'` / `'page_columns'`.

- [ ] **Step 3: Add `timeline_json`**

In `build_telemetry_row.py`, add near the other module-level helpers (after `_counts`):

```python
TIMELINE_LIMIT = 1900


def timeline_json(timeline, limit=TIMELINE_LIMIT):
    """Serialise the timeline within Notion's 2000-char rich-text limit.

    An over-length property rejects the WHOLE row, and a rejected telemetry
    write is non-fatal by design — so without this guard a long run loses
    every column silently, not just its timeline. Oldest entries go first;
    the marker makes the loss visible rather than silent.
    """
    entries = list(timeline)
    dropped = 0
    while True:
        payload = ([{"truncated": dropped}] + entries) if dropped else entries
        text = json.dumps(payload)
        if len(text) <= limit or not entries:
            return text
        entries.pop(0)
        dropped += 1
```

- [ ] **Step 4: Add `page_columns`**

Add directly after `timeline_json`:

```python
def page_columns(page, drivers):
    """Derive the five run-page columns.

    `Page renders` is trustworthy (the renderer records itself); `Page
    publishes` is self-reported, so publishes < renders means the Artifact
    call was skipped. `Max page gap` is scoped to the driver window because
    that is the only stretch with an expected cadence — one wave per
    GAP_SECONDS. Measured across the whole run it would be dominated by
    legitimate waiting at the plan gate.
    """
    page = page or {}
    renders = page.get("renders") or []
    publishes = page.get("publishes") or []

    cols = {
        "Page renders": len(renders),
        "Page publishes": len(publishes),
        "Page URL changes": None,
        "Page cadence": None,
        "Max page gap": None,
    }
    if not publishes:
        return cols

    urls = {p.get("url") for p in publishes if p.get("url")}
    cols["Page URL changes"] = max(len(urls) - 1, 0)

    stamps = [timings.parse_ts(p["at"]) for p in publishes if p.get("at")]
    stamps = [s for s in stamps if s]
    if stamps:
        baseline = None
        if renders and renders[0].get("at"):
            baseline = timings.parse_ts(renders[0]["at"])
        baseline = baseline or stamps[0]
        cols["Page cadence"] = ",".join(
            str(int((s - baseline).total_seconds())) for s in stamps)

    # The window is unknown until every driver has finished; falling back to
    # the finished ones would silently shorten it.
    if drivers and all(d["start"] and d["end"] for d in drivers):
        start = min(d["start"] for d in drivers)
        end = max(d["end"] for d in drivers)
        inside = sorted(s for s in stamps if start <= s <= end)
        if len(inside) >= 2:
            gap = max((b - a).total_seconds()
                      for a, b in zip(inside, inside[1:]))
            cols["Max page gap"] = round(gap / 60.0, 1)
    return cols
```

- [ ] **Step 5: Wire both into the row**

In `build_row`, replace the line:

```python
        "Timeline": json.dumps(timing["timeline"]),
```

with:

```python
        "Timeline": timeline_json(timing["timeline"]),
```

Then, immediately before the `if stage == "committed":` block, add:

```python
    row.update(page_columns(state.get("page"),
                            timings.driver_intervals(run_dir)))
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row -v
```

Expected: PASS, including every pre-existing test.

- [ ] **Step 7: Run the whole suite for regressions**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests
```

Expected: `OK`. Confirm any unrelated failure is pre-existing (`git stash`, re-run, `git stash pop`) and report it rather than fixing it.

- [ ] **Step 8: Commit**

```bash
git add plugins/pl-tools/scripts/build_telemetry_row.py plugins/pl-tools/scripts/tests/test_build_telemetry_row.py
git commit -m "feat(telemetry): derive the run-page columns and cap the timeline"
```

---

### Task 4: Document the columns and the publish hook

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/references/telemetry.md`
- Modify: `plugins/pl-tools/skills/demo-environment/references/run-page.md`
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` ("The run page" section, around line 86)

**Interfaces:**
- Consumes: `run_state.record_publish(run_dir, url)` from Task 1.
- Produces: no code. This is what makes the conductor actually call the recorder.

**Do not edit the ~10 individual republish sites in `SKILL.md`.** They all say "republish — non-fatal" already; this task redefines what republishing includes, in the one section that governs them. Editing ten sites is churn with ten chances to diverge.

- [ ] **Step 1: Add the columns to `telemetry.md`**

In the columns table, after the `Timeline` row, add:

```markdown
| Page publishes | Number | Artifact calls recorded by the conductor. Healthy run ≈ 8–12 |
| Page renders | Number | Renders, recorded by `render_run_page.py` itself. **publishes < renders means a skipped Artifact call** |
| Max page gap | Number | minutes; longest gap between consecutive publishes inside the driver window. Null while any driver is unfinished |
| Page URL changes | Number | distinct published URLs − 1. `0` = stable; ≥1 means readers were left on a URL that stopped updating |
| Page cadence | Text | publish offsets in seconds from the first render, e.g. `0,45,320,610` |
```

- [ ] **Step 2: Add the reading guide to `telemetry.md`**

After the existing "### Reading the timing columns" section, add:

```markdown
### Reading the page columns

Added 2026-08-12 because teammates reported the run page "isn't updating" and
the claim could not be checked: before this, a run that never republished and
one that republished twelve times left identical rows.

| Row reads | Diagnosis |
|---|---|
| publishes ≈ renders ≈ 10, max gap ~3.5 min | Working as designed |
| renders 10, publishes 2 | Conductor renders but skips the Artifact call |
| renders 2, publishes 2 | Conductor skips the whole hook |
| publishes 10, max gap 9 min | Publishing too slowly — the watcher loop is not re-triggering |
| URL changes ≥ 1 | Readers were watching a URL that stopped receiving updates |
| publishes ~10, max gap fine, still reported frozen | Viewer-side: an open tab not picking up redeploys |

**`Page publishes` reads one short.** The run's last publish lands either side
of the `beat2` telemetry write, so the final Artifact call is never counted. A
consistent off-by-one is readable; a special case would not be.

**`Page renders` is the trustworthy half.** `render_run_page.py` records its own
render, so it cannot be skipped-but-reported. Publishes are self-reported and
carry the caveat this file already gives for `manual_intervention`.
```

- [ ] **Step 3: Note the `Timeline` cap in `telemetry.md`**

In the columns table, change the `Timeline` row's Options cell to:

```markdown
the run's timeline as JSON, capped at 1900 chars (Notion rejects a rich-text value over 2000, and a rejected property rejects the whole row); oldest entries drop first behind a `{"truncated": N}` marker
```

- [ ] **Step 4: Update the milestone hook in `run-page.md`**

Replace the "## Milestone hook (the sentence SKILL.md uses)" block's quoted sentence with:

```markdown
> record it via `run_state.py`, re-render with `render_run_page.py <run dir>`,
> republish, then record the publish with
> `run_state.record_publish(<run dir>, <the URL the Artifact call returned>)`
> — non-fatal.
```

- [ ] **Step 5: Define republishing in `SKILL.md`**

In the "## The run page" section, after the sentence "Publishing is never load-bearing.", add:

```markdown
**Republishing includes recording it.** After each Artifact call, record it with
`run_state.record_publish(<run dir>, <the URL the call returned>)`. Renders
record themselves; publishes cannot, so an unrecorded publish is indistinguishable
from one that never happened — and telling those apart is the whole point of the
`Page publishes` / `Page renders` columns. Passing the returned URL is what makes
`Page URL changes` able to show a reader being stranded on a stale URL.
```

- [ ] **Step 6: Verify the docs agree with the code**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
for c in "Page publishes" "Page renders" "Max page gap" "Page URL changes" "Page cadence"; do
  code=$(grep -c "\"$c\"" plugins/pl-tools/scripts/build_telemetry_row.py)
  doc=$(grep -c "$c" plugins/pl-tools/skills/demo-environment/references/telemetry.md)
  echo "$c — code:$code doc:$doc"
done
grep -c "record_publish" plugins/pl-tools/skills/demo-environment/SKILL.md plugins/pl-tools/skills/demo-environment/references/run-page.md
```

Expected: every column name appears at least once in both code and docs, and `record_publish` appears at least once in each of the two skill files.

- [ ] **Step 7: Commit**

```bash
git add plugins/pl-tools/skills/demo-environment/
git commit -m "docs(telemetry): document the run-page columns and the publish hook"
```

---

### Task 5: Whole-repo verification

**Files:**
- Modify: none (fix-forward only if something fails)

**Interfaces:**
- Consumes: every prior task.
- Produces: evidence the suite is green and the plugin still loads.

- [ ] **Step 1: Run the full suite**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest discover -s tests 2>&1 | grep -E "^(OK|FAILED|Ran )"
```

Expected: `OK`. A failure unrelated to this plan must be confirmed pre-existing before being left alone, then reported plainly.

- [ ] **Step 2: Confirm the skills still load**

```bash
cd /Users/jamie.lee-smith/Documents/Claude/Projects/parcellab-claude-skills
python3 - <<'PY'
import pathlib, re
root = pathlib.Path("plugins/pl-tools/skills")
for skill in sorted(root.iterdir()):
    f = skill / "SKILL.md"
    if not f.exists():
        continue
    head = f.read_text().split("---")[1]
    name = re.search(r"^name:\s*(\S+)", head, re.M).group(1)
    print(f"{'OK' if name == skill.name else 'MISMATCH'}: dir={skill.name} name={name}")
PY
```

Expected: `OK` for all seven skills.

- [ ] **Step 3: End-to-end check on a synthetic run dir**

```bash
cd plugins/pl-tools/scripts && python3 - <<'PY'
import json, pathlib, tempfile, run_state, build_telemetry_row
d = tempfile.mkdtemp()
run_state.init(d, "smoke-1", "engage", "Acme")
run_state.record_render(d); run_state.record_publish(d, "https://x.test/a")
run_state.record_render(d); run_state.record_publish(d, "https://x.test/a")
state = run_state.load(d)
print("page:", json.dumps(state["page"], indent=2))
print("cols:", build_telemetry_row.page_columns(state["page"], []))
PY
```

Expected: two renders, two publishes, and `Page renders: 2`, `Page publishes: 2`, `Page URL changes: 0`, a `Page cadence` string, `Max page gap: None` (no drivers).

- [ ] **Step 4: Report**

State the suite result, the skill-name result, and the end-to-end output. Paste real command output — do not summarise a command you did not run.

---

## Notes for the implementer

- **The five Notion columns already exist.** Nothing in this plan touches Notion. If a step seems to require a Notion call, stop and ask.
- **Column name strings are load-bearing.** `"Page publishes"`, `"Page renders"`, `"Max page gap"`, `"Page URL changes"`, `"Page cadence"` — exact, including capitalisation. A typo produces an unknown-property rejection that discards the entire row.
- **Do not change how often the page publishes.** This plan measures the current design; tuning it is a separate decision to be made on the data.
- `render_run_page.py` importing `run_state` is a new dependency between two scripts in the same directory. That is fine — they already share `run-state.json` — but keep `run_state.py` the only writer.
