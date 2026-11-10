from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from . import models
from .db import Base, engine, get_db
from .schemas import Accepted, DailyStat, DropStat, EventBatch
from .security import hash_player, rate_limit, require_api_key


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Anime Heist Analytics", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/events", response_model=Accepted, status_code=202)
def ingest(batch: EventBatch, db: Session = Depends(get_db), key: str = Depends(require_api_key)) -> Accepted:
    rate_limit(key)
    now = datetime.now(timezone.utc)
    rows = [
        models.Event(
            ts=datetime.fromtimestamp(e.ts, timezone.utc) if e.ts else now,
            player_hash=hash_player(e.user_id),
            session_id=e.session_id,
            type=e.type,
            zone=e.zone,
            rarity=e.rarity,
            amount=e.amount,
            data=e.data,
        )
        for e in batch.events
    ]
    db.add_all(rows)
    db.commit()
    return Accepted(accepted=len(rows))


@app.get("/v1/stats/daily", response_model=list[DailyStat], dependencies=[Depends(require_api_key)])
def daily(days: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)) -> list[DailyStat]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    E = models.Event
    day = func.date(E.ts)
    q = (
        select(
            day.label("day"),
            func.count(distinct(E.player_hash)),
            func.count(distinct(E.session_id)),
            func.count(E.id),
            func.count(E.id).filter(E.type == "steal"),
            func.coalesce(func.sum(E.amount).filter(E.type == "purchase"), 0),
        )
        .where(E.ts >= since)
        .group_by(day)
        .order_by(day)
    )
    return [
        DailyStat(day=str(r[0]), dau=r[1], sessions=r[2], events=r[3], steals=int(r[4] or 0), robux=float(r[5] or 0))
        for r in db.execute(q)
    ]


@app.get("/v1/stats/drops", response_model=list[DropStat], dependencies=[Depends(require_api_key)])
def drops(db: Session = Depends(get_db)) -> list[DropStat]:
    """Observed rarity distribution of opened crates, to compare against the designed drop weights."""
    E = models.Event
    rows = db.execute(
        select(E.rarity, func.count(E.id)).where(E.type == "box_open", E.rarity.is_not(None)).group_by(E.rarity)
    ).all()
    total = sum(c for _, c in rows) or 1
    return sorted(
        (DropStat(rarity=r, count=c, share=round(c / total, 4)) for r, c in rows),
        key=lambda d: -d.count,
    )
