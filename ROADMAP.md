# ROADMAP.md — Zapply

Seven phases. Each one teaches one applied-AI-engineering (or data-engineering) concept, closes with a program-gate eval (per the core principle in `CLAUDE.md`), and produces the raw material for one dev.to post. Build them in order. Stop at each boundary for review.

The throughline of the whole series: "I rebuilt Employable's brain — the ingestion, matching, and drafting — without its hands, on purpose, and here's what each piece actually taught me."

## Phase 0 — Scaffolding & observability

Concept: the unglamorous plumbing every LLM app needs, and tracing from day one.

Build:

* Repo scaffold per the layout in `CLAUDE.md` (`uv`, `pyproject.toml`, `.env.example`).
* `llm/` — a thin, provider-agnostic client wrapping the Anthropic SDK. One `complete()` and one `complete_structured()` entry point.
* Langfuse tracing wired through that client so every call is traced automatically.
* A Typer CLI skeleton with a `hello`/`trace-test` command that makes one traced call.

Program gate / Definition of done:

* `trace-test` runs and the call appears as a trace in Langfuse.
* No business logic yet — this phase is done when the seam and the telescope both work.

dev.to post: "Before you build an AI app, build the telescope: tracing an LLM app from line one."

## Phase 1 — Automated ingestion & normalisation

Concept: pulling job openings automatically from heterogeneous, consumption-friendly sources; normalising them into one schema; deduping; refreshing incrementally. This is the aggregation muscle (same shape as a news/RSS aggregator) — no AI yet, and no scraping.

Build:

* A `JobPosting` Pydantic model — the one internal shape every source normalises into.
* `ingest/` with a small pluggable source interface, and these adapters:
   * Greenhouse (`boards.greenhouse.io/embed/job_board?for=<company>`)
   * Lever (`api.lever.co/v0/postings/<company>`)
   * Ashby (public board endpoint)
   * RSS feed adapter
   * a paste/file adapter for one-off JDs
* A curated `companies.yaml` I control (the companies/boards to poll).
* Dedup across sources (same role surfacing on two feeds collapses to one).
* Incremental refresh — re-polling only surfaces genuinely new postings.
* Hold the line: every source here is read-only and built to be consumed. No portal search-scraping, no login. If an adapter can't be built without those, stop and flag it.

Program gate:

* `evals/phase1/` with recorded raw payloads from each source type as fixtures.
* Eval asserts: (a) every source normalises to a schema-valid `JobPosting`, (b) the deduper collapses a known set of duplicate fixtures to the expected count, (c) incremental refresh over a before/after fixture pair yields exactly the expected new items. All program-decided.

dev.to post: "Automating job discovery without scraping: normalising Greenhouse, Lever, Ashby and RSS into one clean feed."

## Phase 2 — Structured extraction

Concept: turning unstructured text into validated structured data — the 80% of real LLM work. Tool/function calling, JSON mode, Pydantic validation, handling malformed output.

Build:

* `Profile` and `Requirements` Pydantic v2 models (skills, experience, education, work auth, seniority, etc.).
* `extract/` — resume → `Profile`, and each ingested `JobPosting` → `Requirements`, first via native tool calling, then a second implementation via `instructor`. Keep both; compare them in `NOTES.md`.
* Robust handling: retries on invalid output, clear failure when a field can't be filled.

Program gate:

* `evals/phase2/` with 5–10 labelled resumes/JDs (hand-annotate the correct fields).
* Eval asserts: (a) 100% schema-valid output, (b) field-level extraction accuracy above a threshold you set against the labels. Gate is code comparing to labels — not the model grading itself.

dev.to post: "Native tool-calling vs instructor: two ways to get structured data out of an LLM, and when each one bites you."

## Phase 3 — Semantic matching

Concept: embeddings and semantic scoring. Why cosine similarity beats keyword overlap, and where it quietly fails.

Build:

* `match/` — embed `Profile` and each `Requirements`, score similarity, emit a 0–100 match score plus a short rationale.
* Start naive: local `sentence-transformers` + in-memory cosine. No vector DB yet.
* In `NOTES.md`, document one case where pure embedding similarity gives a wrong-feeling score, and what a re-ranking or hybrid approach would do about it.

Program gate:

* `evals/phase3/` with ~15 (profile, JD) pairs you've hand-ranked by true fit.
* Eval measures rank correlation (e.g. Spearman) between the system's scores and your labels, against a threshold. Program-decided, not vibe-decided.

dev.to post: "Matching jobs to a resume with embeddings — and the case where cosine similarity confidently lies."

## Phase 4 — Grounded drafting

Concept: grounded generation and anti-hallucination. Context construction, and keeping a model faithful to source (my real profile) instead of inventing impressive filler.

Build:

* `draft/` — given `Profile` + `Requirements`, draft (a) answers to screening questions and (b) tailored resume bullets. Every claim must trace to something in the profile.
* Deliberately construct the context so the model can't invent employers, dates, or skills I don't have. Document the prompt/context strategy in `NOTES.md`.

Program gate:

* `evals/phase4/` with a faithfulness check: an LLM-as-judge scoring each generated claim as supported / unsupported by the profile, plus a programmatic factuality check (e.g. every company/skill named in a bullet must exist in the `Profile`). The programmatic check is the real gate; the judge is a signal.
* Also a relevance check: does the answer actually address the question.

dev.to post: "Stop your job-application AI from lying about you: building a faithfulness gate for grounded generation."

## Phase 5 — Orchestration & the review gate

Concept: multi-agent orchestration and human-in-the-loop (maker-checker). Composing the pieces into one loop with a program-gated handoff to me.

Build:

* `orchestrate/` — wire ingest → extract → match → draft into one pipeline over a batch of ingested postings. Model it as distinct agents (matcher / drafter) with clear contracts.
* A review gate: the pipeline stops and presents each application for my approval/edit before it's packaged. Nothing is "finished" without my check.
* `packet/` — render the approved result into a clean, paste-ready output (resume + answers + rationale) I take to the portal myself.
* Optional stretch: introduce a Redis-backed queue if (and only if) batch orchestration genuinely needs it — connect it to my BullMQ experience, note the parallels.

Program gate:

* An end-to-end eval that runs the full pipeline on a fixture batch and asserts each stage's contract holds (valid handoffs, no stage silently passing bad data). The review gate is enforced in code — the pipeline cannot emit a packet that wasn't approved.

dev.to post: "Maker-checker for AI pipelines: why the human gate is a program, not a polite suggestion."

## Phase 6 — The hands (optional), against a friendly target only

Concept: browser / computer-use agents — grounding an LLM in a live DOM. The highest-value, least-commoditised agent skill, learned without touching a real portal.

Build:

* A friendly target: either a mock application form served locally from this repo, or a public sandbox/ATS form built to receive applications. Never a real job portal.
* `fill/` — a browser agent (Browser Use or Skyvern) that takes an approved packet and completes the friendly form: field mapping, dropdowns/radios, resume upload, multi-step navigation, inline screening answers routed to the Phase 4 drafter.
* Build the naive agent loop understanding first (perceive → decide → act → observe) before leaning fully on the library.

Program gate (this is the whole point):

* `[verify]` — a deterministic post-submit assertion: DOM/URL confirmation state and a saved screenshot. The agent's claim that it submitted is irrelevant; only the program's verdict counts. Failure → retry / stuck-detection / pause. This is the core principle in its purest form.

dev.to post: "I gave an LLM hands and pointed it at a form — every place it broke, and the program-gate that told me the truth."

## Series closer (write after Phase 5 or 6)

"Why my job-application AI stops one click short — the architecture decision that removed all the risk and kept all the learning." This is the post that explains the copilot-not-autopilot choice (automate the reading, never the writing) and why, given funded incumbents already owning the autopilot market, the interesting engineering was always in the brain.
