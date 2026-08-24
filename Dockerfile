# apply-copilot demo web app — container image (works on Hugging Face Spaces, Azure, Fly, a VM…)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/hf \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st \
    PORT=7860

WORKDIR /app

# uv — fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# a couple of libs some scientific wheels expect
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# app source
COPY . .

# bake the job snapshot + embeddings + MiniLM model into the image (needs network at build)
RUN uv run python -m web.build_data

EXPOSE 7860
CMD ["sh", "-c", "uv run uvicorn web.server:app --host 0.0.0.0 --port ${PORT:-7860}"]
