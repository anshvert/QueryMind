"""
QueryMind — Query Validator Node
"""
import re
from backend.agents.state import QueryMindState
from backend.core.config import settings


def _normalize_leading_dot_table_refs(sql: str) -> tuple[str, bool]:
    """
    Fix invalid table refs like `FROM .titanic` or `JOIN .orders`.
    This commonly appears when historical schema context had empty schema + dot.
    """
    pattern = re.compile(r"\b(FROM|JOIN)\s+\.\s*([A-Za-z_][A-Za-z0-9_]*)", flags=re.IGNORECASE)
    fixed = pattern.sub(r"\1 \2", sql)
    return fixed, fixed != sql

async def query_validator_node(state: QueryMindState) -> QueryMindState:
    """Validate the SQL for safety (Read-Only) before execution."""
    normalized_sql, changed = _normalize_leading_dot_table_refs(state["sql"])
    if changed:
        state["sql"] = normalized_sql
        state["reasoning"] = ["Query Validator: Normalized invalid leading-dot table reference."]

    sql_upper = state["sql"].upper()
    
    # Simple heuristic safety check
    forbidden = ["INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "TRUNCATE ", "GRANT ", "REVOKE "]
    
    for word in forbidden:
        if word in sql_upper:
            state["error"] = f"Security Violation: SQL contains forbidden keyword '{word.strip()}'."
            state["reasoning"] = [state["error"]]
            return state
            
    # Optionally: use LLM or sqlglot to validate syntax / cost estimates
    if changed:
        state["reasoning"].append("Query Validator: SQL passed security check.")
    else:
        state["reasoning"] = ["Query Validator: SQL passed security check."]
    return state
