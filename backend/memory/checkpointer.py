"""
QueryMind — LangGraph Postgres Checkpointer (Short-Term Memory)
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from backend.core.config import settings
import structlog

logger = structlog.get_logger(__name__)

_pool: AsyncConnectionPool | None = None
_pool_opened = False
_setup_done = False

async def _get_pool() -> AsyncConnectionPool:
    """Get or create the psycopg AsyncConnectionPool."""
    global _pool, _pool_opened
    if _pool is None:
        # psycopg3 requires the scheme to be 'postgresql' or 'postgres', not 'postgresql+asyncpg'
        conninfo = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=20,
            kwargs={"autocommit": True},
            open=False,
        )
        logger.info("psycopg_pool_created", max_size=20)
    if not _pool_opened:
        await _pool.open()
        _pool_opened = True
        logger.info("psycopg_pool_opened")
    return _pool

@asynccontextmanager
async def get_checkpointer() -> AsyncGenerator[AsyncPostgresSaver, None]:
    """Yields a configured AsyncPostgresSaver for LangGraph."""
    global _setup_done
    pool = await _get_pool()
    saver = AsyncPostgresSaver(pool)
    # Setup tables only once to avoid repeated DDL per request.
    if not _setup_done:
        await saver.setup()
        _setup_done = True
        logger.info("checkpointer_setup_complete")
    try:
        yield saver
    finally:
        pass

async def close_checkpointer():
    """Close the connection pool cleanly on shutdown."""
    global _pool, _pool_opened
    if _pool:
        await _pool.close()
        _pool = None
        _pool_opened = False
        logger.info("psycopg_pool_closed")
