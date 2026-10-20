"""
Quiz and online test discovery MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_quizzes_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_quizzes(course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves quizzes, online tests, and exam items across courses.
        Includes open and close deadlines, time limits (in minutes), and attempt rules.
        
        Args:
            course_id: Optional course ID filter. If omitted, checks all enrolled courses.
        """
        return client.get_quizzes(course_id=course_id)
