#!/usr/bin/env bash
# Load ./data into the running stack. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."
run() { docker compose exec -T api python -m "$@"; }
run app.importers.hsk /data/complete-hsk.json
run app.importers.hanzi /data/makemeahanzi-dictionary.txt
run app.importers.cedict /data/cedict.txt
docker compose restart api   # reload the segmenter dictionary
