"""ds — data surface. Shared loop helpers for team notebooks.

chronicle() writes observations to Mnemosyne (openframe-memory).
query() searches archival passages.
learn() aggregates patterns across the whole shared corpus.
mark_resolved()/resolved_ids() track which passages the drift scanner
should stop flagging.
"""

import os
import json
import hashlib
import logging
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_URL = os.environ.get("OPENFRAME_MEMORY_URL", "http://10.70.0.10:8381")
DEFAULT_AGENT = os.environ.get("OPENFRAME_AGENT_ROLE", "host-manager")
DEFAULT_ARCHIVE = "default"

# The shared corpus is split across several archives (discovered by Huck's
# query-memory tool, 2026-08-18):
#   - UUID archive (MNEMOSYNE_ID)  ~761 passages — where the inline write tools
#     (send-message / write-observation) land.
#   - "default"                     ~395 passages — where ds.chronicle() writes.
#   - infra-lessons / phaedrus / mori — smaller named archives.
# A read that only hits archive_id="default" (ds.query()'s old default) saw
# under 40% of the corpus. query()/learn() now fan out across ALL of these and
# merge, matching the fleet query-memory tool.
MNEMOSYNE_ID = os.environ.get("MNEMOSYNE_ID", "agent-b0c24e6b-303d-433a-a166-4881c563661d")
KNOWN_ARCHIVES = [MNEMOSYNE_ID, "default", "infra-lessons", "phaedrus", "mori"]


def chronicle(
    text: str,
    tags: Optional[list[str]] = None,
    q_value: float = 0.5,
    metadata: Optional[dict] = None,
    agent_id: Optional[str] = None,
    archive_id: str = DEFAULT_ARCHIVE,
) -> dict:
    """Write an observation to Mnemosyne archival memory.

    Returns the created passage dict with id, created_at, etc.
    """
    agent = agent_id or DEFAULT_AGENT
    url = f"{MEMORY_URL}/v1/agents/{agent}/archival-memory"

    body = {
        "text": text,
        "archive_id": archive_id,
        "q_value": q_value,
    }
    if tags:
        body["tags"] = tags
    if metadata:
        body["metadata"] = metadata

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("chronicle failed: %s", e)
        return {}


def content_hash(text: str) -> str:
    """SHA-256 of text — used for dedup lookups."""
    return hashlib.sha256(text.encode()).hexdigest()


def _query_archive(
    query_text: str,
    archive_id: str,
    limit: int,
    min_q: float,
    order_by: str,
    agent: str,
    tracked: bool = True,
) -> tuple[list[dict], Optional[str]]:
    """Query a single archive. Returns (passages, error-or-None)."""
    params = urllib.parse.urlencode({
        "query": query_text,
        "limit": limit,
        "min_q": min_q,
        "archive_id": archive_id,
        "order_by": order_by,
        "tracked": "true" if tracked else "false",
    })
    url = f"{MEMORY_URL}/v1/agents/{agent}/archival-memory?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            # The service's search SELECT does not return archive_id; tag each
            # passage with the archive it came from (mirrors query-memory.ts).
            return [
                {**p, "archive_id": archive_id}
                for p in result.get("passages", [])
            ], None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("query archive %s failed: %s", archive_id, e)
        return [], str(e)


def query(
    query_text: str,
    limit: int = 5,
    min_q: float = 0.5,
    agent_id: Optional[str] = None,
    archive_id: Optional[str] = None,
    order_by: str = "similarity",
    tracked: bool = True,
) -> list[dict]:
    """Search archival memory by semantic similarity.

    Defaults to cross-archive search across ALL known archives (the corpus is
    split across the UUID archive written by the inline tools, "default" written
    by ds.chronicle(), and named archives). Pass archive_id to narrow to one
    archive (or a comma-separated list).

    Returns a list of passage dicts, each with id, text, tags, q_value, etc.
    """
    if not query_text or not query_text.strip():
        return []
    if limit < 1:
        limit = 5
    agent = agent_id or DEFAULT_AGENT

    # Resolve target archives. None / "all" / empty -> every known archive.
    if archive_id in (None, "all", ""):
        targets = KNOWN_ARCHIVES
    else:
        targets = [a.strip() for a in archive_id.split(",") if a.strip()]
    if not targets:
        return []

    # Per-archive fetch 2x the requested limit so the cross-archive merge has
    # better recall; we re-rank and truncate to `limit` at the end.
    per_archive = max(1, min(limit * 2, 50))

    results_per_archive: list[tuple[list[dict], Optional[str]]] = [
        _query_archive(query_text, a, per_archive, min_q, order_by, agent, tracked=tracked)
        for a in targets
    ]

    # Merge, dedupe by id.
    seen: dict[str, dict] = {}
    for passages, _err in results_per_archive:
        for p in passages:
            pid = p.get("id")
            if pid and pid not in seen:
                seen[pid] = p
    merged = list(seen.values())

    # Re-rank after merge across ALL archives (not just within each archive).
    # The service returns a `similarity` per passage; without a global re-rank
    # the first archive in KNOWN_ARCHIVES would dominate the slice even when
    # another archive has closer matches.
    if order_by == "recency":
        merged.sort(
            key=lambda p: p.get("created_at") or "",
            reverse=True,
        )
    else:
        merged.sort(
            key=lambda p: p.get("similarity") if p.get("similarity") is not None else -1,
            reverse=True,
        )

    return merged[:limit]


def learn(
    query_text: str,
    limit: int = 20,
    min_q: float = 0.0,
    agents: Optional[list[str]] = None,
    top_tags: int = 10,
    archive_id: Optional[str] = None,
) -> dict:
    """Query the whole shared corpus and extract recurring patterns.

    Unlike query(), which returns raw passages for one narrow question,
    learn() looks sideways: it pulls a broader slice of the shared archive
    and aggregates the signals a single passage hides — which agents have
    chronicled on a theme, and which tags recur across them. This is the
    cross-agent bridge: what Phaedrus, Carlin, Jung, and the rest noticed
    that Huck hasn't yet.

    Args:
        query_text: theme to mine.
        limit: how many passages to examine (wider = more signal, more noise).
        min_q: similarity floor; default 0.0 to gather a broad sample.
        agents: optional list of agent ids (e.g. ['phaedrus', 'kairos']) to
            restrict to. None means the whole corpus.
        top_tags: how many most-common tags to return.
        archive_id: which archive to read from. None (default) reads across
            all known archives, matching query().

    Returns:
        dict with:
            count       — passages examined
            agents      — distinct agent ids observed (from agent:* tags)
            top_tags    — most frequent tags across the slice
            passages    — trimmed raw passages (id, text, tags)
    """
    if not query_text or not query_text.strip():
        return {"count": 0, "agents": [], "top_tags": [], "passages": []}
    if top_tags < 1:
        top_tags = 10

    passages = query(
        query_text,
        limit=limit,
        min_q=min_q,
        archive_id=archive_id,
        order_by="similarity",
    )

    # Restrict to a subset of agents if asked.
    if agents:
        allowed = {f"agent:{a}".lower() for a in agents}
        passages = [
            p for p in passages
            if any(t in allowed for t in (p.get("tags") or []))
        ]

    from collections import Counter

    seen_agents: set[str] = set()
    tag_counts: Counter = Counter()

    for p in passages:
        for t in p.get("tags") or []:
            if t.startswith("agent:"):
                seen_agents.add(t.split(":", 1)[1])
            else:
                tag_counts[t] += 1

    # Return a trimmed view of the raw passages too, so a caller can read on.
    trimmed = [
        {"id": p.get("id", ""), "text": (p.get("text") or "")[:200], "tags": p.get("tags", [])}
        for p in passages
    ]

    return {
        "count": len(passages),
        "agents": sorted(seen_agents),
        "top_tags": [t for t, _ in tag_counts.most_common(top_tags)],
        "passages": trimmed,
    }


def exists(source_file: str) -> list[dict]:
    """Check if passages already exist for a given source_file metadata key."""
    encoded = urllib.parse.quote(source_file)
    url = f"{MEMORY_URL}/v1/passages/lookup?source_file={encoded}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("passages", [])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("exists failed: %s", e)
        return []


def _state_file(name: str) -> str:
    """Resolve a state file in the repo state/ dir (repo root /state)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "state", name)


def resolved_ids() -> list[str]:
    """Passage ids the drift scanner should stop flagging.

    Reads state/resolved.json — a plain list of passage ids that have been
    addressed in a prior Huck session. Used by check.py's unresolved scan
    so a fixed item doesn't wake Huck forever.
    """
    path = _state_file("resolved.json")
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
        if isinstance(data, dict):
            return [str(x) for x in data.get("ids", [])]
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def mark_resolved(passage_id: str) -> bool:
    """Record a passage id as addressed so the drift scanner stops flagging it."""
    if not passage_id:
        return False
    path = _state_file("resolved.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ids = resolved_ids()
    if passage_id not in ids:
        ids.append(passage_id)
    try:
        with open(path, "w") as f:
            json.dump({"ids": ids, "updated_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
        return True
    except OSError as e:
        logger.warning("mark_resolved failed: %s", e)
        return False


def roundtrip(
    tag: str = "loop-proof",
    agent_id: Optional[str] = None,
    archive_id: str = DEFAULT_ARCHIVE,
    retries: int = 1,
) -> dict:
    """Prove the isolated-agent write→read loop end-to-end.

    Writes a unique marker passage to Mnemosyne, then queries it back through
    the real semantic-search path, and verifies the SAME passage id comes
    back. This is the pattern's core claim: an isolated agent can record its
    state to shared memory and retrieve it again — not just write, not just
    read, but round-trip.

    Deliberate, not timer-driven: each call leaves ONE marker passage in the
    archive (tags: huck, loop-proof). Use it when you want to demonstrate or
    record that the loop works. Do not call it from the 5-minute check — the
    check's read probe is deliberately write-free.

    Returns an evidence dict:
        ok        — True when the written id is found in the query results
        marker    — the exact marker text written
        write_id  — passage id returned by chronicle() (None if write failed)
        read_id   — id of the passage the query returned for the marker
        match     — True when write_id == read_id
        results   — how many passages the query returned
        tag       — the marker tag
        archive   — archive used
        steps     — {"write": "ok"|"failed", "read": "ok"|"empty"|"skipped"}
        retried   — True if the first read came back empty and a retry helped
    """
    marker = (
        f"{tag} {uuid.uuid4().hex[:8]} "
        f"{datetime.now(timezone.utc).isoformat()}"
    )
    created = chronicle(
        marker,
        tags=["huck", "loop-proof", f"tag:{tag}"],
        q_value=0.5,
        agent_id=agent_id,
        archive_id=archive_id,
    )
    write_id = created.get("id") if isinstance(created, dict) else None
    if not write_id:
        return {
            "ok": False,
            "marker": marker,
            "write_id": None,
            "read_id": None,
            "match": False,
            "results": 0,
            "tag": tag,
            "archive": archive_id,
            "steps": {"write": "failed", "read": "skipped"},
            "retried": False,
        }

    def _read() -> list[dict]:
        return query(
            marker,
            limit=5,
            min_q=0.0,
            agent_id=agent_id,
            archive_id=archive_id,
            order_by="similarity",
            tracked=False,  # the verification read must not bump counters
        )

    results = _read()
    # Semantic indexes can lag a write by a beat; one quiet retry is cheap
    # and only happens on an empty first read.
    retried = False
    if not results and retries > 0:
        time.sleep(1.0)
        results = _read()
        retried = True

    ids = [r.get("id") for r in results if r.get("id")]
    match = write_id in ids
    return {
        "ok": match,
        "marker": marker,
        "write_id": write_id,
        "read_id": write_id if match else (ids[0] if ids else None),
        "match": match,
        "results": len(ids),
        "tag": tag,
        "archive": archive_id,
        "steps": {
            "write": "ok",
            "read": "ok" if ids else "empty",
        },
        "retried": retried,
    }
