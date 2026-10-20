"""
Course resources, file downloads, and in-memory document reading MCP tools.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_files_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_get_course_files(
        course_id: int,
        section_name: Optional[str] = None,
        refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Lists all downloadable course files, slides, lecture notes, and resources.
        
        Args:
            course_id: The integer Moodle course ID.
            section_name: Optional section name filter (e.g. 'Week 1', 'General').
            refresh: If True, bypasses local cache and fetches fresh files list from Moodle.
        """
        files = client.get_course_files(course_id, refresh=refresh)
        if section_name:
            files = [f for f in files if section_name.lower() in f.get("section_name", "").lower()]
        return files

    @server.tool()
    def moodle_download_file(
        file_url: str,
        output_directory: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Downloads a course file or resource from Moodle to local storage.
        
        Args:
            file_url: The Moodle pluginfile.php URL.
            output_directory: Optional local directory path where the file should be saved.
        """
        return client.download_file(file_url, output_path=output_directory)

    @server.tool()
    def moodle_read_file_content(
        file_url: str,
        max_chars: int = 15000
    ) -> Dict[str, Any]:
        """
        Downloads a Moodle document (PDF, TXT, MD, HTML, code) directly into memory and extracts
        its textual content for immediate AI inspection without writing to disk.
        
        Args:
            file_url: The Moodle pluginfile.php URL.
            max_chars: Maximum characters to return (default 15,000).
        """
        return client.read_file_content(file_url, max_chars=max_chars)
