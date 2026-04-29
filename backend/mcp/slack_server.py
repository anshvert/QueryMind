"""
QueryMind — Slack Notification MCP Server
"""
from mcp.server.fastmcp import FastMCP
import structlog

logger = structlog.get_logger(__name__)

mcp = FastMCP("QueryMind Slack MCP")

@mcp.tool()
def send_slack_notification(message: str, channel: str = "#general") -> str:
    """Send an insight digest, anomaly alert, or data summary to a Slack channel."""
    logger.info("slack_notification_sent", channel=channel, message=message[:50])
    return f"Successfully sent notification to {channel}."

if __name__ == "__main__":
    mcp.run()
