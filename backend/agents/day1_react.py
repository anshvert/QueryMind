"""
Day 1 baseline ReAct-style SQL generation agent.
"""
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from openai import OpenAI
import structlog

from backend.connectors import get_or_connect
from backend.core.config import settings

logger = structlog.get_logger(__name__)


class AgentState(TypedDict):
    source_id: str
    source_type: str
    credentials: dict[str, Any]
    question: str
    schema_context: str
    sql: str
    reasoning: list[str]


def _build_client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


async def _schema_node(state: AgentState) -> AgentState:
    connector = await get_or_connect(
        source_id=state["source_id"],
        source_type=state["source_type"],
        credentials=state["credentials"],
    )
    schema = await connector.get_schema()
    state["schema_context"] = schema.to_prompt_context()
    state["reasoning"].append("Loaded source schema context.")
    return state


async def _sql_node(state: AgentState) -> AgentState:
    if not settings.OPENROUTER_API_KEY:
        state["sql"] = "SELECT 1;"
        state["reasoning"].append("OPENROUTER_API_KEY missing; returned fallback SQL.")
        return state

    prompt = (
        "You are a SQL generation assistant. Return only a read-only SQL query.\n"
        "Never generate INSERT/UPDATE/DELETE/DDL.\n"
        f"Dialect: {state['source_type']}\n\n"
        f"Schema:\n{state['schema_context']}\n\n"
        f"Question: {state['question']}\n"
    )
    client = _build_client()
    completion = client.chat.completions.create(
        model=settings.LLM_SQL_MODEL,
        messages=[
            {"role": "system", "content": "Generate safe analytical SQL only."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )
    sql = (completion.choices[0].message.content or "").strip()
    if sql.startswith("```"):
        sql = sql.replace("```sql", "").replace("```", "").strip()
    state["sql"] = sql
    state["reasoning"].append("Generated SQL from schema-aware prompt.")
    return state


_graph = StateGraph(AgentState)
_graph.add_node("schema", _schema_node)
_graph.add_node("generate_sql", _sql_node)
_graph.set_entry_point("schema")
_graph.add_edge("schema", "generate_sql")
_graph.add_edge("generate_sql", END)
agent_graph = _graph.compile()


async def run_day1_react_agent(
    source_id: str,
    source_type: str,
    credentials: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    state: AgentState = {
        "source_id": source_id,
        "source_type": source_type,
        "credentials": credentials,
        "question": question,
        "schema_context": "",
        "sql": "",
        "reasoning": [],
    }
    result = await agent_graph.ainvoke(state)
    logger.info(
        "day1_chat_trace",
        source_id=source_id,
        source_type=source_type,
        question=question,
        sql=result.get("sql", ""),
        reasoning=result.get("reasoning", []),
    )
    return {
        "sql": result.get("sql", ""),
        "reasoning": result.get("reasoning", []),
    }
