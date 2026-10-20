"""
Tests for MCP tool registration and server initialization.
"""

import sys
from pathlib import Path
_pkg_parent = str(Path(__file__).resolve().parent.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

import unittest
from moodle_mcp.server import create_server


class TestServerTools(unittest.TestCase):
    def test_create_server(self):
        server, client, panopto = create_server()
        self.assertIsNotNone(server)
        self.assertIsNotNone(client)
        self.assertIsNotNone(panopto)


if __name__ == "__main__":
    unittest.main()
