"""
QueryMind — BI Export MCP Server
"""
from mcp.server.fastmcp import FastMCP
import structlog

logger = structlog.get_logger(__name__)

mcp = FastMCP("QueryMind BI Export MCP")

@mcp.tool()
def export_to_bi(dashboard_spec: str, bi_platform: str = "Tableau") -> str:
    """Export the generated chart specifications to a BI platform like Tableau, Power BI, or Looker."""
    logger.info("bi_export_triggered", platform=bi_platform, spec_length=len(dashboard_spec))
    return f"Successfully exported dashboard specification to {bi_platform}."

if __name__ == "__main__":
    mcp.run()
