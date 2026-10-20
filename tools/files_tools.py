"""
Course files and in-memory document reader MCP tools.
"""

import os
from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_files_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_course_files",
        description="Lists downloadable course slides, documents, and resources."
    )
    def moodle_get_course_files(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None,
        section_name: Optional[str] = None,
        refresh: bool = False
    ) -> Any:
        """
        Lists downloadable course files and slides.
        Args:
            course: Course ID or partial course name (e.g. 'Waves', 'Data Structures').
            course_id: Deprecated numeric course ID fallback.
            section_name: Optional section name filter (e.g. 'Week 1', 'General').
            refresh: If True, bypasses local cache.
        """
        cid = client.resolve_course_id(course if course is not None else course_id)
        if not cid:
            return {"error": f"Course '{course or course_id}' could not be found."}
        files = client.get_course_files(cid, refresh=refresh)
        if section_name:
            files = [f for f in files if section_name.lower() in f.get("section_name", "").lower()]
        return files

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
