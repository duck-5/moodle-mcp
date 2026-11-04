"""
Gradebook and GPA academic summary MCP tools.
"""

from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_grades_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_grades",
        description="Retrieves itemized assignment and exam grades, including Course Total standing, for a course or all courses."
    )
    def moodle_get_grades(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves per-assignment and course-total grades.
        Args:
            course: Optional course ID or partial course name filter.
            course_id: Deprecated numeric course ID fallback.
            refresh: If True, fetches fresh grades from Moodle.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        return client.get_grades(course_id=cid, refresh=refresh)
