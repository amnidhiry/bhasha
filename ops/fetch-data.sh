#!/usr/bin/env bash
# Download the open datasets the importers read into ./data.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
curl -fL -o data/complete-hsk.json \
  https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json
curl -fL -o data/makemeahanzi-dictionary.txt \
  https://raw.githubusercontent.com/skishore/makemeahanzi/master/dictionary.txt
curl -fL -o data/makemeahanzi-graphics.txt \
  https://raw.githubusercontent.com/skishore/makemeahanzi/master/graphics.txt
mkdir -p data/hsk-handwriting
for band in 1-2 3 4 5 6 7-9; do
  curl -fL -o "data/hsk-handwriting/HSK_Level_${band}_handwritten.txt" \
    "https://raw.githubusercontent.com/krmanik/HSK-3.0/main/New%20HSK%20(2025)/HSK%20Handwritten/HSK_Level_${band}_handwritten.txt"
done
curl -fL -o data/cedict.txt.gz \
  https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz
gunzip -f data/cedict.txt.gz
echo "done: $(ls data)"
