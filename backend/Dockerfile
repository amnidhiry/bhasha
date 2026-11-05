FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install . && useradd --system --uid 10001 bhasha
COPY alembic.ini ./
COPY alembic ./alembic

USER bhasha
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --start-interval=2s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
