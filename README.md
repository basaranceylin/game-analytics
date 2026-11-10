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
cp .env.example .env        # then edit the two secrets
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
_Fill in with real measurements after deploying:_
- Load test (locust/k6): **X req/s, p95 Y ms**
- Game: **Z visits, W peak concurrent players**

## Roblox side (already wired into the game)
`Analytics.track` calls are in `GameServer` for: `steal`, `box_open`, `sell`, `fuse`, `upgrade`, `rebirth`,
`shop_buy`, `purchase` (premium crates and gamepasses), `reward_claim`, `boss_catch`; the module itself sends
`session_start`/`session_end`. `train` is not instrumented yet. Until `API_URL` is set the module is a no-op.

`roblox/Analytics.lua` is a ModuleScript for `ServerScriptService`. Set `API_URL`, enable HTTP requests in
Game Settings, add the secret `analytics_api_key`, then call `Analytics.track(player, "steal", {zone = 3})`
next to the existing remote handlers in `GameServer`.
