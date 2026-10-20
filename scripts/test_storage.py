"""
Test suite for CacheManager, DataStore, and storage tools in moodle_mcp.
"""

import sys
import time
from pathlib import Path
import tempfile
import unittest

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add package root to sys.path
_pkg_root = Path(__file__).resolve().parent.parent.parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))

from moodle_mcp.storage import CacheManager, DataStore
from moodle_mcp.server import create_server


class TestStorageAndCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_file = Path(self.temp_dir.name) / "test_cache.json"
        self.store_file = Path(self.temp_dir.name) / "test_store.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cache_manager(self):
        cm = CacheManager(cache_file=self.cache_file)
        # Test cache miss
        self.assertIsNone(cm.get("missing_key"))

        # Test set and hit
        test_data = [{"id": 1, "name": "Operating Systems"}]
        cm.set("courses_123", test_data)
        hit = cm.get("courses_123", max_age=60)
        self.assertEqual(hit, test_data)

        # Test persistence across re-instantiation
        cm2 = CacheManager(cache_file=self.cache_file)
        self.assertEqual(cm2.get("courses_123", max_age=60), test_data)

        # Test TTL expiration
        expired = cm.get("courses_123", max_age=0)
        self.assertIsNone(expired)

        # Test prefix clear
        cm.set("courses_456", test_data)
        cm.set("assignments_123", [{"id": 99}])
        cleared = cm.clear(prefix="courses_")
        self.assertEqual(cleared, 2)
        self.assertIsNone(cm.get("courses_123"))
        self.assertIsNotNone(cm.get("assignments_123"))

        # Test clear all
        cm.clear()
        self.assertIsNone(cm.get("assignments_123"))

    def test_data_store(self):
        ds = DataStore(store_file=self.store_file)
        # Test empty list
        self.assertEqual(ds.list_keys(), [])

        # Test save
        courses = [
            {"id": 101, "name": "Algorithms", "semester": "Semester A"},
            {"id": 102, "name": "Databases", "semester": "Semester A"}
        ]
        res = ds.save("active_courses", courses, description="Fall semester 2026 courses")
        self.assertTrue(res["success"])
        self.assertEqual(res["key"], "active_courses")

        # Test load
        loaded = ds.load("active_courses")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["data"], courses)
        self.assertEqual(loaded["description"], "Fall semester 2026 courses")

        # Test persistence across re-instantiation
        ds2 = DataStore(store_file=self.store_file)
        loaded2 = ds2.load("active_courses")
        self.assertEqual(loaded2["data"], courses)

        # Test list_keys
        keys = ds2.list_keys()
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[0]["key"], "active_courses")
        self.assertEqual(keys[0]["items_count"], 2)

        # Test delete
        self.assertTrue(ds2.delete("active_courses"))
        self.assertIsNone(ds2.load("active_courses"))
        self.assertFalse(ds2.delete("nonexistent"))

    def test_mcp_storage_tools(self):
        from moodle_mcp.client import MoodleClient
        from moodle_mcp.tools.storage_tools import register_storage_tools

        class MockServer:
            def __init__(self):
                self.tools = {}
            def tool(self):
                def decorator(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return decorator

        mock_server = MockServer()
        client = MoodleClient()
        client.cache = CacheManager(cache_file=self.cache_file)
        client.data_store = DataStore(store_file=self.store_file)

        register_storage_tools(mock_server, client)

        save_fn = mock_server.tools["moodle_save_data"]
        load_fn = mock_server.tools["moodle_load_data"]
        list_fn = mock_server.tools["moodle_list_saved_data"]
        del_fn = mock_server.tools["moodle_delete_saved_data"]
        clear_cache_fn = mock_server.tools["moodle_clear_cache"]
        cache_status_fn = mock_server.tools["moodle_get_cache_status"]

        # 1. Save data as dict
        res = save_fn("my_courses", [{"id": 1, "name": "OS"}], description="Current semester")
        self.assertTrue(res["success"])

        # 2. Save data as JSON string (should be parsed)
        res2 = save_fn("json_courses", '[{"id": 2, "name": "DB"}]', description="Stringified JSON")
        self.assertTrue(res2["success"])

        # 3. List data
        items = list_fn()
        self.assertEqual(len(items), 2)

        # 4. Load data
        loaded = load_fn("my_courses")
        self.assertTrue(loaded["success"])
        self.assertEqual(loaded["data"][0]["name"], "OS")

        loaded_json = load_fn("json_courses")
        self.assertTrue(loaded_json["success"])
        self.assertIsInstance(loaded_json["data"], list)

        # 5. Load nonexistent data
        loaded_missing = load_fn("unknown_key")
        self.assertFalse(loaded_missing["success"])
        self.assertIn("available_keys", loaded_missing)

        # 6. Delete data
        del_res = del_fn("my_courses")
        self.assertTrue(del_res["success"])
        self.assertEqual(len(list_fn()), 1)

        # 7. Cache operations
        client.cache.set("courses_999", [{"test": True}])
        status = cache_status_fn()
        self.assertEqual(status["total_entries"], 1)

        clear_res = clear_cache_fn()
        self.assertTrue(clear_res["success"])
        self.assertEqual(clear_res["cleared_entries"], 1)

    def test_server_creation_and_tool_registration(self):
        server, client, panopto = create_server()
        self.assertIsNotNone(server)
        self.assertIsNotNone(client)
        self.assertIsNotNone(client.cache)
        self.assertIsNotNone(client.data_store)


if __name__ == "__main__":
    unittest.main()

