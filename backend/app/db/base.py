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

# pool_pre_ping: test each pooled connection with a lightweight ping before
# handing it out, transparently replacing one Supabase's pgbouncer already
# closed server-side (otherwise the first query on it fails with
# asyncpg.exceptions.InterfaceError: connection is closed). pool_recycle
# proactively retires connections before the pooler's own idle timeout is
# likely to hit, on top of the reactive check.
engine = create_async_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
