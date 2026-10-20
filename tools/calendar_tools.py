"""
Calendar events and comprehensive academic deadline MCP tools.
"""

from typing import Any, Dict, List
from moodle_mcp.client import MoodleClient


def register_calendar_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_calendar_events(days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Retrieves upcoming calendar events across all enrolled courses within the specified timeframe.
        Combines assignment deadlines, scheduled exams, quiz windows, and university events.
        
        Args:
            days_ahead: Number of days into the future to look ahead (default: 14).
        """
        return client.get_calendar_events(days_ahead=days_ahead)
