"""
QueryMind — SQL Architect Node
"""
from openai import AsyncOpenAI
from backend.agents.state import QueryMindState
from backend.core.config import settings

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
            f"\nPrevious SQL:\n{state['sql']}\n"
            f"\nFailed with error:\n{state['error']}\n"
            "Fix the query based on this error."
        )
        state["reasoning"] = [f"SQL Architect: Attempting to fix SQL (Retry {state['retry_count'] + 1})"]

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_SQL_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
    except Exception as exc:
        state["error"] = f"SQL Architect model call failed: {exc}"
        state["reasoning"] = [state["error"]]
        return state
    
    sql = (completion.choices[0].message.content or "").strip()
    if sql.startswith("```"):
        sql = sql.replace("```sql", "").replace("```", "").strip()
        
    state["sql"] = sql
    state["error"] = None
    state["reasoning"] = ["SQL Architect: Generated SQL."]
    return state
