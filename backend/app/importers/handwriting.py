"""Import the HSK 3.0 (November 2025) handwriting lists as character units.

    python -m app.importers.handwriting path/to/dir-with-HSK_Level_*_handwritten.txt

Source: krmanik/HSK-3.0, "New HSK (2025)/HSK Handwritten", transcribed from the
official syllabus. One character per line; files are named by level band
(1-2, 3, 4, 5, 6, 7-9). Tags: hw2025:<band>, with the position kept in
extra.hw_order so practice follows the list order.
"""

import re
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.importers import record_version
from app.units import ensure_character

BANDS = ["1-2", "3", "4", "5", "6", "7-9"]
_FILE = re.compile(r"HSK_Level_([0-9]+(?:-[0-9]+)?)_handwritten\.txt$")


def import_handwriting(db: Session, directory: Path) -> int:
    count = 0
    for f in sorted(directory.iterdir()):
        m = _FILE.search(f.name)
        if not m or m.group(1) not in BANDS:
            continue
        band = m.group(1)
        chars = [line.strip() for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        for i, ch in enumerate(chars):
            unit = ensure_character(db, ch)
            tag = f"hw2025:{band}"
            if tag not in (unit.level_tags or []):
                unit.level_tags = sorted({*(unit.level_tags or []), tag})
            unit.extra = {**(unit.extra or {}), "hw_order": BANDS.index(band) * 10_000 + i}
            count += 1
    record_version(db, "zh", "hsk-handwriting-2025", "krmanik/HSK-3.0")
    db.commit()
    return count


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported {import_handwriting(db, Path(sys.argv[1]))} handwriting characters")
