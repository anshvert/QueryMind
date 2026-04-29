"""
QueryMind — Global Agent State
"""
from typing import Any, Optional, Annotated
import operator
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState

def merge_lists(left: list, right: list) -> list:
    return left + right

class QueryMindState(MessagesState):
    """
    State shared across all nodes in the QueryMind Multi-Agent Crew.
    Inherits 'messages' from MessagesState (automatically handles memory appending).
    """
    # Context
    user_id: str
    source_id: str
    source_type: str
    credentials: dict[str, Any]
    question: str
    
    # Intent & Routing
    intent: Optional[str]
    confidence: float
    needs_clarification: bool
    
    # Data & Schema
    schema_context: str
    long_term_preferences: str
    
    # Execution
    sql: str
    error: Optional[str]
    retry_count: int
    results: Optional[list[dict[str, Any]]]
    row_count: int
    
    # Output
    summary: Optional[str]
    dashboard_spec: Optional[dict[str, Any]]
    
    # Telemetry
    reasoning: Annotated[list[str], merge_lists]
