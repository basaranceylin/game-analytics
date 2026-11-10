from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Event(Base):
    """One gameplay event sent by a Roblox game server.

    player_hash is a salted HMAC of the Roblox UserId: the raw id is never stored.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    player_hash: Mapped[str] = mapped_column(String(64), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    type: Mapped[str] = mapped_column(String(32))
    zone: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_events_type_ts", "type", "ts"),
        Index("ix_events_player_ts", "player_hash", "ts"),
    )
