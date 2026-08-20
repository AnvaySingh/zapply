"""Local embeddings — the naive-first choice, on purpose.

We use a small local `sentence-transformers` model (`all-MiniLM-L6-v2`, 384-dim) and compute
cosine similarity in memory. No hosted embedding API, no vector database. The point is to
understand what an embedding *is* and where cosine similarity misleads before reaching for
heavier machinery. The upgrade path (hosted embeddings like Voyage/OpenAI, an ANN index like
FAISS/Chroma, a cross-encoder re-ranker) is noted in NOTES.md — not built.

The model is loaded lazily and cached, so importing this module is cheap and the (multi-second)
model load only happens on first real use.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    # Imported here so `import apply_copilot.match` doesn't drag in torch until needed.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


class Embedder:
    """Thin wrapper over a sentence-transformers model producing normalised vectors."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        model = _load_model(self.model_name)
        # normalize_embeddings=True → cosine similarity is just a dot product.
        return np.asarray(
            model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        )

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity. Assumes inputs may not be normalised."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)
