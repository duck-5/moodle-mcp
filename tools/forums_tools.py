"""
Course announcements, news, and discussion forums MCP tools.
"""

from typing import Any, Dict, List, Optional, Union
from moodle_mcp.client import MoodleClient


def register_forums_tools(server: Any, client: MoodleClient) -> None:
    @server.tool(
        name="moodle_get_course_announcements",
        description="Retrieves recent official course announcements, lecturer messages, and news updates."
    )
    def moodle_get_course_announcements(
        course: Optional[Union[int, str]] = None,
        course_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recent official announcements and news posted by instructors.
        Includes post subjects, authors, dates, and full announcement text.
        
        Args:
            course: Optional course ID or partial course name filter (e.g. 'Infi 1', 321210299).
            course_id: Deprecated numeric course ID fallback.
        """
        cid = client.resolve_course_id(course if course is not None else course_id) if (course is not None or course_id is not None) else None
        return client.get_course_announcements(course_id=cid)

    @server.tool(
        name="moodle_read_forum_thread",
        description="Retrieves full text and replies of a specific Moodle discussion forum thread by discussion ID."
    )
    def moodle_read_forum_thread(discussion_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves all posts and replies in a forum thread.
        
        Args:
            discussion_id: The integer ID of the discussion topic (found via announcements or course contents).
        """
        return client.get_forum_discussion_posts(discussion_id=discussion_id)
