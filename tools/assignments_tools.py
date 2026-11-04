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
        refresh: bool = False,
        include_submitted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Retrieves pending assignments due within the specified timeframe.
        Args:
            days_ahead: Number of days ahead (default: 14).
            refresh: If True, bypasses local cache.
            include_submitted: If True, also includes completed/submitted assignments.
        """
        return client.get_upcoming_assignments(
            days_ahead=days_ahead,
            refresh=refresh,
            include_submitted=include_submitted
        )

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

    @server.tool(
        name="moodle_upload_submission",
        description="Uploads a solution file (e.g. PDF or code) as a draft submission for an assignment."
    )
    def moodle_upload_submission(
        assignment_id: int,
        file_path: str,
        filename: Optional[str] = None,
        submit_for_grading: bool = False
    ) -> Dict[str, Any]:
        """
        Uploads a solution file as a submission. By default saves as draft (submit_for_grading=False).
        Args:
            assignment_id: The Moodle assignment ID.
            file_path: Local filesystem path to the file to submit.
            filename: Optional custom filename to display in Moodle.
            submit_for_grading: If True, locks and submits for final grading. Defaults to False (Draft).
        """
        return client.submit_assignment(
            assign_id=assignment_id,
            file_path_or_bytes=file_path,
            filename=filename,
            submit_for_grading=submit_for_grading
        )

    # In full toolset mode, also expose direct submission tool alias
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
