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


class TestMnemosyneCheck(unittest.TestCase):
    """check_mnemosyne now probes the read path, not just /health.

    A loop that can write but not read is a broken pattern, so a failed read
    probe must make the service 'unreachable' from the check's point of view.
    All network is mocked — never touch the real Mnemosyne DB in tests.
    """

    @mock.patch("urllib.request.urlopen")
    def test_reachable_when_health_and_read_ok(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"status":"ok"}'
        )
        with mock.patch.object(check.ds, "query", return_value=[{"id": "x"}]):
            result = check.check_mnemosyne()
        self.assertTrue(result["reachable"])
        self.assertTrue(result["read"]["ok"])
        self.assertEqual(result["status"], "ok")

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_when_read_probe_empty(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"status":"ok"}'
        )
        with mock.patch.object(check.ds, "query", return_value=[]):
            result = check.check_mnemosyne()
        self.assertFalse(result["reachable"])
        self.assertFalse(result["read"]["ok"])
        self.assertIn("0 passages", result["read"].get("error", ""))

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_when_health_down(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("down")
        with mock.patch.object(check.ds, "query", return_value=[]) as mock_query:
            result = check.check_mnemosyne()
        self.assertFalse(result["reachable"])
        self.assertIn("error", result)
        mock_query.assert_not_called()  # no read probe when health is down

    @mock.patch("urllib.request.urlopen")
    def test_read_probe_is_write_free(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            b'{"status":"ok"}'
        )
        with mock.patch.object(check.ds, "query", return_value=[{"id": "x"}]) as mock_query:
            check.check_mnemosyne()
        _, kwargs = mock_query.call_args
        self.assertFalse(kwargs.get("tracked", True), "read probe must not bump counters")
        self.assertEqual(kwargs.get("limit"), 1)
        self.assertEqual(kwargs.get("min_q"), 0.0)


class TestIsUnresolved(unittest.TestCase):
    """The unresolved-item filter is pure logic — test it without the network.

    Guardrail: records of work done must not wake Huck; seeds of work to do
    must. Completion chronicles are detected by structure as well as tags.
    """

    def _p(self, text, tags=None, pid="p1", source_file=None):
        r = {"id": pid, "text": text, "tags": tags or []}
        if source_file:
            r["metadata"] = {"source_file": source_file}
        return r

    def test_episode_chronicle_not_unresolved(self):
        r = self._p(
            "## Episode: Open Computer Direction — Plan Ratified PASS 0.85\n"
            "### What was asked\nBuild Phase 0 (bubblewrap sandbox).",
            tags=["phaedrus", "chronicle", "phase-0-complete"],
        )
        self.assertFalse(check._is_unresolved(r, set()))

    def test_alignment_signal_not_unresolved(self):
        r = self._p(
            "## Alignment Signal: HAZ Paper — Formal Validation\n"
            "### The Three-Loop Architecture\nInner Loop (GRPO):",
            tags=["phaedrus", "chronicle", "alignment-signal"],
        )
        self.assertFalse(check._is_unresolved(r, set()))

    def test_past_tense_completion_not_unresolved(self):
        r = self._p(
            "Created pipeline_health_gate.py and integrated into ground skill A2b. "
            "The gate checks 3 layers and outputs verdicts.",
            tags=["carlin", "kairos", "ground-skill"],
        )
        self.assertFalse(check._is_unresolved(r, set()))

    def test_past_tense_built_completion_not_unresolved(self):
        # "Built X" (past tense) is a completion record — NOT a seed.
        # Discovered 2026-08-18 in the b1-memory-loop worktree: the learn()
        # bridge chronicle started "Built the learn() cross-agent bridge..."
        # and was flagged as unresolved because "built " was missing from the
        # past-tense openers. "build " (imperative) must still count as a seed.
        r = self._p(
            "Built the learn() cross-agent bridge (growth seed option 2 of 0f2d383c). "
            "learn(query_text, limit, min_q, agents, top_tags) in ds.py queries "
            "the whole shared corpus and aggregates recurring patterns.",
            tags=["huck", "growth", "build", "learn", "bridge", "cross-agent"],
        )
        self.assertFalse(check._is_unresolved(r, set()))

    def test_imperative_build_still_unresolved(self):
        # "Build X" (imperative) is how a seed talks — the "built " opener
        # must NOT swallow it.
        r = self._p(
            "Build a bridge from Huck to the Wayfinder tracker. Can you build it?",
            tags=["huck", "growth"],
        )
        self.assertTrue(check._is_unresolved(r, set()))

    def test_seed_with_next_session_tag_is_unresolved(self):
        r = self._p(
            "Growth seed — bridges to build. (1) The Wayfinder episode.",
            tags=["huck", "growth", "seed", "next-session"],
        )
        self.assertTrue(check._is_unresolved(r, set()))

    def test_explicit_action_is_unresolved(self):
        r = self._p(
            "Remaining: can you build a loop-proof tool? Pick one.",
            tags=["huck"],
        )
        self.assertTrue(check._is_unresolved(r, set()))

    def test_resolved_id_skipped(self):
        r = self._p("build the next bridge", pid="abc12345")
        self.assertFalse(check._is_unresolved(r, {"abc12345"}))

    def test_self_check_skipped(self):
        r = self._p("Huck check: drift detected — build", tags=["self-check"])
        self.assertFalse(check._is_unresolved(r, set()))

    def test_meta_tag_skipped(self):
        r = self._p("TODO: document the build", tags=["documentation"])
        self.assertFalse(check._is_unresolved(r, set()))

    def test_no_base_signal_skipped(self):
        r = self._p("just a random note about the weather")
        self.assertFalse(check._is_unresolved(r, set()))

    def test_next_session_exempts_completion_structure(self):
        # Explicitly tagged for the next session: counts even with episode shape.
        r = self._p(
            "## Episode: done thing\n### Approach\nnext huck should build X",
            tags=["huck", "next-session"],
        )
        self.assertTrue(check._is_unresolved(r, set()))

    def test_check_py_source_skipped(self):
        r = self._p(
            "build bridge",
            source_file="huck/notebooks/check.py",
        )
        self.assertFalse(check._is_unresolved(r, set()))

    def test_check_py_source_skipped_with_service_metadata_shape(self):
        # The Mnemosyne service returns metadata as `metadata_` (a JSON
        # string), not `metadata` (a dict). Discovered 2026-08-18: the
        # source_file filter was reading the dict shape and had silently
        # stopped matching real passages.
        r = {
            "id": "p1",
            "text": "build bridge",
            "tags": [],
            "metadata_": '{"source_file": "huck/notebooks/check.py"}',
        }
        self.assertFalse(check._is_unresolved(r, set()))


class TestAgentConfig(unittest.TestCase):
    """The repo must carry its own agent definition (isolated-agent seed).

    .opencode/opencode.json is committed so a fresh checkout can instantiate
    Huck without ambient global config. The check fails when the definition
    goes missing or stops defining agent.huck.
    """

    def _tmp_repo(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        old_root = check.REPO_ROOT
        check.REPO_ROOT = tmpdir.name
        self.addCleanup(setattr, check, "REPO_ROOT", old_root)
        return tmpdir.name

    def test_ok_when_config_defines_huck(self):
        root = self._tmp_repo()
        os.makedirs(os.path.join(root, ".opencode"))
        with open(os.path.join(root, ".opencode", "opencode.json"), "w") as f:
            json.dump({
                "agent": {
                    "huck": {
                        "description": "Proving agent",
                        "model": "opencode/deepseek-v4-flash-free",
                        "permission": {"read": "allow"},
                    }
                }
            }, f)
        result = check.check_agent_config()
        self.assertTrue(result["ok"])

    def test_fails_when_file_missing(self):
        self._tmp_repo()
        result = check.check_agent_config()
        self.assertFalse(result["ok"])
        self.assertIn("missing", result["error"])

    def test_fails_when_no_huck_agent(self):
        root = self._tmp_repo()
        os.makedirs(os.path.join(root, ".opencode"))
        with open(os.path.join(root, ".opencode", "opencode.json"), "w") as f:
            json.dump({"agent": {"phaedrus": {"description": "x"}}}, f)
        result = check.check_agent_config()
        self.assertFalse(result["ok"])
        self.assertIn("agent.huck", result["error"])

    def test_fails_when_invalid_json(self):
        root = self._tmp_repo()
        os.makedirs(os.path.join(root, ".opencode"))
        with open(os.path.join(root, ".opencode", "opencode.json"), "w") as f:
            f.write("{not json")
        result = check.check_agent_config()
        self.assertFalse(result["ok"])
        self.assertIn("valid JSON", result["error"])


if __name__ == "__main__":
    unittest.main()