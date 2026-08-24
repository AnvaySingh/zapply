# CLAUDE.md — Zapply

Persistent context for this repo. Read this fully before doing anything. This is a learning project. The point is not to ship a product — it is for me to build, by hand, the full applied-AI-engineering stack (structured extraction, embeddings, grounded generation, orchestration, evals, observability). Optimise every decision for what it teaches me, not for speed or feature count.

## What this is

`zapply` is a personal, local, single-user job-application copilot.

It does everything up to the submit button and hands me a finished packet — a tailored resume, drafted screening answers, and a match rationale — which I then paste into the portal and submit myself.

It is Employable's brain without its hands: same intelligence pipeline (profile, matching, drafting, tailoring), minus the autonomous form-submission worker.

## The one rule that overrides everything

This is a copilot, never an autopilot. The line is read vs. write: automated reading of job openings is fine; automated writing (applying) is not. A human (me) makes the final submit, always.

Do NOT, at any phase, build any of the following. If a task seems to require them, stop and flag it instead of proceeding:

* Automated login to, or automated submission on, Naukri / LinkedIn / Foundit / any live job portal.
* Any anti-bot evasion: proxies, stealth browsers, fingerprint spoofing, CAPTCHA solving, OTP-defeating.
* Scraping a portal's search feed behind its anti-bot / at scale (e.g. harvesting the full Naukri or LinkedIn feed), or storing other people's data.

Ingestion IS automated — but only from consumption-friendly, read-only sources that are built to be pulled: public ATS job-board endpoints (Greenhouse/Lever/Ashby JSON), RSS feeds, and legitimate job APIs. Also accept pasted JDs and local files. Gentle footprint, no login anywhere.

The boundary to hold: comprehensive Naukri/LinkedIn-style coverage would require the scraping-behind-anti-bot path above — that is out of scope. If I ever ask for it, treat it as a scope change that alters the risk profile and confirm with me explicitly; do not add it on your own initiative.

The browser-agent work in Phase 6 (the "hands") is exercised only against a friendly target — a mock form I host locally, or a public sandbox application — never a real portal. The skill is "ground an LLM in a live DOM"; the target is chosen to be one that welcomes automation.

## Core engineering principle

Gates are always programs, never model opinions.

Every loop in this system is closed by a deterministic check, not by the model asserting it succeeded. "The answer is faithful" is decided by an eval harness, not by the drafting model saying so. "The form submitted" (Phase 6) is decided by a DOM/URL assertion + a saved screenshot, not by the agent claiming it clicked. When you add a step that produces model output, you also add the program that judges it.

## Architecture (the pipeline)

```
  ATS boards / RSS / job APIs / paste ─▶ [ingest] ─▶ normalised, deduped JDs
                                                        │
                              resume ─▶ [extract] ─▶ Profile (structured)
                                  JD ─▶ [extract] ─▶ Requirements (structured)
                          │
                          ▼
                     [match] ─▶ score + rationale   (embeddings)
                          │
                          ▼
                     [draft] ─▶ screening answers + tailored bullets  (grounded)
                          │
                          ▼
              [review gate] ─▶ I approve / edit     (maker-checker, human)
                          │
                          ▼
                     [packet] ─▶ everything I need to paste & submit myself
```

Phase 6 (optional) adds a `[fill]` agent that takes the approved packet and completes a friendly form, closed by a program-gate `[verify]` step. It never runs against a real portal.

## Stack (defaults — confirmed decisions marked ✓)

* Language: **Python 3.12** ✓ (confirmed). The agent/eval ecosystem (Browser Use, Skyvern, Langfuse, instructor) is Python-native.
* Env/deps: `uv`.
* LLM: wrapped behind a thin, provider-agnostic `llm/` client so the provider is swappable — I want to learn the seam, not hardcode a vendor. **Dev default: Google Gemini free tier** ✓ (confirmed — free, no credit card), via its OpenAI-compatible endpoint. Anthropic (Claude) and any OpenAI-compatible endpoint (Groq/Ollama/OpenAI) are first-class alternatives selected by the `LLM_PROVIDER` env var — one switch, no code change.
* Ingestion sources: start with public ATS endpoints (Greenhouse `boards.greenhouse.io/embed/job_board?for=…`, Lever `api.lever.co/v0/postings/…`, Ashby) plus RSS and a curated list of companies I care about; add legitimate job APIs later. Normalise every source into one internal `JobPosting` schema. No portal scraping.
* Structured outputs: Pydantic v2, taught first via native tool/function calling, then compared against `instructor`. I want to feel the difference.
* Embeddings / matching: **local `sentence-transformers`** ✓ (confirmed) + in-memory cosine similarity. Note Voyage/OpenAI hosted embeddings and FAISS/Chroma as the upgrade path — do not reach for them until the naive version is understood.
* Evals: `pytest` for programmatic/gate evals; `promptfoo` (config-driven) for generation-quality evals in Phases 3–4. Every phase ships with its eval.
* Observability: Langfuse (self-hosted or free tier), tracing wired in from Phase 0.
* Browser agent (Phase 6 only): Browser Use or Skyvern, against a friendly target.
* Interface: Typer CLI first. A UI comes later if at all (I do Angular; resist the urge to build it early — it's not what this project is teaching).
* Queue (Phase 5+, optional): Redis + a job queue — I have BullMQ experience and want the Python equivalent as a stretch, but only if orchestration genuinely needs it. Don't add it to look impressive.
* Deploy (optional, late): Azure Container Apps / Functions, to connect this to my DevOps track. Local-first until then.

## How to work in this repo

1. Read `ROADMAP.md` before starting any phase. Build strictly phase by phase. Do not pull work forward from a later phase because it's convenient — the sequencing is the curriculum.
2. Eval-first within a phase. Write (or scaffold) the phase's eval and its small labelled dataset before or alongside the implementation. A phase is not done until its program-gate eval passes on the fixtures.
3. Stop at every phase boundary. When a phase's Definition of Done is met, summarise what was built, show the eval results, and wait for me to review before moving on. This is the maker-checker discipline — you make, I check.
4. Teach as you go. For each new concept, add a short `NOTES.md` entry (3–8 sentences) in plain language explaining the concept and the specific tradeoff we chose. These notes are the raw material for a dev.to post per phase — write them for a reader, not for me.
5. Prefer the naive version first. When there's a "proper" heavy tool and a hand-rolled minimal version, build the minimal one first so I understand the problem, then note when and why the heavy tool would earn its place. Concepts before plumbing.
6. Keep secrets in `.env` (gitignored). Never hardcode keys.

## Repo layout (target)

```
zapply/
├── CLAUDE.md              # this file
├── ROADMAP.md             # the phased curriculum
├── NOTES.md               # per-phase learning notes (blog raw material)
├── pyproject.toml
├── .env.example
├── src/zapply/
│   ├── llm/               # provider-agnostic client + tracing
│   ├── ingest/            # automated: ATS JSON, RSS, job APIs, paste → normalise + dedup
│   ├── extract/           # resume→Profile, JD→Requirements (structured)
│   ├── match/             # embeddings + scoring + rationale
│   ├── draft/             # grounded screening answers + tailored bullets
│   ├── orchestrate/       # pipeline wiring + review gate
│   ├── packet/            # final output the human pastes
│   └── fill/              # Phase 6 ONLY: browser agent vs friendly target
├── evals/                 # datasets + harnesses, one dir per phase
└── fixtures/              # sample resumes, JDs, labelled data
```

## Definition of done — applies to every phase

* Code runs from the CLI on a real fixture.
* The phase's program-gate eval exists and passes on the labelled fixtures.
* A Langfuse trace is visible for the phase's LLM calls.
* A `NOTES.md` entry explains the concept and our tradeoff, readable by an outsider.
* You have stopped and asked me to review before touching the next phase.
