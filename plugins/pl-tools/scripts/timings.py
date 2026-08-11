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
