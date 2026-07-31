from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


# engine = create_async_engine(settings.database_url)

# pgbouncer (Supabase session pooler) doesn't support prepared statements,
# so disable asyncpg's statement cache for Postgres. SQLite ignores these.
_connect_args = {}
if settings.database_url.startswith("postgresql"):
    _connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }

engine = create_async_engine(settings.database_url, connect_args=_connect_args)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
