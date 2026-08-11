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
        "Error detail": "; ".join(f["detail"]
                                  for f in state.get("failures", [])),
        "Total elapsed": timing["total_elapsed_min"],
        "Measured working time": timing["measured_min"],
        "Waiting on user": timing["waiting_on_user_min"],
        "Unattributed": timing["unattributed_min"],
        "Event window": timing["event_window_min"],
        "Slowest lane": timing["slowest_lane"],
        "Timeline": json.dumps(timing["timeline"]),
        "Duration to build": timing["duration_to_build_min"],
    }
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
