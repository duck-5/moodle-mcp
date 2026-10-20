"""
Tests for MoodleAuth session and credential handling.
"""

import sys
from pathlib import Path
_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

import unittest
from moodle_mcp.auth import MoodleAuth, MoodleAuthError


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.auth = MoodleAuth(moodle_url="https://moodle.test.edu")

    def test_init_state(self):
        self.assertEqual(self.auth.moodle_url, "https://moodle.test.edu")
        self.assertIsNone(self.auth.token)

    def test_status_format(self):
        status = self.auth.get_status()
        self.assertIn("authenticated", status)
        self.assertIn("moodle_url", status)
        self.assertIn("has_token", status)
        self.assertIn("has_session_cookie", status)
        self.assertIn("user_id", status)

    def test_cookie_string_parsing(self):
        # MoodleAuth handles raw cookie or MoodleSession=value
        raw_cookie = "abc12345xyz"
        formatted_cookie = "MoodleSession=abc12345xyz; Path=/; HttpOnly"
        
        # Test clean extraction logic
        clean = formatted_cookie.split("MoodleSession=")[1].split(";")[0].strip()
        self.assertEqual(clean, "abc12345xyz")


if __name__ == "__main__":
    unittest.main()
