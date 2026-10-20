"""
Persistent storage and automatic caching for moodle_mcp.
Provides:
1. CacheManager: Transparent disk-based caching for API responses with configurable TTLs.
2. DataStore: Named key-value store for AI assistants (e.g., Gemini) to save and load curated data across sessions.
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytz

from moodle_mcp.config import (
    SESSION_DIR,
    CACHE_FILE,
    SAVED_DATA_FILE,
    TIMEZONE,
)

logger = logging.getLogger("moodle_mcp.storage")


def _atomic_json_write(file_path: Path, data: Any) -> None:
    """Atomically writes data as JSON to file_path to prevent file corruption."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(f".tmp_{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, file_path)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        raise e


class CacheManager:
    """
    Manages automatic disk caching of Moodle API responses.
    Each entry is stored with a UNIX timestamp and payload.
    """

    def __init__(self, cache_file: Optional[Path] = None):
        self.cache_file = cache_file or CACHE_FILE
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Loads cache from disk if available."""
        if not self.cache_file.exists():
            self._cache = {}
            return
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load cache from {self.cache_file}: {e}")
            self._cache = {}

    def _save(self) -> None:
        """Saves cache to disk."""
        try:
            _atomic_json_write(self.cache_file, self._cache)
        except Exception as e:
            logger.warning(f"Failed to save cache to {self.cache_file}: {e}")

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[Any]:
        """
        Retrieves cached value if key exists and age does not exceed max_age (in seconds).
        Returns None if expired or not found.
        """
        entry = self._cache.get(key)
        if not entry:
            return None

        entry_time = entry.get("timestamp", 0)
        age = time.time() - entry_time

        if max_age is not None and age > max_age:
            logger.debug(f"Cache expired for '{key}' (age: {age:.0f}s, max: {max_age}s)")
            return None

        logger.debug(f"Cache hit for '{key}' (age: {age:.0f}s)")
        return entry.get("data")

    def set(self, key: str, data: Any) -> None:
        """Stores data in the cache with the current timestamp."""
        self._cache[key] = {
            "timestamp": time.time(),
            "data": data
        }
        self._save()

    def delete(self, key: str) -> bool:
        """Deletes a specific key from the cache."""
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    def clear(self, prefix: Optional[str] = None) -> int:
        """
        Clears all cached entries, or entries matching prefix.
        Returns the number of removed entries.
        """
        if not prefix:
            count = len(self._cache)
            self._cache = {}
            self._save()
            return count

        keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del self._cache[k]
        if keys_to_remove:
            self._save()
        return len(keys_to_remove)

    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics on currently cached entries."""
        now = time.time()
        entries_info = {}
        for k, v in self._cache.items():
            age = now - v.get("timestamp", 0)
            data = v.get("data")
            count = len(data) if isinstance(data, (list, dict)) else 1
            entries_info[k] = {
                "age_seconds": round(age),
                "items_count": count
            }

        return {
            "cache_file": str(self.cache_file),
            "total_entries": len(self._cache),
            "entries": entries_info
        }


class DataStore:
    """
    Key-value store for named items saved by AI assistants (Gemini) across sessions.
    Stores curated data, notes, filtered courses, study plans, etc.
    """

    def __init__(self, store_file: Optional[Path] = None):
        self.store_file = store_file or SAVED_DATA_FILE
        self.tz = pytz.timezone(TIMEZONE)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Loads saved data from disk."""
        if not self.store_file.exists():
            self._data = {}
            return
        try:
            with open(self.store_file, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load saved data from {self.store_file}: {e}")
            self._data = {}

    def _save(self) -> None:
        """Saves data store to disk."""
        try:
            _atomic_json_write(self.store_file, self._data)
        except Exception as e:
            logger.warning(f"Failed to save data store to {self.store_file}: {e}")

    def save(self, key: str, data: Any, description: Optional[str] = None) -> Dict[str, Any]:
        """
        Saves data under key with metadata (timestamp, description, data type).
        """
        clean_key = key.strip()
        now_dt = datetime.now(self.tz)
        saved_entry = {
            "key": clean_key,
            "saved_at": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": time.time(),
            "description": (description or "").strip(),
            "data_type": type(data).__name__,
            "data": data
        }
        self._data[clean_key] = saved_entry
        self._save()
        logger.info(f"Saved custom data under key '{clean_key}'")

        return {
            "success": True,
            "key": clean_key,
            "saved_at": saved_entry["saved_at"],
            "description": saved_entry["description"],
            "data_type": saved_entry["data_type"],
            "message": f"Successfully saved '{clean_key}' to persistent storage."
        }

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Loads an item by its key.
        Returns the full stored record including metadata and payload, or None if not found.
        """
        clean_key = key.strip()
        # Always reload from disk to ensure latest data across independent processes
        self._load()
        return self._data.get(clean_key)

    def list_keys(self) -> List[Dict[str, Any]]:
        """
        Lists metadata for all saved items without including the full data payloads.
        """
        self._load()
        summaries = []
        for key, entry in self._data.items():
            payload = entry.get("data")
            count = len(payload) if isinstance(payload, (list, dict)) else None
            summaries.append({
                "key": key,
                "saved_at": entry.get("saved_at"),
                "description": entry.get("description", ""),
                "data_type": entry.get("data_type", "unknown"),
                "items_count": count
            })
        return summaries

    def delete(self, key: str) -> bool:
        """Deletes a saved item by key."""
        clean_key = key.strip()
        self._load()
        if clean_key in self._data:
            del self._data[clean_key]
            self._save()
            logger.info(f"Deleted saved key '{clean_key}'")
            return True
        return False

    def clear(self) -> int:
        """Clears all saved items."""
        self._load()
        count = len(self._data)
        self._data = {}
        self._save()
        return count
