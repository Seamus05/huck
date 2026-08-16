"""check — drift scanner for Huck's self-sustaining loop.

Runs the test suite, checks docs-vs-filesystem consistency, verifies
Mnemosyne connectivity, and queries for unresolved work. Writes a
structured report to state/check.json and exits with a status code:

  0 — all clear
  1 — drift detected (docs or code out of sync)
  2 — failure (tests failing, Mnemosyne unreachable)
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(REPO_ROOT, "state")
CHECK_FILE = os.path.join(STATE_DIR, "check.json")
NOW = datetime.now(timezone.utc).isoformat()


def _load_previous() -> dict | None:
    try:
        with open(CHECK_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_report(report: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(CHECK_FILE, "w") as f:
        json.dump(report, f, indent=2)


def check_tests() -> dict:
    test_file = os.path.join(REPO_ROOT, "notebooks", "test_ds.py")
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=30,
        )
        passed = result.returncode == 0
        return {
            "passed": passed,
            "exit_code": result.returncode,
            "output": result.stdout[-2000:],
            "stderr": result.stderr[-500:] if result.stderr else None,
        }
    except Exception as e:
        return {"passed": False, "error": str(e)}


def check_mnemosyne() -> dict:
    try:
        url = f"{ds.MEMORY_URL}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return {"reachable": True, "status": data.get("status", "unknown")}
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def check_readme_tree() -> dict:
    readme_path = os.path.join(REPO_ROOT, "README.md")
    if not os.path.exists(readme_path):
        return {"error": "README.md not found"}

    with open(readme_path) as f:
        lines = f.readlines()

    # Extract files mentioned in the layout tree
    in_tree = False
    tree_files = set()
    for line in lines:
        if line.strip() == "```" and in_tree:
            break
        if in_tree:
            # Extract filename from tree drawing chars
            cleaned = line.replace("├──", "").replace("└──", "").replace("│", "").strip()
            if cleaned and not cleaned.endswith("/"):
                # Split on # to remove comments
                name = cleaned.split("#")[0].strip()
                tree_files.add(name)
        if line.strip().startswith("```") and "huck/" in lines[lines.index(line) - 1] if lines.index(line) > 0 else False:
            in_tree = True
        # Simpler: detect the start of the tree block
        if line.strip() == "```" and any(
            l.strip().startswith("huck/") for l in lines[max(0, lines.index(line) - 3) : lines.index(line)]
        ):
            in_tree = True

    # Parse the tree block with directory nesting
    tree_chars = {"│", "├", "└", "─", " "}

    def _tree_indent(raw_line: str) -> int:
        n = 0
        for ch in raw_line:
            if ch in tree_chars:
                n += 1
            else:
                break
        return n // 4

    in_tree = False
    tree_files = set()
    dir_prefixes = {}

    for i, line in enumerate(lines):
        if "## Layout" in line:
            for j in range(i, min(i + 20, len(lines))):
                raw = lines[j]
                stripped = raw.strip()
                if stripped == "```" and not in_tree:
                    in_tree = True
                    continue
                if stripped == "```" and in_tree:
                    break
                if not in_tree:
                    continue

                if not any(c in raw for c in ("├──", "└──")):
                    continue

                name = stripped.lstrip("├──└──│ ").strip()
                if "#" in name:
                    name = name.split("#")[0].strip()

                if not name:
                    continue

                level = _tree_indent(raw)

                if name.endswith("/"):
                    dir_prefixes[level] = name
                    continue

                path = ""
                for d in range(level):
                    prefix = dir_prefixes.get(d, "")
                    if prefix:
                        path += prefix
                path += name
                tree_files.add(path)

    # Get actual tracked files
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, timeout=10,
            cwd=REPO_ROOT,
        )
        actual_files = set(
            f for f in result.stdout.strip().split("\n") if f
        )
    except Exception:
        actual_files = set()

    # Get new untracked files (exclude git-ignored)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True, text=True, timeout=10,
            cwd=REPO_ROOT,
        )
        untracked = set(f for f in result.stdout.strip().split("\n") if f)
    except Exception:
        untracked = set()

    all_on_disk = actual_files | untracked
    missing_from_tree = actual_files - tree_files
    stale_in_tree = tree_files - all_on_disk

    return {
        "tree_files": sorted(tree_files),
        "actual_files": sorted(actual_files),
        "all_on_disk": sorted(all_on_disk),
        "missing_from_tree": sorted(missing_from_tree) if missing_from_tree else [],
        "stale_in_tree": sorted(stale_in_tree) if stale_in_tree else [],
        "untracked": sorted(untracked),
        "drift": bool(missing_from_tree or stale_in_tree),
    }


def check_unresolved() -> dict:
    try:
        results = ds.query(
            "unresolved todo gap missing deferred",
            limit=10,
            min_q=0.4,
            order_by="recency",
        )
        items = []
        for r in results:
            text = r.get("text", "")
            lower = text.lower()
            if not any(kw in lower for kw in ["unresolved", "deferred", "todo", "gap"]):
                continue
            tags = r.get("tags", [])
            if "self-check" in tags:
                continue
            if "huck check found" in lower:
                continue
            if "check.py" in r.get("metadata", {}).get("source_file", ""):
                continue
            meta_tags = {"documentation", "infrastructure", "persona", "readme", "test", "quality", "configuration"}
            if meta_tags & set(tags):
                continue
            items.append({
                "id": r.get("id", "")[:8],
                "tags": r.get("tags", []),
                "snippet": text[:200],
            })
        return {"count": len(items), "items": items}
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=== Huck check ===")
    print(f"  time: {NOW}")
    print()

    report = {"time": NOW, "checks": {}}

    # 1. Tests
    print("─ tests ─")
    tests = check_tests()
    report["checks"]["tests"] = tests
    print(f"  {'PASS' if tests.get('passed') else 'FAIL'}")

    # 2. Mnemosyne
    print("─ mnemosyne ─")
    mnemo = check_mnemosyne()
    report["checks"]["mnemosyne"] = mnemo
    print(f"  {'reachable' if mnemo.get('reachable') else 'UNREACHABLE — ' + mnemo.get('error', 'unknown')}")

    # 3. README tree
    print("─ readme tree ─")
    tree = check_readme_tree()
    report["checks"]["readme_tree"] = tree
    if tree.get("drift"):
        print(f"  DRIFT — missing: {tree.get('missing_from_tree')}, stale: {tree.get('stale_in_tree')}")
    else:
        print("  clean")

    # 4. Unresolved items
    print("─ unresolved ─")
    unresolved = check_unresolved()
    report["checks"]["unresolved"] = unresolved
    if unresolved.get("error"):
        print(f"  error: {unresolved['error']}")
    else:
        print(f"  {unresolved['count']} items")

    # Determine exit code
    report["exit_code"] = 0
    if not tests.get("passed") or not mnemo.get("reachable"):
        report["exit_code"] = 2
    elif tree.get("drift") or unresolved.get("count", 0) > 0:
        report["exit_code"] = 1

    # Compare to previous
    prev = _load_previous()
    changed = True
    if prev:
        prev_exit = prev.get("exit_code", -1)
        if prev_exit == report["exit_code"]:
            # Same severity — check if details changed
            changed = json.dumps(report["checks"], sort_keys=True) != json.dumps(
                prev.get("checks", {}), sort_keys=True
            )

    report["changed_since_last"] = changed
    _save_report(report)

    # Chronicle if something changed
    if changed and report["exit_code"] > 0:
        summary_parts = []
        if not tests.get("passed"):
            summary_parts.append(f"tests failing (exit {tests.get('exit_code')})")
        if not mnemo.get("reachable"):
            summary_parts.append(f"Mnemosyne unreachable: {mnemo.get('error')}")
        if tree.get("drift"):
            summary_parts.append(
                f"README drift — missing: {tree.get('missing_from_tree')}, stale: {tree.get('stale_in_tree')}"
            )
        if unresolved.get("count", 0) > 0:
            summary_parts.append(f"{unresolved['count']} unresolved items in memory")

        summary = "Huck check found issues: " + "; ".join(summary_parts) + "."
        try:
            ds.chronicle(
                summary,
                tags=["huck", "check", "drift", "self-check"],
                q_value=0.6,
                metadata={"source_file": "huck/notebooks/check.py"},
            )
        except Exception:
            pass

    print(f"\nexit: {report['exit_code']} {'(changed)' if changed else '(unchanged)'}")
    sys.exit(report["exit_code"])


if __name__ == "__main__":
    main()
