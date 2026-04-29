"""
QueryMind — Schema Embedding Pipeline
"""
import asyncio
from typing import List, Dict, Any
from uuid import uuid4
import structlog

from backend.connectors.base import SchemaInfo
from backend.core.config import settings
from backend.core.qdrant_client import get_qdrant
from qdrant_client.models import PointStruct

try:
    from fastembed import TextEmbedding
    # bge-small-en-v1.5 outputs 384 dimensions
    _embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
except ImportError:
    _embedder = None

logger = structlog.get_logger(__name__)

async def embed_and_store_schema(schema_info: SchemaInfo) -> None:
    """
    Takes a SchemaInfo, generates semantic text for each table/column,
    embeds them, and stores them in Qdrant.
    """
    if not _embedder:
        logger.warning("fastembed not installed or failed to load. Skipping embedding.")
        return

    qdrant = get_qdrant()
    collection_name = settings.QDRANT_COLLECTION_SCHEMA
    
    points: List[PointStruct] = []
    
    for table in schema_info.tables:
        text_repr = f"Database: {schema_info.database}\n"
        text_repr += f"Table: {table.schema}.{table.name}\n"
        if table.description:
            text_repr += f"Description: {table.description}\n"
        text_repr += "Columns:\n"
        
        for col in table.columns:
            pk_str = " (Primary Key)" if col.is_primary_key else ""
            fk_str = f" (Foreign Key to {col.references})" if col.is_foreign_key else ""
            desc = f" - {col.description}" if col.description else ""
            text_repr += f"- {col.name} [{col.data_type}]{pk_str}{fk_str}{desc}\n"
        
        loop = asyncio.get_event_loop()
        # FastEmbed is CPU-bound, run in executor
        embeddings = await loop.run_in_executor(None, lambda: list(_embedder.embed([text_repr])))
        
        if not embeddings:
            continue
            
        vector = embeddings[0].tolist()
        
        payload = {
            "source_id": str(schema_info.source_id),
            "source_type": schema_info.source_type.value,
            "database": schema_info.database,
            "table_schema": table.schema,
            "table_name": table.name,
            "ddl": table.to_ddl(),
            "text": text_repr
        }
        
        points.append(
            PointStruct(
                id=str(uuid4()),
                vector=vector,
                payload=payload
            )
        )
    
    if points:
        await qdrant.upsert(
            collection_name=collection_name,
            points=points
        )
        logger.info("schema_embedded", source_id=schema_info.source_id, points_count=len(points))

async def retrieve_relevant_tables(source_id: str, question: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Retrieve top_k most relevant tables for a given question.
    """
    if not _embedder:
        return []
        
    qdrant = get_qdrant()
    collection_name = settings.QDRANT_COLLECTION_SCHEMA
    
    loop = asyncio.get_event_loop()
    embeddings = await loop.run_in_executor(None, lambda: list(_embedder.embed([question])))
    
    if not embeddings:
        return []
        
    vector = embeddings[0].tolist()
    
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    try:
        results = await qdrant.query_points(
            collection_name=collection_name,
            query=vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_id",
                        match=MatchValue(value=str(source_id))
                    )
                ]
            ),
            limit=top_k
        )
        return [hit.payload for hit in results.points if hit.payload]
    except Exception as exc:
        logger.warning("schema_retrieval_failed", source_id=source_id, error=str(exc))
        return []
