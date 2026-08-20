# NOTES.md

Per-phase learning notes, in plain language — the raw material for the dev.to series. One
entry per phase, written for an outsider, not for me.

---

## Phase 0 — Before you build an AI app, build the telescope

**The concept.** An LLM app is mostly plumbing, and the single most useful piece of plumbing
is *observability* — being able to see what the model was actually asked and what it actually
said, on every call. LLM calls are non-deterministic and fail in quiet, semantic ways (a
subtly wrong answer, not a stack trace), so if you can't replay a call you can't debug it.
The discipline here is to wire tracing in *before* any business logic exists, so there's never
a call you can't see. We used [Langfuse](https://langfuse.com) — a call becomes a "generation"
span with its inputs, outputs, model, and token usage attached.

**The seam.** The other Phase-0 idea is the *provider seam*: everything talks to the model
through one thin `LLMClient`, never through the Anthropic SDK directly. Two entry points —
`complete()` for free text and `complete_structured()` for a validated Pydantic object — are
all the rest of the app will ever call. Swapping providers later is a one-file change, and,
crucially, the tracing lives *in the seam*, so instrumentation is automatic: you can't make a
model call that isn't traced, because there's only one door and the telescope is bolted to it.

**The tradeoff we chose.** Tracing degrades to a silent no-op when Langfuse keys are absent.
That's a deliberate call: the alternative — making the telescope a hard dependency — means the
app breaks for anyone who just wants to try it, and it couples "can I run this?" to "do I have
an observability account?". The cost is that it's possible to run untraced without noticing;
we accept that for a local, single-user learning tool, and the CLI prints a visible
"Tracing disabled" banner so it's never a silent surprise. For a production service the call
would flip the other way — fail loudly if you can't observe what you're shipping.

**One subtlety worth remembering.** Short-lived processes (like a CLI command) have to *flush*
traces before exiting, because the SDK batches events in the background — exit too fast and the
trace never leaves the machine. So `trace-test` flushes in a `finally` block. It's a small
thing that produces a very confusing "my call worked but nothing shows up in the dashboard"
bug if you forget it.

**The seam paid off on day one.** The plan was to default to Claude. Then the very first
practical question — "do I have to pay to run this?" — made the case for the seam better than
any diagram could. Because every call already went through one `LLMClient`, switching the
whole app from Claude to Google Gemini's *free* tier was a config change, not a rewrite:
`LLM_PROVIDER=gemini` plus a key. The trick is that most vendors (Gemini, Groq, Ollama,
OpenRouter) speak the *OpenAI chat protocol*, so a single "OpenAI-compatible" adapter —
parameterised by base URL, key, and model — covers all of them, and a second adapter handles
Anthropic's native API. The provider is now data, resolved from one env var. That's the whole
point of a seam: the decision you thought was permanent turns out to be a one-line switch.

**A "thinking-model" gotcha the telescope caught.** Running `trace-test` twice with the same
`max_tokens=256` gave a full answer once and a sentence chopped off mid-word the next. The
culprit: Gemini 3.x (like other reasoning models) does hidden "thinking" before answering, and
through the OpenAI-compatible endpoint those thinking tokens come out of the *same* token
budget as the visible reply. When the model thinks more on one run, less budget is left for
output, so the answer truncates — non-deterministically. The tell is the API's `finish_reason`:
`length`/`max_tokens` means "I hit the ceiling," not "I finished." Two fixes went in: give
calls real headroom (`max_tokens` up to 1024), and — more importantly — capture `finish_reason`
and *warn* on truncation instead of returning a chopped string silently. That's the core
principle in miniature: don't trust that output is complete because it looks complete; let a
deterministic signal tell you the truth.

*Definition of done:* `trace-test` makes one real call through the seam and it appears as a
trace in Langfuse. No business logic yet — the seam and the telescope both work.

---

## Phase 1 — Automating job discovery without scraping

**The concept.** Before any AI, you need *material* to work on — a clean, deduplicated stream
of job openings. The instinct is to scrape a big portal, but that path is hostile (anti-bot
defenses), fragile, and legally grey. The better path, and the one this project holds to, is
**read vs. write**: pull only from sources *built to be consumed*. Public ATS platforms expose
JSON endpoints for exactly this — Greenhouse (`boards-api.greenhouse.io`), Lever
(`api.lever.co`), Ashby (`api.ashbyhq.com/posting-api`) — and many boards publish RSS. No
login, no headless browser, one gentle GET each. This is the same shape as a news/RSS
aggregator, just pointed at careers pages.

**The one-schema idea.** Every source has its own field names — Greenhouse nests location under
`location.name`, Lever calls the title `text` and puts location in `categories`, Ashby uses
`isRemote`, RSS gives you `summary`. The design that keeps this sane is a single internal
`JobPosting` model that *every* adapter normalises into. Downstream code (matching, drafting)
never sees a vendor quirk. Each adapter splits cleanly into an impure `fetch_raw()` (the one
HTTP call) and a pure `parse()` (record → `JobPosting`), which is why the eval can feed
recorded real payloads straight into `parse()` and never touch the network.

**Dedup, and the tradeoff I chose.** The same role shows up on multiple feeds, so postings
collapse on a canonical key: normalised `company + title + location`. Including *location* is a
deliberate call — it stops two genuinely different roles that share a title from merging, at
the cost that the *same* role listed as "Remote" on one feed and "Remote – US" on another won't
collapse. For a personal tool that's the right side to err on (a missed merge is a minor
annoyance; a wrong merge hides a real job). A fuzzier key or an embedding-based match is the
upgrade path when this bites — noted, not built.

**Incremental refresh.** Re-polling should be quiet: only genuinely new postings surface. The
naive-but-correct version is a flat JSON file holding the set of keys already seen; a new poll
returns only keys not in it. No database until volume demands one — that's the seam where a
real store slots in later. Proven live: first poll of five real boards surfaced ~1,026 unique
postings (6 cross-source duplicates collapsed); the immediate re-poll surfaced **zero**.

**The boundary held.** Everything here is a read-only GET against an endpoint designed to be
pulled, with an honest User-Agent. No portal search-scraping, no anti-bot anything, no stored
third-party data beyond the openings themselves. Comprehensive LinkedIn/Naukri-style coverage
would require exactly the scraping-behind-anti-bot path that's out of scope — so it stays out.

*Program gate:* three deterministic pytest checks over recorded fixtures — (a) every source
normalises to a schema-valid `JobPosting`, (b) the deduper collapses a known duplicate set to
the expected count, (c) incremental refresh over a before/after pair yields exactly the
expected new items. No LLM in this phase, so no model-graded anything — all three are code
comparing to known answers.

---

## Phase 2 — Two ways to get structured data out of an LLM

**The concept.** Most "AI" work isn't chatting — it's turning messy text into *validated
structured data* you can compute on. Here that's resume → `Profile` and JD → `Requirements`.
The reliable technique is **tool/function calling**: hand the model your Pydantic schema as a
tool it's forced to call, so the arguments it produces *are* your object, then validate them.
If validation fails, you retry. The model proposes; a Pydantic `model_validate` (a program)
disposes — the same "gate, not vibe" principle as everywhere else.

**Two backends, same target.** I built extraction twice on purpose:
* **Native** — hand-rolled through our own `LLMClient.complete_structured`. I own the prompt, the
  forced-tool call, the retry loop, and the validation. More code, but nothing is hidden, and
  because it goes through our seam it's **automatically traced in Langfuse**.
* **`instructor`** — the library does schema-injection, validation, and retries for me in one
  `create(..., response_model=Profile, max_retries=2)` call. Much less code. The costs: it talks
  to the provider **directly**, so those calls **bypass our tracer**, and the machinery I'm
  trying to learn is exactly what it abstracts away.

The honest read: `instructor` is what I'd reach for in production (less to get wrong), but
building the native version first is what makes me *understand* what `instructor` is doing — and
the tracing gap is a real, concrete reason a project might still want the seam.

**Where it bit.** Field *descriptions* aren't decoration — with tool calling the model reads
them as the spec, so "leave null if not stated; never invent" in the description is what keeps
extraction grounded (the foundation Phase 4 builds on). And a subtle divergence showed up
immediately: given a resume whose SKILLS line listed six items but whose job bullets mentioned
"Java", the **native** backend added Java to `skills` (defensible — it *is* a skill named in the
text) while **instructor** stuck to the explicit SKILLS line. Neither is "wrong"; it's a
reminder that "extract the skills" is underspecified, and that two backends over the same schema
can still disagree on judgment calls.

**The model matters, quietly.** Gemini 3.x is a *thinking* model, so extraction calls are
noticeably slower than a one-liner — six sequential calls in the eval take a couple of minutes.
Worth knowing before you put an extraction step on a latency budget.

**The bite that showed up later (and how the seam absorbed it).** The short eval fixtures all
extracted fine via forced tool-calling — but when the full pipeline (Phase 5) hit a *real,
long* job description, Gemini's OpenAI-compatible endpoint began *ignoring the forced
`tool_choice` and returning prose instead*, so the call yielded no structured output at all and
the retry loop just failed three times. This is exactly the reliability gap `instructor` quietly
covers (its JSON mode was rock-solid on the same inputs). The fix stayed inside our own seam: the
OpenAI-compatible provider now **tries tool-calling first and falls back to JSON mode** (schema
injected into the prompt, `response_format={"type":"json_object"}`, lenient parse) when no tool
call comes back. So the "native" path keeps teaching tool-calling where it works, and degrades to
the technique that doesn't break where it doesn't — the whole reason for owning the seam instead
of hardcoding one vendor's happy path.

*Program gate:* an opt-in eval (`RUN_LLM_EVALS=1`) runs the native backend over
hand-labelled resumes and JDs and asserts, **in code**, (a) 100% schema-valid output and
(b) field-level accuracy above a threshold (0.75), scored by comparison to my labels — the
model never grades itself. A separate always-on test proves the *scoring instrument* itself is
correct on synthetic inputs, so the gate's measuring stick is trustworthy before it's pointed
at live output. Measured field-level accuracy on the fixtures with the native backend on Gemini:
**96.6%** over 44 labelled fields, 6/6 schema-valid.

---

## Phase 3 — Matching with embeddings, and where cosine confidently lies

**The concept.** How close is a profile to a role? Keyword overlap is brittle ("K8s" vs
"Kubernetes", "ML" vs "machine learning"). *Embeddings* map text into a vector space where
semantically similar text lands nearby, so cosine similarity captures meaning keywords miss. We
did the naive version deliberately: a small local model (`all-MiniLM-L6-v2`), in-memory cosine,
no vector DB, no hosted API. Scale cosine to 0–100 and you have a match score. On 15 roles I'd
hand-ranked against one profile, the system's ordering hit **Spearman ρ = 0.92** — the ordering
is genuinely good.

**Score vs. rationale — kept apart on purpose.** The *score* is pure cosine. The *rationale* is
**programmatic**: it computes concrete required-skill overlap, missing skills, and seniority
alignment from the structured fields, and it does NOT feed back into the score. That separation
is the interesting part — it lets you *see* when a confident cosine number disagrees with a thin
factual overlap, which is exactly the failure mode below. (It also means every claim in the
rationale is grounded by construction — the CLI demo correctly flagged "missing: distributed
systems" because that skill wasn't in the resume text, even though the role required it.)

**Where cosine confidently lies.** In the eval, the **Enterprise Account Executive** role — the
single *worst* fit for a backend engineer (I ranked it 15th of 15) — scored **46/100**, *above*
the **Technical Product Manager** role (ranked 13th, scored **41**). Pure text-embedding
similarity has no notion of *career adjacency* or *skill transferability*; it measures vocabulary
proximity. A PM description ("product management, roadmapping, stakeholder management") is a
distinctive jargon cluster that sits far from engineering text, so its cosine drops — while a
generically-worded sales role doesn't drop as far. The number *feels* wrong because it is: cosine
answered "how similar is the wording?", not "how good a fit is this person?". Similarly, a
Frontend role edged out an ML Engineer role even though the latter shares "Python" with the
profile.

**What fixes it (the upgrade path).** The signal to fix this is *already computed* — the
required-skill coverage in the rationale. A **hybrid score** would blend cosine with explicit
skill-coverage (so a role you can't do on paper can't ride generic wording to a high score). Two
heavier options: a **cross-encoder re-ranker** (scores the (profile, role) pair jointly instead
of comparing two independent vectors — much better at fit, slower), and, once there are
thousands of roles, an **ANN index** (FAISS/Chroma) so you're not doing a linear scan. None are
built yet — the naive version's job was to make the failure mode legible first.

*Program gate:* the matcher scores all 15 roles against the profile and the eval asserts
**Spearman ρ ≥ 0.6** between the system's scores and my hand-ranking (measured **0.92**). The
correlation metric is hand-rolled and separately unit-tested on synthetic data, so the measuring
stick is verified before it judges the matcher. The whole gate is local and deterministic — no
API cost, no model grading itself.

---

## Phase 4 — Stop your job-application AI from lying about you

**The concept.** A model told to "make this candidate sound great for this role" will happily
invent a skill the job wants, or imply you worked somewhere you didn't. That's catastrophic for a
job application — it's lying on your behalf. Phase 4 is about *grounded generation*: producing
tailored bullets and screening answers that are aimed at the role but strictly true to the real
profile, and then **proving** it with a program.

**Grounding is context construction, not a polite request.** The anti-hallucination work happens
before the model runs, in how the context is built. We hand it an explicit **fact sheet** — the
closed set of employers, skills, and credentials it may use — and frame the task as "reframe
these real facts toward the role," with hard rules ("never introduce a skill the candidate lacks,
even if the role requires it; if the role needs it, just don't mention it"). Tighter context =
less room to invent. We also pass the *target role* so drafting is relevant, but explicitly label
the hiring company as "you have NOT worked here."

**The trick that makes verification exact.** The draft is *structured*: each tailored bullet
self-reports the employer it's about and the profile skills it uses. That turns a fuzzy "is this
faithful?" into checkable tags — a program compares them to the profile. And independently, the
checker scans the free text for the specific bait: any skill the *role* wants that the candidate
*doesn't have* (here the role demands Rust and Kafka, which the profile lacks) and any mention of
the hiring company as a past employer. Within the relevant skill vocabulary (profile ∪ role), a
bullet may only name skills the candidate actually has.

**The gate is a program; the judge is a signal.** This is the core principle at its sharpest. An
**LLM-as-judge** also reads the fact sheet and labels each claim supported/unsupported — and it's
genuinely useful, catching subtle drift like an invented metric that the string-matcher can't.
But it never *decides* the phase: the model grading model output is exactly the loop we refuse to
close with an opinion. `check_draft` (deterministic) passes or fails; the judge is printed as a
number to watch.

**Relevance is honest about its limits.** I first tried keyword overlap to check "does the answer
address the question?" — and it immediately produced false negatives: a perfectly on-topic answer
("At Acme Corp I designed payment APIs…") shares no literal word with "Describe your most relevant
experience." So the programmatic relevance was demoted to what it can *actually* do
deterministically — a floor that catches empty / one-word / stock non-answers — and true topical
relevance became the LLM judge's job. Pretending a brittle heuristic is a real relevance gate
would have been worse than admitting the split.

**Limitation, stated.** The skill scan is bounded to the profile ∪ role vocabulary; a fabricated
skill that appears in *neither* set wouldn't be caught by string-matching alone. That's the seam
where the LLM judge (or an NER pass) earns its place — noted, and the judge already partly covers
it.

*Program gate:* an offline, deterministic test proves the checker itself — a hand-written
faithful draft passes clean, and a planted unfaithful draft is caught with exactly the four
violation types (fabricated employer tag, fabricated skill tag, claimed-absent-skill in text,
claimed-unworked-company). That's the phase's real gate and it needs no LLM. A separate opt-in
live test (`RUN_LLM_EVALS=1`) drafts for real against a role engineered to bait hallucination and
asserts **zero** programmatic violations on the live output, with the judge as a printed signal.

---

## Phase 5 — Maker-checker for AI pipelines: the human gate is a program

**The concept.** The four phases so far are components; Phase 5 makes them a system — one pipeline
that goes ingest → extract → match → draft — and, crucially, stops for a human before anything is
"finished". The interesting engineering isn't the wiring; it's making the human review gate
*structurally unavoidable* rather than a polite convention.

**Model the stages as agents with contracts.** Each stage is a small agent with one typed job
(`PrefilterAgent`, `ExtractAgent`, `MatchAgent`, `DraftAgent`), injected into the `Pipeline`.
Composing rather than entangling them buys two things: the eval can swap real agents for
deterministic stubs, and the *handoffs become checkable*. "No stage silently passes bad data" is
enforced — after each stage the pipeline asserts the output is well-formed (`Requirements` has a
non-empty title, a match score is in range) and raises `PipelineError` otherwise.

**The cost strategy is part of the architecture.** A single ingest run surfaces ~1,000 postings,
and the dev LLM (Gemini free tier) allows only 20 calls/day. So the pipeline is deliberately
two-tier: a **cheap, local embedding prefilter** ranks *all* postings with no LLM, and only the
top-K survivors reach the **expensive** LLM stages (extract + draft). Matching the shape of the
work to the shape of the budget — cheap-and-wide then expensive-and-narrow — is the difference
between a demo that runs and one that 429s on posting #21.

**The gate is a program, in two interlocking pieces.**
1. An `Application` carries a `status`. It starts `pending_review`. A draft that fails the
   (Phase 4) faithfulness gate is marked `blocked`, and `approve()` on a blocked application
   *raises* — the human is not permitted to wave through a draft the machine already caught lying.
2. `build_packet()` *raises* unless the application's status is `approved`. There is no code path
   from `pending_review` / `rejected` / `blocked` to a packet.

Compose those and the invariant holds by construction: **a packet requires human approval, which
requires machine faithfulness.** The maker-checker discipline isn't documentation; it's two
exceptions that fire if you try to skip a step. That's the whole point — "the human gate is a
program, not a polite suggestion."

**On the optional queue.** The roadmap allowed a Redis/BullMQ-style queue here. I didn't add one:
a local, single-user, top-K batch has no orchestration pressure a list comprehension can't handle.
Adding a broker would be resume-driven design, not need-driven — noted as the seam it *would* slot
into (fan-out over many profiles, or decoupling ingest cadence from drafting) if that pressure
ever appears.

*Program gate:* an offline, deterministic end-to-end test runs the full pipeline with stub agents
and asserts every stage's contract holds, that a bad handoff raises `PipelineError`, that a
`blocked` application cannot be approved, and — the crux — that `build_packet` refuses any
application that isn't `approved`. The human gate is verified as code.
