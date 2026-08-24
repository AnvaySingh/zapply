"""FastAPI backend for the apply-copilot demo web app.

A thin JSON API over the engine — ingestion (Phase 1), embeddings/matching (Phase 3) — plus a
hand-crafted static SPA (see `web/static/`). Replaces the earlier Streamlit prototype so the UI
has full control over design (the Streamlit version couldn't hide its own chrome or theme its
widgets). Matching is 100% local; no LLM is called by this server.

Run:  uv run uvicorn web.server:app --port 8501
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from apply_copilot.match import Embedder, cosine
from web.enrich import parse_salary, posted_ago
from web.jobs import (
    SENIORITY_ORDER,
    SNAPSHOT,
    load_jobs,
    load_or_build_vectors,
    seniority_category,
    workplace_category,
)
from web.skills import extract_skills, overlap_and_gaps

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SAMPLE = ROOT.parent / "evals" / "phase2" / "fixtures" / "resume_1.txt"

TECH_OPTIONS = [
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "React", "Node.js",
    "AWS", "Kubernetes", "Docker", "SQL", "PostgreSQL", "Machine Learning", "PyTorch",
    "Kafka", "Spark", "GraphQL", "Terraform",
]

app = FastAPI(title="apply-copilot")

# --- load the corpus once at import (from disk snapshot + cached vectors) ---
_EMB = Embedder()  # model loads lazily on first embed (only /api/match needs it)
_JOBS = load_jobs()
_VECS = load_or_build_vectors(_JOBS, _EMB)
_CATS = [workplace_category(j) for j in _JOBS]
_SENS = [seniority_category(j) for j in _JOBS]
_SKILLS = [extract_skills(f"{j.title} {j.description[:1200]}") for j in _JOBS]


def _updated() -> str:
    try:
        secs = time.time() - os.path.getmtime(SNAPSHOT)
    except OSError:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _payload(i: int, score: int | None = None, cand: set[str] | None = None) -> dict:
    j = _JOBS[i]
    out = {
        "title": j.title, "company": j.company, "location": j.location or "",
        "source": j.source, "url": j.url or "", "workplace": _CATS[i], "seniority": _SENS[i],
        "salary": parse_salary(j.description), "posted": posted_ago(j),
        "skills": sorted(_SKILLS[i])[:8],
    }
    if score is not None:
        out["score"] = score
    if cand is not None:
        matches, gaps = overlap_and_gaps(cand, f"{j.title} {j.description[:2000]}")
        out["matches"] = matches[:8]
        out["gaps"] = gaps[:5]
    return out


def _filtered(q: str, workplace: str, seniority: str, tech: str) -> list[int]:
    wp = {x for x in workplace.split(",") if x}
    sn = {x for x in seniority.split(",") if x}
    tk = {x for x in tech.split(",") if x}
    ql = q.strip().lower()
    out = []
    for i, j in enumerate(_JOBS):
        if wp and _CATS[i] not in wp:
            continue
        if sn and _SENS[i] not in sn:
            continue
        if tk and not (_SKILLS[i] & tk):
            continue
        if ql and ql not in f"{j.title} {j.company} {j.location or ''}".lower():
            continue
        out.append(i)
    return out


def _posted_key(i: int):
    from datetime import timezone

    dt = _JOBS[i].posted_at or _JOBS[i].updated_at
    if dt is None:
        return 0.0
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@app.get("/api/facets")
def facets():
    return {
        "workplace": ["Remote", "Hybrid", "On-site"],
        "seniority": SENIORITY_ORDER,
        "tech": TECH_OPTIONS,
        "total": len(_JOBS),
        "updated": _updated(),
    }


@app.get("/api/jobs")
def jobs(q: str = "", workplace: str = "", seniority: str = "", tech: str = "", limit: int = 12):
    idx = _filtered(q, workplace, seniority, tech)
    idx.sort(key=_posted_key, reverse=True)
    return {"total": len(idx), "mode": "browse", "jobs": [_payload(i) for i in idx[:limit]]}


@app.post("/api/match")
async def match(
    q: str = Form(""),
    workplace: str = Form(""),
    seniority: str = Form(""),
    tech: str = Form(""),
    limit: int = Form(12),
    sample: str = Form(""),
    file: UploadFile | None = File(None),
):
    text = ""
    if file is not None:
        data = await file.read()
        if file.filename and file.filename.lower().endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        else:
            text = data.decode("utf-8", errors="ignore")
    elif sample:
        text = SAMPLE.read_text(encoding="utf-8") if SAMPLE.exists() else ""

    if not text.strip():
        return JSONResponse({"error": "No resume text provided."}, status_code=400)

    cand = extract_skills(text)
    qv = _EMB.encode_one(text)
    idx = _filtered(q, workplace, seniority, tech)
    scored = sorted(((int(round(max(0.0, cosine(qv, _VECS[i])) * 100)), i) for i in idx), reverse=True)
    jobs_out = [_payload(i, score=s, cand=cand) for s, i in scored[:limit]]
    return {"total": len(idx), "mode": "matched", "jobs": jobs_out}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
