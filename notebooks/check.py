"""check — drift scanner for Huck's self-sustaining loop.

Runs the test suite, checks docs-vs-filesystem consistency, verifies
Mnemosyne connectivity, and queries for unresolved work. Writes a
structured report to state/check.json plus a self-updating health
dashboard (state/health.json + state/dashboard.md) and exits with a
status code:

  0 — all clear
  1 — drift detected (docs or code out of sync)
  2 — failure (tests failing, Mnemosyne unreachable)
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DIR = os.path.join(REPO_ROOT, "state")
CHECK_FILE = os.path.join(STATE_DIR, "check.json")
HEALTH_FILE = os.path.join(STATE_DIR, "health.json")
DASHBOARD_FILE = os.path.join(STATE_DIR, "dashboard.md")
HISTORY_LIMIT = 200
TRACKER_REPO = "Seamus05/Lab"
NOW = datetime.now(timezone.utc).isoformat()

# ---- unresolved-item decision vocabulary (see _is_unresolved) ----

# A passage must mention one of these to be a candidate at all.
BASE_SIGNALS = [
    "unresolved", "deferred", "todo", "gap", "build", "bridge", "growth",
]

# Explicit action-to-do phrasing. Seeds tagged next-session/seed are exempt.
ACTION_SIGNALS = [
    "unresolved", "deferred", "todo", "gap", "remaining",
    "can you build", "to build", "pick one", "growth seed",
    "next huck should", "next-session",
]

# Completion tags: records of work done, not seeds of work to do.
COMPLETION_TAGS = {
    "survey", "discovery", "lineage", "episode", "milestone",
    "decision", "isolation-proof", "first-contact", "completion",
}

# Text-structure markers of completion chronicles. Added 2026-08-18 after
# six untagged episode chronicles surfaced as false unresolved items —
# chronicles don't always carry completion tags, but they do carry shape.
COMPLETION_TEXT_MARKERS = (
    "## episode:",
    "## alignment signal:",
    "### what was asked",
    "### what was done",
    "### outcome",
    "### result",
    "### approach",
    "### milestone",
    "### central thesis",
    "### source",
    "### context",
)

# Past-tense openings: "Created X and integrated Y" is a record, not a seed.
# "Build X" (imperative) is how a seed talks — but "Built X" (past tense) is
# a completion record: "Built the learn() cross-agent bridge" is work done,
# not work to do. The two are distinguishable by the trailing 't', so "built "
# belongs in the openers while "build " stays out.
COMPLETION_OPENERS = (
    "created ", "wrote ", "implemented ", "updated ",
    "integrated ", "moved ", "added ", "built ",
)


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
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "discover",
             "-s", os.path.join(REPO_ROOT, "notebooks"), "-p", "test_*.py"],
            capture_output=True,
            text=True,
            timeout=60,
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
    """Verify Mnemosyne is reachable AND the read path of the loop works.

    /health proves the service answers. A read-side probe (no writes,
    tracked=False) proves the semantic-search path an isolated agent depends
    on actually returns passages. A loop that can write but not read is a
    loop that can't learn from its own past — that's a broken pattern, so a
    failed read probe is treated the same as an unreachable service.
    """
    try:
        url = f"{ds.MEMORY_URL}/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            health = {"reachable": True, "status": data.get("status", "unknown")}
    except Exception as e:
        health = {"reachable": False, "error": str(e)}

    read = {"ok": False, "results": 0}
    if health.get("reachable"):
        try:
            # No writes — this runs every 5 minutes. tracked=False so the
            # probe never bumps survival counters.
            results = ds.query("system healthy", limit=1, min_q=0.0, tracked=False)
            read = {"ok": len(results) > 0, "results": len(results)}
            if not read["ok"]:
                read["error"] = (
                    "read probe returned 0 passages (search path may be broken)"
                )
        except Exception as e:
            read = {"ok": False, "error": str(e)}

    result = {
        "reachable": bool(health.get("reachable") and read["ok"]),
        "status": health.get("status", "unknown"),
        "read": read,
    }
    if health.get("error"):
        result["error"] = health["error"]
    return result


def check_agent_config() -> dict:
    """Verify the repo can instantiate its own agent (isolated-agent seed).

    The isolated-agent pattern's claim is that a fresh checkout IS the agent
    seed — it must carry its own identity, not depend on ambient global
    config. So .opencode/opencode.json (the huck agent definition: model,
    permissions, description) is committed to the repo, and this check fails
    if it goes missing or stops defining huck.

    Deliberately loose about model strings: the model name may legitimately
    differ per host. What must NOT differ is the agent's existence.
    """
    try:
        with open(os.path.join(REPO_ROOT, ".opencode", "opencode.json")) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {
            "ok": False,
            "error": ".opencode/opencode.json missing — the repo no longer carries its agent definition",
        }
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f".opencode/opencode.json not valid JSON: {e}"}

    agent = (data.get("agent") or {}).get("huck")
    if not isinstance(agent, dict):
        return {"ok": False, "error": "no agent.huck definition in .opencode/opencode.json"}
    if "description" not in agent or "permission" not in agent:
        return {"ok": False, "error": "agent.huck must define description and permission"}
    return {"ok": True}


def check_readme_tree() -> dict:
    readme_path = os.path.join(REPO_ROOT, "README.md")
    if not os.path.exists(readme_path):
        return {"error": "README.md not found"}

    with open(readme_path) as f:
        lines = f.readlines()

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
            # Scan the whole fenced block, not a fixed 20-line window.
            # The window broke when the README tree grew past 20 lines
            # (exposed 2026-08-18 by adding .opencode/tools/query-memory.ts).
            for j in range(i, len(lines)):
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


def _is_completion_record(lower: str, tags: set) -> bool:
    """Is this passage a record of work done, not a seed of work to do?

    Completion chronicles (episodes, alignment signals, status reports) are
    usually tagged with completion markers, but not always — discovered
    2026-08-18 when six untagged episode chronicles surfaced as false
    unresolved items. So records are detected by TAG and by TEXT STRUCTURE:
    episode/signal headers, work-report section markers, and past-tense
    openings that seeds (imperative prose) don't use.
    """
    if COMPLETION_TAGS & tags:
        return True
    if lower.startswith(COMPLETION_OPENERS):
        return True
    return any(m in lower for m in COMPLETION_TEXT_MARKERS)


def _is_unresolved(r: dict, resolved: set) -> bool:
    """Decide whether a passage is unresolved work for Huck.

    Pure decision logic — unit-testable without the network. A passage is
    unresolved only when it is a seed of work to do, not a record of work
    done. Records are completion chronicles (episodes, signals, status
    reports), detected by tag AND text structure, because chronicles don't
    always carry completion tags.
    """
    pid = r.get("id", "")
    if pid in resolved or pid[:8] in resolved:
        return False
    text = r.get("text", "")
    lower = text.lower()
    if not any(kw in lower for kw in BASE_SIGNALS):
        return False
    tags = set(r.get("tags", []))
    if "self-check" in tags:
        return False
    if "opencode_session" in tags:
        return False
    if "resolved" in tags:
        return False
    if "huck check" in lower:
        return False
    if "check.py" in ds.passage_metadata(r).get("source_file", ""):
        return False
    meta_tags = {"documentation", "infrastructure", "persona", "readme", "test", "quality", "configuration"}
    if meta_tags & tags:
        return False
    # A passage that only mentions build/bridge/growth in passing is a
    # chronicle of work done, not a seed of work to do. Require an action
    # signal unless explicitly tagged for the next session.
    if "next-session" not in tags and "seed" not in tags:
        if _is_completion_record(lower, tags):
            return False
        if not any(sig in lower for sig in ACTION_SIGNALS):
            return False
        # Completion chronicles are records, not unresolved items — but a
        # passage that is itself tagged next-session still counts.
        if COMPLETION_TAGS & tags:
            return False
    return True


def check_unresolved() -> dict:
    try:
        # Similarity ordering (not recency) so recent self-check passages
        # don't flood the window. Query text targets growth/work vocabulary
        # that self-reports don't contain.
        results = ds.query(
            "growth seed bridges to build cross-agent learn capability expansion",
            limit=60,
            min_q=0.5,
            order_by="similarity",
        )
        # Passages recorded as addressed in a prior Huck session (state/resolved.json)
        # or explicitly tagged resolved no longer count as open work.
        resolved = set(ds.resolved_ids())
        items = []
        for r in results:
            if not _is_unresolved(r, resolved):
                continue
            items.append({
                "id": r.get("id", "")[:8],
                "tags": sorted(r.get("tags", [])),
                "snippet": r.get("text", "")[:200],
            })
        return {"count": len(items), "items": items}
    except Exception as e:
        return {"error": str(e)}


def check_tracker() -> dict:
    """Bridge to the Seamus05/Lab#1 Wayfinder tracker (growth seed bridge 1).

    Lists open wayfinder issues via the gh CLI. Informational only — the
    tracker lives outside this repo's scope, so reachability or open-count
    never flips the exit code. Falls back gracefully when gh is missing or
    the network is down.
    """
    try:
        result = subprocess.run(
            [
                "gh", "issue", "list", "-R", TRACKER_REPO,
                "--state", "open", "--limit", "50",
                "--json", "number,title,labels",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {
                "reachable": False,
                "error": (result.stderr or result.stdout).strip()[:300],
            }
        issues = json.loads(result.stdout or "[]")
        return {
            "reachable": True,
            "repo": TRACKER_REPO,
            "open_count": len(issues),
            "issues": [
                {
                    "number": i.get("number"),
                    "title": i.get("title", ""),
                    "labels": [l.get("name", "") for l in i.get("labels", [])],
                }
                for i in issues
            ],
        }
    except Exception as e:
        return {"reachable": False, "error": str(e)}


def _load_health_history() -> list[dict]:
    """Read previous health entries from state/health.json (if any)."""
    try:
        with open(HEALTH_FILE) as f:
            data = json.load(f)
            return data.get("history", []) if isinstance(data, dict) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_health(history: list[dict]) -> None:
    """Persist health history (capped) to state/health.json."""
    os.makedirs(STATE_DIR, exist_ok=True)
    trimmed = history[-HISTORY_LIMIT:]
    with open(HEALTH_FILE, "w") as f:
        json.dump({"history": trimmed}, f, indent=2)


def render_dashboard(entry: dict, history: list[dict]) -> str:
    """Render a human-readable markdown dashboard from a health entry.

    Pure function — easy to unit test without touching the filesystem.
    """
    lines = [
        "# Huck health dashboard",
        "",
        f"_Generated {entry.get('time', '?')} by check.py_",
        "",
        "## Current",
        "",
        f"- Tests: {'PASS' if entry.get('tests_passed') else 'FAIL'}",
        f"- Mnemosyne: {'reachable' if entry.get('mnemo_reachable') else 'UNREACHABLE'}",
        f"- README tree: {'clean' if not entry.get('tree_drift') else 'DRIFT'}",
        f"- Unresolved items in memory: {entry.get('unresolved_count', 0)}",
    ]
    if entry.get("tracker_reachable"):
        lines.append(
            f"- Tracker ({entry.get('tracker_repo', '?')}): "
            f"{entry.get('tracker_open', '?')} open issues"
        )
    else:
        lines.append("- Tracker: unreachable")
    lines += [
        "",
        "## Trend (last {} runs)".format(min(len(history), 10)),
        "",
        "| time | exit | tests | mnemo | tree | unresolved | tracker |",
        "|---|---|---|---|---|---|---|",
    ]
    for h in history[-10:]:
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} |".format(
                (h.get("time") or "?")[:19],
                h.get("exit_code", "?"),
                "P" if h.get("tests_passed") else "F",
                "Y" if h.get("mnemo_reachable") else "N",
                "C" if not h.get("tree_drift") else "D",
                h.get("unresolved_count", "?"),
                h.get("tracker_open", "?") if h.get("tracker_reachable") else "-",
            )
        )
    return "\n".join(lines) + "\n"


def write_dashboard(entry: dict, history: list[dict]) -> None:
    """Persist the health entry + history, and render dashboard.md."""
    os.makedirs(STATE_DIR, exist_ok=True)
    updated = history + [entry]
    _save_health(updated)
    with open(DASHBOARD_FILE, "w") as f:
        f.write(render_dashboard(entry, updated))


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

    # 3b. Agent seed — the repo must carry its own agent definition
    print("─ agent config ─")
    agent_cfg = check_agent_config()
    report["checks"]["agent_config"] = agent_cfg
    if agent_cfg.get("ok"):
        print("  ok — .opencode/opencode.json defines agent.huck")
    else:
        print(f"  DRIFT — {agent_cfg.get('error', 'unknown')}")

    # 4. Unresolved items
    print("─ unresolved ─")
    unresolved = check_unresolved()
    report["checks"]["unresolved"] = unresolved
    if unresolved.get("error"):
        print(f"  error: {unresolved['error']}")
    else:
        print(f"  {unresolved['count']} items")

    # 5. Tracker bridge (informational — never flips exit code)
    print("─ tracker ─")
    tracker = check_tracker()
    report["checks"]["tracker"] = tracker
    if tracker.get("reachable"):
        print(f"  {tracker.get('open_count')} open issues in {TRACKER_REPO}")
        for issue in tracker.get("issues", [])[:5]:
            print(f"    #{issue['number']} {issue['title']}")
    else:
        print(f"  unreachable — {tracker.get('error', 'unknown')}")

    # Determine exit code
    report["exit_code"] = 0
    if not tests.get("passed") or not mnemo.get("reachable"):
        report["exit_code"] = 2
    elif (tree.get("drift") or agent_cfg.get("ok") is False
          or unresolved.get("count", 0) > 0):
        report["exit_code"] = 1

    # Compute a stable fingerprint of non-volatile findings
    fingerprint = {
        "exit_code": report["exit_code"],
        "tests_passed": tests.get("passed"),
        "mnemo_reachable": mnemo.get("reachable"),
        "tree_drift": tree.get("drift"),
        "tree_missing": tree.get("missing_from_tree"),
        "tree_stale": tree.get("stale_in_tree"),
        "agent_config_ok": agent_cfg.get("ok"),
        "unresolved_count": unresolved.get("count", 0),
    }

    prev = _load_previous()
    prev_exit = prev.get("exit_code", -1) if prev else -1
    transition = prev_exit != report["exit_code"]

    prev_fingerprint = prev.get("fingerprint") if prev else None
    detail_changed = prev_fingerprint is None or fingerprint != prev_fingerprint

    report["fingerprint"] = fingerprint

    # Health dashboard (bridge 3 of the growth seed) — self-updating,
    # written on every run so the 5-minute timer keeps it fresh.
    health_entry = {
        "time": NOW,
        "exit_code": report["exit_code"],
        "tests_passed": tests.get("passed"),
        "mnemo_reachable": mnemo.get("reachable"),
        "tree_drift": tree.get("drift"),
        "agent_config_ok": agent_cfg.get("ok"),
        "unresolved_count": unresolved.get("count", 0),
        "tracker_reachable": tracker.get("reachable", False),
        "tracker_repo": TRACKER_REPO,
        "tracker_open": tracker.get("open_count", 0) if tracker.get("reachable") else None,
    }
    try:
        history = _load_health_history()
        write_dashboard(health_entry, history)
    except Exception as e:
        report["dashboard_error"] = str(e)

    report["changed_since_last"] = detail_changed
    report["transition"] = transition
    _save_report(report)

    # Chronicle only on state transitions, not on every detail change
    if transition:
        if report["exit_code"] == 0:
            summary = "Huck check: system healthy — exit 0."
        elif report["exit_code"] == 1:
            summary_parts = []
            if tree.get("drift"):
                summary_parts.append(
                    f"README drift — missing: {tree.get('missing_from_tree')}, stale: {tree.get('stale_in_tree')}"
                )
            if agent_cfg.get("ok") is False:
                summary_parts.append(f"agent config drift — {agent_cfg.get('error')}")
            if unresolved.get("count", 0) > 0:
                summary_parts.append(f"{unresolved['count']} unresolved items in memory")
            summary = "Huck check: drift detected — " + "; ".join(summary_parts) + "."
        else:
            summary_parts = []
            if not tests.get("passed"):
                summary_parts.append(f"tests failing (exit {tests.get('exit_code')})")
            if not mnemo.get("reachable"):
                summary_parts.append(f"Mnemosyne unreachable: {mnemo.get('error')}")
            summary = "Huck check: CRISIS — " + "; ".join(summary_parts) + "."
        try:
            ds.chronicle(
                summary,
                tags=["huck", "check", "self-check"],
                q_value=0.6,
                metadata={"source_file": "huck/notebooks/check.py"},
            )
        except Exception:
            pass

    flag = "(transition)" if transition else ("(detail changed)" if detail_changed else "(unchanged)")
    print(f"\nexit: {report['exit_code']} {flag}")
    sys.exit(report["exit_code"])


if __name__ == "__main__":
    main()