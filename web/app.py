"""apply-copilot — demo web app.

Upload a resume → get a ranked list of matching jobs. A thin Streamlit presentation layer over
the existing brain: ingestion (Phase 1), embeddings/matching (Phase 3), and optional structured
extraction (Phase 2). Matching is 100% local (no API, no quota); the optional "AI analyze" step
is the only thing that calls the LLM, and it degrades gracefully if the daily quota is out.

Run:  uv run streamlit run web/app.py
"""

from __future__ import annotations

import io
from pathlib import Path

import streamlit as st

from apply_copilot.extract import extract_profile
from apply_copilot.llm import LLMError
from apply_copilot.match import Embedder, cosine, profile_to_text
from jobs import (  # sibling module (web/ on sys.path)
    load_jobs,
    load_or_build_vectors,
    refresh_snapshot,
    workplace_category,
)

WORKPLACE_ICON = {"Remote": "🏠", "Hybrid": "🔀", "On-site": "🏢", "Unknown": "❓"}
WORKPLACE_OPTIONS = ["Remote", "Hybrid", "On-site"]

_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RESUME = (_ROOT / "evals" / "phase2" / "fixtures" / "resume_1.txt")

st.set_page_config(page_title="apply-copilot", page_icon="🧭", layout="wide")


# -- cached heavy resources ----------------------------------------------------


@st.cache_resource(show_spinner=False)
def get_embedder() -> Embedder:
    return Embedder()


@st.cache_resource(show_spinner="Loading jobs & embeddings…")
def get_jobs_and_vectors():
    embedder = get_embedder()
    jobs = load_jobs()
    vecs = load_or_build_vectors(jobs, embedder)
    cats = [workplace_category(j) for j in jobs]
    embedder.encode_one("warm up the model")  # so the first real search is instant
    return jobs, vecs, cats


# -- helpers -------------------------------------------------------------------


def read_resume(uploaded) -> str:
    if uploaded.name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(uploaded.getvalue()))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return uploaded.getvalue().decode("utf-8", errors="ignore")


def rank_jobs(query_text: str, top_n: int, allowed: set[str], show_all: bool):
    jobs, vecs, cats = get_jobs_and_vectors()
    qv = get_embedder().encode_one(query_text)
    scored = [
        (round(max(0.0, cosine(qv, v)) * 100), job, cat)
        for v, job, cat in zip(vecs, jobs, cats)
        if show_all or cat in allowed
    ]
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:top_n]


def score_color(score: int) -> str:
    return "#16a34a" if score >= 60 else "#d97706" if score >= 45 else "#6b7280"


# -- UI ------------------------------------------------------------------------

st.title("🧭 apply-copilot")
st.caption("Upload your resume — get the jobs that fit, ranked. Matching runs locally on your machine.")

with st.sidebar:
    st.header("Settings")
    top_n = st.slider("Jobs to show", 5, 30, 10)
    workplace = st.multiselect(
        "Workplace", WORKPLACE_OPTIONS, default=WORKPLACE_OPTIONS,
        help="Filter by Remote / Hybrid / On-site.",
    )
    use_ai = st.toggle("✨ AI-analyze my resume", value=False,
                       help="Extracts a structured profile (skills, seniority) via the LLM. Uses 1 API call.")
    st.divider()
    jobs, _, cats = get_jobs_and_vectors()
    allowed = set(workplace)
    show_all = allowed == set(WORKPLACE_OPTIONS)
    matching = sum(1 for c in cats if show_all or c in allowed)
    st.metric("Jobs in the feed", len(jobs), help="Total ingested postings.")
    st.caption(f"Matching your filter: **{matching}**")
    if st.button("↻ Refresh job feed", help="Re-ingest live from Greenhouse/Lever/Ashby/RSS."):
        with st.spinner("Ingesting live…"):
            refresh_snapshot()
        get_jobs_and_vectors.clear()
        st.rerun()
    st.caption("Sources: public ATS boards + RSS. Read-only, no scraping.")

# --- resume input ---
st.subheader("1. Your resume")
col_a, col_b = st.columns([3, 1])
with col_a:
    uploaded = st.file_uploader("Upload a resume (PDF or .txt)", type=["pdf", "txt"], label_visibility="collapsed")
with col_b:
    use_sample = st.button("Use sample resume", use_container_width=True)

resume_text = ""
if uploaded is not None:
    resume_text = read_resume(uploaded)
elif use_sample and SAMPLE_RESUME.exists():
    resume_text = SAMPLE_RESUME.read_text(encoding="utf-8")
    st.session_state["_sample"] = resume_text
elif st.session_state.get("_sample"):
    resume_text = st.session_state["_sample"]

if not resume_text.strip():
    st.info("👆 Upload a resume or click **Use sample resume** to see matching jobs.")
    st.stop()

with st.expander("Resume text used for matching", expanded=False):
    st.text(resume_text[:3000])

# --- optional AI analysis ---
query_text = resume_text
if use_ai:
    with st.spinner("Analyzing your resume with AI…"):
        try:
            profile = extract_profile(resume_text)
            query_text = profile_to_text(profile) or resume_text
            st.subheader("2. What the AI understood")
            c1, c2, c3 = st.columns(3)
            c1.metric("Seniority", profile.seniority.value)
            c2.metric("Years", profile.years_experience if profile.years_experience is not None else "—")
            c3.metric("Skills found", len(profile.skills))
            if profile.skills:
                st.write(" ".join(f"`{s}`" for s in profile.skills))
        except LLMError as exc:
            st.warning(f"AI analysis unavailable ({exc}). Falling back to matching on raw resume text.")

# --- results ---
st.subheader("3. Matching jobs")
with st.spinner("Ranking jobs…"):
    results = rank_jobs(query_text, top_n, allowed, show_all)

if not results:
    st.warning("No jobs match the selected workplace filter. Try adding categories in the sidebar.")
    st.stop()

for score, job, cat in results:
    with st.container(border=True):
        left, right = st.columns([5, 1])
        with left:
            st.markdown(f"### {job.title}")
            badge = f"{WORKPLACE_ICON.get(cat, '')} {cat}"
            meta = " · ".join(x for x in (job.company, job.location or None, badge, job.source) if x)
            st.caption(meta)
        with right:
            st.markdown(
                f"<div style='text-align:center'><span style='font-size:2rem;font-weight:700;"
                f"color:{score_color(score)}'>{score}</span><br><span style='color:#6b7280'>match</span></div>",
                unsafe_allow_html=True,
            )
            if job.url:
                st.link_button("Apply ↗", job.url, use_container_width=True)

st.caption(
    "This is a copilot: it finds and ranks jobs; you review and apply yourself. "
    "Matching is local — your resume never leaves your machine unless you enable AI analysis."
)
