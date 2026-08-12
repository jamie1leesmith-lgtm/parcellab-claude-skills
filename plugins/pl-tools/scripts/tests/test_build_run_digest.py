import json
import pathlib
import tempfile
import unittest

import build_run_digest


class DigestTests(unittest.TestCase):
    def _run_dir(self, timeline):
        tmp = tempfile.mkdtemp()
        (pathlib.Path(tmp) / "run-state.json").write_text(
            json.dumps({"timeline": timeline}))
        return tmp

    def test_missing_run_state_returns_a_note_not_an_exception(self):
        """Telemetry is an observer. A missing file is not a crash."""
        with tempfile.TemporaryDirectory() as empty:
            out = build_run_digest.run_digest_markdown(empty)
        self.assertIn("No timeline recorded", out)

    def test_spans_table_reports_duration(self):
        run_dir = self._run_dir([
            {"kind": "lane", "name": "scrape", "phase": "start",
             "at": "2026-08-12T09:47:05"},
            {"kind": "lane", "name": "scrape", "phase": "end",
             "at": "2026-08-12T10:04:29"},
        ])
        out = build_run_digest.run_digest_markdown(run_dir)
        self.assertIn("| lane | scrape |", out)
        self.assertIn("17.4", out)

    def test_unclosed_span_shows_a_dash_not_a_zero(self):
        """An agent that died must not read as instantaneous."""
        run_dir = self._run_dir([
            {"kind": "agent", "name": "seed", "phase": "start",
             "at": "2026-08-12T10:36:26"},
        ])
        out = build_run_digest.run_digest_markdown(run_dir)
        self.assertIn("| agent | seed |", out)
        self.assertNotIn("0.0", out)

    def test_every_timeline_entry_appears(self):
        entries = [{"kind": "lane", "name": f"l{i}", "phase": "start",
                    "at": "2026-08-12T10:36:26"} for i in range(60)]
        out = build_run_digest.run_digest_markdown(self._run_dir(entries))
        for i in range(60):
            self.assertIn(f"l{i}", out)

    def test_no_line_exceeds_the_notion_block_limit(self):
        """Rows are separate blocks; a single over-length line is rejected."""
        entries = [{"kind": "lane", "name": f"l{i}", "phase": "start",
                    "at": "2026-08-12T10:36:26"} for i in range(200)]
        out = build_run_digest.run_digest_markdown(self._run_dir(entries))
        for line in out.splitlines():
            self.assertLessEqual(len(line), 2000)


if __name__ == "__main__":
    unittest.main()
