import uuid
from datetime import datetime, timedelta, timezone


def _import(client, body="我在银行工作。朋友是医生。"):
    r = client.post("/api/texts/import", json={"title": "t", "body": body})
    assert r.status_code == 200, r.text
    return r.json()


def test_import_resolves_units_and_reports_coverage(client):
    t = _import(client)
    words = [tok for tok in t["tokens"] if tok["kind"] == "word"]
    assert [w["surface"] for w in words] == ["我", "在", "银行", "工作", "朋友", "是", "医生"]
    assert all(w["unit_id"] for w in words)
    assert t["coverage_at_creation"] == 0.0
    friend = next(w for w in words if w["surface"] == "朋友")
    assert [s["citation_display"] for s in friend["syllables"]] == ["péng", "you"]  # HSK reading wins
    assert friend["status"] == "new" and friend["show_reading"]


def test_placement_mark_changes_coverage(client):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})
    t = _import(client)
    # 我 在 工作 朋友 known (HSK 1 fixture); 银行 是 医生 not.
    assert abs(t["coverage_at_creation"] - 4 / 7) < 1e-9
    p = client.get("/api/progress").json()
    assert p["level_cumulative"][0] == {"level": "1", "label": "1", "words": 4, "known": 4, "coverage": 1.0}
    assert p["known_characters"] == len(set("我在工作朋友"))


def test_lookup(client):
    r = client.get("/api/lookup", params={"q": "银行"}).json()
    assert r["reading"]["citation_display"] == "yín háng"
    assert r["cedict"][0]["glosses"][0] == "bank"
    assert r["units"][0]["classifiers"] == ["家", "个"]
    assert r["characters"][0]["decomposition"] == "⿰钅艮"


def test_mine_requires_context(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    assert client.post("/api/mine", json={"unit_id": bank["unit_id"]}).status_code == 422
    r = client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "我在银行工作。"})
    assert [c["facet"] for c in r.json()["created"]] == ["meaning", "reading"]


def test_review_flow_sibling_rule_and_idempotent_sync(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "我在银行工作。"})

    due = client.get("/api/reviews/due").json()
    assert len(due) == 1  # one facet per unit at a time
    card = due[0]
    assert card["is_new"] and card["context_sentence"] == "我在银行工作。"

    review = {"id": str(uuid.uuid4()), "card_id": card["card_id"], "rating": 3,
              "reviewed_at": datetime.now(timezone.utc).isoformat()}
    assert client.post("/api/reviews", json=[review]).json()["applied"] == [review["id"]]
    assert client.post("/api/reviews", json=[review]).json()["duplicates"] == [review["id"]]

    # The sibling facet was not reviewed today, but its unit was: it must wait.
    assert all(d["unit_id"] != bank["unit_id"] or d["card_id"] == card["card_id"]
               for d in client.get("/api/reviews/due").json())


def test_out_of_order_sync_replays(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    cid = client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s",
                                     "facets": ["meaning"]}).json()["created"][0]["card_id"]
    now = datetime.now(timezone.utc)
    late = {"id": str(uuid.uuid4()), "card_id": cid, "rating": 3, "reviewed_at": now.isoformat()}
    early = {"id": str(uuid.uuid4()), "card_id": cid, "rating": 3,
             "reviewed_at": (now - timedelta(minutes=20)).isoformat()}
    client.post("/api/reviews", json=[late])
    r = client.post("/api/reviews", json=[early]).json()
    assert r["replayed_cards"] == [cid]


def test_listening_card_appears_after_review_state(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    cid = client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s",
                                     "facets": ["meaning"]}).json()["created"][0]["card_id"]
    now = datetime.now(timezone.utc)
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": cid, "rating": 4,
                                   "reviewed_at": now.isoformat()}])
    from sqlalchemy import select
    from app.models import Card
    with client.session_factory() as s:
        facets = set(s.scalars(select(Card.facet).where(Card.unit_id == bank["unit_id"])))
    assert facets == {"meaning", "listening"}


def test_lookup_of_carded_word_logs_failed_review(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    cid = client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s",
                                     "facets": ["meaning"]}).json()["created"][0]["card_id"]
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": cid, "rating": 3,
                                   "reviewed_at": datetime.now(timezone.utc).isoformat()}])
    r = client.get("/api/lookup", params={"q": "银行", "log": True, "text_id": t["id"]}).json()
    assert r["logged"] == "failed_review"


def test_finish_logs_exposures(client):
    t = _import(client)
    r = client.post(f"/api/texts/{t['id']}/finish").json()
    assert r["exposures"] == 7
    assert client.get("/api/progress").json()["texts_finished"] == 1


def test_importers_are_idempotent(client):
    from pathlib import Path
    from sqlalchemy import func, select
    from app.importers.hsk import import_hsk
    from app.importers.cedict import import_cedict
    from app.models import Unit
    fx = Path(__file__).parent / "fixtures"
    with client.session_factory() as s:
        before = s.scalar(select(func.count()).select_from(Unit))
        import_hsk(s, fx / "hsk_sample.json")
        import_cedict(s, fx / "cedict_sample.u8")
        assert s.scalar(select(func.count()).select_from(Unit)) == before


def test_due_card_has_answer_side(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s"})
    card = client.get("/api/reviews/due").json()[0]
    assert card["meanings"] == ["bank"] and card["reading_display"] == "yín háng"
    assert card["classifiers"] == ["家", "个"]


def test_learning_cards_are_not_known_yet(client):
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    cid = client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s",
                                         "facets": ["meaning"]}).json()["created"][0]["card_id"]
    now = datetime.now(timezone.utc)
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": cid, "rating": 3,
                                       "reviewed_at": now.isoformat()}])
    assert client.get("/api/progress").json()["known_words"] == 0  # still in learning steps
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": cid, "rating": 4,
                                       "reviewed_at": (now + timedelta(minutes=1)).isoformat()}])
    assert client.get("/api/progress").json()["known_words"] == 1  # graduated, R ~ 1


def test_scheduler_params_and_card_state_for_offline_clients(client):
    p = client.get("/api/reviews/params").json()
    assert p["version"] == "FSRS-6" and len(p["weights"]) == 21
    assert p["learning_steps_minutes"] == [1.0, 10.0] and p["relearning_steps_minutes"] == [10.0]
    t = _import(client)
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s"})
    card = client.get("/api/reviews/due").json()[0]
    assert card["fsrs"]["state"] == 1 and card["fsrs"]["last_review"] is None
