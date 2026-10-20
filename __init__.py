"""
moodle_mcp: Model Context Protocol (MCP) server & OpenAPI gateway connecting AI providers to Moodle.
"""

import sys
from pathlib import Path

# Ensure parent directory is in sys.path so 'import moodle_mcp' always resolves
_pkg_parent = str(Path(__file__).resolve().parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

from moodle_mcp.auth import MoodleAuth, MoodleAuthError
from moodle_mcp.client import MoodleClient, MoodleClientError
from moodle_mcp.server import create_server, main
from moodle_mcp.openapi_server import create_app, export_openapi_spec

__version__ = "1.1.0"
__all__ = [
    "MoodleAuth",
    "MoodleAuthError",
    "MoodleClient",
    "MoodleClientError",
    "create_server",
    "create_app",
    "export_openapi_spec",
    "main",
]
