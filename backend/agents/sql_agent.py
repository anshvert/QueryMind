"""
QueryMind — Advanced Text-to-SQL Agent (Day 2)
Supports semantic schema retrieval, self-correction, and result summarization.
"""
from typing import Any, TypedDict, Optional
from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
import structlog
import json

from backend.connectors import get_or_connect
from backend.core.config import settings
from backend.schema_registry.embeddings import retrieve_relevant_tables

logger = structlog.get_logger(__name__)

class AgentState(TypedDict):
    source_id: str
    source_type: str
    credentials: dict[str, Any]
    question: str
    schema_context: str
    sql: str
    error: Optional[str]
    retry_count: int
    results: Optional[list[dict[str, Any]]]
    summary: Optional[str]
    reasoning: list[str]

def _build_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

async def _retrieve_schema_node(state: AgentState) -> AgentState:
    """Retrieve relevant schema elements from Qdrant or fallback to full schema."""
    state.setdefault("retry_count", 0)
    
    # Try semantic retrieval first
    tables = await retrieve_relevant_tables(state["source_id"], state["question"], top_k=5)
    
    if tables:
        context_parts = [f"-- Database: {tables[0].get('database', '')}"]
        for t in tables:
            context_parts.append(t.get("ddl", ""))
        state["schema_context"] = "\n\n".join(context_parts)
        state["reasoning"].append(f"Retrieved {len(tables)} relevant tables via semantic search.")
    else:
        # Fallback to full schema if Qdrant is empty or no embedder
        connector = await get_or_connect(
            source_id=state["source_id"],
            source_type=state["source_type"],
            credentials=state["credentials"],
        )
        schema = await connector.get_schema()
        state["schema_context"] = schema.to_prompt_context()
        state["reasoning"].append("Loaded full schema context (semantic search fallback).")
        
    return state

async def _generate_sql_node(state: AgentState) -> AgentState:
    """Generate or fix SQL based on the schema and any prior errors."""
    if not settings.OPENROUTER_API_KEY:
        state["sql"] = "SELECT 1;"
        state["reasoning"].append("OPENROUTER_API_KEY missing; returned fallback SQL.")
        return state

    client = _build_client()
    
    system_prompt = (
        "You are an expert data architect. Return ONLY a valid query payload for the target database.\n"
        "Never generate INSERT/UPDATE/DELETE/DDL or any Markdown formatting around the query.\n"
        f"Dialect: {state['source_type']}\n\n"
    )
    
    if state["source_type"] == "mongodb":
        system_prompt += (
            "CRITICAL FOR MONGODB: You MUST return a pure JSON string representing an aggregation pipeline.\n"
            "The JSON must have exactly two keys: 'collection' (string) and 'pipeline' (array of stages).\n"
            "Example:\n"
            '{"collection": "orders", "pipeline": [{"$match": {"status": "completed"}}, {"$group": {"_id": "$customer_id", "total": {"$sum": "$amount"}}}]}\n'
            "Return ONLY this JSON object. No markdown, no explanations, no `db.collection.aggregate` syntax.\n"
        )
    else:
        system_prompt += "Return ONLY valid, read-only SQL.\n"
        
    system_prompt += f"\nSchema:\n{state['schema_context']}\n"
    
    user_prompt = f"Question: {state['question']}\n"
    
    if state.get("error") and state.get("sql"):
        user_prompt += (
            f"\nYour previous SQL query:\n{state['sql']}\n"
            f"\nFailed with this error:\n{state['error']}\n"
            "\nPlease fix the SQL query to resolve the error. Return ONLY the new SQL."
        )
        state["reasoning"].append(f"Attempting to fix SQL. Retry: {state['retry_count'] + 1}")

    kwargs = {
        "model": settings.LLM_SQL_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }
    
    if state["source_type"] == "mongodb":
        kwargs["response_format"] = {"type": "json_object"}

    completion = await client.chat.completions.create(**kwargs)
    
    sql = (completion.choices[0].message.content or "").strip()
    if sql.startswith("```"):
        sql = sql.replace("```sql\n", "").replace("```sql", "")
        sql = sql.replace("```json\n", "").replace("```json", "")
        sql = sql.replace("```\n", "").replace("```", "")
        sql = sql.strip()
        
    state["sql"] = sql
    state["error"] = None # clear error after generation
    state["reasoning"].append("Generated SQL.")
    return state

async def _execute_sql_node(state: AgentState) -> AgentState:
    """Execute the SQL query against the connected source."""
    if not state.get("sql"):
        state["error"] = "No SQL was generated."
        return state
        
    connector = await get_or_connect(
        source_id=state["source_id"],
        source_type=state["source_type"],
        credentials=state["credentials"],
    )
    
    try:
        result = await connector.execute(state["sql"])
        state["results"] = result.to_dict_list()
        state["reasoning"].append(f"Successfully executed SQL. Retrieved {result.row_count} rows.")
    except Exception as e:
        state["error"] = str(e)
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["reasoning"].append(f"Execution failed: {e}")
        
    return state

async def _summarize_node(state: AgentState) -> AgentState:
    """Generate a natural language summary of the results."""
    if state.get("error"):
        state["summary"] = f"I encountered an error I couldn't resolve: {state['error']}"
        return state
        
    if not state.get("results"):
        state["summary"] = "The query returned no results."
        return state
        
    client = _build_client()
    # Serialize a small sample of results for the prompt
    sample_data = json.dumps(state["results"][:10], default=str)
    
    prompt = (
        f"Question: {state['question']}\n"
        f"SQL Used: {state['sql']}\n"
        f"Data Sample (up to 10 rows):\n{sample_data}\n\n"
        "Provide a concise, natural language summary answering the user's question based on the data. "
        "Do not explain the SQL, just interpret the data."
    )
    
    completion = await client.chat.completions.create(
        model=settings.LLM_FAST_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful data analyst."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    
    state["summary"] = (completion.choices[0].message.content or "").strip()
    state["reasoning"].append("Generated natural language summary.")
    return state

def _router(state: AgentState) -> str:
    """Route to correct node based on execution success/failure."""
    if state.get("error"):
        if state["retry_count"] < 3:
            return "generate_sql"
        else:
            return "summarize"
    return "summarize"

_graph = StateGraph(AgentState)
_graph.add_node("retrieve_schema", _retrieve_schema_node)
_graph.add_node("generate_sql", _generate_sql_node)
_graph.add_node("execute_sql", _execute_sql_node)
_graph.add_node("summarize", _summarize_node)

_graph.set_entry_point("retrieve_schema")
_graph.add_edge("retrieve_schema", "generate_sql")
_graph.add_edge("generate_sql", "execute_sql")
_graph.add_conditional_edges("execute_sql", _router)
_graph.add_edge("summarize", END)

agent_graph = _graph.compile()

async def run_day1_react_agent(
    source_id: str,
    source_type: str,
    credentials: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    """Entry point for the compiled LangGraph agent."""
    state: AgentState = {
        "source_id": source_id,
        "source_type": source_type,
        "credentials": credentials,
        "question": question,
        "schema_context": "",
        "sql": "",
        "error": None,
        "retry_count": 0,
        "results": None,
        "summary": None,
        "reasoning": [],
    }
    
    result = await agent_graph.ainvoke(state)
    
    logger.info(
        "sql_agent_trace",
        source_id=source_id,
        question=question,
        retry_count=result.get("retry_count"),
        sql=result.get("sql", ""),
        error=result.get("error")
    )
    
    return {
        "sql": result.get("sql", ""),
        "results": result.get("results"),
        "summary": result.get("summary", ""),
        "reasoning": result.get("reasoning", []),
    }
