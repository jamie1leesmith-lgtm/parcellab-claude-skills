#!/usr/bin/env python3
"""Report a run's timing shape without claiming a cause.

`demo-environment/references/telemetry.md` already warns that a large
`Unattributed` value can mean "the conductor was fixing its own defects"
rather than a genuine bottleneck. With two rows in the runs database — one of
which predates timing instrumentation entirely — a confident guess at cause
would likely be wrong, and a wrong guess here would undercut every other claim
this skill makes. So this reports size and location only: how big a gap is,
and where it falls, never why.

There is deliberately no cross-run ledger for this. A comms cause generalizes
(`hasReleasedVersion` gates sending on every account, always); a slow lane on
one run has not been shown to generalize the same way. See
docs/superpowers/specs/2026-08-12-run-triage-timing-phase-design.md.
"""
import json
import sys


def format_note(row):
    """A factual, non-causal summary of one row's timing data.

    Returns None when there is nothing to report — a row like Currys' that
    predates the timing columns has `Total elapsed: None`, and silence is the
    honest answer, not a zero.

    Each sentence is independently optional: a field that is null is omitted
    rather than rendered as a placeholder, matching the rule `largest_gap()`
    already follows for an unmeasured run. The gap sentence needs both
    `Largest gap` and `Largest gap after` — they are always produced together
    by `largest_gap()` in current code, but a gap with no label would
    otherwise render an incomplete sentence.
    """
    total = row.get("Total elapsed")
    if not total:
        return None

    parts = [f"Total {total:.1f} min."]

    gap = row.get("Largest gap")
    label = row.get("Largest gap after")
    if gap is not None and label is not None:
        pct = round(gap / total * 100)
        parts.append(
            f"Largest gap {gap:.1f} min after {label} ({pct}% of total).")

    unattributed = row.get("Unattributed")
    if unattributed is not None:
        pct = round(unattributed / total * 100)
        parts.append(
            f"Unattributed {unattributed:.1f} min ({pct}% of total) — "
            f"size and location only, not a diagnosis.")

    return " ".join(parts)


def main():
    row = json.load(sys.stdin)
    note = format_note(row)
    if note:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
