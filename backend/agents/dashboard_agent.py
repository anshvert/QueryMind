"""
QueryMind — Dashboard Agent Node
"""
from backend.dashboard_engine.spec import build_dashboard_spec
from backend.agents.state import QueryMindState
from backend.core.config import settings
from openai import AsyncOpenAI
import json
import structlog

logger = structlog.get_logger(__name__)

async def dashboard_agent_node(state: QueryMindState) -> QueryMindState:
    """Generate a UI Chart Spec based on the data if the intent was 'dashboard'."""
    if state.get("error") or not state.get("results"):
        return state
        
    # Only run if intent is explicitly dashboard
    if state.get("intent") != "dashboard":
        return state

    question = state["question"]
    results = state["results"]
    
    # We take up to 3 rows of sample data
    sample_data = results[:3]
    columns = list(results[0].keys()) if results else []

    if not settings.OPENROUTER_API_KEY:
        state["dashboard_spec"] = build_dashboard_spec(question=question, results=results)
        state["reasoning"].append("Dashboard Agent: Used heuristic fallback (no API key).")
        return state

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )

    system_prompt = """You are an expert Data Visualization Agent.
Your job is to read the user's question, the available columns, and a few sample rows, and decide the best charts to display.
Output valid JSON ONLY matching exactly this schema:
{
  "version": "1.0",
  "title": "Dashboard Title",
  "charts": [
    {
      "type": "bar|line|pie|scatter|area",
      "title": "Chart Title",
      "xAxis": "column_for_x",
      "yAxis": "column_for_y",
      "series": [{"name": "Series Name", "dataKey": "column_for_y"}],
      "nameKey": "column_for_pie_labels",
      "valueKey": "column_for_pie_values"
    }
  ],
  "kpis": [
    {
      "type": "kpi",
      "title": "KPI Title",
      "metric": "column_name",
      "value": 123.45
    }
  ],
  "filters": []
}

Rules:
1. DO NOT plot primary keys, IDs (like PassengerId, UserID), or high-cardinality nominal integers on the yAxis or as a KPI metric. Use your semantic understanding!
2. If the user asks for a simple list or tabular data (e.g., "Top 5 users"), return an empty "charts" array. Do not force a chart if a table is better.
3. Max 3 charts.
4. Output raw JSON only.
"""

    history_lines = []
    for msg in state.get("messages", [])[:-1]:
        role = "User" if getattr(msg, "type", msg[0] if isinstance(msg, tuple) else "user") in ("human", "user") else "AI"
        content = getattr(msg, "content", msg[1] if isinstance(msg, tuple) else str(msg))
        history_lines.append(f"{role}: {content}")
    chat_history = "\n".join(history_lines) if history_lines else "No previous conversation."

    user_prompt = f"Conversation History:\n{chat_history}\n\nLatest Question: {question}\nColumns: {columns}\nSample Data: {json.dumps(sample_data, default=str)}"

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_FAST_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        
        spec_str = completion.choices[0].message.content
        if spec_str:
            state["dashboard_spec"] = json.loads(spec_str)
            if "reasoning" not in state:
                state["reasoning"] = []
            state["reasoning"].append("Dashboard Agent: Generated semantic chart specification via LLM.")
        else:
            raise ValueError("Empty LLM response")

    except Exception as e:
        logger.warning("llm_dashboard_spec_failed", error=str(e))
        if "reasoning" not in state:
            state["reasoning"] = []
        state["reasoning"].append(f"Dashboard Agent LLM failed: {e}. Falling back to heuristic spec.")
        try:
            state["dashboard_spec"] = build_dashboard_spec(question=question, results=results)
        except Exception as fallback_e:
            state["reasoning"].append(f"Dashboard Agent fallback failed: {fallback_e}")
            
    return state
