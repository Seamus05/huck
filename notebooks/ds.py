"""ds — data surface. Shared loop helpers for team notebooks.

chronicle() writes observations to Mnemosyne (openframe-memory).
query() searches archival passages.
"""

import os
import json
import hashlib
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_URL = os.environ.get("OPENFRAME_MEMORY_URL", "http://10.70.0.10:8381")
DEFAULT_AGENT = os.environ.get("OPENFRAME_AGENT_ROLE", "host-manager")
DEFAULT_ARCHIVE = "default"


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


def query(
    query_text: str,
    limit: int = 5,
    min_q: float = 0.5,
    agent_id: Optional[str] = None,
    archive_id: str = DEFAULT_ARCHIVE,
    order_by: str = "similarity",
) -> list[dict]:
    """Search archival memory by semantic similarity.

    Returns a list of passage dicts, each with id, text, tags, q_value, etc.
    """
    if not query_text or not query_text.strip():
        return []
    if limit < 1:
        limit = 5
    agent = agent_id or DEFAULT_AGENT
    params = urllib.parse.urlencode({
        "query": query_text,
        "limit": limit,
        "min_q": min_q,
        "archive_id": archive_id,
        "order_by": order_by,
    })
    url = f"{MEMORY_URL}/v1/agents/{agent}/archival-memory?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("passages", [])
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        logger.warning("query failed: %s", e)
        return []


def learn(
    query_text: str,
    limit: int = 20,
    min_q: float = 0.0,
    agents: Optional[list[str]] = None,
    top_tags: int = 10,
    archive_id: str = DEFAULT_ARCHIVE,
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
        archive_id: which archive to read from.

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
