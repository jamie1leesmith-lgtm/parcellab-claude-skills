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
import json
import pathlib

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
        lines = [raw_line for raw_line in log.read_text().splitlines()
                 if raw_line.strip()]
        if not lines:
            continue
        try:
            start = parse_ts(lines[0].split()[0])
        except ValueError:
            # A partial write or truncated flush must not take down the
            # whole report — skip this driver, keep the others.
            continue
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

    def has_closed(spans):
        return any(s["start"] and s["end"] for s in spans)

    stamps = [t for s in everything for t in (s["start"], s["end"]) if t]
    total = (max(stamps) - min(stamps)).total_seconds() if stamps else None

    covered = union_seconds((s["start"], s["end"]) for s in everything)
    measured = union_seconds((s["start"], s["end"]) for s in work)
    waiting = (union_seconds((s["start"], s["end"]) for s in gates)
               if has_closed(gates) else None)

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
        "measured_min": _minutes(measured) if has_closed(work) else None,
        "waiting_on_user_min": _minutes(waiting),
        "unattributed_min": (_minutes(max(0, total - covered))
                             if total is not None else None),
        "event_window_min": _minutes(window),
        "per_lane": per_lane,
        "per_agent": by_kind("agent"),
        "slowest_lane": slowest,
        "timeline": timeline,
    }
