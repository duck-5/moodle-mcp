"""
Gradebook and academic summary MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_grades_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_grades(
        course_id: Optional[int] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves per-assignment and course-total grades for all courses or a single course.
        Includes raw grades, max grades, percentages, and hidden flags.
        
        Args:
            course_id: Optional course ID filter.
            refresh: If True, bypasses local cache and fetches fresh grades from Moodle.
        """
        return client.get_grades(course_id=course_id, refresh=refresh)

    @server.tool()
    def moodle_get_grades_summary(refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Calculates grade averages, graded assignments counts, and course totals across all courses.
        
        Args:
            refresh: If True, bypasses local cache and recalculates fresh grades from Moodle.
        """
        return client.get_grades_summary(refresh=refresh)
