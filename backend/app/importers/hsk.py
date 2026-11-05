"""Import HSK word lists from complete-hsk-vocabulary (MIT).

    python -m app.importers.hsk path/to/complete.json

Source: https://github.com/drkameleon/complete-hsk-vocabulary

Its level tags map to our version-tagged curriculum spine:
  newest-N -> hsk3-2025:N   (November 2025 syllabus; 7 means levels 7-9)
  new-N    -> hsk3-2021:N   (2021 proposal)
  old-N    -> hsk2:N        (HSK 2.0)
Cumulative 'newest' counts in the data (294/491/978/1950/3497/5181 for 1-6) sit
close to the published 300/500/1000/2000/3600/5400 targets; reconcile against
the official list before relying on exact level boundaries.

Level tags in the source are per headword, not per reading, so every reading of
a polyphone (的 de5 / di4) gets the tags; progress counts per headword.
"""

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.cedict import normalize_pinyin
from app.importers import file_version, record_version
from app.models import Unit

TAG_MAP = {"newest": "hsk3-2025", "new": "hsk3-2021", "old": "hsk2"}


def map_levels(levels: list[str]) -> list[str]:
    out = []
    for tag in levels:
        prefix, _, n = tag.rpartition("-")
        if prefix in TAG_MAP and n.isdigit():
            out.append(f"{TAG_MAP[prefix]}:{n}")
    return sorted(out)


def import_hsk(db: Session, path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = {
        (u.headword, u.reading): u
        for u in db.scalars(select(Unit).where(Unit.language == "zh", Unit.type == "word"))
    }
    count = 0
    for entry in data:
        tags = map_levels(entry.get("level", []))
        for i, form in enumerate(entry.get("forms", [])):
            reading = normalize_pinyin(form["transcriptions"]["numeric"])
            key = (entry["simplified"], reading)
            unit = existing.get(key)
            if unit is None:
                unit = Unit(language="zh", type="word", headword=key[0], reading=reading)
                db.add(unit)
                existing[key] = unit
            unit.traditional = form.get("traditional")
            unit.level_tags = sorted(set(unit.level_tags or []) | set(tags))
            unit.frequency_rank = entry.get("frequency")
            unit.track_tags = sorted(set(unit.track_tags or []) | {"everyday"})
            unit.extra = {
                **(unit.extra or {}),
                "source": "complete-hsk-vocabulary",
                "primary_form": i == 0,
                "pos": entry.get("pos", []),
                "radical": entry.get("radical"),
                "meanings": form.get("meanings", []),
                "classifiers": form.get("classifiers", []),
            }
            count += 1
    record_version(db, "zh", "complete-hsk-vocabulary", file_version(path))
    db.commit()
    return count


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        print(f"imported {import_hsk(db, Path(sys.argv[1]))} HSK word forms")
