"""Local embeddings via ONNX (fastembed) — the deploy-friendly runtime.

Same model as before (`all-MiniLM-L6-v2`, 384-dim) and the same in-memory cosine, but executed by
**ONNX Runtime** through `fastembed` instead of PyTorch. That keeps the embeddings numerically
equivalent (rankings unchanged) while dropping the memory footprint ~5x (~2 GB → ~400 MB), so the
app fits small free hosts. No hosted embedding API, no vector DB — still naive-first.

The model is loaded lazily and cached, so importing this module is cheap and the model load only
happens on first real use.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    # Imported here so `import zapply.match` doesn't drag in the runtime until needed.
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name)


class Embedder:
    """Thin wrapper over a fastembed (ONNX) model producing normalised vectors."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def encode(self, texts: list[str]) -> np.ndarray:
        model = _load_model(self.model_name)
        vecs = np.asarray(list(model.embed(texts)), dtype=float)
        # L2-normalise so cosine similarity is a dot product (matches the old behaviour).
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms

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
