import os
import tempfile

_tmpdir = tempfile.mkdtemp()
os.environ.setdefault("WARBLE_API_KEY", "test-key")
# Force, don't setdefault: .env (or a real shell/CI env var) may already set
# DATABASE_URL to Supabase, and setdefault would leave that in place — tests
# must never be able to touch a real database, no matter what's already in
# the environment. This has to run before any app module (which reads
# settings at import time) is imported.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"

import pytest_asyncio  # noqa: E402

from app.db.base import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _reset_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
