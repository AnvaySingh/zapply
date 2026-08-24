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
import uuid
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

# Cache of resume-derived state (query vector + candidate skills + AI profile), keyed by a token,
# so pagination and filter changes reuse it — no repeat embedding or LLM call.
_MATCH_CACHE: dict[str, dict] = {}


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
        "id": i,
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
def jobs(q: str = "", workplace: str = "", seniority: str = "", tech: str = "",
         limit: int = 20, offset: int = 0):
    idx = _filtered(q, workplace, seniority, tech)
    idx.sort(key=_posted_key, reverse=True)
    page = idx[offset:offset + limit]
    return {"total": len(idx), "mode": "browse", "offset": offset, "jobs": [_payload(i) for i in page]}


async def _read_resume(file: UploadFile | None, sample: str) -> str:
    if file is not None:
        data = await file.read()
        if file.filename and file.filename.lower().endswith(".pdf"):
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        return data.decode("utf-8", errors="ignore")
    if sample:
        return SAMPLE.read_text(encoding="utf-8") if SAMPLE.exists() else ""
    return ""


@app.post("/api/match")
async def match(
    q: str = Form(""),
    workplace: str = Form(""),
    seniority: str = Form(""),
    tech: str = Form(""),
    limit: int = Form(20),
    offset: int = Form(0),
    sample: str = Form(""),
    ai: str = Form(""),
    token: str = Form(""),
    file: UploadFile | None = File(None),
):
    warning = None
    profile_info = None

    if token and token in _MATCH_CACHE:
        entry = _MATCH_CACHE[token]
        qv, cand, profile_info = entry["qv"], entry["cand"], entry["profile"]
    else:
        text = await _read_resume(file, sample)
        if not text.strip():
            return JSONResponse({"error": "No resume text provided."}, status_code=400)

        query_text = text
        profile_obj = None
        if ai:
            try:
                from apply_copilot.extract import extract_profile
                from apply_copilot.match import profile_to_text

                profile_obj = extract_profile(text)
                query_text = profile_to_text(profile_obj) or text
                profile_info = {
                    "seniority": profile_obj.seniority.value,
                    "years": profile_obj.years_experience,
                    "skills": profile_obj.skills[:16],
                }
            except Exception as exc:  # noqa: BLE001 - quota/no-key etc.; fall back to raw text
                warning = f"AI analysis unavailable ({type(exc).__name__}); matched on raw resume text."

        cand = extract_skills(text)
        qv = _EMB.encode_one(query_text)
        token = uuid.uuid4().hex
        _MATCH_CACHE[token] = {"qv": qv, "cand": cand, "profile": profile_info, "profile_obj": profile_obj, "text": text}
        if len(_MATCH_CACHE) > 200:  # crude cap
            _MATCH_CACHE.pop(next(iter(_MATCH_CACHE)))

    idx = _filtered(q, workplace, seniority, tech)
    scored = sorted(((int(round(max(0.0, cosine(qv, _VECS[i])) * 100)), i) for i in idx), reverse=True)
    page = scored[offset:offset + limit]
    jobs_out = [_payload(i, score=s, cand=cand) for s, i in page]
    return {
        "total": len(idx), "mode": "matched", "offset": offset, "jobs": jobs_out,
        "token": token, "profile": profile_info, "warning": warning,
    }


@app.post("/api/packet")
async def packet(token: str = Form(...), id: int = Form(...)):
    """Grounded application packet for one job: extract Requirements → draft → faithfulness gate.

    Needs a resume (a match token). Uses ~2–3 LLM calls. This is the copilot doing its real job —
    everything up to the submit button, with a program that verifies the draft didn't lie.
    """
    if not token or token not in _MATCH_CACHE or not (0 <= id < len(_JOBS)):
        return JSONResponse({"error": "Load a resume and pick a job first."}, status_code=400)

    entry = _MATCH_CACHE[token]
    try:
        from apply_copilot.draft import check_draft
        from apply_copilot.draft import draft as draft_fn
        from apply_copilot.extract import extract_requirements
        from apply_copilot.match.matcher import Matcher

        profile = entry.get("profile_obj")
        if profile is None:
            from apply_copilot.extract import extract_profile

            profile = extract_profile(entry["text"])
            entry["profile_obj"] = profile  # cache for next time

        job = _JOBS[id]
        reqs = extract_requirements(f"{job.title}\n\n{job.description}")
        reqs.company = reqs.company or job.company
        reqs.title = reqs.title or job.title

        packet = draft_fn(profile, reqs)
        report = check_draft(packet, profile, reqs)
        mr = Matcher().score(profile, reqs)
    except Exception as exc:  # noqa: BLE001 - quota/no-key/parse; surface to the UI
        return JSONResponse(
            {"error": f"Could not generate the packet ({type(exc).__name__}). "
                      f"The daily LLM quota may be exhausted — try again after it resets."}
        )

    return {
        "company": reqs.company or job.company,
        "title": reqs.title or job.title,
        "url": job.url or "",
        "score": mr.score,
        "rationale": mr.rationale,
        "missing": mr.missing_skills,
        "bullets": [b.text for b in packet.bullets],
        "answers": [{"question": a.question, "answer": a.answer} for a in packet.answers],
        "faithful": report.is_faithful,
        "violations": [f"{v.where}: {v.kind} — {v.detail}" for v in report.violations],
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
