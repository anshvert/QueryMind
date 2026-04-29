"""
QueryMind — Schema Navigator Node
"""
import re
from backend.agents.state import QueryMindState
from backend.schema_registry.embeddings import retrieve_relevant_tables
from backend.connectors import get_or_connect


def _sanitize_ddl(ddl: str) -> str:
    # Guard against historical bad DDL chunks like "CREATE TABLE .table_name".
    return re.sub(r"(CREATE\s+TABLE\s+)\.\s*([A-Za-z_][A-Za-z0-9_]*)", r"\1\2", ddl, flags=re.IGNORECASE)


async def schema_navigator_node(state: QueryMindState) -> QueryMindState:
    """Retrieve relevant schema from Qdrant based on the user's question."""
    
    tables = await retrieve_relevant_tables(state["source_id"], state["question"], top_k=5)
    
    if tables:
        context_parts = [f"-- Database: {tables[0].get('database', '')}"]
        for t in tables:
            context_parts.append(_sanitize_ddl(t.get("ddl", "")))
        state["schema_context"] = "\n\n".join(context_parts)
        state["reasoning"] = [f"Schema Navigator: Found {len(tables)} relevant tables via semantic search."]
    else:
        # Fallback to full schema
        connector = await get_or_connect(
            source_id=state["source_id"],
            source_type=state["source_type"],
            credentials=state["credentials"],
        )
        schema = await connector.get_schema()
        state["schema_context"] = schema.to_prompt_context()
        state["reasoning"] = ["Schema Navigator: Loaded full schema context (semantic search fallback)."]
        
    return state
