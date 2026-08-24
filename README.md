# apply-copilot

A personal, local, single-user **job-application copilot** — Employable's brain without its hands.
It takes you all the way *up to* the submit button and hands you a finished packet (tailored
resume, drafted screening answers, match rationale) that **you** paste and submit yourself.

> **Copilot, never autopilot.** Automated *reading* of openings is in scope; automated *writing*
> (logging into or submitting on a real portal) never is. See [`CLAUDE.md`](CLAUDE.md) for the full
> guardrail and [`ROADMAP.md`](ROADMAP.md) for the phased curriculum.

This is a learning project built strictly phase by phase. Each phase teaches one applied-AI
concept and closes with a deterministic **program-gate eval**.

📚 **Docs:** [`CONCEPTS.md`](CONCEPTS.md) — the AI concepts with code pointers + interview
talking points · [`NOTES.md`](NOTES.md) — the per-phase story · [`ROADMAP.md`](ROADMAP.md) — the
curriculum.

## Status

**Phase 5 — Orchestration & the review gate** ✅ One pipeline (ingest → prefilter → extract →
match → draft) with agents + contracts, a **program-enforced human review gate** (a packet cannot
be built without approval, and a draft that fails faithfulness cannot be approved), and a
paste-ready `packet/` renderer. Two-tier for cost: local embedding prefilter over all postings,
LLM only on the top-K. End-to-end contract eval in `evals/phase5/`.

**Phase 4 — Grounded drafting** ✅ Tailored bullets + screening answers from `Profile` +
`Requirements`, grounded by an explicit fact sheet. A **programmatic faithfulness gate**
(no skill/employer claimed outside the profile) is the real gate; an LLM judge + relevance floor
are signals. Deterministic gate in `evals/phase4/` (the live drafting test is opt-in).

**Phase 3 — Semantic matching** ✅ Local `sentence-transformers` embeddings of `Profile` vs
`Requirements`, cosine → 0–100 score + a grounded, programmatic rationale. Spearman
rank-correlation eval (ρ = 0.92 vs hand-ranked pairs) in `evals/phase3/`.

**Phase 2 — Structured extraction** ✅ Resume → `Profile` and JD → `Requirements`, via two
interchangeable backends (native tool-calling through our seam, and `instructor`). Field-level
accuracy eval against hand-labelled fixtures in `evals/phase2/`.

**Phase 1 — Automated ingestion & normalisation** ✅ Read-only adapters for Greenhouse, Lever,
Ashby, and RSS (plus a paste/file adapter) normalise into one `JobPosting` schema, with
cross-source dedup and incremental refresh. No scraping, no login, no AI.

**Phase 0 — Scaffolding & observability** ✅ Provider-agnostic LLM client (Gemini/Anthropic/
OpenAI-compatible), Langfuse tracing, Typer CLI.

## Setup

Requires [`uv`](https://docs.astral.sh/uv/) and Python 3.12 (uv will fetch it).

```bash
# 1. Install dependencies into a local venv
uv sync

# 2. Configure secrets
cp .env.example .env
#   then edit .env — set GEMINI_API_KEY (free, no credit card):
#   get one at https://aistudio.google.com/app/apikey
#   Langfuse keys are optional: without them, tracing is a silent no-op.
```

### Picking a provider

The LLM is behind a swappable seam. `LLM_PROVIDER` in `.env` chooses the vendor — one switch,
no code change:

| `LLM_PROVIDER` | Needs | Notes |
|---|---|---|
| `gemini` (default) | `GEMINI_API_KEY` | Free tier, no credit card |
| `anthropic` | `ANTHROPIC_API_KEY` | Claude (paid) |
| `openai` | `OPENAI_API_KEY` + `OPENAI_BASE_URL` | Any OpenAI-compatible endpoint: OpenAI, Groq, Ollama, OpenRouter |

## Usage

```bash
# Sanity check — no API call, no keys needed
uv run apply-copilot hello

# Make one real, traced LLM call (needs your provider's key)
uv run apply-copilot trace-test
```

`trace-test` makes a single `complete()` call through the `llm/` client. If Langfuse keys are set,
the call shows up as a trace in your Langfuse dashboard — that's the Phase 0 definition of done.

### Ingestion (Phase 1)

```bash
# Poll every read-only source in companies.yaml → normalise → dedup → show NEW postings
uv run apply-copilot ingest

# See every unique posting (not just new), cap the table
uv run apply-copilot ingest --all --limit 15

# Dry run — don't update the incremental-refresh state
uv run apply-copilot ingest --no-persist

# Ingest a single pasted/downloaded JD file through the same pipeline
uv run apply-copilot ingest-file jd.txt --company "Acme" --title "Backend Engineer"
```

Curate the sources you poll in [`companies.yaml`](companies.yaml). Every source is a
public, read-only endpoint (ATS JSON or RSS) — no scraping, no login.

### Extraction & matching (Phases 2–3)

```bash
# Resume → structured Profile (native tool-calling, or --backend instructor)
uv run apply-copilot extract-resume evals/phase2/fixtures/resume_1.txt

# JD → structured Requirements
uv run apply-copilot extract-jd evals/phase2/fixtures/jd_1.txt

# Score a resume against a JD: extract both, embed, compare (0–100 + rationale)
uv run apply-copilot match --resume evals/phase2/fixtures/resume_1.txt \
                           --jd evals/phase2/fixtures/jd_1.txt
```

> Extraction uses the LLM (Gemini free tier is **20 requests/day** for `gemini-3.6-flash`).
> Matching itself is fully local — embeddings run on your machine, no API.

### The full pipeline (Phase 5)

```bash
# Ingest → local prefilter → extract + match + draft the top-K → review → packet.
# Stops for your approval on each draft; writes approved packets to ./packets/.
uv run apply-copilot apply --resume my_resume.txt --top-k 3

# Non-interactive (auto-approve faithful drafts) — handy for a quick run:
uv run apply-copilot apply --resume my_resume.txt --top-k 2 --yes
```

Only the **top-K** postings get the (LLM-costed) extract + draft, so a ~1,000-posting feed still
fits the daily quota. A draft that fails the faithfulness gate is **blocked** — you're never
offered it — and no packet is written without your approval.

### Demo web app

A polished [Streamlit](https://streamlit.io) UI over the engine: **browse and filter** engineering
jobs, or **upload a resume** to rank them by fit with per-job skill overlap.

```bash
uv run streamlit run web/app.py
```

- **Zero-friction browsing** — no resume needed to explore; upload one to switch to fit-ranking.
- **Faceted filters** (all local, no LLM): **Workplace** (Remote/Hybrid/On-site), **Seniority**
  (Intern→Manager), and **Tech stack** — each posting is classified from its title/text.
- **Enriched cards**: company avatar, seniority + workplace badges, **salary** (parsed from the
  posting), **posted date**, and skill chips (✓ matches / gaps vs your resume, or the job's tech).
- **Matching is 100% local** (embeddings on your machine) — no API, no quota, works offline.
- Jobs come from a **snapshot** (`data/`, gitignored); the sidebar's *Refresh* re-ingests live.
  First run builds the snapshot + embeddings; after that startup is fast.
- The optional **"✨ AI-analyze"** toggle extracts a structured profile via the LLM (1 call) and
  degrades gracefully if the daily quota is out.

## Layout

```
src/apply_copilot/
├── llm/          # provider-agnostic client + Langfuse tracing   (Phase 0 — built)
├── ingest/       # ATS JSON / RSS / paste → normalise + dedup     (Phase 1 — built)
├── extract/      # resume→Profile, JD→Requirements (structured)   (Phase 2 — built)
├── match/        # embeddings + scoring + rationale               (Phase 3 — built)
├── draft/        # grounded screening answers + tailored bullets  (Phase 4 — built)
├── orchestrate/  # pipeline wiring + review gate                  (Phase 5 — built)
├── packet/       # final paste-ready output                       (Phase 5 — built)
└── fill/         # browser agent vs a friendly form               (Phase 6, optional)
```
