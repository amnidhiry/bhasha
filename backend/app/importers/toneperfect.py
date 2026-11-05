"""Index Tone Perfect recordings (Michigan State University, open access; cite
"Tone Perfect: Multimodal Database for Mandarin Chinese" when you use it).

    python -m app.importers.toneperfect /data/toneperfect

Download the collection yourself from tone.lib.msu.edu and unpack it under the
audio directory (BHASHA_AUDIO_DIR, default /data/toneperfect). Files are named
like `ma3_FV1_MP3.mp3`: syllable, tone, speaker (FV1-3 female, MV1-3 male).
Only the index goes into the database; files are served from disk.
"""

import re
import sys
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.importers import record_version
from app.models import AudioSyllable

NAME = re.compile(r"^([a-zü]+?)([1-4])_([A-Za-z]+\d+)(?:_MP3)?\.mp3$", re.IGNORECASE)


def import_toneperfect(db: Session, root: Path) -> tuple[int, int]:
    db.execute(delete(AudioSyllable))
    seen: set[tuple[str, str]] = set()
    rows, skipped = [], 0
    for f in sorted(root.rglob("*.mp3")):
        m = NAME.match(f.name)
        if not m:
            skipped += 1
            continue
        key = (m.group(1).lower().replace("ü", "v").replace("u:", "v") + m.group(2))
        speaker = m.group(3).upper()
        if (key, speaker) in seen:
            continue
        seen.add((key, speaker))
        rows.append({"key": key, "speaker": speaker, "path": str(f.relative_to(root))})
    for i in range(0, len(rows), 2000):
        db.bulk_insert_mappings(AudioSyllable, rows[i : i + 2000])
    record_version(db, "zh", "toneperfect", f"{len(rows)} files")
    db.commit()
    return len(rows), skipped


if __name__ == "__main__":
    from app.bootstrap import ensure_defaults
    from app.db import SessionLocal

    with SessionLocal() as db:
        ensure_defaults(db)
        n, skipped = import_toneperfect(db, Path(sys.argv[1]))
        print(f"indexed {n} recordings" + (f" ({skipped} files didn't match the naming pattern)" if skipped else ""))
