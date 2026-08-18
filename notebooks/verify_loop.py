#!/usr/bin/env python3
"""verify_loop — prove the isolated-agent loop end-to-end (write → read → match).

Runs ds.roundtrip(): writes a unique marker passage to Mnemosyne, reads it
back through the real semantic-search path, and verifies the same passage id
round-trips. Prints a human-readable proof and writes machine-readable
evidence to state/loop-proof.json.

DELIBERATE — NOT timer-driven. Each run writes ONE marker passage to the
'default' archive (tags: huck, loop-proof). Run it when you want to
demonstrate or record that the loop works:

    python3 notebooks/verify_loop.py             # run + print + save evidence
    python3 notebooks/verify_loop.py --no-save   # run + print only
    python3 notebooks/verify_loop.py --tag weekly

Exit code 0 on a matched round-trip; 1 when the write or read failed.

Part of the isolated-agent pattern proof (Seamus05/Lab#1, Track B): an agent
that can verify its own memory loop is an agent that works independently,
end-to-end — at the memory layer, at least.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(REPO_ROOT, "state")
PROOF_FILE = os.path.join(STATE_DIR, "loop-proof.json")


def render_proof(evidence: dict) -> str:
    """Human-readable proof from the roundtrip evidence dict."""
    lines = [
        "=== Isolated-agent loop proof (write -> read -> match) ===",
        "",
        f"  marker : {evidence.get('marker', '?')}",
        f"  archive: {evidence.get('archive', '?')}",
        f"  write  : {evidence.get('write_id') or '(failed)'}",
        f"  read   : {evidence.get('read_id') or '(none)'}",
        f"  results: {evidence.get('results', 0)} passage(s) matched",
        f"  match  : {evidence.get('match', False)}",
        f"  steps  : {evidence.get('steps', {})}",
    ]
    if evidence.get("retried"):
        lines.append("  note   : first read was empty; one quiet retry succeeded")
    lines.append("")
    if evidence.get("ok"):
        lines.append("  RESULT : LOOP VERIFIED — the passage this agent wrote was")
        lines.append("           found again by query. Write -> read -> match works.")
    else:
        lines.append("  RESULT : LOOP BROKEN — see steps above.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="print the proof but do not write state/loop-proof.json",
    )
    parser.add_argument(
        "--tag",
        default="loop-proof",
        help="marker tag (default: loop-proof)",
    )
    parser.add_argument(
        "--archive",
        default=ds.DEFAULT_ARCHIVE,
        help="archive to write to and read from (default: default)",
    )
    args = parser.parse_args(argv)

    evidence = ds.roundtrip(tag=args.tag, archive_id=args.archive)
    print(render_proof(evidence))

    if not args.no_save:
        os.makedirs(STATE_DIR, exist_ok=True)
        evidence = dict(evidence)
        evidence["saved_at"] = datetime.now(timezone.utc).isoformat()
        with open(PROOF_FILE, "w") as f:
            json.dump(evidence, f, indent=2)
        print(f"  evidence: {PROOF_FILE}")

    return 0 if evidence.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
