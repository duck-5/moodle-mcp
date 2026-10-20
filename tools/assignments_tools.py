"""
Assignment discovery, deadlines, and submission status MCP tools.
"""

import os
from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_assignments_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_upcoming_assignments",
        description="Retrieves pending assignments due within the next N days."
    )
    def moodle_get_upcoming_assignments(
        days_ahead: int = 14,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves pending assignments due within the specified timeframe.
        Args:
            days_ahead: Number of days ahead (default: 14).
            refresh: If True, bypasses local cache.
        """
        return client.get_upcoming_assignments(days_ahead=days_ahead, refresh=refresh)

    @server.tool(
        name="moodle_get_assignments",
        description="Retrieves assignments and true deadlines for a course or all courses."
    )
    def moodle_get_assignments(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves assignments with due dates and submission state.
        Args:
            course: Course ID or partial course name (optional).
            course_id: Deprecated numeric course ID fallback.
            status_filter: Filter by status ('Submitted', 'Assigned').
            refresh: If True, fetches fresh assignments from Moodle.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        assignments = client.get_assignments(course_id=cid, refresh=refresh)
        if status_filter:
            assignments = [a for a in assignments if a.get("status", "").lower() == status_filter.lower()]
        return assignments

    @server.tool(
        name="moodle_get_assignment_status",
        description="Retrieves detailed submission status and grading feedback for an assignment."
    )
    def moodle_get_assignment_status(assignment_id: int) -> Dict[str, Any]:
        """
        Retrieves submission status, feedback, and extension deadline for an assignment.
        Args:
            assignment_id: The Moodle assignment ID.
        """
        return client.get_assignment_status(assignment_id)

    # In full toolset mode, also expose direct submission tool
    if os.getenv("MOODLE_TOOLSET", "compact").lower() == "full":
        @server.tool(
            name="moodle_submit_assignment",
            description="Submits assignment draft or final solution for grading."
        )
        def moodle_submit_assignment(
            assignment_id: int,
            file_path: Optional[str] = None,
            filename: Optional[str] = None,
            online_text: Optional[str] = None,
            submit_for_grading: bool = False
        ) -> Dict[str, Any]:
            return client.submit_assignment(
                assign_id=assignment_id,
                file_path_or_bytes=file_path,
                filename=filename,
                online_text=online_text,
                submit_for_grading=submit_for_grading
            )
