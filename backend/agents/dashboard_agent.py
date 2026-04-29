"""
QueryMind — Dashboard Agent Node
"""
import json
from openai import AsyncOpenAI
from backend.agents.state import QueryMindState
from backend.core.config import settings

async def dashboard_agent_node(state: QueryMindState) -> QueryMindState:
    """Generate a UI Chart Spec based on the data if the intent was 'dashboard'."""
    if state.get("error") or not state.get("results"):
        return state
        
    # Only run if intent is explicitly dashboard
    if state.get("intent") != "dashboard":
        return state

    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
    )
    
    sample_data = json.dumps(state["results"][:10], default=str)
    
    prompt = f"""
The user wants to visualize this data as a dashboard/chart.
Question: {state['question']}
Data Sample:
{sample_data}

Return a JSON object representing an ECharts (or generic chart) configuration.
The JSON must have keys: "type" (e.g. 'bar', 'line', 'pie'), "xAxis", "yAxis", and "series".
Only output the raw JSON.
"""

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_FAST_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a UI data visualization engineer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
    except Exception as exc:
        state["reasoning"] = [f"Dashboard Agent: model call failed: {exc}"]
        return state
    
    try:
        spec = json.loads(completion.choices[0].message.content or "{}")
        state["dashboard_spec"] = spec
        state["reasoning"] = ["Dashboard Agent: Generated chart specification."]
    except Exception as e:
        state["reasoning"] = [f"Dashboard Agent: Failed to generate chart spec: {e}"]
        
    return state
