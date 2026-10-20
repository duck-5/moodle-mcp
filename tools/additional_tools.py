"""
Dispatcher MCP tool collapsing secondary and utility Moodle actions.
"""

from typing import Any, Dict, Optional, Union
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager


def register_additional_tools(server: Any, client: MoodleClient, panopto: PanoptoManager) -> None:
    @server.tool(
        name="moodle_additional_tools",
        description="Access secondary tools: announcements, participants, meetings, recordings, downloads, submissions, storage, and cache."
    )
    def moodle_additional_tools(
        action: str,
        course: Optional[Union[int, str]] = None,
        assignment_id: Optional[int] = None,
        file_url: Optional[str] = None,
        key: Optional[str] = None,
        value: Optional[str] = None,
        description: Optional[str] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        online_text: Optional[str] = None,
        submit_for_grading: bool = False,
        category: Optional[str] = None,
        refresh: bool = False
    ) -> Any:
        """
        Executes a secondary Moodle utility action specified by title.

        Args:
            action: Action title to run:
                - 'announcements': Recent course announcements & forum news.
                - 'participants': Lecturers, TAs, and student roster for a course.
                - 'meetings': Zoom links and live class meeting sessions.
                - 'recordings': Panopto video recordings and lecture captures.
                - 'download_file': Download a course resource to local storage.
                - 'submit_assignment': Upload solution file or text for an assignment.
                - 'save_data': Save a persistent note or data item.
                - 'load_data': Retrieve a saved note or item by key.
                - 'list_data': List all saved notes in persistent storage.
                - 'delete_data': Remove a saved item from storage.
                - 'clear_cache': Flush cached API responses.
                - 'user_profile': Current user profile and site details.
                - 'session_status': Active authentication status.
            course: Course ID or partial course name (for course-specific actions).
            assignment_id: Assignment ID (for 'submit_assignment').
            file_url: File URL (for 'download_file').
            key: Name of the key (for 'save_data', 'load_data', 'delete_data').
            value: Data string or JSON value to store (for 'save_data').
            description: Optional note description (for 'save_data').
            file_path: Local file path to submit (for 'submit_assignment').
            filename: Custom filename to display (for 'submit_assignment').
            online_text: Online text submission body (for 'submit_assignment').
            submit_for_grading: If True, locks submission for grading (for 'submit_assignment').
            category: Cache category to flush (for 'clear_cache').
            refresh: If True, bypasses local cache.
        """
        act = action.lower().strip().replace("-", "_").replace(" ", "_")
        cid = client.resolve_course_id(course) if course is not None else None

        if act in ("announcements", "announcement", "forum", "news"):
            return client.get_course_announcements(course_id=cid)

        if act in ("participants", "participant", "roster", "staff"):
            if not cid:
                return {"error": "course parameter (ID or name) is required for participants."}
            return client.get_course_participants(course_id=cid)

        if act in ("meetings", "meeting", "zoom"):
            return client.get_course_meetings(course_id=cid, refresh=refresh)

        if act in ("recordings", "recording", "panopto", "videos"):
            return panopto.get_course_recordings(course_id=cid)

        if act in ("download_file", "download"):
            if not file_url:
                return {"error": "file_url parameter is required for download_file."}
            return client.download_file(file_url=file_url)

        if act in ("submit_assignment", "submit"):
            if not assignment_id:
                return {"error": "assignment_id parameter is required for submit_assignment."}
            return client.submit_assignment(
                assign_id=assignment_id,
                file_path_or_bytes=file_path,
                filename=filename,
                online_text=online_text,
                submit_for_grading=submit_for_grading
            )

        if act in ("save_data", "save"):
            if not key or value is None:
                return {"error": "key and value parameters are required for save_data."}
            return client.data_store.save(key=key, data=value, description=description)

        if act in ("load_data", "load", "get_data"):
            if not key:
                return {"error": "key parameter is required for load_data."}
            return client.data_store.load(key=key)

        if act in ("list_data", "list_saved", "saved_data"):
            return client.data_store.list_keys()

        if act in ("delete_data", "delete_saved"):
            if not key:
                return {"error": "key parameter is required for delete_data."}
            deleted = client.data_store.delete(key=key)
            return {"success": deleted, "key": key}

        if act in ("clear_cache", "flush_cache"):
            count = client.clear_cache(category=category)
            return {"success": True, "cleared_entries": count, "category": category or "all"}

        if act in ("user_profile", "profile", "site_info"):
            return client.get_site_info()

        if act in ("session_status", "status", "auth_status"):
            return client.auth.get_status()

        return {
            "error": f"Unknown action: '{action}'.",
            "available_actions": [
                "announcements", "participants", "meetings", "recordings",
                "download_file", "submit_assignment", "save_data", "load_data",
                "list_data", "delete_data", "clear_cache", "user_profile", "session_status"
            ]
        }
