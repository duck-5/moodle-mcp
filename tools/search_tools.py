"""
Global search MCP tool across courses, assignments, files, and meetings.
"""

from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager


def register_search_tools(server: Any, client: MoodleClient, panopto: PanoptoManager) -> None:
    @server.tool(
        name="moodle_search",
        description="Searches courses, assignments, files, and resources by keyword."
    )
    def moodle_search(
        query: str,
        search_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Searches across all Moodle courses, assignments, downloadable files, meetings, and recordings.
        
        Args:
            query: The search term (course name, code, assignment title, topic, or keyword).
            search_types: Optional list of domains to search: ['courses', 'assignments', 'files', 'meetings', 'recordings'].
                         Defaults to searching all domains.
        """
        q = query.lower().strip()
        types = [t.lower() for t in (search_types or ["courses", "assignments", "files", "meetings", "recordings"])]
        results: Dict[str, List[Any]] = {
            "courses": [],
            "assignments": [],
            "files": [],
            "meetings": [],
            "recordings": []
        }

        # 1. Search courses
        if "courses" in types:
            courses = client.get_enrolled_courses()
            for c in courses:
                if (
                    q in c.get("fullname", "").lower()
                    or q in c.get("shortname", "").lower()
                    or q in c.get("display_name", "").lower()
                    or q in str(c.get("id", ""))
                ):
                    results["courses"].append(c)

        # 2. Search assignments
        if "assignments" in types:
            assignments = client.get_assignments()
            for a in assignments:
                if (
                    q in a.get("name", "").lower()
                    or q in a.get("course_name", "").lower()
                    or q in a.get("instructions", "").lower()
                ):
                    results["assignments"].append(a)

        # 3. Search files
        if "files" in types:
            enrolled = client.get_enrolled_courses()
            for c in enrolled:
                files = client.get_course_files(c["id"])
                for f in files:
                    if (
                        q in f.get("filename", "").lower()
                        or q in f.get("section_name", "").lower()
                        or q in f.get("module_name", "").lower()
                    ):
                        results["files"].append(f)

        # 4. Search meetings
        if "meetings" in types:
            meetings = client.get_course_meetings()
            for m in meetings:
                if (
                    q in m.get("title", "").lower()
                    or q in m.get("course_name", "").lower()
                    or q in m.get("section", "").lower()
                ):
                    results["meetings"].append(m)

        # 5. Search recordings
        if "recordings" in types:
            recordings = panopto.get_course_recordings()
            for r in recordings:
                if (
                    q in r.get("lecture_title", "").lower()
                    or q in r.get("course_name", "").lower()
                ):
                    results["recordings"].append(r)

        return results
