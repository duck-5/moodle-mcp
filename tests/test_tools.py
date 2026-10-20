"""
Tests for MCP tool registration and server initialization.
"""

import sys
from pathlib import Path
_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

import json
import unittest
from moodle_mcp.server import create_server


class TestServerTools(unittest.TestCase):
    def test_create_server(self):
        server, client, panopto = create_server()
        self.assertIsNotNone(server)
        self.assertIsNotNone(client)
        self.assertIsNotNone(panopto)

    def test_list_serialization_single_content_block(self):
        server, client, panopto = create_server()
        tool = server._tool_manager.get_tool("moodle_get_enrolled_courses")
        self.assertIsNotNone(tool)

        sample_courses = [
            {"id": 1, "name": "Course 1"},
            {"id": 2, "name": "Course 2"},
            {"id": 3, "name": "Course 3"}
        ]
        res = tool.fn_metadata.convert_result(sample_courses)
        self.assertEqual(len(res.content), 1, "List of items must be serialized into exactly 1 TextContent block")
        parsed = json.loads(res.content[0].text)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["name"], "Course 1")
        self.assertEqual(parsed[2]["name"], "Course 3")

    def test_empty_list_serialization(self):
        server, client, panopto = create_server()
        tool = server._tool_manager.get_tool("moodle_get_upcoming_assignments")
        self.assertIsNotNone(tool)

        res = tool.fn_metadata.convert_result([])
        self.assertEqual(len(res.content), 1, "Empty list must be serialized into exactly 1 TextContent block")
        self.assertEqual(res.content[0].text, "[]")


if __name__ == "__main__":
    unittest.main()
