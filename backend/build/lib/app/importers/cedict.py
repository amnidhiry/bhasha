"""Import CC-CEDICT (CC BY-SA 4.0) into its own table.

    python -m app.importers.cedict path/to/cedict_ts.u8

Download: https://www.mdbg.net/chinese/dictionary?page=cedict
"""

import re
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.importers import record_version
from app.models import CedictEntry

_LINE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]*)\]\s+/(.*)/\s*$")


def normalize_pinyin(p: str) -> str:
    """'Bei3 jing1' -> 'bei3 jing1'; 'lu:4' -> 'lv4'; bare 'r' / 'xx' kept, neutral 5 kept."""
    return " ".join(s.lower().replace("u:", "v") for s in p.split())


def parse(lines: Iterable[str]) -> Iterator[tuple[str, str, str, list[str]]]:
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        m = _LINE.match(line.strip())
        if m:
            trad, simp, pinyin, glosses = m.groups()
            yield trad, simp, pinyin, [g for g in glosses.split("/") if g]


def version_of(lines: list[str]) -> str:
    for line in lines[:40]:
        if line.startswith("#! date="):
            return line.split("=", 1)[1].strip()
    return "unknown"


def import_cedict(db: Session, path: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    db.execute(delete(CedictEntry))
    rows = [
        {"traditional": t, "simplified": s, "pinyin": p, "glosses": g}
        for t, s, p, g in parse(lines)
    ]
    for i in range(0, len(rows), 5000):
        db.bulk_insert_mappings(CedictEntry, rows[i : i + 5000])
    record_version(db, "zh", "cc-cedict", version_of(lines))
    db.commit()
    return len(rows)


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported {import_cedict(db, Path(sys.argv[1]))} CC-CEDICT entries")
