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
    """Mechanical signals, unioned with whatever the conductor logged live.

    `state["deviations"]` is `run_state.add_deviation()`'s own record —
    logged inline, the moment the conductor notices a variance, not
    reconstructed from memory at Beat 2. It is the primary source now; the
    checks below catch a few mechanical signals a conductor might not think
    to log itself (a failed lane, an inline scrape/seed fallback), and stay
    as a floor under the live log rather than a replacement for it.

    Before `add_deviation()` existed, `manual_intervention`,
    `instruction_unfollowable`, and `workaround_invented` were never derived
    here at all — the conductor could only add them at Beat 2, from memory,
    which under-reports exactly the cases worth catching (live 2026-08-11: a
    conductor launched drivers with `nohup` against the skill's instruction
    and did not notice until the user asked). They are logged the same way as
    every other category now, so they no longer need special-casing here.
    """
    found = list({d["category"] for d in state.get("deviations", [])
                  if d.get("category")})
    if state.get("failures") and "api_error" not in found:
        found.append("api_error")
    for lane in state.get("lanes", {}).values():
        if lane.get("status") == "failed" and "api_error" not in found:
            found.append("api_error")
    for name in ("scrape", "seed"):
        lane = state.get("lanes", {}).get(name, {})
        if lane.get("fallback_inline") and "lane_fallback_inline" not in found:
            found.append("lane_fallback_inline")
    if (results or {}).get("validator_rejected") and "validator_rejected" not in found:
        found.append("validator_rejected")
    return found


DEVIATION_NOTES_LIMIT = 1900


def deviation_notes_text(deviations, limit=DEVIATION_NOTES_LIMIT):
    """Render the free-text detail behind each logged deviation.

    Same shape and cap as `timeline_text` and for the same reason: an
    over-length text property rejects the whole row, and a rejected write is
    non-fatal by design, so this must self-limit rather than rely on the
    caller. Oldest entries drop first, with the same visible marker.
    """
    entries = list(deviations or [])

    def render(items):
        return "; ".join(
            f"{d.get('at')} {d.get('category')}: {d.get('detail')}"
            for d in items)

    dropped = 0
    while True:
        text = render(entries)
        if dropped:
            text = f"+{dropped} earlier dropped; " + text
        if len(text) <= limit or not entries:
            return text
        entries.pop(0)
        dropped += 1


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


def timeline_text(timeline, limit=TIMELINE_LIMIT):
    """Serialise the timeline as `<at> <kind>/<name>/<phase>; ...`.

    **Deliberately not JSON.** The Notion connector rejects a JSON-parseable
    string written to this text property — `properties.Timeline: Invalid
    input` — and a failed telemetry write is non-fatal, so the column
    disappears with no error. Proven live 2026-08-12 against the real
    database: JSON array, JSON object, and space-prefixed JSON array all
    rejected; plain text accepted. Run thenorthface-20260812-2328 shipped with
    a blank Timeline before this was found.

    The format is also denser than the JSON it replaces, so more of a long run
    survives the cap below.

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

    def render(items):
        return "; ".join(
            f"{e.get('at')} {e.get('kind')}/{e.get('name')}/{e.get('phase')}"
            for e in items)

    dropped = 0
    while True:
        text = render(entries)
        if dropped:
            text = f"+{dropped} earlier dropped; " + text
        if len(text) <= limit or not entries:
            return text
        entries.pop(0)
        dropped += 1


def page_columns(page, drivers):
    """Derive the five run-page columns.

    These five all stay at their empty defaults now, by design: the run page
    is served live by run_server.py and polls GET /state itself every two
    seconds, so there is no render call, no publish call, and no second URL
    for a run to drift to. Nothing in demo-environment's SKILL.md calls
    run_state.record_publish() or record_render() any more (see SKILL.md's
    "The run page" and references/telemetry.md), so `page.get("renders")`
    and `page.get("publishes")` read empty on every current run — this
    function still tolerates a populated `page` (an old run's state, or a
    future reintroduction of publish recording) without changing shape, but
    no live run feeds it one. `Max page gap` is scoped to the driver window
    for the same reason it always was — that is the only stretch with an
    expected cadence, one wave per GAP_SECONDS — it is simply never
    reached with no publishes to measure a gap between.
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
        "Mode": manifest.get("run", {}).get("mode") or "babysit",
        "Outcome": outcome,
        "Reached": STAGE_REACHED.get(stage, "Gate"),
        "Lanes failed": lanes_failed,
        "Orders planned": len(manifest.get("orders", [])),
        "Orders created": len(state.get("orders", [])),
        "Events pushed": pushed,
        "Events planned": planned,
        "Deviations": derive_deviations(state, results),
        "Deviation notes": deviation_notes_text(state.get("deviations")),
        "Error detail": "; ".join(errors),
        "Total elapsed": timing["total_elapsed_min"],
        "Measured working time": timing["measured_min"],
        "Waiting on user": timing["waiting_on_user_min"],
        "Unattributed": timing["unattributed_min"],
        "Event window": timing["event_window_min"],
        "Slowest lane": timing["slowest_lane"],
        "Timeline": timeline_text(timing["timeline"]),
        "Duration to build": timing["duration_to_build_min"],
        "Largest gap": timing["largest_gap"],
        "Largest gap after": timing["largest_gap_after"],
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
