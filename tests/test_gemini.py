"""
Unit tests for Moodle MCP Gemini Agent.
"""

import sys
import unittest
from pathlib import Path

_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

from moodle_mcp.gemini_client import MoodleGeminiAgent


class TestGeminiAgent(unittest.TestCase):
    def setUp(self):
        # Initialize agent with dummy/no key for offline unit testing
        self.agent = MoodleGeminiAgent(api_key="test_dummy_key_12345")

    def test_agent_initialization(self):
        self.assertIsNotNone(self.agent)
        self.assertIsNotNone(self.agent.client)
        self.assertIsNotNone(self.agent.panopto)
        self.assertEqual(self.agent.api_key, "test_dummy_key_12345")

    def test_tools_registered(self):
        self.assertGreaterEqual(len(self.agent.tool_functions), 10)
        expected_tools = {
            "moodle_get_enrolled_courses",
            "moodle_get_upcoming_assignments",
            "moodle_get_course_assignments",
            "moodle_get_assignment_status",
            "moodle_get_course_contents",
            "moodle_get_grades_summary",
            "moodle_get_course_grades",
            "moodle_get_quizzes",
            "moodle_get_calendar_events",
            "moodle_get_course_announcements",
            "moodle_read_file_content",
            "moodle_search",
            "moodle_search_recordings",
        }
        actual_tools = set(self.agent.tool_map.keys())
        for tool in expected_tools:
            self.assertIn(tool, actual_tools)

    def test_missing_key_graceful(self):
        agent_no_key = MoodleGeminiAgent(api_key="")
        res = agent_no_key.query_once("What are my deadlines?")
        self.assertIn("GEMINI_API_KEY is not set", res)


if __name__ == "__main__":
    unittest.main()
