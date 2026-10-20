"""
Course discovery and course contents MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_courses_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_enrolled_courses(
        semester: Optional[str] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all courses the user is enrolled in, enriched with course code, group ID,
        academic year, and semester breakdown. Automatically cached for fast responses.
        
        Args:
            semester: Optional filter by semester name (e.g. 'Semester A', 'Semester B', 'Yearly').
            refresh: If True, bypasses local cache and fetches fresh data from Moodle.
        """
        courses = client.get_enrolled_courses(refresh=refresh)
        if semester:
            courses = [c for c in courses if semester.lower() in c.get("semester", "").lower()]
        return courses

    @server.tool()
    def moodle_get_course_contents(
        course_id: int,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the complete section-by-section syllabus and contents of a Moodle course,
        including all sections, assignments, resources, quizzes, and file links.
        
        Args:
            course_id: The integer Moodle course ID (e.g. 12345).
            refresh: If True, bypasses local cache and fetches fresh contents from Moodle.
        """
        return client.get_course_contents(course_id, refresh=refresh)
