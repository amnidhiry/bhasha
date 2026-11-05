import hashlib
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import PackVersion


def file_version(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def record_version(db: Session, language: str, component: str, version: str) -> None:
    """Idempotent: re-importing the same data version replaces its record."""
    db.execute(delete(PackVersion).where(
        PackVersion.language == language, PackVersion.component == component, PackVersion.version == version))
    db.add(PackVersion(language=language, component=component, version=version))
