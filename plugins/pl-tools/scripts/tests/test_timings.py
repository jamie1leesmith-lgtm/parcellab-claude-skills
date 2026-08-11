"""Unit tests for timings. Stdlib unittest — no pytest."""
import datetime
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import timings  # noqa: E402


def dt(hh, mm, ss=0):
    return datetime.datetime(2026, 8, 11, hh, mm, ss)


class TestParseTs(unittest.TestCase):
    def test_parses_second_precision(self):
        self.assertEqual(timings.parse_ts("2026-08-11T21:35:56Z"), dt(21, 35, 56))

    def test_parses_millisecond_precision(self):
        # events.jsonl stamps carry .000Z; the timeline does not.
        self.assertEqual(timings.parse_ts("2026-08-11T21:38:56.000Z"),
                         dt(21, 38, 56))

    def test_none_passes_through(self):
        self.assertIsNone(timings.parse_ts(None))

    def test_unparseable_raises(self):
        with self.assertRaises(ValueError):
            timings.parse_ts("yesterday")


class TestPairIntervals(unittest.TestCase):
    def test_pairs_start_and_end_by_name(self):
        timeline = [
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-11T20:52:00Z"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-11T21:01:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["name"], "scrape")
        self.assertEqual(spans[0]["start"], dt(20, 52))
        self.assertEqual(spans[0]["end"], dt(21, 1))

    def test_unclosed_interval_has_no_end(self):
        # An agent that died mid-run. Must not report zero, and must not be
        # silently stretched to the end of the run.
        timeline = [{"kind": "agent", "name": "seed", "phase": "start",
                     "at": "2026-08-11T21:00:00Z"}]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(len(spans), 1)
        self.assertIsNone(spans[0]["end"])

    def test_gate_asked_answered_pairs(self):
        timeline = [
            {"kind": "gate", "name": "plan", "phase": "asked",
             "at": "2026-08-11T21:20:00Z"},
            {"kind": "gate", "name": "plan", "phase": "answered",
             "at": "2026-08-11T21:23:00Z"},
        ]
        spans = timings.pair_intervals(timeline)
        self.assertEqual(spans[0]["start"], dt(21, 20))
        self.assertEqual(spans[0]["end"], dt(21, 23))

    def test_same_name_in_different_kinds_does_not_cross_pair(self):
        timeline = [
            {"kind": "lane", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:00:00Z"},
            {"kind": "agent", "name": "seed", "phase": "start",
             "at": "2026-08-11T21:05:00Z"},
            {"kind": "agent", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:07:00Z"},
            {"kind": "lane", "name": "seed", "phase": "end",
             "at": "2026-08-11T21:10:00Z"},
        ]
        spans = {(s["kind"], s["name"]): s for s in timings.pair_intervals(timeline)}
        self.assertEqual(spans[("lane", "seed")]["end"], dt(21, 10))
        self.assertEqual(spans[("agent", "seed")]["end"], dt(21, 7))


class TestUnionSeconds(unittest.TestCase):
    def test_disjoint_spans_add_up(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), dt(11, 5))]), 600)

    def test_overlapping_spans_are_not_double_counted(self):
        # The whole reason union exists: the scrape agent runs during the
        # intake interview, so summing would count the same minutes twice.
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 10)),
                                   (dt(10, 5), dt(10, 15))]), 900)

    def test_fully_contained_span_adds_nothing(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 30)),
                                   (dt(10, 5), dt(10, 10))]), 1800)

    def test_unclosed_spans_are_ignored(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(11, 0), None)]), 300)

    def test_no_spans_is_zero(self):
        self.assertEqual(timings.union_seconds([]), 0)

    def test_touching_spans_merge(self):
        self.assertEqual(
            timings.union_seconds([(dt(10, 0), dt(10, 5)),
                                   (dt(10, 5), dt(10, 10))]), 600)


if __name__ == "__main__":
    unittest.main()
