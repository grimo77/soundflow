"""
Test fixtures — uses a temp file DB so tables persist within a test session.
"""

import os
import tempfile
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Set env BEFORE any app imports
_tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmpdb.close()
os.environ["STOC_DB_PATH"] = _tmpdb.name
os.environ["STOC_DISCOVERY_ENABLED"] = "false"
os.environ["STOC_SPOTIFY_CLIENT_ID"] = ""
os.environ["STOC_SPOTIFY_CLIENT_SECRET"] = ""


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def client():
    from soundtouch.main import app
    from soundtouch.database import init_db
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
