# demo-environment Run Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every run deposits one honest, structured row in a shared Notion database, so skill defects are found by query across users rather than by anecdote.

**Architecture:** A pure function derives the row from `run-state.json` + the manifest + `results/*.json` — no new bookkeeping, because the live-visibility work already made the conductor keep structured state. The row is written three times (gate approval, Beat 1, Beat 2) so runs that die are visible rather than absent. Writes go through each user's own Notion connector; triage columns are never touched by a run.

**Tech Stack:** Python 3 (stdlib only), Notion MCP connector, Markdown skill documents.

**Spec:** `docs/superpowers/specs/2026-08-11-demo-environment-live-visibility-and-telemetry-design.md` (Part C)

**Depends on:** `2026-08-11-demo-environment-live-visibility.md` Task 1 (`run_state.py`). Do not start this plan until that task has landed.

## Global Constraints

- Tests use **stdlib `unittest` only — never pytest**.
- Scripts in `plugins/pl-tools/scripts/`; tests in `plugins/pl-tools/scripts/tests/test_<name>.py`.
- Run tests from `plugins/pl-tools/scripts/` as `python3 -m unittest tests.test_<module> < /dev/null`. **Never bare `discover`** — it prompts interactively and hangs.
- **No network calls in tests.** The row builder is pure; the Notion write is performed by the conductor through its MCP connector, never by this Python code.
- **Never write credentials, tokens, or real customer data into a row.** Demo customers are synthetic; brand URL and account id are internal-only.
- **Nothing outward-facing happens before the plan gate.** The first write occurs only after the user approves the plan.
- **No version bump on release** — `pl-tools` is SHA-versioned: commit, push to `main`, `/pl-update`.
- **Never rename any `parcellab-*` string** listed under *"Renaming things — read this first"* in the root README — including `~/.claude/parcellab-demo-request.env`.
- Work on `main`.
- **The repo owner's standing rule: do not run `git commit` until he has explicitly said he is happy.** Each commit step means `git add`, show `git diff --staged`, then commit on his go-ahead.

## File Structure

| File | Responsibility |
|---|---|
| `plugins/pl-tools/scripts/build_telemetry_row.py` | Derive the row (and mechanical deviations) from run artefacts. Pure; no I/O beyond reading the run dir. |
| `plugins/pl-tools/skills/demo-environment/references/telemetry.md` | The database's exact columns, one-time setup, and the write contract. |
| `plugins/pl-tools/skills/pl-setup/SKILL.md` | Capture `PL_RUN_TELEMETRY_DB`; enabling it is the opt-in. |
| `plugins/pl-tools/skills/demo-environment/SKILL.md` | The three write points. |

---

### Task 1: `build_telemetry_row.py`

**Files:**
- Create: `plugins/pl-tools/scripts/build_telemetry_row.py`
- Test: `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`

**Interfaces:**
- Consumes: `run-state.json` (shape from live-visibility Task 1), `demo-manifest.json`, `results/*.json`.
- Produces:
  - `DEVIATIONS` — the exact taxonomy tuple.
  - `derive_deviations(state, results) -> list[str]` (mechanical signals only).
  - `build_row(run_dir, stage, skill_version) -> dict` where `stage` is one of `committed`, `beat1`, `beat2`.
  - CLI: `build_telemetry_row.py <run_dir> <stage> [--skill-version SHA]` prints the row as JSON. This is the dry run — it never writes to Notion.

- [ ] **Step 1: Write the failing test**

Create `plugins/pl-tools/scripts/tests/test_build_telemetry_row.py`:

```python
"""Unit tests for build_telemetry_row. Stdlib unittest — no pytest, no network."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import build_telemetry_row as btr  # noqa: E402
import run_state  # noqa: E402

MANIFEST = {
    "run": {"id": "uniqlo-20260811-1913", "pace": "standard"},
    "path": "engage",
    "brand": {"name": "UNIQLO", "url": "https://www.uniqlo.com/uk/en/",
              "region": "UK", "category": "Fashion"},
    "account": {"id": 1626718, "name": "Demo - Jamie Lee-Smith"},
    "orders": [
        {"label": "Clean delivery", "shipments": [
            {"label": "A", "events": ["InTransit", "OutForDelivery",
                                      "Delivered"]}]},
        {"label": "Split", "shipments": [
            {"label": "A", "events": ["InTransit", "Delivered"]},
            {"label": "B", "events": ["InTransit", "WarehouseDelay"]}]},
    ],
}


def a_run(finished=True, with_failure=False):
    d = pathlib.Path(tempfile.mkdtemp())
    (d / "results").mkdir()
    (d / "demo-manifest.json").write_text(json.dumps(MANIFEST))
    run_state.init(d, "uniqlo-20260811-1913", "engage", "Demo - JLS")
    run_state.set_lane(d, "scrape", "ok")
    run_state.set_lane(d, "template", "published", layout_id=20701)
    run_state.set_lane(d, "seed", "skipped")
    run_state.set_lane(d, "orders", "ok")
    run_state.set_lane(d, "cdc", "failed" if with_failure else "ok")
    run_state.add_order(d, "Clean delivery", "UNQ-1", [
        {"label": "A", "tracking_number": "TN1", "courier": "dpd-uk",
         "planned": ["InTransit", "OutForDelivery", "Delivered"]}])
    for status in ("InTransit", "OutForDelivery", "Delivered"):
        run_state.confirm_event(d, "TN1", status, "2026-08-11T18:43:27Z", 204)
    if with_failure:
        run_state.add_failure(d, "cdc", "500 from API")
    if finished:
        run_state.finish(d)
    return d


class TestBuildTelemetryRow(unittest.TestCase):
    def test_identity_fields_come_from_the_manifest(self):
        row = btr.build_row(a_run(), "beat2", skill_version="f0ee309")
        self.assertEqual(row["Run ID"], "uniqlo-20260811-1913")
        self.assertEqual(row["Brand"], "UNIQLO")
        self.assertEqual(row["Path"], "engage")
        self.assertEqual(row["Account"], 1626718)
        self.assertEqual(row["Skill version"], "f0ee309")

    def test_stage_sets_outcome_and_reached(self):
        self.assertEqual(btr.build_row(a_run(), "committed")["Outcome"],
                         "Committed")
        self.assertEqual(btr.build_row(a_run(), "beat2")["Outcome"], "Verified")

    def test_counts_events_pushed_and_confirmed(self):
        row = btr.build_row(a_run(), "beat2")
        self.assertEqual(row["Events pushed"], 3)

    def test_failed_lane_appears_in_lanes_failed(self):
        row = btr.build_row(a_run(with_failure=True), "beat2")
        self.assertIn("cdc", row["Lanes failed"])

    def test_clean_run_has_no_lanes_failed(self):
        self.assertEqual(btr.build_row(a_run(), "beat2")["Lanes failed"], [])

    def test_skipped_lane_is_not_a_failure(self):
        self.assertNotIn("seed", btr.build_row(a_run(), "beat2")["Lanes failed"])

    def test_api_error_deviation_is_derived_mechanically(self):
        d = a_run(with_failure=True)
        deviations = btr.derive_deviations(run_state.load(d), {})
        self.assertIn("api_error", deviations)

    def test_no_deviations_on_a_clean_run(self):
        d = a_run()
        self.assertEqual(btr.derive_deviations(run_state.load(d), {}), [])

    def test_every_derived_deviation_is_in_the_taxonomy(self):
        d = a_run(with_failure=True)
        for dev in btr.derive_deviations(run_state.load(d), {}):
            self.assertIn(dev, btr.DEVIATIONS)

    def test_row_contains_no_triage_columns(self):
        # Triage is written by review, never by a run — a run must not be able
        # to clobber it.
        row = btr.build_row(a_run(), "beat2")
        for column in ("Triage status", "Reviewed at", "Action taken",
                       "Fix commit", "Verified in run", "Reviewed by"):
            self.assertNotIn(column, row)

    def test_row_carries_no_customer_pii(self):
        blob = json.dumps(btr.build_row(a_run(), "beat2"))
        self.assertNotIn("@", blob.replace("https://", ""))

    def test_unfinished_run_reports_stalled(self):
        row = btr.build_row(a_run(finished=False), "beat2")
        self.assertEqual(row["Outcome"], "Stalled")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row < /dev/null
```

Expected: `ModuleNotFoundError: No module named 'build_telemetry_row'`.

- [ ] **Step 3: Write the implementation**

Create `plugins/pl-tools/scripts/build_telemetry_row.py`:

```python
#!/usr/bin/env python3
"""Derive a run's telemetry row from what the run already recorded.

No new bookkeeping: run-state.json and the manifest hold everything. The row is
deliberately free of triage columns — those belong to review, and a run that
could write them could also silently destroy them.
"""
import argparse
import json
import pathlib
import sys

DEVIATIONS = (
    "validator_rejected",
    "api_error",
    "retry_needed",
    "gate_reasked",
    "comm_missing",
    "lane_fallback_inline",
    "manual_intervention",
    "instruction_unfollowable",
    "workaround_invented",
)

STAGE_OUTCOME = {"committed": "Committed", "beat1": "Built",
                 "beat2": "Verified"}
STAGE_REACHED = {"committed": "Gate", "beat1": "Beat 1", "beat2": "Beat 2"}


def _load(path, default=None):
    p = pathlib.Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def derive_deviations(state, results):
    """Mechanical signals only.

    The three self-report deviations (manual_intervention,
    instruction_unfollowable, workaround_invented) are never derived here — the
    conductor adds them at Beat 2 if it can. Treat them as a bonus signal: an
    agent reporting its own mistakes under-reports exactly the cases worth
    catching.
    """
    found = []
    if state.get("failures"):
        found.append("api_error")
    for lane in state.get("lanes", {}).values():
        if lane.get("status") == "failed":
            if "api_error" not in found:
                found.append("api_error")
    for name in ("scrape", "seed"):
        lane = state.get("lanes", {}).get(name, {})
        if lane.get("fallback_inline"):
            found.append("lane_fallback_inline")
    if (results or {}).get("validator_rejected"):
        found.append("validator_rejected")
    return found


def _counts(state, manifest):
    planned = 0
    for order in (manifest or {}).get("orders", []):
        for ship in order.get("shipments", []):
            planned += len(ship.get("events", []))
    pushed = sum(len(s["confirmed"])
                 for o in state.get("orders", [])
                 for s in o["shipments"])
    return planned, pushed


def build_row(run_dir, stage, skill_version=""):
    run_dir = pathlib.Path(run_dir)
    state = _load(run_dir / "run-state.json", {})
    manifest = _load(run_dir / "demo-manifest.json", {}) or {}
    results = _load(run_dir / "results" / "summary.json", {}) or {}

    brand = manifest.get("brand", {})
    account = manifest.get("account", {})
    planned, pushed = _counts(state, manifest)

    lanes_failed = [name for name, lane in state.get("lanes", {}).items()
                    if lane.get("status") == "failed"]

    outcome = STAGE_OUTCOME.get(stage, "Committed")
    if stage == "beat2" and not state.get("finished"):
        outcome = "Stalled"
    if lanes_failed and stage != "committed":
        outcome = "Failed" if len(lanes_failed) > 1 else outcome

    return {
        "Run ID": state.get("run_id") or manifest.get("run", {}).get("id"),
        "Brand": brand.get("name"),
        "Prospect URL": brand.get("url"),
        "Path": manifest.get("path"),
        "Account": account.get("id"),
        "Skill version": skill_version,
        "Run page": manifest.get("run", {}).get("page_url"),
        "Outcome": outcome,
        "Reached": STAGE_REACHED.get(stage, "Gate"),
        "Lanes failed": lanes_failed,
        "Orders planned": len(manifest.get("orders", [])),
        "Orders created": len(state.get("orders", [])),
        "Events pushed": pushed,
        "Events planned": planned,
        "Deviations": derive_deviations(state, results),
        "Error detail": "; ".join(f["detail"]
                                  for f in state.get("failures", [])),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Print a run's telemetry row as JSON (never writes to Notion)")
    parser.add_argument("run_dir")
    parser.add_argument("stage", choices=["committed", "beat1", "beat2"])
    parser.add_argument("--skill-version", default="")
    args = parser.parse_args()
    print(json.dumps(build_row(args.run_dir, args.stage, args.skill_version),
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd plugins/pl-tools/scripts && python3 -m unittest tests.test_build_telemetry_row < /dev/null
```

Expected: `Ran 12 tests` … `OK`.

- [ ] **Step 5: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/scripts/build_telemetry_row.py plugins/pl-tools/scripts/tests/test_build_telemetry_row.py
git commit -m "feat(demo-environment): derive run telemetry row from run state"
```

---

### Task 2: The database reference

**Files:**
- Create: `plugins/pl-tools/skills/demo-environment/references/telemetry.md`

**Interfaces:**
- Consumes: the row keys produced by Task 1 — every column name here must match a key from `build_row()` exactly, or the write silently drops data.
- Produces: the one-time setup instructions and write contract used by Tasks 3 and 4.

- [ ] **Step 1: Write the reference**

Create `plugins/pl-tools/skills/demo-environment/references/telemetry.md`:

```markdown
# Run telemetry

Every run deposits one row in a shared Notion database, so defects are found by
query across users instead of by anecdote.

## One-time setup (the database owner)

Create a Notion **database, table view**, then share it with the team. Columns,
exactly:

| Column | Type | Options |
|---|---|---|
| Run ID | Title | |
| Date | Date | |
| Ran by | Person | |
| Brand | Text | |
| Prospect URL | URL | |
| Path | Select | engage · retain · retain-shopify |
| Account | Number | |
| Skill version | Text | |
| Run page | URL | |
| Outcome | Select | Committed · Built · Verified · Stalled · Failed |
| Reached | Select | Gate · Template · Orders · CDC · Beat 1 · Beat 2 |
| Lanes failed | Multi-select | scrape · template · seed · orders · cdc |
| Orders planned | Number | |
| Orders created | Number | |
| Events planned | Number | |
| Events pushed | Number | |
| Comms expected | Number | |
| Comms fired | Number | |
| Duration to build | Number | |
| Deviations | Multi-select | validator_rejected · api_error · retry_needed · gate_reasked · comm_missing · lane_fallback_inline · manual_intervention · instruction_unfollowable · workaround_invented |
| Error detail | Text | |
| Issue key | Text | |
| Triage status | Select | Untriaged · Reviewed, no action · Fix planned · Fix shipped · Can't reproduce |
| Reviewed at | Date | |
| Reviewed by | Text | |
| Action taken | Text | |
| Fix commit | URL | |
| Verified in run | Text | |

Then give every teammate the database id to set as `PL_RUN_TELEMETRY_DB` during
`/pl-setup`.

## The write contract

**Three writes per run**, all through the user's own Notion connector:

| When | Stage | Effect |
|---|---|---|
| Plan gate approved | `committed` | Create the row |
| Beat 1 | `beat1` | Update with build results |
| Beat 2 | `beat2` | Update with verification results |

Build each payload with:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_telemetry_row.py <run dir> <stage> \
  --skill-version "$(git -C <plugin repo> rev-parse --short HEAD)"
```

**Why the row is created at gate approval, not at the end.** If it were written
only on completion, every run that died would never appear, and the table would
systematically over-represent success — hiding exactly the failures it exists to
surface. A stalled run leaves a row with no Beat 2, which is the signal.

## Rules

- **Never write the triage columns from a run.** They belong to review. A run
  that could write them could also silently destroy them.
- **Never write credentials, tokens, or customer data.** Demo customers are
  synthetic; account id and brand URL are internal-only.
- **`PL_RUN_TELEMETRY_DB` unset means no telemetry, silently.** Enabling it at
  setup is the opt-in, per person. Never prompt mid-run.
- **A failed Notion write never fails a run.** Record it in the run dir, mention
  it once in the final report, carry on. Telemetry is an observer, never a
  dependency.
- **Self-reported deviations are the weak link.** `manual_intervention`,
  `instruction_unfollowable` and `workaround_invented` cannot be derived and
  depend on the conductor noticing its own mistakes. Live 2026-08-11 a conductor
  launched drivers with `nohup` against the skill's intent and did not notice
  until the user asked. Ask the closed questions at Beat 2 — "did any instruction
  fail to work as written? which line?" — rather than an open "did anything go
  wrong?", and treat the answers as a bonus signal, never as coverage.
```

- [ ] **Step 2: Verify every column matches a row key**

```bash
cd plugins/pl-tools/scripts && python3 - <<'PY' < /dev/null
import pathlib, re, sys, tempfile
sys.path.insert(0, ".")
import build_telemetry_row as btr
import run_state

doc = pathlib.Path(
    "../skills/demo-environment/references/telemetry.md").read_text()
documented = set(re.findall(r"^\| ([A-Z][^|]+?) \|", doc, re.M))

run_dir = tempfile.mkdtemp()
run_state.init(run_dir, "r", "engage", "acct")
row_keys = set(btr.build_row(run_dir, "beat2").keys())

print("row keys not documented:", (row_keys - documented) or "none")
PY
```

Expected: `row keys not documented: none`. Columns in the doc but not in the row are intentional — they are either triage, or filled by the conductor at write time (`Date`, `Ran by`, `Comms expected/fired`, `Duration to build`, `Issue key`).

- [ ] **Step 3: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/demo-environment/references/telemetry.md
git commit -m "docs(demo-environment): run telemetry database and write contract"
```

---

### Task 3: `/pl-setup` captures the database id

**Files:**
- Modify: `plugins/pl-tools/skills/pl-setup/SKILL.md`

**Interfaces:**
- Consumes: `references/telemetry.md` from Task 2.
- Produces: `PL_RUN_TELEMETRY_DB` in the user's global `~/.claude/settings.json` env block.

- [ ] **Step 1: Add the optional telemetry step**

Add a new optional step, following the file's existing style for optional integrations (the Shopify CLI section is the model):

```markdown
## Optional — run telemetry

If your team keeps a shared run-telemetry database (see
`demo-environment/references/telemetry.md`), set its id so your runs contribute:

```json
"env": {
  "PL_RUN_TELEMETRY_DB": "<notion database id>"
}
```

in the **global** `~/.claude/settings.json` env block.

**Setting this is the opt-in.** Runs post three rows-worth of updates — what was
built, what broke, and what deviated — through *your own* Notion connector, so
writes are attributed to you and no shared credential is distributed. Leave it
unset and no telemetry is sent, silently; nothing will prompt you mid-run.

Never post to a database you do not own or have not been invited to.
```

- [ ] **Step 2: Verify the variable name matches everywhere**

```bash
grep -rn "PL_RUN_TELEMETRY_DB" plugins/pl-tools/ | sort
```

Expected: hits in `pl-setup/SKILL.md`, `demo-environment/references/telemetry.md` and (after Task 4) `demo-environment/SKILL.md` — all spelled identically.

- [ ] **Step 3: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/pl-setup/SKILL.md
git commit -m "feat(pl-setup): optional run telemetry database id"
```

---

### Task 4: Wire the three writes into the conductor

**Files:**
- Modify: `plugins/pl-tools/skills/demo-environment/SKILL.md` (Phase 0 step 8; Phase 4 Beat 1; Phase 4 Beat 2)

**Interfaces:**
- Consumes: `build_telemetry_row.py` (Task 1), `references/telemetry.md` (Task 2), `PL_RUN_TELEMETRY_DB` (Task 3).
- Produces: nothing.

- [ ] **Step 1: Add the write at the plan gate**

In Phase 0 step 8, immediately after "Once approved:", add:

```markdown
   **Then open the telemetry row** (skip entirely when `PL_RUN_TELEMETRY_DB` is unset):
   build the payload with
   `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/build_telemetry_row.py <run dir> committed
   --skill-version "$(git -C ${CLAUDE_PLUGIN_ROOT}/../.. rev-parse --short HEAD)"`,
   then create the page in the telemetry database via the Notion connector, setting `Date` to
   today and `Ran by` to the current user. Record the returned page id in the run dir as
   `results/telemetry.json` so Beats 1 and 2 can update the same row. See
   `${CLAUDE_PLUGIN_ROOT}/skills/demo-environment/references/telemetry.md`.

   This is the first outward-facing write of the run, and it happens only after the gate — never
   before.
```

- [ ] **Step 2: Add the Beat 1 update**

In Phase 4 Beat 1, after the run-page republish hook, add:

```markdown
Update the telemetry row (stage `beat1`) with the build results, if
`results/telemetry.json` exists.
```

- [ ] **Step 3: Add the Beat 2 update and the closed self-report questions**

In Phase 4 Beat 2, after the run-page republish hook, add:

```markdown
Update the telemetry row (stage `beat2`), filling `Comms expected` and `Comms fired` from the
verification you just performed, and `Duration to build` from the gate-approval and Beat 1
timestamps.

**Then answer these three questions explicitly before writing the row** — they are the only source
for the self-reported deviations, and an open "did anything go wrong?" reliably returns "no":

1. Did any instruction fail to work as written? If so, which file and line?
   → `instruction_unfollowable`
2. Did you do anything the skill does not describe, including a workaround for a tool that
   behaved unexpectedly? → `workaround_invented`
3. Did the user have to intervene, correct you, or ask why something had not happened?
   → `manual_intervention`

Answer them from the actual run, not from intent. Live 2026-08-11 all three would have been
answered "no" by a conductor that had in fact wrapped its drivers in `nohup` against the skill's
instruction, leaving the user staring at an empty task list — question 3 is the one that would have
caught it.
```

- [ ] **Step 4: Verify the wiring is complete and consistent**

```bash
grep -n "build_telemetry_row\|PL_RUN_TELEMETRY_DB\|telemetry.json" plugins/pl-tools/skills/demo-environment/SKILL.md
ls plugins/pl-tools/scripts/build_telemetry_row.py plugins/pl-tools/skills/demo-environment/references/telemetry.md
```

Expected: three write points referenced; both files exist.

- [ ] **Step 5: Dry-run the payload against the completed UNIQLO run**

```bash
python3 plugins/pl-tools/scripts/build_telemetry_row.py \
  ~/parcellab-demo-runs/uniqlo-20260811-1913 beat2 --skill-version f0ee309
```

Expected: valid JSON printed, nothing written to Notion. That run predates `run-state.json`, so counts derived from state will be zero — the manifest-derived fields are what to check here.

- [ ] **Step 6: Stage and commit** (owner approval required)

```bash
git add plugins/pl-tools/skills/demo-environment/SKILL.md
git commit -m "feat(demo-environment): write run telemetry at gate, beat 1 and beat 2"
```
