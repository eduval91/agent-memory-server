"""
Embeddings: turn text into vectors so we can do *semantic* search
(match by meaning, not just keywords).

Providers are pluggable. The default is real local embeddings via
sentence-transformers. A dependency-free "hashing" provider is included so the
project still runs anywhere (CI, sandboxes, before you install torch) — it does
lexical matching only, so swap it for a real one in production.

All embedders return L2-normalized vectors, which makes cosine similarity a
plain dot product (see memory_store.py).
"""
from __future__ import annotations
import hashlib
import re
from typing import Protocol

import numpy as np

import config


class Embedder(Protocol):
    dim: int
    name: str
    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class SentenceTransformerEmbedder:
    """Real semantic embeddings. Downloads a small model on first use (~90MB).

    This is the recommended default for production: 'refund policy' and
    'how do I get my money back' land near each other even with no shared words.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # lazy import
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()
        self.name = f"sentence-transformers:{model_name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


class HashingEmbedder:
    """Dependency-free fallback. Bag-of-words hashed into a fixed vector.

    This captures LEXICAL overlap (shared words -> higher similarity) but NOT
    deeper meaning. It exists so the server runs with zero ML dependencies and
    so tests are deterministic. Do not ship it as your real search quality.
    """

    _token_re = re.compile(r"[a-z0-9]+")

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing:{dim}"

    def _tokenize(self, text: str) -> list[str]:
        return self._token_re.findall(text.lower())

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in self._tokenize(text):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        return _l2_normalize(out)


class OpenAIEmbedder:
    """Hosted embeddings (no local model). Needs OPENAI_API_KEY.

    Kept minimal on purpose — uncomment/adapt if you prefer a hosted provider
    over a local model. Any embedding API works the same way.
    """

    def __init__(self, model: str = "text-embedding-3-small"):
        import os
        import httpx
        self._httpx = httpx
        self._key = os.environ["OPENAI_API_KEY"]
        self._model = model
        self.dim = 1536
        self.name = f"openai:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        resp = self._httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": texts},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return _l2_normalize(np.asarray([d["embedding"] for d in data], dtype=np.float32))


def get_embedder() -> Embedder:
    """Build the configured embedder, falling back gracefully if unavailable."""
    provider = config.EMBEDDINGS_PROVIDER
    if provider == "sentence-transformers":
        try:
            return SentenceTransformerEmbedder(config.EMBEDDINGS_MODEL)
        except Exception as exc:  # not installed, or model can't be downloaded
            print(
                f"[embeddings] sentence-transformers unavailable ({exc}); "
                f"falling back to the 'hashing' embedder (lexical only). "
                f"Install requirements.txt for real semantic search."
            )
            return HashingEmbedder()
    if provider == "openai":
        return OpenAIEmbedder()
    if provider == "hashing":
        return HashingEmbedder()
    raise ValueError(f"Unknown EMBEDDINGS_PROVIDER: {provider!r}")
