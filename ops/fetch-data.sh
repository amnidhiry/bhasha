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
# SUBTLEX-CH word frequencies (Cai & Brysbaert, 2010). This is a GitHub copy of the
# research dataset; the original is at crr.ugent.be (SUBTLEX-CH-WF), and either works.
curl -fL -o data/SUBTLEX-CH-WF \
  https://raw.githubusercontent.com/leonsilicon/subtlex-ch-wf/main/data/SUBTLEX-CH-WF
# Tatoeba sentences (CC BY 2.0 FR); the importer reads the .bz2 files directly.
mkdir -p data/tatoeba
for f in cmn/cmn_sentences.tsv.bz2 eng/eng_sentences.tsv.bz2 cmn/cmn-eng_links.tsv.bz2; do
  curl -fL -o "data/tatoeba/$(basename "$f")" "https://downloads.tatoeba.org/exports/per_language/$f"
done
curl -fL -o data/cedict.txt.gz \
  https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz
gunzip -f data/cedict.txt.gz
echo "done: $(ls data)"
