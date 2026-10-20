"""
Quiz and online exam discovery MCP tools.
"""

from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_quizzes_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_quizzes",
        description="Retrieves active and upcoming quizzes, exam windows, and time limits."
    )
    def moodle_get_quizzes(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves quizzes, online tests, and exam windows.
        Args:
            course: Optional course ID or partial course name filter.
            course_id: Deprecated numeric course ID fallback.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        return client.get_quizzes(course_id=cid)
