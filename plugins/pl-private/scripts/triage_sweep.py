#!/usr/bin/env python3
"""Rank untriaged telemetry rows so the worst one gets looked at first.

Arithmetic only, deliberately: a conductor asked to weigh severity in prose
weighs it differently each run, and the whole point of the runs database is
that defects are found by query rather than by anecdote.
"""
import json
import sys

SEVERE_OUTCOMES = ("Stalled", "Failed")


def severity(row):
    """Higher is worse.

    The weights say a run that stopped (4) matters more than one that ran but
    mailed nobody (3), which matters more than a failed lane (2 each) or a run
    that never reached Beat 2 (2), which matters more than a recorded deviation
    (1 each). They are a starting order, not a measurement — revisit once ten
    rows exist.

    A run with no Beat 2 scores for it rather than being read as missing data:
    it stopped before anything was verified, which is a finding. Unlike every
    other field here, an absent `Reached` key also scores rather than
    defaulting to neutral — `build_telemetry_row` writes it at every stage, so
    a row without one did not reach Beat 2 either.
    """
    score = 0
    if row.get("Outcome") in SEVERE_OUTCOMES:
        score += 4

    expected = row.get("Comms expected") or 0
    fired = row.get("Comms fired") or 0
    if expected and fired < expected:
        score += 3

    if row.get("Reached") != "Beat 2":
        score += 2

    score += 2 * len(row.get("Lanes failed") or [])
    score += len(row.get("Deviations") or [])
    return score


def rank(rows):
    """Worst first: severity, then the largest uninstrumented gap.

    A null `Largest gap` sorts last rather than first — it means the run was
    not measured, which is not evidence that it was fast.
    """
    return sorted(rows,
                  key=lambda r: (severity(r), r.get("Largest gap") or -1.0),
                  reverse=True)


def main():
    rows = json.load(sys.stdin)
    ranked = rank(rows)
    print(f"{'Run ID':32s} {'Sev':>3s} {'Gap':>6s} {'Total':>6s}  Outcome")
    for r in ranked:
        gap = r.get("Largest gap")
        total = r.get("Total elapsed")
        print(f"{str(r.get('Run ID'))[:32]:32s} {severity(r):3d} "
              f"{'-' if gap is None else format(gap, '.1f'):>6s} "
              f"{'-' if total is None else format(total, '.1f'):>6s}  "
              f"{r.get('Outcome')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
