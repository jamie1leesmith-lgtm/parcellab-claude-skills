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

    One span per open/close pair, not one per name: a re-asked gate is an
    enumerated deviation, and collapsing 20:00→20:05 and 21:00→21:05 into a
    single 65-minute span reports a wrong number for a real, common case.
    A second open while one is still unclosed starts a new span; the previous
    one stays unclosed rather than being retro-fitted with someone else's end.

    An interval whose close never arrived keeps `end: None` — an agent that
    died must not read as zero, nor be stretched to the end of the run.
    """
    spans = []
    open_span = {}
    for entry in timeline or []:
        key = (entry.get("kind"), entry.get("name"))
        at = parse_ts(entry.get("at"))
        phase = entry.get("phase")
        if phase in OPEN_PHASES:
            span = {"kind": key[0], "name": key[1], "start": at, "end": None}
            spans.append(span)
            open_span[key] = span
        elif phase in CLOSE_PHASES:
            span = open_span.pop(key, None)
            if span is None:
                # A close with no open: keep it visible rather than dropping
                # it, but it has no duration.
                spans.append({"kind": key[0], "name": key[1],
                              "start": None, "end": at})
            else:
                span["end"] = at
    return spans


def union_seconds(spans):
    """Total wall-clock seconds covered by any span. Unclosed spans ignored.

    A span whose end precedes its start is impossible; it raises rather than
    returning a negative, which would make `covered` negative and push
    `unattributed` above `total`.
    """
    closed = sorted((s, e) for s, e in spans if s is not None and e is not None)
    for start, end in closed:
        if end < start:
            raise ValueError(f"span ends before it starts: {start} → {end}")
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


def _live_start_index(lines):
    """Index of the live driver's START line, or None if there is no live run.

    `run-lifecycle.sh` appends, and both SKILL.mds mandate a `DRYRUN=1` pass
    into the same run.log immediately before the live launch. Taking lines[0]
    therefore measured from the dry run: a real 3.0-minute order read as 6.7.
    Anchor on the LAST `START sequence` carrying `dryrun=0`.

    The guard fails CLOSED. A log with no `dryrun=0` START — whether it holds
    only dry-run passes, or the line was reworded and lost the flag — has no
    identifiable live driver, so it has no driver interval. Falling back to
    lines[0] would re-admit exactly the dry-run inflation this guard exists to
    stop, and a wrong number is worse than a null.

    This parses `run-lifecycle.sh`'s START line; that line carries a comment
    naming this function, and a test pins the `dryrun=` token.
    """
    live = None
    for i, line in enumerate(lines):
        if "START sequence" in line and "dryrun=0" in line:
            live = i
    return live


def _stamp_of(line):
    """The leading timestamp of a log line, or None if it is corrupt."""
    try:
        return parse_ts(line.split()[0])
    except (ValueError, IndexError):
        return None


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
        first = _live_start_index(lines)
        if first is None:
            continue
        start = _stamp_of(lines[first])
        if start is None:
            # A partial write or truncated flush must not take down the
            # whole report — skip this driver, keep the others.
            continue
        end = None
        for line in lines[first + 1:]:
            if "DONE sequence complete" in line:
                # A corrupt DONE stamp leaves the driver unfinished, which is
                # honest; guessing an end would be a wrong number.
                end = _stamp_of(line)
                break
        spans.append({"kind": "driver", "name": log.parent.name,
                      "start": start, "end": end})
    return spans


def _last_stamp(timeline, kind, name, phase):
    """The last stamp for one exact mark, or None if it was never written.

    Last, not first: a re-asked gate is answered more than once, and the
    build starts from the answer that released it.
    """
    found = None
    for entry in timeline or []:
        if (entry.get("kind") == kind and entry.get("name") == name
                and entry.get("phase") == phase):
            at = parse_ts(entry.get("at"))
            if at is not None:
                found = at
    return found


def duration_to_build(timeline):
    """Seconds from the plan gate being answered to Beat 1, or None.

    Derived, never hand-computed: a model reading two stamps off a page and
    subtracting them is exactly the estimate this module exists to replace.
    """
    approved = _last_stamp(timeline, "gate", "plan", "answered")
    built = _last_stamp(timeline, "gate", "beat1", "end")
    if approved is None or built is None or built < approved:
        return None
    return (built - approved).total_seconds()


def summarise(run_dir):
    """Every headline metric, derived from recorded stamps only.

    total, measured, waiting and unattributed are NOT additive: a gate can
    overlap measured work, so unattributed comes from one union across every
    interval including gates, and waiting is an overlapping view of it.
    """
    run_dir = pathlib.Path(run_dir)
    try:
        state = json.loads((run_dir / "run-state.json").read_text())
    except (OSError, ValueError):
        # Telemetry is an observer that never fails a run: a missing or
        # unreadable run-state is an empty timeline, not an exception.
        state = {}
    timeline = state.get("timeline") or []

    marked = pair_intervals(timeline)
    drivers = driver_intervals(run_dir)
    everything = marked + drivers

    gates = [s for s in everything if s["kind"] == "gate"]
    work = [s for s in everything if s["kind"] != "gate"]

    def has_closed(spans):
        return any(s["start"] and s["end"] for s in spans)

    # Fewer than two distinct stamps is not a zero-length run, it is a run
    # nobody measured. "Total elapsed 0.0, Unattributed 0.0" would read as
    # fully instrumented with nothing unexplained.
    stamps = {t for s in everything for t in (s["start"], s["end"]) if t}
    total = ((max(stamps) - min(stamps)).total_seconds()
             if len(stamps) >= 2 else None)

    covered = union_seconds((s["start"], s["end"]) for s in everything)
    measured = union_seconds((s["start"], s["end"]) for s in work)
    waiting = (union_seconds((s["start"], s["end"]) for s in gates)
               if has_closed(gates) else None)

    # The window is not known until every driver has finished: falling back
    # to the other drivers' stamps silently shortens it.
    if drivers and all(s["start"] and s["end"] for s in drivers):
        window = (max(s["end"] for s in drivers)
                  - min(s["start"] for s in drivers)).total_seconds()
    else:
        window = None

    def by_kind(kind):
        """Minutes per name, unioned across every closed span for that name.

        `pair_intervals` emits one span per open/close pair, so a lane marked
        twice has several. Keying by name alone let the last one overwrite the
        rest — 52 minutes of work reported as 2.0. A name with no closed span
        stays absent.
        """
        grouped = {}
        for s in everything:
            if s["kind"] == kind and s["start"] and s["end"]:
                grouped.setdefault(s["name"], []).append((s["start"], s["end"]))
        return {name: _minutes(union_seconds(spans))
                for name, spans in grouped.items()}

    per_lane = by_kind("lane")
    slowest = max(per_lane, key=per_lane.get) if per_lane else None

    return {
        "total_elapsed_min": _minutes(total),
        "measured_min": _minutes(measured) if has_closed(work) else None,
        "waiting_on_user_min": _minutes(waiting),
        "unattributed_min": (_minutes(max(0, total - covered))
                             if total is not None else None),
        "event_window_min": _minutes(window),
        "duration_to_build_min": _minutes(duration_to_build(timeline)),
        "per_lane": per_lane,
        "per_agent": by_kind("agent"),
        "slowest_lane": slowest,
        "timeline": timeline,
    }
