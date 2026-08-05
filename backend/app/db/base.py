"""The one shared async engine/session factory, and the declarative Base
every ORM model inherits from. Everything else in the app gets its DB
session through `get_session()` here, never by constructing its own.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


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
# Supabase's session-mode pooler caps the whole project at 15 clients, and
# more than one process shares it (collector + web API, each locally and on
# Railway). SQLAlchemy's defaults — pool_size 5 plus max_overflow 10 — let a
# single process claim all 15 on its own, which is exactly how the collector
# started dying with "max clients reached in session mode". Capping each
# process at 5 (3 + 2 burst) leaves room for the others; pool_timeout makes a
# busy moment wait for a free connection instead of raising.
engine = create_async_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=3,
    max_overflow=2,
    pool_timeout=30,
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
