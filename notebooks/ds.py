"""ds — data surface. Shared loop helpers for team notebooks.

chronicle() writes observations to Mnemosyne (openframe-memory).
query() searches archival passages.
"""

import os
import json
import hashlib
import urllib.request
from typing import Optional

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
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def content_hash(text: str) -> str:
    """SHA-256 of text — used for dedup lookups."""
    return hashlib.sha256(text.encode()).hexdigest()


def exists(source_file: str) -> list[dict]:
    """Check if passages already exist for a given source_file metadata key."""
    encoded = urllib.parse.quote(source_file)
    url = f"{MEMORY_URL}/v1/passages/lookup?source_file={encoded}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        result = json.loads(resp.read().decode())
        return result.get("passages", [])
