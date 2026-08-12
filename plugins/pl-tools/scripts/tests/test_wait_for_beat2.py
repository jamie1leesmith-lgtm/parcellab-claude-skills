"""Unit tests for wait_for_beat2. Stdlib unittest — no pytest."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
import wait_for_beat2  # noqa: E402


def a_run(events_by_order, floor_seconds=None):
    """Run dir with one events.jsonl per order."""
    d = pathlib.Path(tempfile.mkdtemp())
    for label, stamps in events_by_order.items():
        od = d / "orders" / label
        od.mkdir(parents=True)
        with open(od / "events.jsonl", "w") as f:
            for at in stamps:
                f.write(json.dumps({"status": "InTransit",
                                    "tracking_number": "1", "at": at,
                                    "http": "OK"}) + "\n")
    return d


class TestNewestEvent(unittest.TestCase):
    """Beat 2's floor is measured from the LAST event of the whole run.

    Not per order: the conductor posts one Beat 2 covering every arc, so a run
    whose slowest driver is still going must not be verified off a faster
    order's final event.
    """

    def test_picks_the_latest_event_across_all_orders(self):
        d = a_run({
            "01-a": ["2026-08-12T22:58:15.000Z"],
            "02-b": ["2026-08-12T23:05:06.000Z"],   # the real last event
            "03-c": ["2026-08-12T23:01:51.000Z"],
        })
        self.assertEqual(wait_for_beat2.newest_event(d),
                         "2026-08-12T23:05:06.000Z")

    def test_picks_the_latest_line_within_one_order(self):
        d = a_run({"01-a": ["2026-08-12T22:51:33.000Z",
                            "2026-08-12T22:58:15.000Z"]})
        self.assertEqual(wait_for_beat2.newest_event(d),
                         "2026-08-12T22:58:15.000Z")

    def test_returns_none_when_no_events_exist(self):
        # Armed before any driver wrote a line — caller must not treat this as
        # "the floor has passed".
        self.assertIsNone(wait_for_beat2.newest_event(a_run({})))

    def test_ignores_blank_and_malformed_lines(self):
        d = a_run({"01-a": ["2026-08-12T22:51:33.000Z"]})
        with open(d / "orders" / "01-a" / "events.jsonl", "a") as f:
            f.write("\n")
            f.write("not json\n")
        self.assertEqual(wait_for_beat2.newest_event(d),
                         "2026-08-12T22:51:33.000Z")


class TestSecondsRemaining(unittest.TestCase):
    def test_zero_once_the_floor_has_passed(self):
        self.assertEqual(
            wait_for_beat2.seconds_remaining(
                "2026-08-12T23:00:00.000Z", floor=300,
                now="2026-08-12T23:06:00.000Z"), 0)

    def test_counts_down_within_the_floor(self):
        self.assertEqual(
            wait_for_beat2.seconds_remaining(
                "2026-08-12T23:00:00.000Z", floor=300,
                now="2026-08-12T23:02:00.000Z"), 180)

    def test_full_floor_immediately_after_the_event(self):
        self.assertEqual(
            wait_for_beat2.seconds_remaining(
                "2026-08-12T23:00:00.000Z", floor=300,
                now="2026-08-12T23:00:00.000Z"), 300)

    def test_floor_default_is_five_minutes(self):
        # Lowered from 15 on 2026-08-12; the re-check in SKILL.md carries the
        # safety the longer wait used to.
        self.assertEqual(wait_for_beat2.DEFAULT_FLOOR_SECONDS, 300)


class TestCli(unittest.TestCase):
    def _run(self, run_dir, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "wait_for_beat2.py"),
             str(run_dir), *args],
            capture_output=True, text=True, timeout=30)

    def test_exits_zero_and_reports_when_floor_already_passed(self):
        d = a_run({"01-a": ["2020-01-01T00:00:00.000Z"]})
        r = self._run(d)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Beat 2", r.stdout)

    def test_exits_nonzero_when_there_are_no_events(self):
        # Silence here would look identical to "ready"; the conductor needs to
        # know it armed nothing.
        r = self._run(a_run({}))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no events", (r.stdout + r.stderr).lower())

    def test_actually_sleeps_when_the_floor_is_ahead(self):
        d = a_run({"01-a": ["2020-01-01T00:00:00.000Z"]})
        r = self._run(d, "--floor", "2", "--from-now")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
