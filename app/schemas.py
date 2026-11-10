from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# Event names mirror the game's server-side actions (see README "Event catalogue").
EventType = Literal[
    "session_start",
    "session_end",
    "steal",         # crate grabbed from a mine zone
    "box_open",      # crate opened at base -> character rolled
    "sell",
    "fuse",
    "upgrade",
    "rebirth",
    "train",         # batched: amount = reps
    "purchase",      # Robux: gamepass or developer product, amount = robux
    "shop_buy",      # in-game cash purchase
    "reward_claim",  # daily / quest / playtime / code
    "boss_catch",
]


class EventIn(BaseModel):
    type: EventType
    user_id: int = Field(gt=0, description="Roblox UserId; hashed server-side, never stored")
    ts: Optional[int] = Field(default=None, description="Unix seconds; defaults to receive time")
    session_id: Optional[str] = Field(default=None, max_length=64)
    zone: Optional[int] = Field(default=None, ge=1, le=20)
    rarity: Optional[str] = Field(default=None, max_length=16)
    amount: Optional[float] = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventBatch(BaseModel):
    # Roblox limits HttpService to 500 requests/min per server, so the game batches events.
    events: list[EventIn] = Field(min_length=1, max_length=100)


class Accepted(BaseModel):
    accepted: int


class DailyStat(BaseModel):
    day: str
    dau: int
    sessions: int
    events: int
    steals: int
    robux: float


class DropStat(BaseModel):
    rarity: str
    count: int
    share: float
