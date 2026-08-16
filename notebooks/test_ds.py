import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


class TestContentHash(unittest.TestCase):
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


class TestQuery(unittest.TestCase):
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


class TestExists(unittest.TestCase):
    def test_known_file(self):
        results = ds.exists("huck/notebooks/ds.py")
        self.assertIsInstance(results, list)

    def test_unknown_file(self):
        results = ds.exists("huck/notebooks/nonexistent.py")
        self.assertEqual(results, [])


class TestChronicle(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
