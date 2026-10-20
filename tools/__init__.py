"""
Tools module initialization for moodle_mcp.
Supports compact core mode (default) and full legacy mode.
"""

import os
from typing import Any
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager

from moodle_mcp.tools.dashboard_tools import register_dashboard_tools
from moodle_mcp.tools.courses_tools import register_courses_tools
from moodle_mcp.tools.assignments_tools import register_assignments_tools
from moodle_mcp.tools.grades_tools import register_grades_tools
from moodle_mcp.tools.files_tools import register_files_tools
from moodle_mcp.tools.quizzes_tools import register_quizzes_tools
from moodle_mcp.tools.calendar_tools import register_calendar_tools
from moodle_mcp.tools.search_tools import register_search_tools
from moodle_mcp.tools.additional_tools import register_additional_tools

# Legacy separate tools (loaded in full mode)
from moodle_mcp.tools.auth_tools import register_auth_tools
from moodle_mcp.tools.meetings_tools import register_meetings_tools
from moodle_mcp.tools.recordings_tools import register_recordings_tools
from moodle_mcp.tools.forums_tools import register_forums_tools
from moodle_mcp.tools.participants_tools import register_participants_tools
from moodle_mcp.tools.storage_tools import register_storage_tools


def register_all_tools(server: Any, client: MoodleClient, panopto: PanoptoManager) -> None:
    """Registers Moodle MCP tools onto the given server."""
    # Core high-frequency tools
    register_dashboard_tools(server, client)
    register_courses_tools(server, client)
    register_assignments_tools(server, client)
    register_grades_tools(server, client)
    register_files_tools(server, client)
    register_quizzes_tools(server, client)
    register_calendar_tools(server, client)
    register_search_tools(server, client, panopto)

    # Consolidated additional tools dispatcher (announcements, participants, meetings, recordings, downloads, storage, cache, etc.)
    register_additional_tools(server, client, panopto)

    # If full mode is requested, also expose individual legacy tools
    if os.getenv("MOODLE_TOOLSET", "compact").lower() == "full":
        register_auth_tools(server, client)
        register_meetings_tools(server, client)
        register_recordings_tools(server, panopto)
        register_forums_tools(server, client)
        register_participants_tools(server, client)
        register_storage_tools(server, client)
