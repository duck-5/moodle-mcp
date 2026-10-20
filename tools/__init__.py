"""
Tools module initialization for moodle_mcp.
"""

from typing import Any
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager

from moodle_mcp.tools.auth_tools import register_auth_tools
from moodle_mcp.tools.courses_tools import register_courses_tools
from moodle_mcp.tools.assignments_tools import register_assignments_tools
from moodle_mcp.tools.grades_tools import register_grades_tools
from moodle_mcp.tools.files_tools import register_files_tools
from moodle_mcp.tools.meetings_tools import register_meetings_tools
from moodle_mcp.tools.recordings_tools import register_recordings_tools
from moodle_mcp.tools.search_tools import register_search_tools
from moodle_mcp.tools.quizzes_tools import register_quizzes_tools
from moodle_mcp.tools.calendar_tools import register_calendar_tools
from moodle_mcp.tools.forums_tools import register_forums_tools
from moodle_mcp.tools.participants_tools import register_participants_tools
from moodle_mcp.tools.storage_tools import register_storage_tools


def register_all_tools(server: Any, client: MoodleClient, panopto: PanoptoManager) -> None:
    """Registers all Moodle MCP tools onto the given server."""
    register_auth_tools(server, client)
    register_courses_tools(server, client)
    register_assignments_tools(server, client)
    register_grades_tools(server, client)
    register_files_tools(server, client)
    register_meetings_tools(server, client)
    register_recordings_tools(server, panopto)
    register_search_tools(server, client, panopto)
    register_quizzes_tools(server, client)
    register_calendar_tools(server, client)
    register_forums_tools(server, client)
    register_participants_tools(server, client)
    register_storage_tools(server, client)
