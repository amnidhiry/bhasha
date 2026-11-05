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
run app.importers.hanzi_graphics /data/makemeahanzi-graphics.txt
run app.importers.handwriting /data/hsk-handwriting
# After CC-CEDICT (Traditional filter) and SUBTLEX (sentence difficulty), in this order.
run app.importers.subtlex /data/SUBTLEX-CH-WF
run app.importers.tatoeba /data/tatoeba/cmn_sentences.tsv.bz2 /data/tatoeba/eng_sentences.tsv.bz2 /data/tatoeba/cmn-eng_links.tsv.bz2
# Optional: Tone Perfect recordings, downloaded by hand into data/toneperfect (see README).
if [ -d data/toneperfect ]; then run app.importers.toneperfect /data/toneperfect; fi
docker compose restart api   # reload the segmenter dictionary
