"""
Tests for FastAPI OpenAPI 3.1 REST Server.
"""

import sys
from pathlib import Path
_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

import unittest
from moodle_mcp.openapi_server import create_app


class TestOpenAPIServer(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def test_app_created(self):
        self.assertIsNotNone(self.app)
        self.assertEqual(self.app.title, "Moodle MCP OpenAPI Server")

    def test_openapi_spec_structure(self):
        spec = self.app.openapi()
        self.assertIn("openapi", spec)
        self.assertTrue(spec["openapi"].startswith("3.1"))
        self.assertIn("paths", spec)

        # Check required endpoints
        paths = spec["paths"]
        self.assertIn("/health", paths)
        self.assertIn("/api/v1/status", paths)
        self.assertIn("/api/v1/courses", paths)
        self.assertIn("/api/v1/assignments", paths)
        self.assertIn("/api/v1/grades", paths)
        self.assertIn("/api/v1/quizzes", paths)
        self.assertIn("/api/v1/calendar/events", paths)

    def test_operation_ids(self):
        spec = self.app.openapi()
        op_ids = set()
        for path_item in spec["paths"].values():
            for method in ("get", "post", "put", "delete"):
                if method in path_item and "operationId" in path_item[method]:
                    op_ids.add(path_item[method]["operationId"])

        expected = {
            "moodle_get_status",
            "moodle_login",
            "moodle_get_enrolled_courses",
            "moodle_get_assignments",
            "moodle_get_grades",
            "moodle_get_quizzes",
            "moodle_get_calendar_events",
        }
        for exp in expected:
            self.assertIn(exp, op_ids)


if __name__ == "__main__":
    unittest.main()
