"""
Live Zoom and online meeting session MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_meetings_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_course_meetings(
        course_id: Optional[int] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Discovers Zoom links, recurring class meetings, and live sessions linked on course pages.
        
        Args:
            course_id: Optional course ID filter. If omitted, checks all enrolled courses.
            refresh: If True, bypasses local cache and fetches fresh meetings from Moodle.
        """
        return client.get_course_meetings(course_id=course_id, refresh=refresh)
