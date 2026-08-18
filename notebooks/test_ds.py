import unittest
import sys
import os
import json
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


def _mock_http_open(mock_open):
    """Patch urllib.request.urlopen so tests never touch the real Mnemosyne DB.

    ds.query() and ds.chronicle() make HTTP calls via urllib.request.urlopen.
    Without mocking, running the test suite WRITES to the shared memory DB
    (chronicle) and issues live queries — which, run every 5 min by huck-check,
    flooded the archive with thousands of q=0.01 test passages (Aug 2026 purge).

    This returns a fake response object whose .read() yields a JSON body the
    calling function expects. We route by URL path: /archival-memory returns a
    passage list (for query), and anything else returns a created passage (for
    chronicle).
    """

    class FakeResp:
        def __init__(self, body_bytes):
            self._b = body_bytes

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/archival-memory" in url and ("query=" in url or url.rstrip("/").endswith("/archival-memory")):
            if "query=" in url:
                body = json.dumps({"passages": [{"id": "mock-1", "text": "mock result", "tags": ["mock"], "q_value": 0.9}]}).encode()
            else:
                # chronicle POST returns the created passage
                body = json.dumps({"id": "mock-created", "text": "mock", "created_at": "2026-01-01T00:00:00Z"}).encode()
            return FakeResp(body)
        # fallback: generic created-passage shape for unknown write endpoints
        body = json.dumps({"id": "mock-created", "text": "mock", "created_at": "2026-01-01T00:00:00Z"}).encode()
        return FakeResp(body)

    mock_open.side_effect = fake_open


def _FakeResp(body_bytes):
    class FakeResp:
        def __init__(self, body_bytes):
            self._b = body_bytes

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return FakeResp(body_bytes)


def _mock_roundtrip_http_open(mock_open):
    """Stateful fake for ds.roundtrip: writes return id 'rt-abc123', reads return it."""

    def fake_open(req, *a, **k):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "query=" in url:
            body = json.dumps({"passages": [{
                "id": "rt-abc123",
                "text": "loop-proof marker",
                "tags": ["huck", "loop-proof"],
                "q_value": 0.9,
            }]}).encode()
        else:
            body = json.dumps({
                "id": "rt-abc123",
                "text": "loop-proof marker",
                "created_at": "2026-01-01T00:00:00Z",
            }).encode()
        return _FakeResp(body)

    mock_open.side_effect = fake_open


class IsolatedTest(unittest.TestCase):
    """Base class: mock the network so tests never touch the real Mnemosyne DB.

    Without this, running the suite writes q=0.01 debris to shared memory and
    issues live queries. huck-check runs this every 5 min, which is what flooded
    the archive (2,224 debris passages purged 2026-08-18).
    """

    def setUp(self):
        patcher = mock.patch.object(ds.urllib.request, "urlopen", autospec=True)
        self._urlopen_mock = patcher.start()
        self.addCleanup(patcher.stop)
        _mock_http_open(self._urlopen_mock)


class TestContentHash(IsolatedTest):
    def test_deterministic(self):
        self.assertEqual(ds.content_hash("hello"), ds.content_hash("hello"))

    def test_different_inputs(self):
        self.assertNotEqual(ds.content_hash("hello"), ds.content_hash("world"))

    def test_known_vector(self):
        self.assertEqual(
            ds.content_hash("hello"),
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        )

    def test_empty_string(self):
        h = ds.content_hash("")
        self.assertEqual(len(h), 64)
        self.assertEqual(h, ds.content_hash(""))


class TestQuery(IsolatedTest):
    def test_empty_query_returns_empty(self):
        self.assertEqual(ds.query(""), [])

    def test_whitespace_query_returns_empty(self):
        self.assertEqual(ds.query("   "), [])

    def test_normal_query_returns_results(self):
        results = ds.query("huck", limit=3)
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("id", r)
            self.assertIn("text", r)

    def test_limit_respected(self):
        results = ds.query("huck", limit=2)
        self.assertLessEqual(len(results), 2)

    def test_negative_limit_clamped(self):
        results = ds.query("huck", limit=-1)
        self.assertIsInstance(results, list)

    def test_no_results_for_nonsense(self):
        results = ds.query("xyzkwtxabcdefwhocares123", limit=1)
        self.assertIsInstance(results, list)


class TestLearn(IsolatedTest):
    def test_empty_query_returns_empty_shape(self):
        result = ds.learn("")
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["agents"], [])
        self.assertEqual(result["top_tags"], [])
        self.assertEqual(result["passages"], [])

    def test_whitespace_query_returns_empty(self):
        result = ds.learn("   ")
        self.assertEqual(result["count"], 0)

    def test_normal_query_returns_pattern_dict(self):
        result = ds.learn("session", limit=10)
        self.assertIn("count", result)
        self.assertIn("agents", result)
        self.assertIn("top_tags", result)
        self.assertIn("passages", result)
        self.assertIsInstance(result["agents"], list)
        self.assertIsInstance(result["top_tags"], list)
        for p in result["passages"]:
            self.assertIn("id", p)
            self.assertIn("text", p)

    def test_agent_filter_restricts_results(self):
        result = ds.learn("session", limit=30, agents=["phaedrus"])
        for p in result["passages"]:
            tags = [t.lower() for t in p["tags"]]
            self.assertTrue(any(t.startswith("agent:phaedrus") for t in tags))

    def test_negative_top_tags_clamped(self):
        result = ds.learn("session", limit=5, top_tags=-1)
        self.assertIsInstance(result["top_tags"], list)


class TestExists(IsolatedTest):
    def test_known_file(self):
        results = ds.exists("huck/notebooks/ds.py")
        self.assertIsInstance(results, list)

    def test_unknown_file(self):
        results = ds.exists("huck/notebooks/nonexistent.py")
        self.assertEqual(results, [])


class TestChronicle(IsolatedTest):
    def test_write_and_verify(self):
        text = "ds.py unit test passage — auto-generated, safe to drop."
        result = ds.chronicle(
            text,
            tags=["test", "huck", "unit-test"],
            q_value=0.01,
            metadata={"source_file": "huck/notebooks/test_ds.py"},
        )
        self.assertIn("id", result)

    def test_with_tags(self):
        result = ds.chronicle(
            "tagged test",
            tags=["test", "huck"],
            q_value=0.01,
        )
        self.assertIn("id", result)

    def test_without_tags(self):
        result = ds.chronicle(
            "untagged test",
            q_value=0.01,
        )
        self.assertIn("id", result)

    def test_with_metadata(self):
        result = ds.chronicle(
            "metadata test",
            tags=["test", "huck"],
            q_value=0.01,
            metadata={"source_file": "huck/notebooks/test_ds.py", "test": True},
        )
        self.assertIn("id", result)


class TestQueryTracked(IsolatedTest):
    """ds.query must forward `tracked` to the service.

    Discovered during the loop-proof build: the Python port accepted a
    `tracked` parameter but never sent it, so every query silently bumped
    survival counters. Fixed in _query_archive.
    """

    def _urls(self):
        return [
            call.args[0] if call.args else ""
            for call in self._urlopen_mock.call_args_list
        ]

    def test_tracked_false_forwarded(self):
        ds.query("huck", limit=1, min_q=0.0, tracked=False)
        urls = self._urls()
        self.assertTrue(urls)
        self.assertTrue(all("tracked=false" in u for u in urls))

    def test_tracked_true_default_forwarded(self):
        ds.query("huck", limit=1, min_q=0.0)
        urls = self._urls()
        self.assertTrue(urls)
        self.assertTrue(all("tracked=true" in u for u in urls))


class TestRoundtrip(unittest.TestCase):
    """ds.roundtrip() with a mocked network — never touches real Mnemosyne.

    The whole point of the roundtrip proof is that an isolated agent can
    write a marker and read the SAME passage back. These tests verify the
    logic against a fake service, so the real proof run can be saved as
    evidence instead of being polluted by the test suite.
    """

    def setUp(self):
        patcher = mock.patch.object(ds.urllib.request, "urlopen", autospec=True)
        self._urlopen_mock = patcher.start()
        self.addCleanup(patcher.stop)
        _mock_roundtrip_http_open(self._urlopen_mock)

    def test_matching_roundtrip(self):
        ev = ds.roundtrip()
        self.assertTrue(ev["ok"])
        self.assertTrue(ev["match"])
        self.assertEqual(ev["write_id"], "rt-abc123")
        self.assertEqual(ev["read_id"], "rt-abc123")
        self.assertGreaterEqual(ev["results"], 1)
        self.assertEqual(ev["steps"]["write"], "ok")
        self.assertEqual(ev["steps"]["read"], "ok")
        self.assertIn("loop-proof", ev["marker"])
        self.assertFalse(ev["retried"])

    def test_custom_tag_in_marker(self):
        ev = ds.roundtrip(tag="weekly")
        self.assertIn("weekly", ev["marker"])
        self.assertIn("weekly", ev["tag"])

    def test_write_failure_returns_failed_evidence(self):
        self._urlopen_mock.side_effect = OSError("service down")
        ev = ds.roundtrip()
        self.assertFalse(ev["ok"])
        self.assertFalse(ev["match"])
        self.assertIsNone(ev["write_id"])
        self.assertEqual(ev["steps"]["write"], "failed")
        self.assertEqual(ev["steps"]["read"], "skipped")

    def test_read_mismatch_not_ok(self):
        def fake(req, *a, **k):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "query=" in url:
                body = json.dumps({"passages": [{
                    "id": "other-id", "text": "x", "q_value": 0.9,
                }]}).encode()
            else:
                body = json.dumps({
                    "id": "rt-abc123", "created_at": "2026-01-01T00:00:00Z",
                }).encode()
            return _FakeResp(body)

        self._urlopen_mock.side_effect = fake
        ev = ds.roundtrip(retries=0)
        self.assertFalse(ev["ok"])
        self.assertFalse(ev["match"])
        self.assertEqual(ev["steps"]["read"], "ok")  # read found something, just not ours
        self.assertEqual(ev["read_id"], "other-id")

    def test_empty_read_not_ok(self):
        def fake(req, *a, **k):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "query=" in url:
                body = json.dumps({"passages": []}).encode()
            else:
                body = json.dumps({
                    "id": "rt-abc123", "created_at": "2026-01-01T00:00:00Z",
                }).encode()
            return _FakeResp(body)

        self._urlopen_mock.side_effect = fake
        ev = ds.roundtrip(retries=0)
        self.assertFalse(ev["ok"])
        self.assertEqual(ev["steps"]["read"], "empty")
        self.assertEqual(ev["results"], 0)


if __name__ == "__main__":
    unittest.main()
