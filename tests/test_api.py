import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Event


def ev(**kw):
    base = {"type": "steal", "user_id": 123, "session_id": "s1", "zone": 1}
    base.update(kw)
    return base


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_requires_api_key(client):
    r = client.post("/v1/events", json={"events": [ev()]})
    assert r.status_code == 401
    r = client.post("/v1/events", json={"events": [ev()]}, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


def test_ingest_batch(client, headers):
    r = client.post("/v1/events", json={"events": [ev(), ev(type="session_start")]}, headers=headers)
    assert r.status_code == 202
    assert r.json() == {"accepted": 2}


def test_raw_user_id_is_never_stored(client, headers):
    client.post("/v1/events", json={"events": [ev(user_id=987654321)]}, headers=headers)
    with SessionLocal() as db:
        row = db.scalars(select(Event)).one()
    assert "987654321" not in row.player_hash
    assert len(row.player_hash) == 64


def test_same_player_gets_same_hash(client, headers):
    client.post("/v1/events", json={"events": [ev(user_id=5), ev(user_id=5), ev(user_id=6)]}, headers=headers)
    with SessionLocal() as db:
        hashes = [e.player_hash for e in db.scalars(select(Event))]
    assert len(set(hashes)) == 2


def test_rejects_unknown_event_type(client, headers):
    r = client.post("/v1/events", json={"events": [ev(type="nope")]}, headers=headers)
    assert r.status_code == 422


def test_rejects_empty_and_oversized_batches(client, headers):
    assert client.post("/v1/events", json={"events": []}, headers=headers).status_code == 422
    big = {"events": [ev() for _ in range(101)]}
    assert client.post("/v1/events", json=big, headers=headers).status_code == 422


def test_rejects_bad_user_id(client, headers):
    assert client.post("/v1/events", json={"events": [ev(user_id=0)]}, headers=headers).status_code == 422


def test_daily_stats(client, headers):
    events = [
        ev(user_id=1, session_id="a"),
        ev(user_id=1, session_id="a", type="purchase", amount=99),
        ev(user_id=2, session_id="b"),
        ev(user_id=2, session_id="b", type="purchase", amount=199),
    ]
    client.post("/v1/events", json={"events": events}, headers=headers)
    rows = client.get("/v1/stats/daily?days=1", headers=headers).json()
    assert len(rows) == 1
    day = rows[0]
    assert day["dau"] == 2
    assert day["sessions"] == 2
    assert day["events"] == 4
    assert day["steals"] == 2
    assert day["robux"] == 298


def test_drop_distribution(client, headers):
    events = [ev(type="box_open", rarity="Common") for _ in range(3)] + [ev(type="box_open", rarity="Rare")]
    client.post("/v1/events", json={"events": events}, headers=headers)
    rows = client.get("/v1/stats/drops", headers=headers).json()
    assert rows[0] == {"rarity": "Common", "count": 3, "share": 0.75}
    assert rows[1]["rarity"] == "Rare"


def test_stats_require_api_key(client):
    assert client.get("/v1/stats/daily").status_code == 401
    assert client.get("/v1/stats/drops").status_code == 401


def test_rate_limit(client, headers):
    os.environ["RATE_LIMIT_PER_MIN"] = "3"
    codes = [client.post("/v1/events", json={"events": [ev()]}, headers=headers).status_code for _ in range(5)]
    assert codes == [202, 202, 202, 429, 429]


def test_dashboard_page_is_served_without_key(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Anime Heist" in r.text
    # the page itself carries no data; stats endpoints still need the key
    assert client.get("/v1/stats/daily").status_code == 401
