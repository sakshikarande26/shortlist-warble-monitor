import os
import tempfile

_tmpdir = tempfile.mkdtemp()
os.environ.setdefault("WARBLE_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmpdir}/test.db")

import pytest_asyncio  # noqa: E402

from app.db.base import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
