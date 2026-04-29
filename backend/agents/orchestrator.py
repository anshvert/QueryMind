"""
QueryMind — LangGraph Multi-Agent Orchestrator
"""
from langgraph.graph import StateGraph, END
import structlog

from backend.agents.state import QueryMindState
from backend.agents.intent_classifier import intent_classifier_node
from backend.agents.schema_navigator import schema_navigator_node
from backend.agents.sql_architect import sql_architect_node
from backend.agents.query_validator import query_validator_node
from backend.agents.execution_agent import execution_agent_node
from backend.agents.insight_extractor import insight_extractor_node
from backend.agents.dashboard_agent import dashboard_agent_node
from backend.agents.critic_agent import critic_agent_node

logger = structlog.get_logger(__name__)

def route_intent(state: QueryMindState) -> str:
    """Route based on user intent."""
    if state.get("needs_clarification", False):
        return END
    return "schema_navigator"

def route_execution(state: QueryMindState) -> str:
    """Route after SQL execution attempt."""
    # Self-Correction Loop
    if state.get("error"):
        if state.get("retry_count", 0) < 3:
            return "sql_architect"
        else:
            return "insight_extractor" # give up and summarize the error
    
    # Success Path Routing
    if state.get("intent") == "dashboard":
        return "dashboard_agent"
    return "insight_extractor"

_graph = StateGraph(QueryMindState)

_graph.add_node("intent_classifier", intent_classifier_node)
_graph.add_node("schema_navigator", schema_navigator_node)
_graph.add_node("sql_architect", sql_architect_node)
_graph.add_node("query_validator", query_validator_node)
_graph.add_node("execution_agent", execution_agent_node)
_graph.add_node("insight_extractor", insight_extractor_node)
_graph.add_node("dashboard_agent", dashboard_agent_node)
_graph.add_node("critic_agent", critic_agent_node)

_graph.set_entry_point("intent_classifier")

_graph.add_conditional_edges("intent_classifier", route_intent, {
    END: END,
    "schema_navigator": "schema_navigator"
})

_graph.add_edge("schema_navigator", "sql_architect")
_graph.add_edge("sql_architect", "query_validator")
_graph.add_edge("query_validator", "execution_agent")

_graph.add_conditional_edges("execution_agent", route_execution, {
    "sql_architect": "sql_architect",
    "dashboard_agent": "dashboard_agent",
    "insight_extractor": "insight_extractor"
})

_graph.add_edge("dashboard_agent", "insight_extractor")
_graph.add_edge("insight_extractor", "critic_agent")
_graph.add_edge("critic_agent", END)

def get_compiled_graph(checkpointer=None):
    """Return the compiled graph, optionally with Postgres state saving."""
    return _graph.compile(checkpointer=checkpointer)
