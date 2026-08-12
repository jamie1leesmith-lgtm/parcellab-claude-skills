#!/usr/bin/env python3
"""Render a run's detail as markdown for the body of its Notion row.

A run page is a private artifact: its owner can share it by hand, but there is
no publish-time setting and no default, so nobody else can open it. The Notion
row is in a database the team already shares, and its page body has no
equivalent of the 2000-character property limit that truncates `Timeline`.
Writing the detail here is what makes a teammate's run readable at all.

Tables, not code blocks: each table row becomes its own Notion block, so a long
timeline cannot produce one over-length block.
"""
import json
import pathlib
import sys

import timings


def _fmt(stamp):
    return stamp.strftime("%H:%M:%S") if stamp else "—"


def run_digest_markdown(run_dir):
    """Markdown for one run: its spans, then every timeline entry."""
    path = pathlib.Path(run_dir) / "run-state.json"
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        return "## Run detail\n\nNo timeline recorded for this run.\n"

    timeline = state.get("timeline") or []
    if not timeline:
        return "## Run detail\n\nNo timeline recorded for this run.\n"

    lines = ["## Run detail", "", "### Spans", "",
             "| Kind | Name | Start | End | Minutes |",
             "|---|---|---|---|---|"]
    for span in timings.pair_intervals(timeline):
        if span["start"] and span["end"]:
            minutes = f"{(span['end'] - span['start']).total_seconds() / 60:.1f}"
        else:
            # Unclosed: an agent that died must not read as zero.
            minutes = "—"
        lines.append(f"| {span['kind']} | {span['name']} | "
                     f"{_fmt(span['start'])} | {_fmt(span['end'])} | "
                     f"{minutes} |")

    lines += ["", "### Timeline (full, untruncated)", "",
              "| At | Kind | Name | Phase |", "|---|---|---|---|"]
    for entry in timeline:
        lines.append(f"| {entry.get('at')} | {entry.get('kind')} | "
                     f"{entry.get('name')} | {entry.get('phase')} |")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(run_digest_markdown(sys.argv[1]))
