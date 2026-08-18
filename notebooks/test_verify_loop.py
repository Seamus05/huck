import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_loop

OK_EVIDENCE = {
    "ok": True,
    "marker": "loop-proof test abc123 2026-01-01T00:00:00+00:00",
    "write_id": "w1",
    "read_id": "w1",
    "match": True,
    "results": 1,
    "tag": "loop-proof",
    "archive": "default",
    "steps": {"write": "ok", "read": "ok"},
    "retried": False,
}

BAD_EVIDENCE = {
    **OK_EVIDENCE,
    "ok": False,
    "match": False,
    "write_id": None,
    "steps": {"write": "failed", "read": "skipped"},
}


class TestRenderProof(unittest.TestCase):
    def test_ok_renders_verified(self):
        out = verify_loop.render_proof(OK_EVIDENCE)
        self.assertIn("LOOP VERIFIED", out)
        self.assertIn("w1", out)

    def test_bad_renders_broken(self):
        out = verify_loop.render_proof(BAD_EVIDENCE)
        self.assertIn("LOOP BROKEN", out)

    def test_empty_evidence_does_not_crash(self):
        out = verify_loop.render_proof({})
        self.assertIn("RESULT", out)


class TestMain(unittest.TestCase):
    def test_ok_returns_zero_and_prints(self):
        buf = io.StringIO()
        with mock.patch.object(verify_loop.ds, "roundtrip", return_value=OK_EVIDENCE):
            with redirect_stdout(buf):
                code = verify_loop.main(["--no-save"])
        self.assertEqual(code, 0)
        self.assertIn("LOOP VERIFIED", buf.getvalue())

    def test_bad_returns_one(self):
        buf = io.StringIO()
        with mock.patch.object(verify_loop.ds, "roundtrip", return_value=BAD_EVIDENCE):
            with redirect_stdout(buf):
                code = verify_loop.main(["--no-save"])
        self.assertEqual(code, 1)
        self.assertIn("LOOP BROKEN", buf.getvalue())

    def test_save_writes_evidence_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_state = verify_loop.STATE_DIR
            old_file = verify_loop.PROOF_FILE
            verify_loop.STATE_DIR = tmp
            verify_loop.PROOF_FILE = os.path.join(tmp, "loop-proof.json")
            try:
                buf = io.StringIO()
                with mock.patch.object(verify_loop.ds, "roundtrip", return_value=OK_EVIDENCE):
                    with redirect_stdout(buf):
                        code = verify_loop.main([])
                self.assertEqual(code, 0)
                self.assertTrue(os.path.exists(verify_loop.PROOF_FILE))
                with open(verify_loop.PROOF_FILE) as f:
                    saved = json.load(f)
                self.assertTrue(saved["ok"])
                self.assertIn("saved_at", saved)
                self.assertEqual(saved["write_id"], "w1")
            finally:
                verify_loop.STATE_DIR = old_state
                verify_loop.PROOF_FILE = old_file

    def test_no_save_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_state = verify_loop.STATE_DIR
            old_file = verify_loop.PROOF_FILE
            verify_loop.STATE_DIR = tmp
            verify_loop.PROOF_FILE = os.path.join(tmp, "loop-proof.json")
            try:
                buf = io.StringIO()
                with mock.patch.object(verify_loop.ds, "roundtrip", return_value=OK_EVIDENCE):
                    with redirect_stdout(buf):
                        code = verify_loop.main(["--no-save"])
                self.assertEqual(code, 0)
                self.assertFalse(os.path.exists(verify_loop.PROOF_FILE))
            finally:
                verify_loop.STATE_DIR = old_state
                verify_loop.PROOF_FILE = old_file


if __name__ == "__main__":
    unittest.main()
