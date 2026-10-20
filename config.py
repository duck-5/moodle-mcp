"""
Configuration and settings for moodle_mcp.
Loads environment variables from .env or moodle_test_credentials.env if present.
"""

import os
import re
from pathlib import Path
from typing import Dict, Optional
from dotenv import load_dotenv

# Try loading from multiple env file locations
_pkg_root = Path(__file__).resolve().parent
_candidates = [
    Path(".env"),
    Path("moodle_test_credentials.env"),
    _pkg_root / ".env",
    _pkg_root / "moodle_test_credentials.env",
    Path("d:/ProgramFiles/Projects/Noodle/moodle_test_credentials.env"),
    _pkg_root.parent / "moodle_test_credentials.env",
    Path("legacy/.env"),
]
for env_path in _candidates:
    if env_path.exists():
        load_dotenv(env_path)

# Moodle Base URL (defaults to Tel Aviv University Moodle)
MOODLE_URL = os.getenv("MOODLE_URL", "https://moodle.tau.ac.il").rstrip("/")

# Direct Master Token (optional, if available)
MOODLE_TOKEN = os.getenv("MOODLE_TOKEN", os.getenv("MOODLE_API_KEY", "")).strip()

# SSO Credentials (for zero-token session starting)
MOODLE_USERNAME = os.getenv("MOODLE_USERNAME", os.getenv("MOODLE_TESTING_USERNAME", os.getenv("UNIVERSITY_USERNAME", ""))).strip()
MOODLE_PASSWORD = os.getenv("MOODLE_PASSWORD", os.getenv("MOODLE_TESTING_PASSWORD", os.getenv("UNIVERSITY_PASSWORD", ""))).strip()
MOODLE_STUDENT_ID = os.getenv("MOODLE_STUDENT_ID", os.getenv("MOODLE_TESTING_ID", os.getenv("STUDENT_ID", ""))).strip()

# Session Cookie (optional)
MOODLE_SESSION_COOKIE = os.getenv("MOODLE_SESSION_COOKIE", "").strip()

# Timezone (defaults to Israel Time)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jerusalem")

# Panopto URL and credentials (optional)
PANOPTO_URL = os.getenv("PANOPTO_URL", "https://tau.cloud.panopto.eu").rstrip("/")
SCRAPE_PANOPTO = os.getenv("SCRAPE_PANOPTO", "0") in ("1", "true", "True")

# Persistent Session & Cache Storage Base Directory
SESSION_DIR = Path(os.getenv("MOODLE_STORAGE_DIR", str(Path.home() / ".moodle_mcp")))
PROFILES_DIR = SESSION_DIR / "profiles"

# Active User Profile Name (defaults to MOODLE_PROFILE, then MOODLE_USERNAME, then 'default')
MOODLE_PROFILE = os.getenv("MOODLE_PROFILE", MOODLE_USERNAME or "default").strip() or "default"


def sanitize_profile_name(profile: Optional[str] = None) -> str:
    """Sanitizes a profile or username into a safe directory name."""
    raw = (profile or os.getenv("MOODLE_PROFILE") or MOODLE_PROFILE or MOODLE_USERNAME or "default").strip()
    sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw)
    return sanitized or "default"


def get_profile_dir(profile: Optional[str] = None) -> Path:
    """Returns the isolated storage directory for a given user profile."""
    return PROFILES_DIR / sanitize_profile_name(profile)


def get_profile_paths(profile: Optional[str] = None) -> Dict[str, Path]:
    """Returns isolated session, cache, and saved_data file paths for a profile."""
    pdir = get_profile_dir(profile)
    return {
        "profile_dir": pdir,
        "session_file": pdir / "session.json",
        "cache_file": pdir / "cache.json",
        "saved_data_file": pdir / "saved_data.json",
    }


def get_configured_profiles() -> list[str]:
    """
    Discovers all configured profile names from environment variables and storage:
    - Profiles explicitly listed in MOODLE_PROFILES (comma-separated, e.g. 'yuval,yaeli')
    - Variables matching '{PROFILE}_MOODLE_USERNAME' (e.g. YUVAL_MOODLE_USERNAME)
    - Existing profile directories in ~/.moodle_mcp/profiles/
    - Default profile
    """
    profiles = set()
    env_profiles = os.getenv("MOODLE_PROFILES", "")
    if env_profiles:
        for p in env_profiles.split(","):
            p_clean = sanitize_profile_name(p.strip())
            if p_clean:
                profiles.add(p_clean)

    for k in os.environ.keys():
        if k.endswith("_MOODLE_USERNAME") and k != "MOODLE_USERNAME":
            p_clean = sanitize_profile_name(k.replace("_MOODLE_USERNAME", "").lower())
            if p_clean:
                profiles.add(p_clean)

    if PROFILES_DIR.is_dir():
        for item in PROFILES_DIR.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                profiles.add(sanitize_profile_name(item.name))

    if MOODLE_PROFILE:
        profiles.add(sanitize_profile_name(MOODLE_PROFILE))
    profiles.add("default")
    return sorted(list(profiles))


_default_paths = get_profile_paths(MOODLE_PROFILE)
SESSION_FILE = Path(os.getenv("MOODLE_SESSION_FILE", str(_default_paths["session_file"])))
CACHE_FILE = Path(os.getenv("MOODLE_CACHE_FILE", str(_default_paths["cache_file"])))
SAVED_DATA_FILE = Path(os.getenv("MOODLE_SAVED_DATA_FILE", str(_default_paths["saved_data_file"])))

# Default Cache Time-To-Live (in seconds)
CACHE_TTL_COURSES = int(os.getenv("MOODLE_CACHE_TTL_COURSES", str(24 * 3600)))      # 24 hours
CACHE_TTL_CONTENTS = int(os.getenv("MOODLE_CACHE_TTL_CONTENTS", str(6 * 3600)))    # 6 hours
CACHE_TTL_FILES = int(os.getenv("MOODLE_CACHE_TTL_FILES", str(6 * 3600)))          # 6 hours
CACHE_TTL_ASSIGNMENTS = int(os.getenv("MOODLE_CACHE_TTL_ASSIGNMENTS", str(15 * 60))) # 15 minutes
CACHE_TTL_GRADES = int(os.getenv("MOODLE_CACHE_TTL_GRADES", str(30 * 60)))         # 30 minutes
CACHE_TTL_MEETINGS = int(os.getenv("MOODLE_CACHE_TTL_MEETINGS", str(6 * 3600)))    # 6 hours

# Default user agent for requests
USER_AGENT = os.getenv(
    "MOODLE_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class Config:
    """Namespace wrapper for configuration settings."""
    BASE_URL = MOODLE_URL
    URL = MOODLE_URL
    TOKEN = MOODLE_TOKEN
    USERNAME = MOODLE_USERNAME
    PASSWORD = MOODLE_PASSWORD
    ID_NUMBER = MOODLE_STUDENT_ID
    STUDENT_ID = MOODLE_STUDENT_ID
    SESSION_COOKIE = MOODLE_SESSION_COOKIE
    TIMEZONE = TIMEZONE
    PANOPTO_URL = PANOPTO_URL
    SCRAPE_PANOPTO = SCRAPE_PANOPTO
    SESSION_DIR = SESSION_DIR
    PROFILES_DIR = PROFILES_DIR
    PROFILE = MOODLE_PROFILE
    SESSION_FILE = SESSION_FILE
    CACHE_FILE = CACHE_FILE
    SAVED_DATA_FILE = SAVED_DATA_FILE
    CACHE_TTL_COURSES = CACHE_TTL_COURSES
    CACHE_TTL_CONTENTS = CACHE_TTL_CONTENTS
    CACHE_TTL_FILES = CACHE_TTL_FILES
    CACHE_TTL_ASSIGNMENTS = CACHE_TTL_ASSIGNMENTS
    CACHE_TTL_GRADES = CACHE_TTL_GRADES
    CACHE_TTL_MEETINGS = CACHE_TTL_MEETINGS
    USER_AGENT = USER_AGENT



