# CONCEPTS.md — the applied-AI stack behind apply-copilot

A study + interview-prep companion to this repo. `NOTES.md` tells the *story* of each phase;
this file is the *reference*: every AI/ML-engineering concept the project uses, in plain
language, with **where it lives in the code** and **how to talk about it in an interview**.

**How to use it.** Read a concept, then open the file it points to and connect the idea to the
lines. For interviews, each concept has a "Say this" block — a crisp, senior-sounding answer —
and the end has a rapid-fire Q&A bank.

> One framing worth internalising up front: this project is **applied AI engineering — building
> systems *around* pre-trained models**. It is *not* about training or fine-tuning models. That
> distinction itself is a common interview opener (see the last section).

---

## The big picture (the one-paragraph version)

apply-copilot is a pipeline: **ingest** job postings from read-only sources → **extract**
structured data from a resume and each JD → **match** them with embeddings → **draft** tailored,
*grounded* application text → **human review gate** → **packet** you paste and submit. Every
stage is closed by a **deterministic program that judges the model's output** — never the model
judging itself. That single principle ("gates are programs, not model opinions") is the spine of
the whole thing and the best one-liner to lead with.

---

## 1. The provider seam (LLM abstraction)

**What it is.** A thin layer that every part of the app calls instead of talking to a vendor SDK
directly. Swapping models/vendors becomes a config change, not a rewrite.

**How this project uses it.** `src/apply_copilot/llm/client.py` exposes exactly two entry points
— `complete()` (free text) and `complete_structured()` (validated object). `providers.py` has
two adapters: `AnthropicProvider` (native Anthropic API) and `OpenAICompatibleProvider`
(anything speaking the OpenAI chat protocol — Gemini, Groq, Ollama, OpenAI). `config.py` picks
one via the `LLM_PROVIDER` env var. We develop on Gemini's free tier and can flip to a local
Ollama with one variable.

**Why it matters.** Vendor lock-in is a real risk; pricing, rate limits, and quality change. A
seam also gives you one place to add tracing, retries, and fallbacks.

> **Say this:** "I put all model calls behind one interface with two methods, so the provider is
> data, not code. It also gave me a single choke point to bolt tracing and a structured-output
> fallback onto — the payoff of the seam showed up immediately when I switched Claude → Gemini
> for the free tier without touching business logic."

---

## 2. Observability / tracing for LLM apps

**What it is.** Recording every model call — its inputs, output, model, token usage, latency — so
you can debug and measure. LLM calls fail *semantically* (a subtly wrong answer, not a stack
trace), so if you can't replay a call you can't debug it.

**How this project uses it.** `src/apply_copilot/llm/tracing.py` wraps each call in a
[Langfuse](https://langfuse.com) "generation" span, *inside the seam*, so instrumentation is
automatic — you can't make an untraced call. It degrades to a no-op when keys are absent.

**Why it matters.** Non-determinism + no logs = undebuggable. Wiring observability from line one
is the "build the telescope before the ship" discipline.

> **Say this:** "I treat tracing as day-one plumbing, not an afterthought. Because it lives in
> the provider seam, every call is traced by construction, and I can see prompt, output, and
> token usage per call in a dashboard."

**Gotcha to mention:** short-lived processes must *flush* traces before exiting or the batch
never leaves the machine.

---

## 3. Structured outputs: tool-calling vs JSON mode

**What it is.** Getting *validated, typed data* out of an LLM instead of prose. Two techniques:
- **Tool/function calling** — hand the model your schema as a "tool" it's forced to call; its
  arguments *are* your object.
- **JSON mode** — ask for a JSON object (`response_format={"type":"json_object"}`) with the schema
  in the prompt, then parse.
Both are followed by **schema validation** (Pydantic) — the program decides the output is usable.

**How this project uses it.** `complete_structured()` uses forced tool-calling; the extractors
(`src/apply_copilot/extract/native.py`) turn a resume→`Profile` and a JD→`Requirements`
(`extract/models.py`). When Gemini's forced tool-calling flaked on long inputs and returned no
tool call, the OpenAI-compatible provider now **falls back to JSON mode**
(`llm/providers.py::_json_mode`, with a lenient parser). We also built a second implementation
with the **`instructor`** library (`extract/instructor_impl.py`) to feel the difference.

**Why it matters.** ~80% of production "LLM work" is text-in, structured-data-out. Reliability of
that step is everything downstream.

> **Say this:** "Structured extraction is the workhorse. I did it by hand with forced
> tool-calling + Pydantic validation, and again with `instructor`. Hand-rolling taught me the
> failure modes — e.g., Gemini's OpenAI-compatible endpoint intermittently ignores a forced tool
> call on long inputs — which I fixed with a JSON-mode fallback inside my provider. `instructor`
> hides that machinery; owning the seam let me patch it without changing call sites."

**Interview gold:** native-vs-`instructor` tradeoff — library = less code + built-in retries;
hand-rolled = full control, own tracing, and you understand what broke.

---

## 4. Validation & retry loops

**What it is.** Treating model output as *untrusted* until a program validates it, and retrying
(often feeding the error back) on failure.

**How this project uses it.** `extract/native.py::_extract` retries up to N times, appending the
validation error to the prompt. Validation is `response_model.model_validate(...)` in
`llm/client.py` — invalid output raises, it never silently passes.

> **Say this:** "The model proposes; Pydantic disposes. I never trust the shape of model output —
> validation is a hard gate, and on failure I re-prompt with the specific error."

---

## 5. Embeddings & semantic similarity

**What it is.** An **embedding** maps text to a vector so that *similar meaning → nearby vectors*.
**Cosine similarity** measures the angle between two vectors (1 = identical direction). This beats
keyword overlap ("K8s" vs "Kubernetes", "ML" vs "machine learning").

**How this project uses it.** `src/apply_copilot/match/` — `embed.py` runs a **local**
`sentence-transformers` model (`all-MiniLM-L6-v2`, 384-dim), `represent.py` decides *what text*
to embed (a real modelling lever), `matcher.py` scores a `Profile` vs `Requirements` (0–100) and
adds a programmatic rationale. Naive-first: in-memory cosine, no vector DB.

**Why it matters.** Semantic retrieval/ranking is the backbone of search, RAG, recommendations,
and dedup.

> **Say this:** "Matching is embeddings + cosine, run locally so it's free and I understand it.
> The serialisation — what fields I turn into the embedded string — mattered more than the model
> choice."

**The failure you should be able to name:** cosine measures *vocabulary proximity, not fit*. In
my eval the worst-fit role (Enterprise Account Executive) out-scored a closer one (Technical
Product Manager) because the PM's jargon sits far from engineering text. Fixes: blend in explicit
skill-overlap (hybrid), or a **cross-encoder re-ranker** (scores the pair jointly), and a **vector
DB / ANN index** (FAISS/Chroma) once you have thousands of items.

---

## 6. Evaluating a ranker: rank correlation (Spearman)

**What it is.** For a system that *orders* things, you don't grade absolute numbers — you ask "is
the ordering right?" **Spearman's rho** is correlation computed on ranks (−1 reversed, +1
identical).

**How this project uses it.** `evals/phase3/rank_metrics.py` (hand-rolled, unit-tested) scores the
matcher's ordering of 15 hand-ranked roles: **ρ = 0.92**, gated at ≥ 0.6.

> **Say this:** "I evaluated the matcher with Spearman against a hand-ranking — the right question
> for a ranker is ordering, not exact scores. And I unit-tested the metric itself before trusting
> it to judge the system."

---

## 7. Grounded generation & anti-hallucination

**What it is.** Making a generator stick to source truth instead of inventing plausible filler.
The mechanism is **context construction**, not a polite prompt: you give the model a closed set of
allowed facts and frame the task as *reframe these*, never *impress me*.

**How this project uses it.** `src/apply_copilot/draft/context.py` builds an explicit **fact
sheet** (the only employers/skills the model may use) with hard rules ("never claim a skill the
candidate lacks, even if the role wants it"). Drafts are *structured* — each bullet self-reports
the employer and profile-skills it used — so a program can verify them.

**Why it matters.** This is the same family as **RAG** (retrieve trusted context, generate
grounded in it). For a job-application tool, hallucination = lying on the user's behalf.

> **Say this:** "Grounding is an engineering property of the context, not a request. I hand the
> model a closed fact sheet and structure the output so each claim is checkable against it."

---

## 8. Faithfulness evaluation: programmatic gate + LLM-as-judge

**What it is.** Checking that generated claims are supported by the source. Two tools:
- **Programmatic checks** — deterministic string/entity checks (does any named skill/employer
  exist in the profile?).
- **LLM-as-judge** — a second model call that labels each claim supported/unsupported.

**How this project uses it.** `draft/faithfulness.py` is the **real gate**: it flags fabricated
employer/skill tags, any role-required skill the candidate lacks appearing in text, and the hiring
company named as a past employer. `evals/phase4/judge.py` is the **judge — a signal only**. The
program passes/fails the phase; the model never grades itself.

**Why it matters.** LLM-as-judge is everywhere in modern eval — but it's a model with opinions.
The discipline is: use it as a signal, close the loop with a program.

> **Say this:** "Faithfulness is decided by a deterministic checker; the LLM judge is a
> corroborating signal, never the gate. I refuse to close a loop with one model grading another."

**Limitation to volunteer:** the string-matcher only catches skills in the profile∪role
vocabulary; a skill fabricated outside that set needs NER or the judge — a stated, bounded
limitation (interviewers love that you know your gate's edges).

---

## 9. Relevance evaluation (and being honest about heuristics)

**What it is.** "Does the answer actually address the question?" Tempting to do with keyword
overlap — but that produces false negatives (an on-topic answer often shares no literal word with
the question).

**How this project uses it.** `draft/relevance.py` was demoted to an honest *floor* (catches
empty/one-word/stock non-answers); true topical relevance is left to the LLM judge.

> **Say this:** "I tried keyword-overlap relevance, saw it false-negative on a clearly relevant
> answer, and demoted it to a substantive-answer floor — pretending a brittle heuristic is a real
> gate is worse than admitting the split."

---

## 10. Multi-agent orchestration & contracts

**What it is.** Composing single-purpose "agents" (each a typed input→output stage) into a
pipeline, with the *handoffs* validated so no stage silently passes bad data.

**How this project uses it.** `src/apply_copilot/orchestrate/` models `PrefilterAgent →
ExtractAgent → MatchAgent → DraftAgent`, composed by `Pipeline`, which raises `PipelineError` on a
malformed handoff (e.g., empty title, out-of-range score).

> **Say this:** "I model stages as agents with explicit contracts and check every handoff, so a
> bug surfaces at the boundary that produced it instead of three stages later."

**Note:** "agent" here means a bounded pipeline stage with a contract — not an autonomous
open-ended loop. Being precise about that wins points.

---

## 11. Human-in-the-loop / maker-checker (as a *program*)

**What it is.** A required human approval step — enforced by code, not convention.

**How this project uses it.** `orchestrate/review.py`: an `Application` starts `pending_review`; a
draft that fails faithfulness is `blocked` and `approve()` on it *raises*. `packet/build.py`
*raises* unless status is `approved`. Compose them: **a packet requires human approval, which
requires machine faithfulness.** There is no code path around it.

> **Say this:** "The human gate is two interlocking exceptions, not a comment that says 'please
> review'. The system is structurally incapable of emitting an unapproved packet."

**Product framing:** this is the "copilot, not autopilot" decision — automate the reading, never
the final submit.

---

## 12. Eval-driven development / "gates are programs"

**What it is.** Every phase ships a deterministic check on its own output *before* it's "done" —
programmatic where possible, LLM-judge only as signal.

**How this project uses it.** `evals/phaseN/` — schema-validity + field accuracy (Phase 2),
Spearman (Phase 3), faithfulness (Phase 4), pipeline contracts + the review-gate lock (Phase 5).
Expensive/LLM tests are opt-in (`RUN_LLM_EVALS=1`); the fast deterministic suite runs by default.

> **Say this:** "Each capability has a gate that judges it in code. It's how I keep
> non-deterministic components honest and catch regressions."

---

## 13. Cost & quota-aware design

**What it is.** Matching the shape of the work to the shape of the budget. LLM calls cost
money/latency/rate-limit; cheap local computation doesn't.

**How this project uses it.** The dev model (Gemini free tier) allows **20 calls/day**, and one
ingest run surfaces ~1,000 postings. So the pipeline is **two-tier**: a cheap *local embedding
prefilter* ranks all postings with no LLM, and only the **top-K** reach the expensive extract +
draft stages. Cheap-and-wide, then expensive-and-narrow.

> **Say this:** "I never run an LLM over the whole feed. A free local embedding pass narrows 1,000
> postings to a handful, and only those get the paid model. The cost model is part of the
> architecture, not an afterthought."

---

## 14. Knowing your model's real behaviour

Two concrete quirks this project hit — great "tell me about a bug" material:

- **Thinking/reasoning tokens.** Gemini 3.x spends hidden reasoning tokens *from the same output
  budget*. With a tight `max_tokens`, the visible answer gets truncated non-deterministically. The
  tell is `finish_reason == "length"`. Fix: real headroom + surface truncation instead of
  returning a chopped string (`llm/client.py`, `providers.py` capture `finish_reason`).
- **Structured-output reliability differs by endpoint.** Forced tool-calling worked on Anthropic
  and on short inputs, but Gemini's OpenAI-compatible endpoint dropped the tool call on long JDs —
  fixed with a JSON-mode fallback.

> **Say this:** "Two production-shaped bugs: reasoning-token truncation, which I made *visible*
> via `finish_reason` instead of trusting output that merely looked complete; and endpoint-specific
> tool-calling flakiness, which I absorbed with a JSON-mode fallback in the seam."

---

## 15. (Optional / not built) Browser & computer-use agents

**What it would be.** Grounding an LLM in a live DOM to operate a UI — the perceive → decide →
act → observe loop — with a **deterministic post-action verification** (DOM/URL + screenshot), not
the agent's claim that it clicked. Reserved for Phase 6 against a *friendly mock form only*.

> **Say this:** "Computer-use agents are the least-commoditised agent skill. The key idea is the
> same as everywhere in this project — verify the outcome with a program, don't trust the agent's
> self-report."

---

## Rapid-fire interview Q&A

- **Q: What's the difference between this and fine-tuning a model?** A: This is *inference-time*
  systems engineering — extraction, retrieval/matching, grounded generation, orchestration, eval
  — around a frozen pre-trained model. No gradients, no training data, no fine-tuning. It's where
  most applied-AI work actually is.
- **Q: How do you get reliable structured data out of an LLM?** A: Forced tool/function calling or
  JSON mode, then *validate* against a schema (Pydantic) and retry on failure. Never trust the raw
  shape.
- **Q: Tool-calling vs JSON mode — when each?** A: Tool-calling is cleaner when the endpoint
  honours it (Anthropic, OpenAI); JSON mode is the portable fallback when an endpoint ignores a
  forced tool choice (I hit this on Gemini). I try tool-calling, fall back to JSON mode.
- **Q: Why embeddings over keyword search?** A: They capture meaning, not surface form. But cosine
  measures vocabulary proximity, not true fit — so it can confidently mis-rank; hybrid scoring or a
  cross-encoder re-ranker fixes it.
- **Q: How do you evaluate a matcher/ranker?** A: Rank correlation (Spearman) against a
  hand-ranking — ordering, not absolute numbers — with a threshold gate.
- **Q: How do you stop an LLM from hallucinating?** A: Construct the context as a closed fact set,
  structure the output to be checkable, and enforce a *programmatic* faithfulness gate; use
  LLM-as-judge only as a signal.
- **Q: Isn't LLM-as-judge circular?** A: Yes if it's the gate. I use it as a signal and close the
  loop with deterministic code — "gates are programs, not model opinions."
- **Q: What is RAG, and is this RAG?** A: Retrieval-Augmented Generation = retrieve trusted
  context, generate grounded in it. Phase 4's fact-sheet grounding is the same family; the
  "retrieval" here is the structured profile rather than a document store.
- **Q: How do you keep LLM costs sane at scale?** A: Do the cheap thing first. A free local
  embedding prefilter narrows the candidate set; the paid model only runs on the top-K.
- **Q: How do you debug a non-deterministic system?** A: Trace every call (inputs/outputs/tokens)
  from day one; close each component with a deterministic eval so regressions are caught.
- **Q: What's an "agent" here?** A: A single-purpose pipeline stage with a typed contract and
  checked handoffs — not an open-ended autonomous loop.
- **Q: How do you enforce human review?** A: As code — a packet can't be built unless the
  application is `approved`, and a faithfulness-failed draft can't be approved. Two exceptions, no
  bypass.

---

## Glossary

- **Embedding** — a vector representation of text where distance ≈ semantic dissimilarity.
- **Cosine similarity** — similarity as the cosine of the angle between two vectors.
- **Cross-encoder / re-ranker** — a model that scores a (query, candidate) *pair jointly*; more
  accurate than comparing two independent embeddings, slower.
- **Vector DB / ANN index** (FAISS, Chroma) — fast approximate nearest-neighbour search over many
  embeddings.
- **Tool/function calling** — the model returns a structured call to a named tool/schema.
- **JSON mode** — the model returns a JSON object conforming to a requested shape.
- **Grounding** — constraining generation to provided source facts.
- **RAG** — Retrieval-Augmented Generation: retrieve context, then generate grounded in it.
- **LLM-as-judge** — using an LLM to score another model's output (a signal, not a gate here).
- **Faithfulness** — whether generated claims are supported by the source.
- **Spearman's rho** — rank correlation; agreement of two orderings.
- **finish_reason** — why generation stopped (`stop`/`end_turn` = done; `length`/`max_tokens` =
  truncated).
- **Reasoning/thinking tokens** — hidden tokens a reasoning model spends before its visible answer,
  counted against the output budget.
- **Maker-checker / human-in-the-loop** — a required human approval step in an automated flow.

---

*Pair this with `NOTES.md` (the per-phase narrative) and `ROADMAP.md` (the curriculum). The code
for every concept above is small and readable — open the referenced file and trace it.*
