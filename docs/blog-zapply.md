---
title: "I built a job-application copilot that can't lie about me"
published: false
description: "The applied-AI stack behind Zapply: extraction, embeddings, grounded drafting, and a faithfulness check that a plain program enforces."
tags: ai, python, machinelearning, tutorial
cover_image: https://raw.githubusercontent.com/AnvaySingh/zapply/main/docs/cover.png
---

## TL;DR

- I built **Zapply**, a personal job-application copilot. It finds jobs, ranks them against my resume, and drafts a tailored application. I paste and submit it myself.
- The design rule I kept everywhere: **every check is closed by a program that judges the model's output.** The model proposes, a plain function decides.
- Live: [zapply-az41.onrender.com](https://zapply-az41.onrender.com). Code: [github.com/AnvaySingh/zapply](https://github.com/AnvaySingh/zapply).

## Why I built this

Applying to jobs is a lot of repetitive work. Read the posting, figure out if you fit, rewrite your bullets to match, answer the same screening questions again. The tools that automate the whole thing (including the submit) sit in a legal and ethical grey zone, and honestly the interesting part was never the clicking.

So I set a boundary and built to it. Zapply does everything up to the submit button and hands me a finished packet. A human (me) always makes the final submit. The line is simple: automated **reading** of job openings is fine, automated **writing** (applying) is not. Copilot, never autopilot.

That gave me a clean project to learn the full applied-AI stack by hand: structured extraction, embeddings, grounded generation, orchestration, evaluation, and deployment. This post walks through each piece and the one idea that ties them together.

## The one rule: gates are programs, not model opinions

Here is the rule I applied at every step. When a step produces model output, I also write the program that judges it.

"The answer is faithful to my resume" is decided by a checker function that reads the profile. "This application is ready" is decided by a status flag a human flips. LLMs are non-deterministic and fail in quiet, plausible ways, so a loop closed by another opinion is not really closed.

Keep that in mind as you read. Most sections below are the same idea in a different place.

## The pipeline

```text
job boards / RSS  ->  ingest  ->  one clean JobPosting schema
resume  ->  extract  ->  Profile (structured)
job     ->  extract  ->  Requirements (structured)
                     ->  match   (embeddings) -> score + why
                     ->  draft   (grounded)   -> bullets + answers
                     ->  faithfulness gate     (a program)
                     ->  human review          (I approve)
                     ->  packet                (paste-ready)
```

Now the concepts, one at a time.

## 1. A provider-agnostic seam for the LLM

I did not want to hardcode a vendor. Every model call in Zapply goes through one thin client, never through a vendor SDK directly.

```python
# one door for the whole app
class LLMClient:
    def complete(self, prompt, system=None, ...):        # free text out
    def complete_structured(self, prompt, model_cls, ...): # a validated object out
```

Behind that client is a small adapter per vendor. One speaks the Anthropic API, one speaks the OpenAI chat protocol (which covers Gemini, Groq, Ollama, and OpenAI itself). A single environment variable picks the provider:

```bash
LLM_PROVIDER=gemini   # or anthropic, or openai
```

The payoff showed up on day one. I planned to use Claude, then the very first practical question was "do I have to pay to run this?". Because every call already went through one client, switching the whole app to Google Gemini's free tier took one environment variable. No business logic changed. That is the whole reason for the seam.

## 2. Tracing from line one

LLM apps fail semantically. You do not get a stack trace, you get a subtly wrong answer. If you cannot replay a call, you cannot debug it.

So before any business logic, I wired [Langfuse](https://langfuse.com) tracing into the client. Every call becomes a "generation" with its prompt, output, model, and token usage attached. Because the tracing lives inside the one client, you cannot make a call that is not traced.

One small thing that bit me: short-lived commands (a CLI run) have to flush traces before exiting, because the SDK batches them in the background. Exit too fast and the trace never leaves your machine. A `finally` block fixed it.

## 3. Structured extraction (the 80% of real LLM work)

Most "AI" work is not chatting. It is turning messy text into validated, typed data you can compute on. In Zapply that is resume to `Profile` and job description to `Requirements`.

The reliable technique is tool/function calling. You hand the model your schema as a tool it is forced to call, so its arguments *are* your object. Then you validate with Pydantic. Invalid output is rejected right there, it never silently passes.

I built this by hand first, then again with the [`instructor`](https://python.useinstructor.com/) library, to feel the difference. Library means less code and built-in retries. Hand-rolled means I own the prompt, the retry loop, and the tracing, and I understand exactly what breaks.

**What broke.** The short test resumes extracted fine with forced tool-calling. Then the full pipeline hit a real, long job description and Gemini's OpenAI-compatible endpoint started ignoring the forced tool call and returning prose instead. No structured output at all. The fix stayed inside my own provider: try tool-calling first, and fall back to JSON mode (ask for a JSON object, inject the schema into the prompt, parse leniently) when no tool call comes back.

```python
tool_calls = response.choices[0].message.tool_calls
if tool_calls:
    return json.loads(tool_calls[0].function.arguments)  # happy path
# some endpoints (Gemini) drop the forced tool call on long inputs:
return self._json_mode(prompt, system, schema, ...)      # fall back to JSON mode
```

That is the whole reason for owning the seam instead of trusting one vendor's happy path.

## 4. Matching with embeddings, and where cosine lies

How close is my resume to a role? Keyword overlap is brittle ("K8s" vs "Kubernetes"). Embeddings map text to a vector where similar meaning lands nearby, so cosine similarity captures meaning that keywords miss.

I kept the naive version on purpose: a small local model (`all-MiniLM-L6-v2`, 384 numbers per text) and in-memory cosine, no vector database.

```python
def cosine(a, b) -> float:
    # 1.0 = same direction, 0 = unrelated
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
```

To evaluate a ranker you do not grade absolute numbers, you ask "is the ordering right?". I hand-ranked 15 roles for one profile and measured the **Spearman rank correlation** between my order and the system's. It came out at 0.92, which is a strong agreement.

Cosine has a real failure mode. It measures vocabulary proximity rather than fit. In my eval the worst-fit role (an enterprise sales job) out-scored a technical Product Manager role, because the PM's language sits further from engineering text than generic corporate sales does. The number felt wrong because it was. Cosine answered "how similar is the wording" when the question I cared about was "how good a fit is this person". A skill-overlap signal or a re-ranker is the fix, and I compute the skill overlap already for the card display.

## 5. Grounded drafting and a faithfulness gate

This is the part I care most about. A model told to "make me sound great for this role" will happily invent a skill the job wants. On a job application, that is lying on your behalf.

Grounding is not a polite request in the prompt. It is how you build the context. I hand the model a closed fact sheet (the only employers, skills, and credentials it may use) and frame the task as "reframe these real facts", with a hard rule: never claim a skill the candidate lacks, even if the role asks for it.

The check comes next. The draft is structured, so each bullet reports the employer and the profile skills it used. A plain function verifies those against the profile, and independently scans the text for any role-required skill the candidate does not have.

**What broke, on purpose.** I pointed it at a role that demanded Rust and Kafka, which my test profile did not have. The drafter produced good bullets from real experience and did not claim Rust or Kafka. The faithfulness function confirmed it in the UI:

```text
Faithfulness gate passed — every claim traces to your resume.
Role skills you didn't claim: Rust, C/C++.
```

That is the anti-hallucination guarantee working. The model resisted the bait, and a program (not the model) confirmed it.

I also run an **LLM-as-judge**: a second model call that reads the fact sheet and labels each claim supported or unsupported. It is genuinely useful for subtle drift like an invented metric. But it is only a signal. The deterministic checker passes or fails the step. Using a model to grade a model is exactly the loop I refuse to close with an opinion.

## 6. Orchestration and a human gate that is a program

The pieces above become one pipeline: ingest, extract, match, draft, review, packet. The interesting engineering is not the wiring, it is making the human review step impossible to skip.

I modelled it with an `Application` that carries a status. It starts `pending_review`. A draft that fails the faithfulness check is marked `blocked`, and the approve function raises if you try to approve a blocked one. The packet builder raises unless the status is `approved`.

```python
def approve(app):
    if not app.is_faithful:                 # can't wave through a draft the checker caught
        raise ReviewError("failed the faithfulness gate")
    app.status = ApplicationStatus.approved

def build_packet(app):
    if app.status != ApplicationStatus.approved:  # no path from pending/blocked to a packet
        raise NotApprovedError("a packet requires human approval")
    ...
```

Compose those two and the maker-checker rule holds by construction: a packet requires human approval, which requires machine faithfulness. Two exceptions enforce that at runtime, so the human step cannot be skipped by accident.

## 7. Designing around cost

The dev model is Gemini's free tier, which allows 20 requests a day. A single ingest run surfaces around 4,000 postings. If you extract requirements for every one, you hit the wall on posting number 21.

So the pipeline is two-tier. A cheap local embedding pass ranks all postings with no LLM call, and only the top few survivors reach the expensive LLM steps (extract and draft). Cheap and wide first, expensive and narrow second. Matching the shape of the work to the shape of the budget is the difference between a demo that runs and one that fails immediately.

The web app takes the same care. Browsing and matching are 100% local. The only calls that touch the LLM are the optional "AI analyze" and "generate packet" features, and on the public deployment those sit behind an access code so a stranger cannot spend my quota.

## 8. Making it cheap to host (ONNX)

I wanted the demo online for free. Every free host kept failing for the same reason: PyTorch needs around 2 GB of RAM, and free tiers give you 512 MB.

The fix was to stop hunting for a big free box and remove PyTorch. I swapped `sentence-transformers` for [`fastembed`](https://github.com/qdrant/fastembed), which runs the *same* MiniLM model through ONNX Runtime instead of PyTorch. Same 384-dimension vectors, so the rankings do not change (I re-ran the Spearman eval and it was still 0.92). Memory dropped from about 2 GB to about 400 MB, and the app now fits a free tier. As a bonus the test suite got roughly ten times faster because it no longer imports torch.

It is deployed on a free Render instance from a `Dockerfile` that bakes the job snapshot and the model into the image at build time, so the container boots fast.

## What I would tell someone starting this

The thread through all of it is one sentence: **do not let a model be the judge of its own work.** Extraction is validated by a schema. Matching is graded by a rank correlation against my labels. Faithfulness is decided by a function that scans for skills I do not have. Review is a status a human flips. The model is the powerful, unreliable part in the middle, and every loop around it is closed by a plain program.

The other half is the boundary. Zapply stops one click short of submitting, on purpose. That single decision removed almost all of the risk and kept all of the learning, because the interesting engineering was always in the brain, not the hands.

Try it: [zapply-az41.onrender.com](https://zapply-az41.onrender.com) (browse and match are open, the AI features are behind an access code). Code and a per-phase writeup: [github.com/AnvaySingh/zapply](https://github.com/AnvaySingh/zapply).

Hope you find it useful. Any kind of feedback and suggestions are highly appreciated. If you have built something similar, I would like to hear how you handled the faithfulness problem. `#discuss`
