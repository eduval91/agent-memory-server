"""
One memory store for the whole process.

http_server.py (REST) and mcp_server.py (MCP) both serve the same product. If
each built its own MemoryStore they'd write to the same database but keep
separate in-memory vector caches — so a memory an agent stored over REST would
be invisible to a search over MCP until the next restart. Sharing one instance
keeps the two interfaces genuinely the same service.
"""
from __future__ import annotations

from memory_store import MemoryStore

store = MemoryStore()
