import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    from app import db as dbmod
    from app.db import Base, make_engine
    from sqlalchemy.orm import sessionmaker
    import app.models  # noqa: F401  (register tables)

    engine = make_engine(url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "SessionLocal", Session)
    import app.main as main
    monkeypatch.setattr(main, "SessionLocal", Session)

    def _get_db():
        with Session() as s:
            yield s

    from app.importers.cedict import import_cedict
    from app.importers.hanzi import import_hanzi
    from app.importers.hsk import import_hsk
    from app.bootstrap import ensure_defaults

    with Session() as s:
        ensure_defaults(s)
        import_cedict(s, FIXTURES / "cedict_sample.u8")
        import_hanzi(s, FIXTURES / "hanzi_sample.txt")
        import_hsk(s, FIXTURES / "hsk_sample.json")

    from app.packs import get_pack
    get_pack.cache_clear()

    from fastapi.testclient import TestClient
    main.app.dependency_overrides[dbmod.get_db] = _get_db
    with TestClient(main.app) as c:
        c.session_factory = Session
        yield c
    main.app.dependency_overrides.clear()
    get_pack.cache_clear()
