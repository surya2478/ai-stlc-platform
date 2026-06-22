"""
Database engine, session factory, and base model class.
Uses SQLAlchemy 2.x async engine with pgvector support.

Pool configuration:
  - Production (db_pool_enabled=True): AsyncAdaptedQueuePool with configurable
    pool_size, max_overflow, timeout, and recycle settings.
  - Testing / single-shot scripts (db_pool_enabled=False): NullPool — one
    connection per checkout, no background connections.
"""
import logging
from typing import AsyncGenerator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Async database URL
# ---------------------------------------------------------------------------
def _build_async_db_url(database_url: str) -> tuple[str, dict]:
    """
    Convert a generic Postgres URL into an asyncpg-compatible SQLAlchemy URL.

    Supabase examples commonly use `sslmode=require`, but asyncpg expects an
    `ssl` argument instead. Normalize that here so production URLs copied from
    Supabase work without manual rewriting.
    """
    async_url = database_url.replace(
        "postgresql://", "postgresql+asyncpg://"
    ).replace(
        "postgres://", "postgresql+asyncpg://"
    )
    parts = urlsplit(async_url)
    query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    connect_args: dict = {}

    sslmode = query_params.pop("sslmode", None)
    if sslmode:
        sslmode = sslmode.strip().lower()
        if sslmode in {"require", "verify-ca", "verify-full"}:
            connect_args["ssl"] = "require"
        elif sslmode in {"disable", "allow", "prefer"}:
            connect_args["ssl"] = sslmode

    normalized_query = urlencode(query_params)
    normalized_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, normalized_query, parts.fragment)
    )
    return normalized_url, connect_args


_db_url, _connect_args = _build_async_db_url(settings.database_url)

# ---------------------------------------------------------------------------
# Engine — pool strategy driven by config
# ---------------------------------------------------------------------------
_pool_kwargs: dict = {}

if settings.db_pool_enabled:
    # Production: use the default QueuePool (AsyncAdaptedQueuePool under async)
    _pool_kwargs = {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_pool_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
        "pool_pre_ping": settings.db_pool_pre_ping,
    }
    logger.info(
        "Database pool: QueuePool  size=%d  max_overflow=%d  "
        "timeout=%ds  recycle=%ds  pre_ping=%s",
        settings.db_pool_size,
        settings.db_pool_max_overflow,
        settings.db_pool_timeout,
        settings.db_pool_recycle,
        settings.db_pool_pre_ping,
    )
else:
    # Testing / dev-scripts: no persistent connections
    _pool_kwargs = {"poolclass": NullPool}
    logger.info("Database pool: NullPool (no connection reuse)")

engine = create_async_engine(
    _db_url,
    echo=settings.app_debug,
    connect_args=_connect_args,
    **_pool_kwargs,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_pool_status() -> dict:
    """
    Return current connection pool statistics.
    Useful for /health and /metrics endpoints.
    Returns empty dict when using NullPool.
    """
    pool = engine.pool
    if isinstance(pool, NullPool):
        return {"pool_type": "NullPool"}
    return {
        "pool_type": pool.__class__.__name__,
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalidated_count if hasattr(pool, "invalidated_count") else 0,
    }
