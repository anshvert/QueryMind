"""
QueryMind — Long-Term Memory (User Preferences) via Qdrant
"""
import uuid
import asyncio
from typing import List
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
import structlog

from backend.core.qdrant_client import get_qdrant
from backend.core.config import settings

try:
    from fastembed import TextEmbedding
    _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
except ImportError:
    _embedder = None

logger = structlog.get_logger(__name__)

async def store_user_preference(user_id: str, preference_text: str) -> None:
    """Store a long-term user preference or fact as a vector in Qdrant."""
    if not _embedder:
        logger.warning("fastembed not available. Skipping long term memory storage.")
        return

    qdrant = get_qdrant()
    collection_name = settings.QDRANT_COLLECTION_MEMORY
    
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(None, lambda: list(_embedder.embed([preference_text])))
    
    if not embeddings:
        return
        
    vector = embeddings[0].tolist()
    
    point_id = str(uuid.uuid4())
    await qdrant.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "user_id": user_id,
                    "preference": preference_text
                }
            )
        ]
    )
    logger.info("user_preference_stored", user_id=user_id, point_id=point_id)

async def retrieve_user_preferences(user_id: str, query: str, top_k: int = 3) -> List[str]:
    """Retrieve relevant user preferences based on the current query."""
    if not _embedder:
        return []

    qdrant = get_qdrant()
    collection_name = settings.QDRANT_COLLECTION_MEMORY
    
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(None, lambda: list(_embedder.embed([query])))
    
    if not embeddings:
        return []
        
    vector = embeddings[0].tolist()
    
    try:
        results = await qdrant.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=str(user_id))
                    )
                ]
            ),
            limit=top_k
        )
        return [hit.payload.get("preference", "") for hit in results.points if hit.payload]
    except Exception as exc:
        logger.warning("user_preference_lookup_failed", user_id=user_id, error=str(exc))
        return []
