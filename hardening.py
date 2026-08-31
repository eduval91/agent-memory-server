"""
Hardening: the guards that keep one misbehaving agent from hurting the service.

Three protections, all enforced BEFORE payment is taken (an agent never pays
for a call that gets refused):

  * rate limiting  — a token bucket per client (IP or agent id); refuses with
                     `rate_limited` when a client calls faster than
                     config.RATE_LIMIT_PER_MIN.
  * input caps     — text/query/metadata byte sizes, top_k, agent id shape.
  * storage quota  — max memories per agent (config.MAX_MEMORIES_PER_AGENT).

Payment replay protection lives in payments.py (nonce tracking); this module
is transport-agnostic and used by both http_server.py and mcp_server.py.
"""
from __future__ import annotations
import json
import time
from threading import Lock

import config


# ---------------------------------------------------------------------------
# Rate limiting — token bucket per key
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, per_minute: int | None = None):
        self.per_minute = per_minute if per_minute is not None else config.RATE_LIMIT_PER_MIN
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_ts)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        """Take one token for `key`; False means the client must slow down."""
        if self.per_minute <= 0:  # 0 disables rate limiting
            return True
        now = time.monotonic()
        rate = self.per_minute / 60.0
        with self._lock:
            tokens, last = self._buckets.get(key, (float(self.per_minute), now))
            tokens = min(float(self.per_minute), tokens + (now - last) * rate)
            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return False
            self._buckets[key] = (tokens - 1.0, now)
            # opportunistic prune so the dict can't grow unbounded
            if len(self._buckets) > 10_000:
                cutoff = now - 300
                self._buckets = {k: v for k, v in self._buckets.items() if v[1] > cutoff}
            return True


limiter = RateLimiter()  # shared instance for the process


# ---------------------------------------------------------------------------
# Input validation — returns an error string, or None when the input is fine
# ---------------------------------------------------------------------------
def check_agent_id(agent_id) -> str | None:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return "agent_id must be a non-empty string"
    if len(agent_id) > 128:
        return "agent_id too long (max 128 chars)"
    if any(c in agent_id for c in "\x00\n\r\t"):
        return "agent_id contains control characters"
    return None


def check_store(text, metadata) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return "text must be a non-empty string"
    if len(text.encode()) > config.MAX_TEXT_BYTES:
        return f"text too large (max {config.MAX_TEXT_BYTES} bytes)"
    if metadata is not None:
        if not isinstance(metadata, dict):
            return "metadata must be an object"
        try:
            if len(json.dumps(metadata).encode()) > config.MAX_METADATA_BYTES:
                return f"metadata too large (max {config.MAX_METADATA_BYTES} bytes)"
        except (TypeError, ValueError):
            return "metadata must be JSON-serializable"
    return None


def check_search(query, top_k) -> str | None:
    if not isinstance(query, str) or not query.strip():
        return "query must be a non-empty string"
    if len(query.encode()) > config.MAX_QUERY_BYTES:
        return f"query too large (max {config.MAX_QUERY_BYTES} bytes)"
    if not isinstance(top_k, int) or top_k < 1 or top_k > config.MAX_TOP_K:
        return f"top_k must be between 1 and {config.MAX_TOP_K}"
    return None


def check_quota(store, namespace: str) -> str | None:
    if store.count(namespace) >= config.MAX_MEMORIES_PER_AGENT:
        return (f"storage quota reached ({config.MAX_MEMORIES_PER_AGENT} memories); "
                f"delete some memories before storing more")
    return None
