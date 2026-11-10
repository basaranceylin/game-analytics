import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict

from fastapi import Header, HTTPException, status


def _api_key() -> str:
    return os.getenv("API_KEY", "")


def require_api_key(x_api_key: str = Header(default="")) -> str:
    expected = _api_key()
    if not expected or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
    return x_api_key


def hash_player(user_id: int) -> str:
    """Pseudonymise a Roblox UserId with a server-side secret salt."""
    salt = os.getenv("PLAYER_SALT", "dev-only-salt").encode()
    return hmac.new(salt, str(user_id).encode(), hashlib.sha256).hexdigest()


# ---- rate limiting: Redis when REDIS_URL is set, in-process fixed window otherwise ----
_local_hits: dict[str, list[float]] = defaultdict(list)
_redis = None


def _get_redis():
    global _redis
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    if _redis is None:
        import redis  # imported lazily so tests run without a Redis server

        _redis = redis.Redis.from_url(url, socket_timeout=0.5)
    return _redis


def reset_rate_limiter() -> None:
    _local_hits.clear()


def rate_limit(api_key: str) -> None:
    limit = int(os.getenv("RATE_LIMIT_PER_MIN", "600"))
    window = int(time.time() // 60)
    r = _get_redis()
    if r is not None:
        try:
            key = f"rl:{api_key[:8]}:{window}"
            count = r.incr(key)
            if count == 1:
                r.expire(key, 70)
            if count > limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
            return
        except HTTPException:
            raise
        except Exception:
            pass  # Redis down: fall back to the local limiter instead of failing the game
    now = time.time()
    hits = [t for t in _local_hits[api_key] if now - t < 60]
    if len(hits) >= limit:
        _local_hits[api_key] = hits
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
    hits.append(now)
    _local_hits[api_key] = hits
