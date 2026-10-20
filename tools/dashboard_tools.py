"""
Unified academic dashboard MCP tool.
"""

from typing import Any, Dict
from moodle_mcp.client import MoodleClient


def register_dashboard_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_dashboard",
        description="Retrieves unified academic overview: active courses, upcoming deadlines, quizzes, and recent announcements."
    )
    def moodle_get_dashboard(days_ahead: int = 14) -> Dict[str, Any]:
        """
        Retrieves a complete academic overview in a single call.
        Args:
            days_ahead: Days ahead for deadlines and events (default: 14).
        """
        return client.get_dashboard(days_ahead=days_ahead)
