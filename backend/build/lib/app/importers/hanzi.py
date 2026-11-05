"""Import Make Me a Hanzi dictionary.txt (decomposition, radical, etymology).

    python -m app.importers.hanzi path/to/dictionary.txt

Source: https://github.com/skishore/makemeahanzi (dictionary.txt is separately
licensed from the Arphic-licensed graphics.txt; check before redistributing).
Stroke data (graphics.txt) is served to clients by Hanzi Writer and is not
stored here yet.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.importers import file_version, record_version
from app.models import CharacterInfo


def import_hanzi(db: Session, path: Path) -> int:
    db.execute(delete(CharacterInfo))
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rows.append(
            {
                "character": d["character"],
                "definition": d.get("definition"),
                "pinyin": d.get("pinyin", []),
                "decomposition": d.get("decomposition"),
                "radical": d.get("radical"),
                "etymology": d.get("etymology"),
            }
        )
    for i in range(0, len(rows), 5000):
        db.bulk_insert_mappings(CharacterInfo, rows[i : i + 5000])
    record_version(db, "zh", "makemeahanzi", file_version(path))
    db.commit()
    return len(rows)


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported {import_hanzi(db, Path(sys.argv[1]))} characters")
