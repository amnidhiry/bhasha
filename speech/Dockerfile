# CPU speech service for the homelab. For an NVIDIA GPU host, see windows/README.md
# (or swap the torch index for a CUDA one on a Linux GPU host).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models
WORKDIR /app
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml ./
COPY bhasha_speech ./bhasha_speech
RUN pip install ".[kokoro]" && useradd --system --uid 10002 speech && mkdir -p /models && chown speech /models
USER speech
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=3s --start-period=180s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8790/health')"
CMD ["uvicorn", "bhasha_speech.app:app", "--host", "0.0.0.0", "--port", "8790"]
