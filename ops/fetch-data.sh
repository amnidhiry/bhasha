#!/usr/bin/env bash
# Download the open datasets the importers read into ./data.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
curl -fL -o data/complete-hsk.json \
  https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json
curl -fL -o data/makemeahanzi-dictionary.txt \
  https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt
curl -fL -o data/cedict.txt.gz \
  https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz
gunzip -f data/cedict.txt.gz
echo "done: $(ls data)"
