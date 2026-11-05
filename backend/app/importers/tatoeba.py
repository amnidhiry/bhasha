"""Import Tatoeba Mandarin sentences with English translations (CC BY 2.0 FR).

    python -m app.importers.tatoeba cmn_sentences.tsv[.bz2] eng_sentences.tsv[.bz2] cmn-eng_links.tsv[.bz2]

Files from https://downloads.tatoeba.org/exports/ : per_language/cmn/cmn_sentences.tsv.bz2,
per_language/eng/eng_sentences.tsv.bz2 and per_language/cmn/cmn-eng_links.tsv.bz2
(the full links.csv works too). Sentence files are `id<TAB>lang<TAB>text`; link
files are `id<TAB>id`.

Kept: Simplified-script sentences of 2-30 characters with an English
translation. Traditional ones are skipped by checking for characters that only
appear on CC-CEDICT's traditional side, so import CC-CEDICT first. Each
sentence keeps its Tatoeba id: attribution is a link to its page.
"""

import bz2
import re
import sys
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.bootstrap import warm_packs
from app.importers import record_version
from app.models import CedictEntry, ExampleSentence, SentenceUnit, Unit, WordFrequency
from app.packs import get_pack
from app.packs.base import WORD

MAX_CHARS = 30
_CJK = re.compile(r"[㐀-鿿]")
_LATIN = re.compile(r"[A-Za-z]")
UNKNOWN_RANK = 1_000_000


def _lines(path: Path) -> Iterator[str]:
    opener = bz2.open if path.suffix == ".bz2" else open
    with opener(path, "rt", encoding="utf-8") as f:
        yield from f


def _sentences(path: Path) -> Iterator[tuple[int, str]]:
    for line in _lines(path):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3 and parts[0].isdigit():
            yield int(parts[0]), parts[2].strip()


def traditional_only_chars(db: Session) -> set[str]:
    trad, simp = set(), set()
    for t, s in db.execute(select(CedictEntry.traditional, CedictEntry.simplified)):
        trad.update(t)
        simp.update(s)
    return {c for c in trad - simp if _CJK.match(c)}


def import_tatoeba(db: Session, cmn: Path, eng: Path, links: Path) -> int:
    trad_only = traditional_only_chars(db)
    kept: dict[int, str] = {}
    for sid, text in _sentences(cmn):
        if 2 <= len(text) <= MAX_CHARS and _CJK.search(text) and not _LATIN.search(text) \
                and not any(c in trad_only for c in text):
            kept[sid] = text

    wanted: dict[int, list[int]] = {}
    for line in _lines(links):
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            a, b = int(parts[0]), int(parts[1])
            if a in kept:
                wanted.setdefault(a, []).append(b)
    needed = {e for ids in wanted.values() for e in ids}
    english = {sid: text for sid, text in _sentences(eng) if sid in needed}

    warm_packs(db)
    pack = get_pack("zh")
    units: dict[str, int] = {}
    for uid, head, extra in db.execute(select(Unit.id, Unit.headword, Unit.extra)
                                       .where(Unit.language == "zh", Unit.type == "word").order_by(Unit.id)):
        if head not in units or (extra or {}).get("primary_form"):
            units[head] = uid
    unit_rank = dict(db.execute(select(Unit.headword, Unit.frequency_rank)
                                .where(Unit.language == "zh", Unit.frequency_rank.is_not(None))).all())
    freq = dict(db.execute(select(WordFrequency.word, WordFrequency.rank).where(WordFrequency.language == "zh")).all())

    old = select(ExampleSentence.id).where(ExampleSentence.language == "zh")
    db.execute(delete(SentenceUnit).where(SentenceUnit.sentence_id.in_(old)))
    db.execute(delete(ExampleSentence).where(ExampleSentence.language == "zh"))
    sentences, links_rows = [], []
    for sid, text in kept.items():
        translations = sorted(i for i in wanted.get(sid, []) if i in english)
        if not translations:
            continue
        words = [t.surface for t in pack.analyze(text) if t.kind == WORD]
        if not words:
            continue
        ranks = [freq.get(w) or unit_rank.get(w) or UNKNOWN_RANK for w in words]
        sentences.append({"id": sid, "language": "zh", "source": "tatoeba", "text": text, "translation": english[translations[0]],
                          "n_words": len(words), "difficulty": max(ranks)})
        for uid in {units[w] for w in words if w in units}:
            links_rows.append({"sentence_id": sid, "unit_id": uid})
    for i in range(0, len(sentences), 5000):
        db.bulk_insert_mappings(ExampleSentence, sentences[i : i + 5000])
    for i in range(0, len(links_rows), 10000):
        db.bulk_insert_mappings(SentenceUnit, links_rows[i : i + 10000])
    record_version(db, "zh", "tatoeba", f"{len(sentences)} sentences")
    db.commit()
    return len(sentences)


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        n = import_tatoeba(db, Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
        print(f"imported {n} Tatoeba sentences")
