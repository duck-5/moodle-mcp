"""
Calendar events and academic deadline MCP tools.
"""

from typing import Any, Dict, List
from moodle_mcp.client import MoodleClient


def register_calendar_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_calendar_events",
        description="Retrieves upcoming calendar events, deadlines, and scheduled exams."
    )
    def moodle_get_calendar_events(days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Retrieves upcoming calendar events across enrolled courses.
        Args:
            days_ahead: Number of days ahead (default: 14).
        """
        return client.get_calendar_events(days_ahead=days_ahead)
