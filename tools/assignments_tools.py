"""
Assignment management, deadline calculation, and submission MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_assignments_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_assignments(
        course_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves assignments with their True Deadlines (accounting for due dates, strict cutoffs,
        and individual student extensions) and current submission state.
        
        Args:
            course_id: Optional course ID filter.
            status_filter: Optional filter by status ('Submitted', 'Assigned', 'Not submitted').
            refresh: If True, bypasses local cache and fetches fresh assignments from Moodle.
        """
        assignments = client.get_assignments(course_id=course_id, refresh=refresh)
        if status_filter:
            assignments = [a for a in assignments if a.get("status", "").lower() == status_filter.lower()]
        return assignments

    @server.tool()
    def moodle_get_upcoming_assignments(
        days_ahead: int = 7,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves pending assignments due within the next specified number of days (default 7 days).
        
        Args:
            days_ahead: Number of days into the future to check (default: 7).
            refresh: If True, bypasses local cache and fetches fresh upcoming assignments from Moodle.
        """
        return client.get_upcoming_assignments(days_ahead=days_ahead, refresh=refresh)

    @server.tool()
    def moodle_get_assignment_status(assignment_id: int) -> Dict[str, Any]:
        """
        Retrieves detailed submission status, feedback, extension deadline, and uploaded files
        for a specific assignment.
        
        Args:
            assignment_id: The Moodle assignment ID.
        """
        return client.get_assignment_status(assignment_id)

    @server.tool()
    def moodle_submit_assignment(
        assignment_id: int,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        online_text: Optional[str] = None,
        submit_for_grading: bool = False
    ) -> Dict[str, Any]:
        """
        Uploads a solution file to Moodle's draft area and/or provides online text submission.
        Optionally locks and submits the assignment for grading.
        
        Args:
            assignment_id: The Moodle assignment ID.
            file_path: Optional local filesystem path to the file being submitted (e.g. 'solution.pdf').
            filename: Optional custom filename to display in Moodle.
            online_text: Optional text submission body (HTML or plain text).
            submit_for_grading: If True, submits for grading (locking changes). If False, saves as draft.
        """
        return client.submit_assignment(
            assign_id=assignment_id,
            file_path_or_bytes=file_path,
            filename=filename,
            online_text=online_text,
            submit_for_grading=submit_for_grading
        )

