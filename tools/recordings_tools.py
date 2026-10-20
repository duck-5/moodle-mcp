"""
Lecture recordings and Panopto session MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.panopto import PanoptoManager


def register_recordings_tools(server: Any, panopto: PanoptoManager) -> None:
    @server.tool()
    def moodle_get_recordings(course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves lecture recordings and recitation (tirgul) video links for courses.
        
        Args:
            course_id: Optional course ID filter.
        """
        return panopto.get_course_recordings(course_id=course_id)
