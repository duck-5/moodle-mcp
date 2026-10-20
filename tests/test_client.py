"""
Tests for MoodleClient and domain helper functions.
"""

import sys
from pathlib import Path
_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

import unittest
from moodle_mcp.client import parse_course_metadata, clean_course_name, MoodleClient
from moodle_mcp.auth import MoodleAuth


class TestCourseMetadata(unittest.TestCase):
    def test_parse_valid_tau_course(self):
        course = {
            "id": 1234,
            "idnumber": "03211100-01-2025-1",
            "shortname": "03211100-01-2025-1",
            "fullname": "Calculus 1"
        }
        meta = parse_course_metadata(course)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["base_course_code"], "03211100")
        self.assertEqual(meta["group_id"], "01")
        self.assertEqual(meta["year"], "2025")
        self.assertEqual(meta["semester_code"], "1")
        self.assertEqual(meta["semester_name"], "Semester A")

    def test_parse_semester_b(self):
        course = {"idnumber": "03681118-02-2025-2"}
        meta = parse_course_metadata(course)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["semester_name"], "Semester B")

    def test_parse_invalid_format(self):
        course = {"idnumber": "invalid-code"}
        meta = parse_course_metadata(course)
        self.assertIsNone(meta)

    def test_clean_course_name(self):
        name = clean_course_name("0368-1118 - Data Structures", "Data Structures Full")
        self.assertEqual(name, "0368 - Data Structures")

        fallback = clean_course_name("SinglePart", "Full Title")
        self.assertEqual(fallback, "Full Title")


class TestClientLogic(unittest.TestCase):
    def setUp(self):
        self.auth = MoodleAuth(moodle_url="https://test.moodle.edu")
        self.client = MoodleClient(auth=self.auth)

    def test_client_init(self):
        self.assertEqual(self.client.auth.moodle_url, "https://test.moodle.edu")
        self.assertIsNotNone(self.client.tz)


if __name__ == "__main__":
    unittest.main()
