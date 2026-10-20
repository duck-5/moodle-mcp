"""
Course discovery and course contents MCP tools.
"""

from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_courses_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_enrolled_courses",
        description="Retrieves enrolled courses with course IDs, codes, names, and semester breakdown."
    )
    def moodle_get_enrolled_courses(
        semester: Optional[str] = None,
        academic_only: bool = True,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves enrolled courses. Automatically cached.
        
        Args:
            semester: Optional semester filter (e.g. 'Semester A', 'Semester B', 'Yearly').
            academic_only: If True (default), filters out university mandatory compliance/safety tutorials.
            refresh: If True, fetches live data bypassing cache.
        """
        courses = client.get_enrolled_courses(refresh=refresh, academic_only=academic_only)
        if semester:
            courses = [c for c in courses if semester.lower() in c.get("semester", "").lower()]
        return courses

    @server.tool(
        name="moodle_get_course_contents",
        description="Retrieves section syllabus, modules, and links for a course."
    )
    def moodle_get_course_contents(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None,
        refresh: bool = False
    ) -> Any:
        """
        Retrieves syllabus sections and contents of a course.
        
        Args:
            course: Course ID or partial name (e.g. 'Waves', 'Data Structures', 321210299).
            course_id: Deprecated numeric course ID fallback.
            refresh: If True, fetches fresh contents from Moodle.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        if not cid:
            return {"error": f"Course '{course or course_id}' could not be found."}
        return client.get_course_contents(cid, refresh=refresh)
