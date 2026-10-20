"""
Course participants, professors, and teaching assistants MCP tools.
"""

from typing import Any, Dict, List
from moodle_mcp.client import MoodleClient


def register_participants_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_course_participants(course_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves lecturers, teaching assistants (TAs), managers, and enrolled students of a course.
        Highlights staff members and includes academic roles, departments, and email contacts.
        
        Args:
            course_id: The integer Moodle course ID (e.g. 12345).
        """
        return client.get_course_participants(course_id=course_id)
