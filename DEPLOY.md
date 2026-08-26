# DEPLOY.md — hosting the Zapply demo web app

The web app (`web/`) is a FastAPI backend + a static SPA. It ships a `Dockerfile` that bakes the
job snapshot, embeddings, and the local model into the image, so the container boots fast and
needs no network for browsing or matching. Matching runs on a small **ONNX** model (fastembed) —
total footprint ~**400 MB**, so it fits the **free 512 MB tiers** (no big VM needed).

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

## Option A — Koyeb (free, no credit card, always-on) — recommended

Koyeb's free tier runs one always-on web service with **no credit card**. Now that the app is
ONNX-based (~400 MB), it fits.

1. Sign up at https://www.koyeb.com with **GitHub** (no card).
2. **Create Web Service → GitHub →** pick `AnvaySingh/zapply`. Koyeb auto-detects the `Dockerfile`.
3. Instance type: **Free**. Port: **8000** (Koyeb injects `PORT`, which the app binds).
4. **Environment variables:** `PUBLIC_MODE=on`, `ACCESS_CODE=<code>`, and `GEMINI_API_KEY=<key>`
   (the key only if you want AI-analyze / packet live).
5. Deploy. Koyeb builds the image (installs deps + bakes the snapshot & model — a few minutes) and
   serves at `https://<app>-<org>.koyeb.app`.

> **Render** (free) and **Fly.io** deploy the same way from the `Dockerfile`. Koyeb is the simplest
> no-card, always-on one.

## Option B — Oracle Cloud Always Free (forever-free VM, if capacity is available in your region)

A real ARM VM — up to **4 CPU / 24 GB RAM**, free forever, no sleep, no Docker limits. ~20 min of
one-time setup; Oracle asks for a card to verify identity (not charged).

**1. Create the VM.** Oracle Cloud console → **Compute → Instances → Create instance**:
- Image **Canonical Ubuntu 22.04**; Shape **Ampere → VM.Standard.A1.Flex**, e.g. **2 OCPU / 12 GB**
  (within the Always-Free 4 OCPU / 24 GB grant).
- Paste your SSH **public key**, create, and note the **public IP**.

**2. Open ports 80 + 443** (two layers):
- Console → your VCN → **Security List** → add ingress `0.0.0.0/0` TCP **80** and **443**.
- On the VM (Oracle images firewall everything by default):
  ```bash
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save
  ```

**3. Install + build** (SSH in as `ubuntu`):
```bash
ssh ubuntu@<public-ip>
sudo apt-get update && sudo apt-get install -y git
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.bashrc
git clone https://github.com/AnvaySingh/zapply && cd zapply
uv sync
uv run python -m web.build_data          # bake job snapshot + model (a few minutes)
```

**4. Secrets** — create `~/zapply/.env`:
```bash
cat > ~/zapply/.env <<'EOF'
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
PUBLIC_MODE=on
ACCESS_CODE=<your-code>
EOF
```

**5. Run it as a service** (survives reboots/crashes):
```bash
sudo tee /etc/systemd/system/zapply.service >/dev/null <<'EOF'
[Unit]
Description=Zapply
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/zapply
EnvironmentFile=/home/ubuntu/zapply/.env
ExecStart=/home/ubuntu/.local/bin/uv run uvicorn web.server:app --host 127.0.0.1 --port 8000
Restart=always
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now zapply
```

**6. Free HTTPS via Caddy + nip.io** (no domain needed — `<ip>.nip.io` is a real hostname that
resolves to your IP, so Let's Encrypt issues a cert for it):
```bash
sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt-get update && sudo apt-get install -y caddy
echo "<public-ip>.nip.io {
    reverse_proxy 127.0.0.1:8000
}" | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Live at **`https://<public-ip>.nip.io`** — forever-free, HTTPS, never sleeps.
Update later with: `cd ~/zapply && git pull && uv run python -m web.build_data && sudo systemctl restart zapply`.

## Option C — Hugging Face Spaces (only if your account shows the free "CPU basic" hardware)

HF's free **CPU basic** tier gives **2 vCPU / 16 GB RAM** — enough for the embedding model, with a
persistent public URL. (Free Spaces sleep after ~48h idle and cold-start on the next visit.)

1. Create a **Docker** Space: https://huggingface.co/new-space → SDK = **Docker**.
2. In the Space's **`README.md`**, put this front matter at the very top:
   ```yaml
   ---
   title: Zapply
   emoji: ⚡
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

## Option D — Azure Container Apps (connects to a DevOps track; ~free for a month on the $200 credit)

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

> Use **Container Apps**, not **Functions** — a long-lived in-memory model doesn't fit the
> function model. An always-on container is ~$15–40/mo after the free credit.

## Option E — any Docker host / VM

`docker build -t zapply . && docker run -p 7860:7860 -e PUBLIC_MODE=on -e ACCESS_CODE=code zapply`
Works on Fly.io, Google Cloud Run (`gcloud run deploy --source . --memory 1Gi`), Render, or any
VM — the ONNX build fits small free tiers (see Option A).

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
