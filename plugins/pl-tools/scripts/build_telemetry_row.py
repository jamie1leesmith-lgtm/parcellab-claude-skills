#!/usr/bin/env python3
"""Derive a run's telemetry row from what the run already recorded.

No new bookkeeping: run-state.json and the manifest hold everything. The row
is deliberately free of triage columns — those belong to review, and a run
that could write them could also silently destroy them.
"""
import argparse
import json
import pathlib
import sys

import timings

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
    catching (live 2026-08-11: a conductor launched drivers with `nohup`
    against the skill's instruction and did not notice until the user asked).
    """
    found = []
    if state.get("failures"):
        found.append("api_error")
    for lane in state.get("lanes", {}).values():
        if lane.get("status") == "failed" and "api_error" not in found:
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
    timing = timings.summarise(run_dir)

    # A corrupt pair of marks nulls its durations rather than killing the row.
    # Say so here, or five empty columns read as "never instrumented".
    errors = [f["detail"] for f in state.get("failures", [])]
    if timing["timing_error"]:
        errors.append(f"timing: {timing['timing_error']}")

    outcome = STAGE_OUTCOME.get(stage, "Committed")
    if stage == "beat2" and not state.get("finished"):
        outcome = "Stalled"
    if lanes_failed and stage != "committed":
        outcome = "Failed" if len(lanes_failed) > 1 else outcome

    row = {
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
        "Error detail": "; ".join(errors),
        "Total elapsed": timing["total_elapsed_min"],
        "Measured working time": timing["measured_min"],
        "Waiting on user": timing["waiting_on_user_min"],
        "Unattributed": timing["unattributed_min"],
        "Event window": timing["event_window_min"],
        "Slowest lane": timing["slowest_lane"],
        "Timeline": timeline_json(timing["timeline"]),
        "Duration to build": timing["duration_to_build_min"],
    }
    row.update(page_columns(state.get("page"),
                            timings.driver_intervals(run_dir)))
    if stage == "committed":
        # The one permitted triage write, and only at row creation: emitting
        # it again at beat1/beat2 would reset a reviewer's value.
        row["Triage status"] = "Untriaged"
    return row


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
