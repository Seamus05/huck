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
