import os
import tempfile

# Must be set before the app is imported.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["API_KEY"] = "test-key"
os.environ["PLAYER_SALT"] = "test-salt"
os.environ.pop("REDIS_URL", None)

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.security import reset_rate_limiter

HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_rate_limiter()
    os.environ["RATE_LIMIT_PER_MIN"] = "600"
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def headers():
    return HEADERS
