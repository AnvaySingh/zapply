# DEPLOY.md — hosting the Zapply demo web app

The web app (`web/`) is a FastAPI backend + a static SPA. It ships a `Dockerfile` that bakes the
job snapshot, embeddings, and the local model into the image, so the container boots fast and
needs no network for browsing or matching.

## Environment variables

| Var | Purpose | Notes |
|---|---|---|
| `GEMINI_API_KEY` | LLM key for **AI-analyze** + **packet** generation | Only needed if you want those two features on. Browse + match work without it. |
| `PUBLIC_MODE` | `on` to enable the public gate | When on **and** `ACCESS_CODE` is set, the LLM features require the code. |
| `ACCESS_CODE` | Shared secret that unlocks the LLM features | Hand it only to people you want to spend your quota. |
| `PORT` | Port to bind (default `7860`) | HF Spaces expects `7860`. |

**Recommended for a public link:** `PUBLIC_MODE=on` + a private `ACCESS_CODE`. Then anyone can
browse and match (all local — no key, no PII leaves the box), but only people with the code can
run AI-analyze / packet (which use your key + send resume text to the LLM).

---

## Option A — Hugging Face Spaces (forever-free, recommended)

HF's free **CPU basic** tier gives **2 vCPU / 16 GB RAM** — enough for the embedding model, with a
persistent public URL. (Free Spaces sleep after ~48h idle and cold-start on the next visit.)

1. Create a **Docker** Space: https://huggingface.co/new-space → SDK = **Docker**.
2. In the Space's **`README.md`**, put this front matter at the very top:
   ```yaml
   ---
   title: zapply
   emoji: 🧭
   colorFrom: indigo
   colorTo: blue
   sdk: docker
   app_port: 7860
   pinned: false
   ---
   ```
3. Push this repo's files to the Space (it's a git repo):
   ```bash
   git remote add space https://huggingface.co/spaces/<you>/zapply
   git push space main
   ```
4. In **Settings → Variables and secrets**, add secrets: `GEMINI_API_KEY`, `PUBLIC_MODE=on`,
   `ACCESS_CODE=<your-code>`.
5. The Space builds the image (installs deps + bakes data/model — a few minutes) and serves at
   `https://<you>-zapply.hf.space`.

## Option B — Azure Container Apps (connects to a DevOps track; ~free for a month on the $200 credit)

Scale-to-zero serverless containers, HTTPS + domain included. Give it ~**4 GiB**.

```bash
az group create -n zapply-rg -l centralindia
az containerapp up \
  --name zapply --resource-group zapply-rg \
  --source . --ingress external --target-port 7860 \
  --env-vars PUBLIC_MODE=on ACCESS_CODE=<code>
# add the LLM key as a secret (only if enabling AI features):
az containerapp secret set -n zapply -g zapply-rg --secrets gemini=<key>
az containerapp update -n zapply -g zapply-rg \
  --set-env-vars GEMINI_API_KEY=secretref:gemini
```

> Use **Container Apps**, not **Functions** — a long-lived Torch model doesn't fit the
> function model. An always-on 4 GiB container is ~$15–40/mo after the free credit.

## Option C — any Docker host / VM

`docker build -t zapply . && docker run -p 7860:7860 -e PUBLIC_MODE=on -e ACCESS_CODE=code zapply`
Works on Fly.io, Render (paid tier — free RAM is too small), or an **Oracle Cloud Always-Free**
ARM VM (up to 24 GB RAM, never sleeps; you manage HTTPS via Caddy/nginx).

## Local

```bash
uv run uvicorn web.server:app --port 8501   # no gate; all features open with your .env key
```

---

## Getting your own URL (custom domain) for free

The free tiers give you a platform subdomain (`*.hf.space`). HF **custom domains are paid**, so to
put your own name in front — for free — proxy it:

- **Free subdomains:** `is-a.dev`, `js.org` (open-source), or a `*.vercel.app` / `*.netlify.app`
  prefix you choose.
- **Vercel / Netlify can't *run* this app** (it's Python + PyTorch, not static/edge JS) — but they
  can **proxy a free URL to your HF Space.** Create a Vercel project with a `vercel.json`:
  ```json
  { "rewrites": [ { "source": "/(.*)", "destination": "https://<you>-zapply.hf.space/$1" } ] }
  ```
  Now `your-name.vercel.app` (or a custom domain you add to Vercel, free) serves your HF-hosted app.
  Netlify: a `_redirects` file with `/*  https://<you>-zapply.hf.space/:splat  200`.
- **Cloudflare (free)** can do the same proxy for a custom domain, and is the most robust for file
  uploads / large responses.

So: **backend on HF Spaces (free) + a Vercel/Cloudflare proxy (free) = your own URL, $0.** A real
domain (`yourname.com`) is ~$1–12/yr if you want one — not free, but cheap.
