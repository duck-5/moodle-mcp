"""
Course announcements, news, and discussion forums MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_forums_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_course_announcements(course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves recent official announcements and news posted by instructors.
        Includes post subjects, authors, dates, and full announcement text.
        
        Args:
            course_id: Optional course ID filter. If omitted, checks announcements across all enrolled courses.
        """
        return client.get_course_announcements(course_id=course_id)
