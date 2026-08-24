"""apply-copilot — demo web app.

Browse & filter engineering jobs (zero friction), or upload a resume to rank them by fit with
per-job skill overlap. A thin, polished Streamlit layer over the engine: ingestion (Phase 1),
embeddings/matching (Phase 3), optional structured extraction (Phase 2). Matching is 100% local
(no API, no quota); the "AI-analyze" toggle is the only LLM call and degrades gracefully.

Run:  uv run streamlit run web/app.py
"""

from __future__ import annotations

import hashlib
import html as html_lib
import io
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from apply_copilot.extract import extract_profile
from apply_copilot.llm import LLMError
from apply_copilot.match import Embedder, cosine, profile_to_text
from enrich import parse_salary, posted_ago
from jobs import (
    SENIORITY_ORDER,
    SNAPSHOT,
    load_jobs,
    load_or_build_vectors,
    refresh_snapshot,
    seniority_category,
    workplace_category,
)
from skills import extract_skills, overlap_and_gaps

GITHUB_URL = "https://github.com/AnvaySingh"  # the developer's profile
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

WORKPLACE_ICON = {"Remote": "🏠", "Hybrid": "🔀", "On-site": "🏢", "Unknown": "📍"}
WORKPLACE_CLASS = {"Remote": "b-remote", "Hybrid": "b-hybrid", "On-site": "b-onsite", "Unknown": "b-onsite"}
WORKPLACE_OPTIONS = ["Remote", "Hybrid", "On-site"]
TECH_OPTIONS = [
    "Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "C++", "React", "Node.js",
    "AWS", "Kubernetes", "Docker", "SQL", "PostgreSQL", "Machine Learning", "PyTorch",
    "Kafka", "Spark", "GraphQL", "Terraform",
]
AVATAR_COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"]

LIGHT = {
    "bg": "#f6f8f7", "surface": "#ffffff", "card": "#ffffff", "border": "#e6e8eb",
    "input-bg": "#ffffff", "text": "#111827", "sub": "#6b7280", "accent": "#0e8a6a",
    "sen-bg": "#eef2ff", "sen-fg": "#4338ca",
    "remote-bg": "#dcfce7", "remote-fg": "#166534",
    "hybrid-bg": "#fef9c3", "hybrid-fg": "#854d0e",
    "onsite-bg": "#f1f5f9", "onsite-fg": "#475569",
    "salary-bg": "#ecfccb", "salary-fg": "#3f6212",
    "date-bg": "#f3f4f6", "date-fg": "#6b7280",
    "match-bg": "#dcfce7", "match-fg": "#166534",
    "gap-bg": "#ffedd5", "gap-fg": "#9a3412",
    "tech-bg": "#eef2ff", "tech-fg": "#3730a3",
}
DARK = {
    "bg": "#0f1116", "surface": "#15171e", "card": "#15171e", "border": "#2a2e3a",
    "input-bg": "#1f2430", "text": "#e5e7eb", "sub": "#9ca3af", "accent": "#34d399",
    "sen-bg": "#1e293b", "sen-fg": "#93c5fd",
    "remote-bg": "#064e3b", "remote-fg": "#a7f3d0",
    "hybrid-bg": "#3f2d0a", "hybrid-fg": "#fde68a",
    "onsite-bg": "#1f2937", "onsite-fg": "#cbd5e1",
    "salary-bg": "#052e16", "salary-fg": "#86efac",
    "date-bg": "#1f2430", "date-fg": "#94a3b8",
    "match-bg": "#064e3b", "match-fg": "#a7f3d0",
    "gap-bg": "#7c2d12", "gap-fg": "#fed7aa",
    "tech-bg": "#1e1b4b", "tech-fg": "#c7d2fe",
}

STATIC_CSS = """
  #MainMenu, footer, [data-testid="stStatusWidget"] {visibility: hidden;}
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--bg) !important; }
  .block-container { padding-top: 1.4rem; max-width: 1080px; }
  section[data-testid="stSidebar"][data-testid="stSidebar"],
  [data-testid="stSidebarContent"][data-testid="stSidebarContent"] { background: var(--surface) !important; }
  section[data-testid="stSidebar"] { border-right: 1px solid var(--border) !important; }
  section[data-testid="stSidebar"] * { color: var(--text) !important; }
  section[data-testid="stSidebar"] [data-baseweb="select"] > div,
  section[data-testid="stSidebar"] [data-baseweb="base-input"],
  section[data-testid="stSidebar"] [data-baseweb="input"] > div,
  section[data-testid="stSidebar"] input { background: var(--input-bg) !important; border-color: var(--border) !important; }
  section[data-testid="stSidebar"] [data-baseweb="tag"] { background: var(--accent) !important; color: #fff !important; }
  h1,h2,h3,h4,h5,p,label,li,span,div,.stMarkdown,[data-testid="stWidgetLabel"] p { color: var(--text); }
  .stApp a { color: var(--accent); }
  .stTextInput input { border-radius: 12px; border: 1px solid var(--border); padding: .7rem 1rem; font-size: 1rem; background: var(--surface); }
  .brand { font-size: 1.7rem; font-weight: 800; letter-spacing: -.02em; }
  .brand span { color: var(--accent); }
  .tagline { color: var(--sub); font-size: .92rem; margin-top: -.15rem; }
  .topmeta { text-align: right; color: var(--sub); font-size: .82rem; }
  .topmeta a { text-decoration: none; font-weight: 600; }
  .result-head { color: var(--sub); font-size: .9rem; margin: .6rem 0 1rem; }
  .job-card {
    display: flex; gap: 14px; align-items: flex-start; background: var(--card);
    border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px;
    box-shadow: 0 1px 2px rgba(0,0,0,.04); transition: border-color .15s, transform .15s, box-shadow .15s;
  }
  .job-card:hover { border-color: var(--accent); transform: translateY(-1px); box-shadow: 0 4px 14px rgba(0,0,0,.08); }
  .avatar { width: 42px; height: 42px; border-radius: 10px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 1.1rem; }
  .job-main { flex: 1; min-width: 0; }
  .job-title { font-size: 1.05rem; font-weight: 650; color: var(--text); line-height: 1.25; }
  .job-company { font-size: .84rem; color: var(--sub); margin: .15rem 0 .55rem; }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .badge { font-size: .72rem; padding: 2px 9px; border-radius: 999px; white-space: nowrap; font-weight: 500; }
  .chip { font-size: .72rem; padding: 1px 9px; border-radius: 999px; margin: 0 5px 5px 0; display: inline-block; }
  .b-sen{color:var(--sen-fg);background:var(--sen-bg)} .b-remote{color:var(--remote-fg);background:var(--remote-bg)}
  .b-hybrid{color:var(--hybrid-fg);background:var(--hybrid-bg)} .b-onsite{color:var(--onsite-fg);background:var(--onsite-bg)}
  .b-salary{color:var(--salary-fg);background:var(--salary-bg)} .b-date{color:var(--date-fg);background:var(--date-bg)}
  .c-match{color:var(--match-fg);background:var(--match-bg)} .c-gap{color:var(--gap-fg);background:var(--gap-bg)}
  .c-tech{color:var(--tech-fg);background:var(--tech-bg)}
  .job-right { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; min-width: 86px; }
  .score { font-size: 1.7rem; font-weight: 800; line-height: 1; }
  .score-lbl { font-size: .66rem; color: var(--sub); margin-top: -2px; }
  .apply-btn { background: var(--accent); color: #fff !important; text-decoration: none !important; padding: 6px 15px; border-radius: 8px; font-size: .82rem; font-weight: 600; white-space: nowrap; }
  .apply-btn:hover { filter: brightness(1.08); }
"""

st.set_page_config(page_title="apply-copilot", page_icon="🧭", layout="wide")

theme = st.session_state.setdefault("theme", "light")
_palette = DARK if theme == "dark" else LIGHT
_root = "".join(f"--{k}:{v};" for k, v in _palette.items())
st.markdown(f"<style>:root{{{_root}}}{STATIC_CSS}</style>", unsafe_allow_html=True)


# -- cached resources ----------------------------------------------------------


@st.cache_resource(show_spinner=False)
def get_embedder() -> Embedder:
    return Embedder()


@st.cache_resource(show_spinner="Loading jobs, embeddings & facets…")
def get_data():
    embedder = get_embedder()
    jobs = load_jobs()
    vecs = load_or_build_vectors(jobs, embedder)
    cats = [workplace_category(j) for j in jobs]
    sens = [seniority_category(j) for j in jobs]
    jobskills = [extract_skills(f"{j.title} {j.description[:1500]}") for j in jobs]
    embedder.encode_one("warm up the model")
    return jobs, vecs, cats, sens, jobskills


# -- helpers -------------------------------------------------------------------


def read_resume(uploaded) -> str:
    if uploaded.name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(uploaded.getvalue()))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return uploaded.getvalue().decode("utf-8", errors="ignore")


def snapshot_age() -> str:
    try:
        secs = time.time() - os.path.getmtime(SNAPSHOT)
    except OSError:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def avatar(company: str) -> str:
    initial = html_lib.escape((company or "?").strip()[:1].upper())
    idx = int(hashlib.md5((company or "").encode()).hexdigest(), 16) % len(AVATAR_COLORS)
    return f"<div class='avatar' style='background:{AVATAR_COLORS[idx]}'>{initial}</div>"


def score_color(score: int) -> str:
    return "#22c55e" if score >= 60 else "#f59e0b" if score >= 45 else "#9ca3af"


def render_card(job, cat, sen, job_skills, score, cand_skills) -> str:
    esc = html_lib.escape
    loc = (job.location or "").strip()
    loc = (loc[:38] + "…") if len(loc) > 40 else loc

    b = [f"<span class='badge b-sen'>{esc(sen)}</span>",
         f"<span class='badge {WORKPLACE_CLASS.get(cat, 'b-onsite')}'>{WORKPLACE_ICON.get(cat, '')} {esc(cat)}</span>"]
    sal = parse_salary(job.description)
    if sal:
        b.append(f"<span class='badge b-salary'>💰 {esc(sal)}</span>")
    ago = posted_ago(job)
    if ago:
        b.append(f"<span class='badge b-date'>🕑 {esc(ago)}</span>")

    chips = ""
    if cand_skills is not None:
        overlap, gaps = overlap_and_gaps(cand_skills, f"{job.title} {job.description[:2000]}")
        chips += "".join(f"<span class='chip c-match'>{esc(s)}</span>" for s in overlap[:7])
        chips += "".join(f"<span class='chip c-gap'>{esc(s)}</span>" for s in gaps[:5])
    else:
        chips += "".join(f"<span class='chip c-tech'>{esc(s)}</span>" for s in sorted(job_skills)[:8])

    right = ""
    if score is not None:
        right += f"<div class='score' style='color:{score_color(score)}'>{score}</div><div class='score-lbl'>match</div>"
    if job.url:
        right += f"<a class='apply-btn' href='{esc(job.url)}' target='_blank' rel='noopener'>Apply ↗</a>"

    company_line = esc(job.company) + (f" · {esc(loc)}" if loc else "") + f" · {esc(job.source)}"
    return (
        f"<div class='job-card'>{avatar(job.company)}<div class='job-main'>"
        f"<div class='job-title'>{esc(job.title)}</div>"
        f"<div class='job-company'>{company_line}</div>"
        f"<div class='badges'>{''.join(b)}</div><div>{chips}</div></div>"
        f"<div class='job-right'>{right}</div></div>"
    )


# -- header --------------------------------------------------------------------

jobs, vecs, cats, sens, jobskills = get_data()

h_left, h_right = st.columns([5, 1.15])
with h_left:
    st.markdown("<div class='brand'>🧭 apply<span>-copilot</span></div>", unsafe_allow_html=True)
    st.markdown("<div class='tagline'>Curated engineering roles — ranked to your resume.</div>", unsafe_allow_html=True)
with h_right:
    if st.button(("🌙 Dark" if theme == "light" else "☀️ Light"), use_container_width=True):
        st.session_state["theme"] = "dark" if theme == "light" else "light"
        st.rerun()
    st.markdown(
        f"<div class='topmeta'>Updated {snapshot_age()} · <a href='{GITHUB_URL}' target='_blank'>GitHub ↗</a></div>",
        unsafe_allow_html=True,
    )

search = st.text_input("search", placeholder="🔍  Search by title, company, or location…", label_visibility="collapsed")

# -- sidebar filters -----------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    workplace = st.multiselect("Workplace", WORKPLACE_OPTIONS, default=WORKPLACE_OPTIONS)
    seniority = st.multiselect("Seniority", SENIORITY_ORDER, default=SENIORITY_ORDER)
    tech = st.multiselect("Tech stack", TECH_OPTIONS, help="Show jobs mentioning any selected tech.")
    top_n = st.slider("Results to show", 5, 40, 12)
    st.divider()
    use_ai = st.toggle("✨ AI-analyze my resume", value=False,
                       help="Extracts a structured profile via the LLM (1 API call). Optional.")
    if st.button("↻ Refresh job feed", use_container_width=True):
        with st.spinner("Ingesting live…"):
            refresh_snapshot()
        get_data.clear()
        st.rerun()
    st.caption(f"{len(jobs)} jobs · public ATS boards + RSS · read-only, no scraping.")

wp_all = set(workplace) == set(WORKPLACE_OPTIONS)
sn_all = set(seniority) == set(SENIORITY_ORDER)
tech_set = set(tech)
q = search.strip().lower()

# -- resume input (optional) ---------------------------------------------------

with st.expander("📄 Upload a resume to rank jobs by fit (optional)", expanded=False):
    col_a, col_b = st.columns([3, 1])
    uploaded = col_a.file_uploader("Resume (PDF or .txt)", type=["pdf", "txt"], label_visibility="collapsed")
    if col_b.button("Use sample", use_container_width=True):
        st.session_state["_sample"] = True
    if col_b.button("Clear", use_container_width=True):
        st.session_state.pop("_sample", None)

resume_text = ""
if uploaded is not None:
    resume_text = read_resume(uploaded)
elif st.session_state.get("_sample"):
    sample = Path(__file__).resolve().parent.parent / "evals" / "phase2" / "fixtures" / "resume_1.txt"
    resume_text = sample.read_text(encoding="utf-8") if sample.exists() else ""

cand_skills = None
query_vec = None
if resume_text.strip():
    query_text = resume_text
    profile = None
    if use_ai:
        with st.spinner("Analyzing your resume with AI…"):
            try:
                profile = extract_profile(resume_text)
                query_text = profile_to_text(profile) or resume_text
                c1, c2, c3 = st.columns(3)
                c1.metric("Seniority", profile.seniority.value)
                c2.metric("Years", profile.years_experience if profile.years_experience is not None else "—")
                c3.metric("Skills found", len(profile.skills))
            except LLMError as exc:
                st.warning(f"AI analysis unavailable ({exc}). Using raw resume text.")
    cand_skills = extract_skills(resume_text)
    if profile and profile.skills:
        cand_skills |= extract_skills(" ".join(profile.skills))
    query_vec = get_embedder().encode_one(query_text)

# -- filter → rank/sort → render -----------------------------------------------


def _matches_search(i: int) -> bool:
    if not q:
        return True
    return q in f"{jobs[i].title} {jobs[i].company} {jobs[i].location or ''}".lower()


idx = [
    i for i in range(len(jobs))
    if (wp_all or cats[i] in workplace)
    and (sn_all or sens[i] in seniority)
    and (not tech_set or (jobskills[i] & tech_set))
    and _matches_search(i)
]

if query_vec is not None:
    ranked = sorted(idx, key=lambda i: cosine(query_vec, vecs[i]), reverse=True)
    mode = "ranked by fit to your resume"
else:
    def _posted(i):
        dt = jobs[i].posted_at or jobs[i].updated_at
        if dt is None:
            return _EPOCH
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    ranked = sorted(idx, key=_posted, reverse=True)
    mode = "newest first — upload a resume to rank by fit"

st.markdown(
    f"<div class='result-head'><b>{len(idx)}</b> jobs match · showing {min(len(idx), top_n)} · {mode}</div>",
    unsafe_allow_html=True,
)

if not idx:
    st.warning("No jobs match these filters. Try widening them or clearing the search.")
    st.stop()

cards = []
for i in ranked[:top_n]:
    score = int(round(max(0.0, cosine(query_vec, vecs[i])) * 100)) if query_vec is not None else None
    cards.append(render_card(jobs[i], cats[i], sens[i], jobskills[i], score, cand_skills))
st.markdown("\n".join(cards), unsafe_allow_html=True)

st.caption(
    "A copilot: it finds and ranks jobs; you review and apply yourself. Matching is local — your "
    "resume never leaves your machine unless you enable AI analysis."
)
