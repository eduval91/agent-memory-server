"""
The product itself: agent-native searchable memory — now PERSISTENT.

Memories are stored in SQLite (data/memories.db, MEMORY_DB overrides) so they
survive restarts — table stakes for a paid service: an agent that paid to store
something expects it to still be there tomorrow.

Design: SQLite is the durable record; vectors are also kept in an in-memory
cache per namespace, so search stays a fast numpy dot product. Writes go to
both. If you change embedding providers, rows embedded with the old provider
are re-embedded automatically at startup (their text is stored, so nothing is
lost).

The public methods (store / retrieve / search / delete / count) are the seam —
swap the internals for a real vector DB (pgvector, Qdrant, Pinecone) when you
outgrow this; nothing else in the project changes.
"""
from __future__ import annotations
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

import numpy as np

from embeddings import Embedder, get_embedder


@dataclass
class Memory:
    id: str
    namespace: str
    text: str
    metadata: dict
    created_at: float
    vector: np.ndarray = field(repr=False, default=None)

    def public(self, score: float | None = None) -> dict:
        out = {
            "id": self.id,
            "text": self.text,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
        if score is not None:
            out["score"] = round(float(score), 4)
        return out


def _default_db_path() -> str:
    return os.getenv(
        "MEMORY_DB", str(Path(__file__).resolve().parent / "data" / "memories.db")
    )


class MemoryStore:
    def __init__(self, embedder: Embedder | None = None, db_path: str | None = None):
        self.embedder = embedder or get_embedder()
        self._db_path = db_path or _default_db_path()
        self._by_ns: dict[str, list[Memory]] = {}
        self._lock = Lock()
        self._init_db()
        self._load()

    # -- persistence internals ---------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    text TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    embedder TEXT NOT NULL,
                    vector BLOB NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_ns ON memories(namespace)"
            )

    def _load(self) -> None:
        """Load all memories into the cache; re-embed rows from other embedders."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, namespace, text, metadata, created_at, embedder, vector"
                " FROM memories ORDER BY created_at"
            ).fetchall()

        stale = [r for r in rows if r["embedder"] != self.embedder.name]
        if stale:
            print(f"[memory] re-embedding {len(stale)} memories stored with a "
                  f"different embedder ({stale[0]['embedder']} -> {self.embedder.name})")
            with self._connect() as conn:
                for i in range(0, len(stale), 64):
                    batch = stale[i:i + 64]
                    vecs = self.embedder.embed([r["text"] for r in batch])
                    for r, v in zip(batch, vecs):
                        conn.execute(
                            "UPDATE memories SET embedder=?, vector=? WHERE id=?",
                            (self.embedder.name,
                             np.asarray(v, dtype=np.float32).tobytes(), r["id"]),
                        )
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, namespace, text, metadata, created_at, embedder, vector"
                    " FROM memories ORDER BY created_at"
                ).fetchall()

        for r in rows:
            mem = Memory(
                id=r["id"], namespace=r["namespace"], text=r["text"],
                metadata=json.loads(r["metadata"]), created_at=r["created_at"],
                vector=np.frombuffer(r["vector"], dtype=np.float32),
            )
            self._by_ns.setdefault(mem.namespace, []).append(mem)
        if rows:
            print(f"[memory] loaded {len(rows)} memories "
                  f"across {len(self._by_ns)} namespaces from {self._db_path}")

    # -- write -------------------------------------------------------------
    def store(self, namespace: str, text: str, metadata: dict | None = None) -> dict:
        vec = np.asarray(self.embedder.embed([text])[0], dtype=np.float32)
        mem = Memory(
            id=str(uuid.uuid4()), namespace=namespace, text=text,
            metadata=metadata or {}, created_at=time.time(), vector=vec,
        )
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO memories (id, namespace, text, metadata,"
                    " created_at, embedder, vector) VALUES (?,?,?,?,?,?,?)",
                    (mem.id, namespace, text, json.dumps(mem.metadata),
                     mem.created_at, self.embedder.name, vec.tobytes()),
                )
            self._by_ns.setdefault(namespace, []).append(mem)
        return mem.public()

    # -- read by id --------------------------------------------------------
    def retrieve(self, namespace: str, memory_id: str) -> dict | None:
        with self._lock:
            for mem in self._by_ns.get(namespace, []):
                if mem.id == memory_id:
                    return mem.public()
        return None

    # -- semantic search ---------------------------------------------------
    def search(self, namespace: str, query: str, top_k: int = 5) -> list[dict]:
        with self._lock:
            mems = list(self._by_ns.get(namespace, []))
        if not mems:
            return []
        qvec = self.embedder.embed([query])[0]
        matrix = np.vstack([m.vector for m in mems])
        scores = matrix @ qvec  # L2-normalized -> cosine similarity
        order = np.argsort(-scores)[:top_k]
        return [mems[i].public(score=scores[i]) for i in order]

    # -- housekeeping ------------------------------------------------------
    def delete(self, namespace: str, memory_id: str) -> bool:
        with self._lock:
            mems = self._by_ns.get(namespace, [])
            for i, mem in enumerate(mems):
                if mem.id == memory_id:
                    mems.pop(i)
                    with self._connect() as conn:
                        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
                    return True
        return False

    def count(self, namespace: str) -> int:
        with self._lock:
            return len(self._by_ns.get(namespace, []))


def stats(db_path: str | None = None) -> dict:
    """Totals for the dashboard — read-only, works without a MemoryStore."""
    path = db_path or _default_db_path()
    if not Path(path).exists():
        return {"memories": 0, "namespaces": 0}
    conn = sqlite3.connect(path)
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT namespace) FROM memories"
    ).fetchone()
    conn.close()
    return {"memories": row[0], "namespaces": row[1]}
