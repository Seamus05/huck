import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check


class TestRenderDashboard(unittest.TestCase):
    def test_healthy_entry(self):
        entry = {
            "time": "2026-08-16T00:00:00+00:00",
            "exit_code": 0,
            "tests_passed": True,
            "mnemo_reachable": True,
            "tree_drift": False,
            "unresolved_count": 0,
            "tracker_reachable": True,
            "tracker_repo": "Seamus05/Lab",
            "tracker_open": 2,
        }
        out = check.render_dashboard(entry, [entry])
        self.assertIn("# Huck health dashboard", out)
        self.assertIn("Tests: PASS", out)
        self.assertIn("Mnemosyne: reachable", out)
        self.assertIn("README tree: clean", out)
        self.assertIn("Unresolved items in memory: 0", out)
        self.assertIn("2 open issues", out)
        self.assertIn("| time | exit |", out)

    def test_unhealthy_entry(self):
        entry = {
            "time": "t",
            "exit_code": 1,
            "tests_passed": False,
            "mnemo_reachable": False,
            "tree_drift": True,
            "unresolved_count": 3,
            "tracker_reachable": False,
        }
        out = check.render_dashboard(entry, [entry])
        self.assertIn("Tests: FAIL", out)
        self.assertIn("Mnemosyne: UNREACHABLE", out)
        self.assertIn("README tree: DRIFT", out)
        self.assertIn("Unresolved items in memory: 3", out)
        self.assertIn("Tracker: unreachable", out)

    def test_trend_limits_to_ten_rows(self):
        history = [{"time": f"t{i}", "exit_code": 0, "tests_passed": True,
                    "mnemo_reachable": True, "tree_drift": False,
                    "unresolved_count": 0, "tracker_reachable": True,
                    "tracker_open": 0} for i in range(20)]
        out = check.render_dashboard({}, history)
        # Header + 10 data rows
        rows = [l for l in out.splitlines() if l.startswith("| ")]
        self.assertEqual(len(rows), 11)

    def test_missing_keys_do_not_crash(self):
        out = check.render_dashboard({}, [])
        self.assertIn("# Huck health dashboard", out)
        self.assertIn("Tests: FAIL", out)  # None is falsy


class TestHealthPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_state = check.STATE_DIR
        self.old_health = check.HEALTH_FILE
        self.old_dashboard = check.DASHBOARD_FILE
        check.STATE_DIR = self.tmpdir.name
        check.HEALTH_FILE = os.path.join(self.tmpdir.name, "health.json")
        check.DASHBOARD_FILE = os.path.join(self.tmpdir.name, "dashboard.md")

    def tearDown(self):
        check.STATE_DIR = self.old_state
        check.HEALTH_FILE = self.old_health
        check.DASHBOARD_FILE = self.old_dashboard
        self.tmpdir.cleanup()

    def test_write_then_load_roundtrip(self):
        entry = {"time": "t1", "exit_code": 0}
        check.write_dashboard(entry, [])
        history = check._load_health_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["time"], "t1")

    def test_history_capped(self):
        old_limit = check.HISTORY_LIMIT
        check.HISTORY_LIMIT = 3
        try:
            entries = [{"time": f"t{i}", "exit_code": 0} for i in range(5)]
            check.write_dashboard(entries[-1], entries[:-1])
            history = check._load_health_history()
            self.assertEqual(len(history), 3)
            self.assertEqual(history[-1]["time"], "t4")
        finally:
            check.HISTORY_LIMIT = old_limit

    def test_missing_health_file_returns_empty(self):
        self.assertEqual(check._load_health_history(), [])

    def test_dashboard_file_written(self):
        check.write_dashboard({"time": "t", "exit_code": 0}, [])
        with open(check.DASHBOARD_FILE) as f:
            self.assertIn("Huck health dashboard", f.read())


class TestTracker(unittest.TestCase):
    @mock.patch("check.subprocess.run")
    def test_reachable(self, mock_run):
        mock_run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps([
                {"number": 1, "title": "Open item", "labels": [{"name": "wayfinder:map"}]},
            ]),
            stderr="",
        )
        result = check.check_tracker()
        self.assertTrue(result["reachable"])
        self.assertEqual(result["open_count"], 1)
        self.assertEqual(result["issues"][0]["number"], 1)
        self.assertEqual(result["issues"][0]["labels"], ["wayfinder:map"])

    @mock.patch("check.subprocess.run")
    def test_unreachable_on_nonzero(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="gh: not found")
        result = check.check_tracker()
        self.assertFalse(result["reachable"])
        self.assertIn("gh", result.get("error", ""))

    @mock.patch("check.subprocess.run")
    def test_unreachable_on_exception(self, mock_run):
        mock_run.side_effect = FileNotFoundError("no gh binary")
        result = check.check_tracker()
        self.assertFalse(result["reachable"])


if __name__ == "__main__":
    unittest.main()