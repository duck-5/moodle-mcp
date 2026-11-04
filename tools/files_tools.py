"""
Course files and in-memory document reader MCP tools.
"""

import os
from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_files_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_read_file_content",
        description="Extracts plain text in memory from a course file (PDF, PPTX, DOCX, TXT, MD, HTML)."
    )
    def moodle_read_file_content(
        file_url: str,
        max_chars: int = 15000
    ) -> Dict[str, Any]:
        """
        Reads and extracts text from a file into memory for instant AI inspection.
        Args:
            file_url: The Moodle pluginfile.php URL.
            max_chars: Maximum characters to return (default: 15,000).
        """
        return client.read_file_content(file_url, max_chars=max_chars)

    if os.getenv("MOODLE_TOOLSET", "compact").lower() == "full":
        @server.tool(
            name="moodle_download_file",
            description="Downloads a course file to local server storage."
        )
        def moodle_download_file(
            file_url: str,
            output_directory: Optional[str] = None
        ) -> Dict[str, Any]:
            return client.download_file(file_url, output_path=output_directory)
