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

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ---------------------------------------------------------------------------
# Async database URL
# ---------------------------------------------------------------------------
_db_url = settings.database_url.replace(
    "postgresql://", "postgresql+asyncpg://"
).replace(
    "postgres://", "postgresql+asyncpg://"
)

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
