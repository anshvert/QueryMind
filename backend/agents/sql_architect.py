"""
QueryMind — SQL Architect Node
"""
from openai import AsyncOpenAI
from backend.agents.state import QueryMindState
from backend.core.config import settings
import structlog

logger = structlog.get_logger(__name__)

async def sql_architect_node(state: QueryMindState) -> QueryMindState:
    """Generate or fix SQL based on schema and intent."""
    if not settings.OPENROUTER_API_KEY:
        state["sql"] = "SELECT 1;"
        state["reasoning"] = ["SQL Architect: Missing API Key, returning dummy SQL."]
        return state

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
    )

    is_mongo = state["source_type"] == "mongodb"

    if is_mongo:
        system_prompt = (
            "You are an expert MongoDB query architect.\n"
            "You MUST return a single, pure JSON object (no markdown, no explanation).\n"
            "The JSON must have exactly two keys:\n"
            "  - 'collection': a string with the MongoDB collection name\n"
            "  - 'pipeline': an array of MongoDB aggregation pipeline stages\n"
            "\nExample output:\n"
            '{"collection": "orders", "pipeline": [{"$group": {"_id": "$status", "total": {"$sum": "$amount"}}}]}\n'
            "Do NOT use db.collection.find(), db.collection.aggregate(), or any shell syntax.\n"
            "Return ONLY the JSON object.\n\n"
            f"Schema:\n{state['schema_context']}\n\n"
            f"User Preferences: {state['long_term_preferences']}"
        )
    else:
        system_prompt = (
            "You are an expert SQL architect. Return ONLY valid SQL.\n"
            "Do not include markdown tags like ```sql or any explanations.\n"
            f"Dialect: {state['source_type']}\n\n"
            f"Schema:\n{state['schema_context']}\n\n"
            f"User Preferences: {state['long_term_preferences']}"
        )

    user_prompt = f"Question: {state['question']}\n"

    # Self-correction logic
    if state.get("error") and state.get("sql"):
        user_prompt += (
            f"\nPrevious query:\n{state['sql']}\n"
            f"\nFailed with error:\n{state['error']}\n"
            "Fix the query based on this error."
        )
        state["reasoning"] = [f"SQL Architect: Attempting to fix SQL (Retry {state['retry_count'] + 1})"]

    kwargs = {
        "model": settings.LLM_SQL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }

    if is_mongo:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        completion = await client.chat.completions.create(**kwargs)
    except Exception as exc:
        state["error"] = f"SQL Architect model call failed: {exc}"
        state["reasoning"] = [state["error"]]
        return state

    sql = (completion.choices[0].message.content or "").strip()
    # Strip any markdown formatting the LLM may have added
    if sql.startswith("```"):
        for fence in ("```sql\n", "```sql", "```json\n", "```json", "```\n", "```"):
            sql = sql.replace(fence, "")
        sql = sql.strip()

    logger.info("sql_architect_generated", source_type=state["source_type"], sql_preview=sql[:300])

    state["sql"] = sql
    state["error"] = None
    state["reasoning"] = ["SQL Architect: Generated SQL."]
    return state
