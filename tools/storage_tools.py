"""
Persistent named storage and cache management MCP tools.
Allows AI assistants (like Gemini) to save and load named data across conversations,
and manage the automatic Moodle API cache.
"""

import json
from typing import Any, Dict, List, Optional
from moodle_mcp.client import MoodleClient


def register_storage_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_save_data(
        key: str,
        data: Any,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Saves curated data, summaries, notes, or filtered outputs under a custom key in persistent storage.
        This data persists across conversations and sessions so it never needs to be re-computed or re-fetched.
        
        Examples:
        - key: 'active_courses', data: [list of this semester's courses], description: 'Spring 2025 enrolled courses'
        - key: 'operating_systems_syllabus', data: { 'exam_weight': '60%', 'topics': [...] }
        - key: 'weekly_study_priorities', data: [...]
        
        Args:
            key: A unique, human-readable identifier (e.g. 'active_courses', 'cs101_summary').
            data: The JSON-serializable data to store (dict, list, string, number).
            description: Optional note explaining what this saved data contains.
        """
        # If data is passed as a JSON string, try to parse it for cleaner storage
        payload = data
        if isinstance(data, str):
            try:
                payload = json.loads(data)
            except Exception:
                payload = data

        return client.data_store.save(key=key, data=payload, description=description)

    @server.tool()
    def moodle_load_data(key: str) -> Dict[str, Any]:
        """
        Loads previously saved data by its key name from persistent storage.
        Returns the data, the timestamp of when it was saved, and its description.
        
        Args:
            key: The name of the saved data item to retrieve.
        """
        item = client.data_store.load(key)
        if not item:
            available = client.data_store.list_keys()
            available_names = [a["key"] for a in available]
            return {
                "success": False,
                "error": f"Item '{key}' not found in saved data storage.",
                "available_keys": available_names
            }
        return {
            "success": True,
            "key": item["key"],
            "saved_at": item["saved_at"],
            "description": item["description"],
            "data_type": item["data_type"],
            "data": item["data"]
        }

    @server.tool()
    def moodle_list_saved_data() -> List[Dict[str, Any]]:
        """
        Lists all items currently saved in persistent storage, including their key names,
        descriptions, timestamps, item counts, and data types.
        """
        return client.data_store.list_keys()

    @server.tool()
    def moodle_delete_saved_data(key: str) -> Dict[str, Any]:
        """
        Deletes a specific saved data item from persistent storage.
        
        Args:
            key: The name of the saved item to delete.
        """
        deleted = client.data_store.delete(key)
        if deleted:
            return {
                "success": True,
                "message": f"Successfully deleted '{key}' from saved data storage."
            }
        return {
            "success": False,
            "message": f"Key '{key}' was not found in saved data storage."
        }

    @server.tool()
    def moodle_clear_cache(category: Optional[str] = None) -> Dict[str, Any]:
        """
        Clears cached Moodle API responses.
        Use this when you want to force fresh data to be retrieved from Moodle on subsequent calls.
        
        Args:
            category: Optional category to clear: 'courses', 'contents', 'assignments', 'grades', 'files', 'meetings'.
                      If omitted, clears the entire API cache.
        """
        count = client.clear_cache(category=category)
        return {
            "success": True,
            "cleared_entries": count,
            "category": category or "all",
            "message": f"Cleared {count} cached entries ({category or 'all'})."
        }

    @server.tool()
    def moodle_get_cache_status() -> Dict[str, Any]:
        """
        Returns status information about the automatic API cache, including total cached entries,
        cache file location, and the age of each cached key.
        """
        return client.cache.get_stats()
