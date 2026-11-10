"""Load test for the analytics API.

    API_KEY=... locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \
        --headless -u 50 -r 10 -t 60s --csv loadtest/out

Traffic shape mimics the game: many small event batches (a server flushes every 10 s with a handful
of events), occasional dashboard reads. Every event carries data.load_test=true so test rows can be
deleted later (DELETE FROM events WHERE data->>'load_test' = 'true').
"""
import os
import random
import time

from locust import HttpUser, between, task

API_KEY = os.environ["API_KEY"]
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# rough share of each event type in real play
TYPES = ["steal"] * 30 + ["box_open"] * 20 + ["sell"] * 15 + ["upgrade"] * 10 + ["train"] * 10 + [
    "shop_buy", "reward_claim", "fuse", "boss_catch", "rebirth", "purchase",
]
RARITIES = ["Common", "Rare", "Epic", "Legendary", "Mythic", "Secret"]


def make_event(player: int, session: str) -> dict:
    t = random.choice(TYPES)
    ev = {
        "type": t,
        "user_id": player,
        "ts": int(time.time()),
        "session_id": session,
        "zone": random.randint(1, 9),
        "data": {"load_test": True},
    }
    if t == "box_open":
        ev["rarity"] = random.choice(RARITIES)
    if t in ("steal", "purchase", "train"):
        ev["amount"] = random.randint(1, 5000)
    return ev


class GameServer(HttpUser):
    """One simulated Roblox server: flushes a batch every ~10 s (compressed here to 0.2-1 s for load)."""

    wait_time = between(0.2, 1.0)

    def on_start(self):
        self.player = random.randint(1, 1_000_000)
        self.session = f"{random.getrandbits(64):016x}"

    @task(20)
    def send_events(self):
        batch = [make_event(self.player, self.session) for _ in range(random.randint(1, 25))]
        self.client.post("/v1/events", json={"events": batch}, headers=HEADERS, name="POST /v1/events")

    @task(1)
    def daily(self):
        self.client.get("/v1/stats/daily?days=7", headers=HEADERS, name="GET /v1/stats/daily")

    @task(1)
    def drops(self):
        self.client.get("/v1/stats/drops", headers=HEADERS, name="GET /v1/stats/drops")
