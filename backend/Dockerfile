# Build context is the repo root (see docker-compose.yml). Targets:
#   api    (default, last stage): FastAPI + the built PWA
#   worker: the same app plus CPU-only PyTorch for the nightly FSRS optimizer

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 BHASHA_WEB_DIR=/app/web
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install . && useradd --system --uid 10001 bhasha
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=web /web/dist ./web

FROM base AS worker
# The CPU wheel avoids PyTorch's multi-GB CUDA libraries; the optimizer runs fine on CPU.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install numpy pandas tqdm
USER bhasha
CMD ["python", "-m", "app.worker"]

FROM base AS api
USER bhasha
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --start-interval=2s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
