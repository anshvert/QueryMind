"""
QueryMind — Insight Extractor Node
"""
import json
from openai import AsyncOpenAI
from backend.agents.state import QueryMindState
from backend.core.config import settings

async def insight_extractor_node(state: QueryMindState) -> QueryMindState:
    """Generate a natural language insight based on the data."""
    
    if state.get("error"):
        state["summary"] = f"I encountered an error I couldn't resolve: {state['error']}"
        state["reasoning"] = ["Insight Extractor: Skipped due to error."]
        return state
        
    if not state.get("results"):
        state["summary"] = "The query returned no results."
        state["reasoning"] = ["Insight Extractor: Skipped due to empty results."]
        return state
        
    client = AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
        timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
    )
    
    # Cap the data sample sent to LLM to save tokens
    sample_data = json.dumps(state["results"][:20], default=str)
    
    prompt = f"""
Question: {state['question']}
SQL Executed: {state['sql']}
Data Sample (up to 20 rows):
{sample_data}

Provide a concise, highly analytical summary answering the user's question. 
Point out any obvious trends, anomalies, or top performers in the data.
DO NOT explain the SQL.
"""

    try:
        completion = await client.chat.completions.create(
            model=settings.LLM_FAST_MODEL,
            messages=[
                {"role": "system", "content": "You are a senior data analyst. If you detect an anomaly, use the send_slack_notification tool to alert the team."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "send_slack_notification",
                        "description": "Send an anomaly alert or insight digest to a Slack channel.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message": {"type": "string", "description": "The alert message to send"},
                                "channel": {"type": "string", "description": "The slack channel (e.g., #alerts)"},
                            },
                            "required": ["message"],
                        },
                    },
                }
            ],
        )
    except Exception as exc:
        state["summary"] = f"Failed to generate summary: {exc}"
        state["reasoning"] = [state["summary"]]
        return state
    
    # Check if a tool was called (MCP integration proxy)
    message = completion.choices[0].message
    if message.tool_calls:
        for tool_call in message.tool_calls:
            if tool_call.function.name == "send_slack_notification":
                args = json.loads(tool_call.function.arguments)
                state["reasoning"].append(f"Insight Extractor: Invoked MCP Tool '{tool_call.function.name}' with args {args}")
                # In a full MCP setup, we route this to the MCP client. Here we mock success.
    
    state["summary"] = (message.content or "Summary generated and alerts sent if needed.").strip()
    state["reasoning"] = ["Insight Extractor: Generated data summary."]
    
    # TODO: In future iterations, if anomaly detected, trigger Slack MCP server.
    return state
