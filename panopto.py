"""
Panopto and course lecture recordings integration for moodle_mcp.
Extracts Panopto links embedded inside Moodle course contents, as well as
supporting Playwright-based Panopto scraping when configured.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger("moodle_mcp.panopto")


def enrich_recording(r: Dict[str, Any]) -> Dict[str, Any]:
    """Classifies recording as Lecture or Recitation (Tirgul)."""
    title = r.get("lecture_title", "") or r.get("title", "")
    is_recitation = "tirgul" in title.lower() or "תרגול" in title or "recitation" in title.lower()
    r["type"] = "Recitation" if is_recitation else "Lecture"
    return r


class PanoptoManager:
    def __init__(self, moodle_client: Any):
        self.client = moodle_client

    def get_course_recordings(self, course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Discovers lecture recordings by scanning Moodle course contents for Panopto LTI modules,
        embedded video URLs, and course links.
        """
        courses = self.client.get_enrolled_courses()
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        recordings = []

        for c in courses:
            c_id = c["id"]
            c_name = c["display_name"]
            contents = self.client.get_course_contents(c_id)

            for section in contents:
                sec_name = section.get("name", "General")
                for mod in section.get("modules", []):
                    modname = mod.get("modname")
                    name = mod.get("name", "").strip()
                    name_lower = name.lower()

                    is_recording = False
                    link = ""

                    # Check Panopto LTI or tool
                    if "panopto" in modname or "panopto" in name_lower or "הקלט" in name_lower or "recording" in name_lower:
                        is_recording = True
                        link = mod.get("url") or f"{self.client.auth.moodle_url}/mod/{modname}/view.php?id={mod.get('id')}"

                    # Check URL modules
                    if not is_recording and modname == "url":
                        for cnt in mod.get("contents", []):
                            furl = cnt.get("fileurl", "")
                            if "panopto" in furl or "cloud.panopto" in furl or "youtube" in furl or "vimeo" in furl or any(k in name_lower for k in ["הקלטה", "הקלטות", "recording", "video"]):
                                is_recording = True
                                link = furl
                                break

                    if is_recording and link:
                        rec_item = {
                            "course_id": c_id,
                            "course_name": c_name,
                            "section": sec_name,
                            "lecture_title": name,
                            "recording_link": link,
                            "published_date": datetime.now().strftime("%Y-%m-%d")
                        }
                        recordings.append(enrich_recording(rec_item))

        return recordings
