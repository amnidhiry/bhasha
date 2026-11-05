#!/usr/bin/env bash
# Load ./data into the running stack. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
run() { docker compose exec -T api python -m "$@"; }

# The api container runs migrations before serving, so wait until it answers.
echo -n "waiting for api"
for _ in $(seq 1 60); do
  if docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1; then
    echo " ok"; break
  fi
  echo -n "."; sleep 2
done
docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" >/dev/null 2>&1 \
  || { echo; echo "api not healthy after 120s; check: docker compose logs api" >&2; exit 1; }
run app.importers.hsk /data/complete-hsk.json
run app.importers.hanzi /data/makemeahanzi-dictionary.txt
run app.importers.cedict /data/cedict.txt
docker compose restart api   # reload the segmenter dictionary
