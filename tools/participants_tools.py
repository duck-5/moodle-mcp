"""
Course participants, professors, and teaching assistants MCP tools.
"""

from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient, MoodleClientError


def register_participants_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_course_participants",
        description="Retrieves lecturers, teaching assistants (TAs), managers, and enrolled students of a course."
    )
    def moodle_get_course_participants(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves lecturers, teaching assistants (TAs), managers, and enrolled students of a course.
        Highlights staff members and includes academic roles, departments, and email contacts.
        
        Args:
            course: Course ID or partial course name (e.g. 'Infi 1', 'Data Structures', 321210299).
            course_id: Deprecated numeric course ID fallback.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        if not cid:
            raise MoodleClientError(f"Course '{course or course_id}' could not be found.")
        return client.get_course_participants(course_id=cid)
