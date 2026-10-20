"""Unit and integration tests for moodle_mcp."""

import sys
from pathlib import Path

# Ensure parent of moodle_mcp is in sys.path so 'import moodle_mcp' works during test discovery
_test_dir = Path(__file__).resolve().parent
_pkg_parent = str(_test_dir.parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)
