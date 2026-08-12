#!/usr/bin/env python3
"""Sleep until Beat 2's floor has passed, then exit.

A conductor only acts when something invokes it. By Beat 1 every driver and
every `wait_for_event.sh` watcher has already exited, so nothing is left to
wake it — and Beat 2 simply never happens. Live 2026-08-12 a fully built
environment sat unverified for 19 minutes until the user asked why.

Run this as a tracked background task at Beat 1. Its exit notification is the
wake-up: when it returns, run Beat 2.

    python3 wait_for_beat2.py <run dir> [--floor SECONDS] [--from-now]

Exit 0 = the floor has passed, go and verify. Non-zero = nothing was armed
(say so rather than assuming the wait happened).
"""
import argparse
import datetime
import json
import pathlib
import sys
import time

# Lowered from 900 on 2026-08-12, verified against the operator's own inbox.
# SKILL.md's Beat 2 pairs this with a re-check before any comm is called
# missing — that re-check is what carries the safety the longer wait used to,
# because a split order's `package_delivered_*` was measured at over 10
# minutes on 2026-08-11.
DEFAULT_FLOOR_SECONDS = 300


def _parse(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def newest_event(run_dir):
    """The latest `at` across every order's events.jsonl, or None.

    Measured across the whole run, never per order: one Beat 2 covers every
    arc, so the floor has to be anchored to the slowest driver's last event.
    """
    newest = None
    for f in sorted(pathlib.Path(run_dir).glob("orders/*/events.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                at = json.loads(line).get("at")
            except ValueError:
                continue
            if at and (newest is None or _parse(at) > _parse(newest)):
                newest = at
    return newest


def seconds_remaining(last_event, floor=DEFAULT_FLOOR_SECONDS, now=None):
    now_dt = (_parse(now) if now
              else datetime.datetime.now(datetime.timezone.utc))
    elapsed = (now_dt - _parse(last_event)).total_seconds()
    return max(0, int(round(floor - elapsed)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--floor", type=int, default=DEFAULT_FLOOR_SECONDS,
                    help="seconds after the last event (default 300)")
    ap.add_argument("--from-now", action="store_true",
                    help="wait the full floor from now, ignoring event age")
    args = ap.parse_args()

    last = newest_event(args.run_dir)
    if last is None:
        print(f"no events found under {args.run_dir}/orders/*/events.jsonl — "
              f"nothing armed; Beat 2 was NOT scheduled", file=sys.stderr)
        return 1

    remaining = args.floor if args.from_now else seconds_remaining(
        last, args.floor)
    if remaining:
        print(f"last event {last}; sleeping {remaining}s "
              f"({args.floor}s floor)", flush=True)
        time.sleep(remaining)
    print(f"Beat 2 floor reached — last event was {last}, "
          f"{args.floor}s floor elapsed. Verify now.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
