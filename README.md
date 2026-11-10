# Anime Heist Analytics

Analytics backend for my live Roblox game **Steal An Anime Character**.
The game's server scripts batch gameplay events and POST them to this API, which stores them
in PostgreSQL and exposes aggregate stats (DAU, sessions, Robux revenue, observed crate drop rates).

**Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, Docker, GitHub Actions, Pytest, Luau.

## Why it exists
The game has a drop-rate economy (9 mine zones, 9 rarity tiers, mutations, premium crates).
Designed odds and what players actually see can drift, and I want data on where players
progress, what they buy and where they leave, so balance changes are based on numbers.

## Architecture
```
Roblox server (Luau)                       This API
Analytics.track(...)  --queue--> batch --> POST /v1/events  --> PostgreSQL
 (flush every 10 s,                         API-key auth        GET /v1/stats/daily
  max 100 events,                           rate limit (Redis)  GET /v1/stats/drops
  retry, bounded queue)                     pydantic validation
```
Design decisions
- **Batching:** Roblox allows ~500 HTTP requests/min per server, so events are queued and sent in batches of up to 100.
- **Privacy:** the game sends the Roblox UserId only to this API, which immediately replaces it with a salted
  HMAC-SHA256 (`player_hash`). The raw id is never stored (covered by a test). No usernames or chat are collected.
- **Never hurt gameplay:** failed sends are retried from a bounded in-memory queue; Redis outage falls back to a local rate limiter.
- **Secrets:** the API key lives in Roblox Secrets and `.env`, never in source.

## Event catalogue (mapped from the game's server remotes)
| Event | Fired when | Fields |
|---|---|---|
| `session_start` / `session_end` | player joins / leaves | |
| `steal` | crate grabbed in a mine zone (`CollectAll`, mine pickup) | `zone`, `amount` = crate weight |
| `box_open` | crate opened at base (`OpenBox`) | `zone`, `rarity`, `data.character`, `data.mutation` |
| `sell` / `fuse` / `upgrade` | `Sell`, `Fuse`, `Upgrade` remotes | `amount` = cash, `data.character` |
| `rebirth` | `Rebirth` | `data.count` |
| `train` | batched `TrainClick` reps | `amount` = reps, `data.kind` (Power/Speed) |
| `purchase` | `ProcessReceipt`, gamepass purchased | `amount` = Robux, `data.product` |
| `shop_buy` | `BuyShop`, `BuyPotion`, `BuyTrail` | `amount` = cash, `data.item` |
| `reward_claim` | `Reward` (Daily/Quest/Playtime/Code) | `data.kind` |
| `boss_catch` | boss catches a carrier | `zone` |

## Run locally
```bash
cp .env.example .env        # then replace the three change-me values (use letters and digits only in POSTGRES_PASSWORD, it goes into a URL)
docker compose up --build   # API on http://localhost:8000/docs
```
Without Docker:
```bash
pip install -r requirements-dev.txt
pytest -q
API_KEY=dev PLAYER_SALT=dev uvicorn app.main:app --reload
```

## API
- `POST /v1/events` (header `X-API-Key`): `{"events": [{"type": "steal", "user_id": 1, "zone": 3, "amount": 5000}]}`
- `GET /v1/stats/daily?days=7`: DAU, sessions, events, steals, Robux per day
- `GET /v1/stats/drops`: observed rarity distribution of opened crates
- `GET /health`

## Results
Load test with [Locust](https://locust.io) (`loadtest/locustfile.py`): 50 simulated game servers, each sending
event batches of 1-25 events, plus occasional stats reads, for 60 s.

Environment: single uvicorn worker on a Windows dev machine, **SQLite** (not PostgreSQL), rate limit disabled,
Locust on the same machine. These numbers are a local baseline, not production capacity.

| Endpoint | Requests | Failures | Median | p95 | p99 |
|---|---|---|---|---|---|
| `POST /v1/events` | 3,460 | 0 | 46 ms | 740 ms | 2,300 ms |
| `GET /v1/stats/daily` | 170 | 0 | 51 ms | 100 ms | 150 ms |
| `GET /v1/stats/drops` | 144 | 0 | 17 ms | 75 ms | 110 ms |
| **All** | 3,774 | 0 | 44 ms | 670 ms | 2,200 ms |

Throughput was about **64 requests/s** (58 req/s of event ingestion). The long tail on `POST /v1/events`
(max 5.3 s) is probably SQLite's single-writer lock, but that has not been verified against PostgreSQL.
The deployed Render free instance has not been load tested: it spins down when idle and the API enforces
600 requests/min per key by default.

Run it yourself: `API_KEY=... locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 --headless -u 50 -r 10 -t 60s`.
Test events carry `data.load_test = true` so they can be deleted afterwards.

Game traffic numbers (visits, peak concurrent players) are not included yet because the game is not published.

## Roblox side (already wired into the game)
`Analytics.track` calls are in `GameServer` for: `steal`, `box_open`, `sell`, `fuse`, `upgrade`, `rebirth`,
`shop_buy`, `purchase` (premium crates and gamepasses), `reward_claim`, `boss_catch`; the module itself sends
`session_start`/`session_end`. `train` is not instrumented yet. Until `API_URL` is set the module is a no-op.

`roblox/Analytics.lua` is a ModuleScript for `ServerScriptService`. Set `API_URL`, enable HTTP requests in
Game Settings, add the secret `analytics_api_key`, then call `Analytics.track(player, "steal", {zone = 3})`
next to the existing remote handlers in `GameServer`.
