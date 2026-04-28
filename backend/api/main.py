"""
QueryMind Backend — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.api.routers import sources, chat, health
from backend.core.config import settings
from backend.core.database import engine, Base
from backend.core.redis_client import get_redis
from backend.core.qdrant_client import get_qdrant
from backend.observability.langfuse_client import init_langfuse
from backend.observability.prometheus import setup_prometheus
import structlog

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("QueryMind starting up", env=settings.APP_ENV)

    # Initialize DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized")

    # Test Redis connection
    redis = await get_redis()
    await redis.ping()
    logger.info("Redis connected")

    # Initialize Qdrant collections
    qdrant = get_qdrant()
    await _ensure_qdrant_collections(qdrant)
    logger.info("Qdrant collections initialized")

    # Initialize LangFuse
    init_langfuse()
    logger.info("LangFuse initialized")

    # Setup Prometheus metrics
    setup_prometheus(app)
    logger.info("Prometheus metrics setup")

    logger.info("QueryMind is ready", host=settings.APP_HOST, port=settings.APP_PORT)
    yield

    # Shutdown
    logger.info("QueryMind shutting down")
    await engine.dispose()
    await redis.aclose()


async def _ensure_qdrant_collections(qdrant):
    """Create Qdrant collections if they don't exist."""
    from qdrant_client.models import Distance, VectorParams
    collections = await qdrant.get_collections()
    existing = {c.name for c in collections.collections}

    vector_config = VectorParams(size=1536, distance=Distance.COSINE)

    for collection_name in [
        settings.QDRANT_COLLECTION_SCHEMA,
        settings.QDRANT_COLLECTION_MEMORY,
        settings.QDRANT_COLLECTION_QUERY_CACHE,
    ]:
        if collection_name not in existing:
            await qdrant.create_collection(
                collection_name=collection_name,
                vectors_config=vector_config,
            )
            logger.info("Qdrant collection created", collection=collection_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title="QueryMind API",
        description="Enterprise AI-to-SQL Conversational BI Platform",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, tags=["health"])
    app.include_router(sources.router, prefix="/api/v1/sources", tags=["sources"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    return app


app = create_app()
