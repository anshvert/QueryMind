"""
QueryMind — Execution Agent Node
"""
from backend.agents.state import QueryMindState
from backend.connectors import get_or_connect

async def execution_agent_node(state: QueryMindState) -> QueryMindState:
    """Execute the validated SQL against the active data source."""
    
    if state.get("error"):
        # Skip execution if query is invalid
        return state
        
    if not state.get("sql"):
        state["error"] = "No SQL was generated to execute."
        return state
        
    connector = await get_or_connect(
        source_id=state["source_id"],
        source_type=state["source_type"],
        credentials=state["credentials"],
    )
    
    try:
        result = await connector.execute(state["sql"])
        state["results"] = result.to_dict_list()
        state["row_count"] = result.row_count
        state["reasoning"] = [f"Execution Agent: Executed SQL successfully. Returned {result.row_count} rows."]
    except Exception as e:
        state["error"] = str(e)
        state["retry_count"] = state.get("retry_count", 0) + 1
        state["reasoning"] = [f"Execution Agent: Execution failed: {e}"]
        
    return state
