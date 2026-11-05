"""Import Make Me a Hanzi graphics.txt (stroke paths and medians).

    python -m app.importers.hanzi_graphics path/to/graphics.txt

Licensed under the Arphic Public License (see the Make Me a Hanzi repo); kept
in its own table and served only to this app's handwriting quizzes.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.importers import file_version, record_version
from app.models import CharacterStrokes


def import_graphics(db: Session, path: Path) -> int:
    db.execute(delete(CharacterStrokes))
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                rows.append({"character": d["character"], "strokes": d["strokes"], "medians": d["medians"]})
    for i in range(0, len(rows), 1000):
        db.bulk_insert_mappings(CharacterStrokes, rows[i : i + 1000])
    record_version(db, "zh", "makemeahanzi-graphics", file_version(path))
    db.commit()
    return len(rows)


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported strokes for {import_graphics(db, Path(sys.argv[1]))} characters")
