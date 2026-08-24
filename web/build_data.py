"""Bake the job snapshot, embeddings, and the embedding model into the image.

Run once at Docker build time (see Dockerfile). Ingests live from the public ATS boards,
computes the embeddings, and downloads the local model — so the deployed container starts fast
and needs no network for browsing/matching.
"""

from __future__ import annotations

from apply_copilot.match import Embedder
from web.jobs import load_or_build_vectors, refresh_snapshot


def main() -> None:
    jobs = refresh_snapshot()          # ingest ATS boards + RSS → data/jobs_snapshot.json
    embedder = Embedder()
    vecs = load_or_build_vectors(jobs, embedder)  # downloads MiniLM + builds data/job_vectors.npy
    embedder.encode_one("warm up")     # ensure the model is fully cached
    print(f"baked {len(jobs)} jobs; vectors {vecs.shape}")


if __name__ == "__main__":
    main()
