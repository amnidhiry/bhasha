"""Spell ü as v in stored readings (lü4 -> lv4), matching pypinyin and CC-CEDICT.

complete-hsk-vocabulary wrote ü; everything else uses v, so lookups by reading
missed and the reader showed raw "lü3". A unit whose v-spelled twin already
exists is left alone rather than merged.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, language, type, headword, reading FROM unit WHERE reading LIKE :p"),
                        {"p": "%ü%"}).fetchall()
    for uid, lang, typ, head, reading in rows:
        fixed = reading.replace("ü", "v")
        twin = conn.execute(sa.text("SELECT 1 FROM unit WHERE language=:l AND type=:t AND headword=:h AND reading=:r"),
                            {"l": lang, "t": typ, "h": head, "r": fixed}).first()
        if twin is None:
            conn.execute(sa.text("UPDATE unit SET reading=:r WHERE id=:id"), {"r": fixed, "id": uid})


def downgrade() -> None:
    pass  # the v spelling is equivalent; nothing to undo
