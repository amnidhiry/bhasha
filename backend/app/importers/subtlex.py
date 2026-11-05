"""Import SUBTLEX-CH-WF word frequencies (Cai & Brysbaert, 2010).

    python -m app.importers.subtlex path/to/SUBTLEX-CH-WF

The file is tab-separated: two metadata lines ("Total word count: ..." and
"Context number: ..."), a header (Word, WCount, W/million, logW, W-CD, W-CD%,
logW-CD), then one word per line. Official copies are often GBK-encoded;
UTF-8 works too. Units without a frequency rank (words outside the HSK list,
including ones first met in your texts) get the SUBTLEX rank.
"""

import sys
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.importers import file_version, record_version
from app.models import Unit, WordFrequency


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("SUBTLEX file is neither UTF-8 nor GB18030")


def parse(text: str) -> list[tuple[str, int, float, float]]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    header_at = next(i for i, ln in enumerate(lines) if ln.split("\t")[0].strip().strip('"') == "Word")
    cols = [c.strip().strip('"') for c in lines[header_at].split("\t")]
    i_word, i_count, i_pm, i_cdp = cols.index("Word"), cols.index("WCount"), cols.index("W/million"), cols.index("W-CD%")
    rows = []
    for ln in lines[header_at + 1:]:
        parts = ln.split("\t")
        if len(parts) <= max(i_word, i_count, i_pm, i_cdp):
            continue
        word = parts[i_word].strip()
        try:
            rows.append((word, int(float(parts[i_count])), float(parts[i_pm]), float(parts[i_cdp])))
        except ValueError:
            continue
    rows.sort(key=lambda r: -r[1])
    return rows


def import_subtlex(db: Session, path: Path) -> int:
    rows = parse(_decode(path.read_bytes()))
    db.execute(delete(WordFrequency).where(WordFrequency.language == "zh"))
    seen: set[str] = set()
    mappings = []
    for rank, (word, _count, pm, cdp) in enumerate(rows, start=1):
        if word in seen:
            continue
        seen.add(word)
        mappings.append({"language": "zh", "word": word, "rank": rank, "per_million": pm, "cd_percent": cdp})
    for i in range(0, len(mappings), 5000):
        db.bulk_insert_mappings(WordFrequency, mappings[i : i + 5000])
    db.flush()
    # Fill ranks the HSK data doesn't have.
    ranks = {m["word"]: m["rank"] for m in mappings}
    for uid, head in db.execute(select(Unit.id, Unit.headword).where(Unit.type == "word", Unit.frequency_rank.is_(None))):
        if head in ranks:
            db.execute(update(Unit).where(Unit.id == uid).values(frequency_rank=ranks[head]))
    record_version(db, "zh", "subtlex-ch-wf", file_version(path))
    db.commit()
    return len(mappings)


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported {import_subtlex(db, Path(sys.argv[1]))} SUBTLEX-CH word frequencies")
