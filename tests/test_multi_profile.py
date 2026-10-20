"""
Unit tests for multi-profile configuration and credential discovery.
"""

import os
import unittest
from pathlib import Path

from moodle_mcp.config import get_configured_profiles, get_profile_paths
from moodle_mcp.auth import MoodleAuth


class TestMultiProfile(unittest.TestCase):
    def setUp(self):
        os.environ["MOODLE_PROFILES"] = "yuval,yaeli"
        os.environ["YUVAL_MOODLE_USERNAME"] = "user_yuval"
        os.environ["YUVAL_MOODLE_PASSWORD"] = "pass_yuval"
        os.environ["YAELI_MOODLE_USERNAME"] = "user_yaeli"
        os.environ["YAELI_MOODLE_PASSWORD"] = "pass_yaeli"

    def tearDown(self):
        for k in ["MOODLE_PROFILES", "YUVAL_MOODLE_USERNAME", "YUVAL_MOODLE_PASSWORD", "YAELI_MOODLE_USERNAME", "YAELI_MOODLE_PASSWORD"]:
            if k in os.environ:
                del os.environ[k]

    def test_get_configured_profiles(self):
        profs = get_configured_profiles()
        self.assertIn("yuval", profs)
        self.assertIn("yaeli", profs)
        self.assertIn("default", profs)

    def test_isolated_profile_paths(self):
        paths_yuval = get_profile_paths("yuval")
        paths_yaeli = get_profile_paths("yaeli")
        self.assertNotEqual(paths_yuval["session_file"], paths_yaeli["session_file"])
        self.assertTrue(str(paths_yuval["session_file"]).endswith("profiles/yuval/session.json"))
        self.assertTrue(str(paths_yaeli["session_file"]).endswith("profiles/yaeli/session.json"))

    def test_profile_auth_initialization(self):
        auth_yuval = MoodleAuth(profile="yuval")
        auth_yaeli = MoodleAuth(profile="yaeli")
        self.assertEqual(auth_yuval.profile, "yuval")
        self.assertEqual(auth_yaeli.profile, "yaeli")
        self.assertIn("profiles/yuval", str(auth_yuval.session_file))
        self.assertIn("profiles/yaeli", str(auth_yaeli.session_file))


if __name__ == "__main__":
    unittest.main()
