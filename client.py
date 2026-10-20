"""
Moodle API Client for moodle_mcp.
Communicates with Moodle REST Web Services and authenticated session endpoints.
Handles course parsing, assignment true deadline calculation, submission, grades,
file downloads, and in-memory document reading for AI analysis.
"""

import base64
import datetime
import html
import io
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytz

import requests
from bs4 import BeautifulSoup

from moodle_mcp.auth import MoodleAuth, MoodleAuthError
from moodle_mcp.storage import CacheManager, DataStore
from moodle_mcp.config import (
    TIMEZONE,
    CACHE_TTL_COURSES,
    CACHE_TTL_CONTENTS,
    CACHE_TTL_FILES,
    CACHE_TTL_ASSIGNMENTS,
    CACHE_TTL_GRADES,
    CACHE_TTL_MEETINGS
)

logger = logging.getLogger("moodle_mcp.client")


class MoodleClientError(Exception):
    """Raised when an operation on Moodle fails."""
    pass


def parse_course_metadata(course: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parses academic year and semester from Moodle's idnumber or shortname.
    TAU idnumber structure: [8-digit Course Code]-[2-digit Group]-[4-digit Year]-[1-digit Semester]
    e.g. 03211100-01-2025-1 -> Year 2025, Semester A (1)
    """
    idnumber = course.get("idnumber", "")
    match = re.match(r"^(\d{8})-(\d{2})-(\d{4})-(\d)$", idnumber)
    if match:
        course_code, group_id, year, semester = match.groups()
        semester_map = {"1": "Semester A", "2": "Semester B", "0": "Yearly"}
        worksheet_name = f"{year}-Semester{'A' if semester == '1' else 'B' if semester == '2' else 'Yearly'}"
        return {
            "course_id": f"{course_code}{group_id}",
            "base_course_code": course_code,
            "group_id": group_id,
            "year": year,
            "semester_code": semester,
            "semester_name": semester_map.get(semester, f"Semester {semester}"),
            "worksheet_name": worksheet_name
        }
    return None


def is_academic_course(c: Dict[str, Any]) -> bool:
    """Checks whether a course is an academic course or university safety/compliance tutorial."""
    if "is_academic" in c and c["is_academic"] is not None:
        return bool(c["is_academic"])
    cid_str = str(c.get("id", ""))
    idnum_str = str(c.get("idnumber", ""))
    fullname = c.get("fullname", "")
    return not (
        cid_str.startswith("5900")
        or idnum_str.startswith("5900")
        or "בטיחות" in fullname
        or "לומדת" in fullname
    )


def clean_course_name(shortname: str, fullname: str) -> str:
    """Extracts a clean human-readable course name."""
    parts = shortname.split("-")
    if len(parts) >= 2:
        code = parts[0].strip()
        eng = parts[-1].strip()
        return f"{code} - {eng}"
    return fullname or shortname


class MoodleClient:
    def __init__(
        self,
        auth: Optional[MoodleAuth] = None,
        cache: Optional[CacheManager] = None,
        data_store: Optional[DataStore] = None,
        profile: Optional[str] = None,
    ):
        self.auth = auth or MoodleAuth(profile=profile)
        self.profile = self.auth.profile
        self.tz = pytz.timezone(TIMEZONE)
        self.cache = cache or CacheManager(profile=self.profile)
        self.data_store = data_store or DataStore(profile=self.profile)

    def _call_ws(
        self,
        wsfunction: str,
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET",
        retry_on_auth_fail: bool = True
    ) -> Any:
        """Executes a call to Moodle's REST server with automatic token refresh on expiry."""
        if not self.auth.ensure_authenticated():
            raise MoodleClientError("Not authenticated with Moodle. Please call moodle_login first.")

        endpoint = f"{self.auth.moodle_url}/webservice/rest/server.php"
        query_params = {
            "moodlewsrestformat": "json",
            "wsfunction": wsfunction
        }
        
        if self.auth.token:
            query_params["wstoken"] = self.auth.token

        call_params = {**(params or {})}
        
        try:
            if method.upper() == "POST":
                resp = self.auth.session.post(endpoint, params=query_params, data=call_params, timeout=25)
            else:
                combined_params = {**query_params, **call_params}
                resp = self.auth.session.get(endpoint, params=combined_params, timeout=25)

            if resp.status_code in (401, 403) and retry_on_auth_fail:
                logger.warning("Moodle session returned 401/403. Attempting force re-authentication...")
                if self.auth.ensure_authenticated(force_refresh=True):
                    return self._call_ws(wsfunction, params, method, retry_on_auth_fail=False)

            resp.raise_for_status()
            data = resp.json()

            # Check for Moodle API exception or errorcode (HTTP 200 with error payload)
            if isinstance(data, dict):
                err_code = data.get("errorcode", "")
                if err_code in ("invalidtoken", "accessexception", "sessionerroruser") and retry_on_auth_fail:
                    logger.warning(f"Moodle returned auth error [{err_code}]. Attempting force re-authentication...")
                    if self.auth.ensure_authenticated(force_refresh=True):
                        return self._call_ws(wsfunction, params, method, retry_on_auth_fail=False)

                if "exception" in data:
                    err_msg = data.get("message", "Moodle Exception")
                    raise MoodleClientError(f"Moodle API Error [{err_code or 'exception'}]: {err_msg}")
                if "errorcode" in data and str(data.get("errorcode")) != "0":
                    err_msg = data.get("message", "Moodle Error")
                    raise MoodleClientError(f"Moodle Error [{data['errorcode']}]: {err_msg}")

            return data
        except requests.RequestException as e:
            raise MoodleClientError(f"Failed to communicate with Moodle server: {e}")


    def get_site_info(self) -> Dict[str, Any]:
        """Retrieves information about the current user and Moodle site."""
        data = self._call_ws("core_webservice_get_site_info")
        if isinstance(data, dict) and "userid" in data:
            self.auth.user_id = data["userid"]
            self.auth.user_profile = data
        return data

    def get_enrolled_courses(self, refresh: bool = False, academic_only: bool = False) -> List[Dict[str, Any]]:
        """Retrieves all courses the current user is enrolled in."""
        cache_key = f"courses_{self.auth.user_id or 0}"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_COURSES)
            if cached is not None:
                if academic_only:
                    return [c for c in cached if is_academic_course(c)]
                return cached

        if not self.auth.user_id:
            info = self.get_site_info()
            self.auth.user_id = info.get("userid")
            cache_key = f"courses_{self.auth.user_id or 0}"

        courses = self._call_ws("core_enrol_get_users_courses", {"userid": self.auth.user_id})
        if not isinstance(courses, list):
            return []

        enriched = []
        for c in courses:
            meta = parse_course_metadata(c)
            clean_name = clean_course_name(c.get("shortname", ""), c.get("fullname", ""))
            is_academic = is_academic_course(c)

            c_info = {
                "id": c.get("id"),
                "shortname": c.get("shortname"),
                "fullname": c.get("fullname"),
                "display_name": clean_name,
                "idnumber": c.get("idnumber"),
                "startdate": c.get("startdate"),
                "enddate": c.get("enddate"),
                "visible": bool(c.get("visible", 1)),
                "semester": meta["semester_name"] if meta else "Other",
                "academic_year": meta["year"] if meta else "",
                "is_academic": is_academic,
                "metadata": meta
            }
            enriched.append(c_info)

        self.cache.set(cache_key, enriched)
        if academic_only:
            return [c for c in enriched if is_academic_course(c)]
        return enriched

    def resolve_course_id(self, course_identifier: Any) -> Optional[int]:
        """
        Resolves a course identifier (numeric ID or partial course name) to an integer course ID.
        Supports fuzzy name matching in Hebrew and English.
        """
        if course_identifier is None:
            return None
        if isinstance(course_identifier, int):
            return course_identifier
        
        s = str(course_identifier).strip()
        if s.isdigit():
            return int(s)

        courses = self.get_enrolled_courses()
        q = s.lower()
        # 1. Exact match on ID or code
        for c in courses:
            if q == str(c.get("id")) or q == str(c.get("idnumber", "")).lower():
                return c["id"]
        # 2. Substring match on display_name or fullname
        for c in courses:
            if q in c.get("display_name", "").lower() or q in c.get("fullname", "").lower():
                return c["id"]
        return None

    def get_course_contents(self, course_id: int, refresh: bool = False) -> List[Dict[str, Any]]:
        """Retrieves the full syllabus and sections/modules of a course."""
        cache_key = f"contents_{course_id}"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_CONTENTS)
            if cached is not None:
                return cached

        data = self._call_ws("core_course_get_contents", {"courseid": course_id})
        if isinstance(data, list):
            self.cache.set(cache_key, data)
        return data

    def get_assignments(self, course_id: Optional[int] = None, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves assignments and calculates True Deadlines taking nominal due date,
        cutoff date, and student personal extensions into account.
        """
        cache_key = f"assignments_{course_id}" if course_id else "assignments_all"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_ASSIGNMENTS)
            if cached is not None:
                return cached

        params = {}
        if course_id:
            params["courseids[0]"] = course_id

        data = self._call_ws("mod_assign_get_assignments", params)
        courses_data = data.get("courses", [])

        # Fetch enrolled courses to map names
        enrolled = self.get_enrolled_courses(refresh=refresh)
        course_names = {c["id"]: c["display_name"] for c in enrolled}

        now_dt = datetime.datetime.now(self.tz)
        results = []

        def process_assign(c_id: int, c_name: str, assign: Dict[str, Any]) -> Dict[str, Any]:
            assign_id = assign.get("id")
            cmid = assign.get("cmid")
            title = assign.get("name", "").strip()

            status = "Assigned"
            extension_ts = 0
            submission_date = None
            sub_status_raw = "new"

            try:
                sub_info = self._call_ws("mod_assign_get_submission_status", {"assignid": assign_id})
                lastattempt = sub_info.get("lastattempt", {})
                submission = lastattempt.get("submission", {})
                sub_status_raw = submission.get("status", "new")
                
                if sub_status_raw == "submitted":
                    status = "Submitted"
                    if submission.get("timemodified"):
                        sub_dt = datetime.datetime.fromtimestamp(submission["timemodified"], self.tz)
                        submission_date = sub_dt.strftime("%Y-%m-%d %H:%M:%S")
                
                extension_ts = lastattempt.get("extensionduedate", 0)
            except Exception as e:
                logger.debug(f"Could not retrieve submission status for assign {assign_id}: {e}")

            due_ts = assign.get("duedate", 0) if isinstance(assign.get("duedate"), int) else 0
            cutoff_ts = assign.get("cutoffdate", 0) if isinstance(assign.get("cutoffdate"), int) else 0

            final_deadline_ts = max(due_ts, cutoff_ts, extension_ts)

            def _fmt_ts(ts: int) -> str:
                if ts and ts > 0:
                    return datetime.datetime.fromtimestamp(ts, self.tz).strftime("%Y-%m-%d %H:%M:%S")
                return ""

            deadline_str = _fmt_ts(final_deadline_ts)
            due_str = _fmt_ts(due_ts)
            cutoff_str = _fmt_ts(cutoff_ts)
            extension_str = _fmt_ts(extension_ts)

            is_overdue = False
            if final_deadline_ts > 0:
                deadline_dt = datetime.datetime.fromtimestamp(final_deadline_ts, self.tz)
                if status != "Submitted" and deadline_dt < now_dt:
                    status = "Not submitted"
                    is_overdue = True

            opened_str = ""
            allow_sub = assign.get("allowsubmissionsfromdate", 0)
            if allow_sub and allow_sub > 0:
                opened_dt = datetime.datetime.fromtimestamp(allow_sub, self.tz)
                opened_str = opened_dt.strftime("%Y-%m-%d %H:%M:%S")

            moodle_link = f"{self.auth.moodle_url}/mod/assign/view.php?id={cmid}" if cmid else ""

            intro_html = assign.get("intro", "")
            intro_text = BeautifulSoup(intro_html, "html.parser").get_text(separator="\n").strip() if intro_html else ""

            intro_files = []
            for att in assign.get("introattachments", []):
                intro_files.append({
                    "filename": att.get("filename"),
                    "fileurl": att.get("fileurl")
                })

            return {
                "id": assign_id,
                "cmid": cmid,
                "course_id": c_id,
                "course_name": c_name,
                "name": title,
                "status": status,
                "sub_status_raw": sub_status_raw,
                "is_overdue": is_overdue,
                "deadline": deadline_str,
                "deadline_timestamp": final_deadline_ts,
                "effective_deadline": deadline_str,
                "due_date": due_str,
                "due_date_timestamp": due_ts,
                "cutoff_date": cutoff_str,
                "cutoff_date_timestamp": cutoff_ts,
                "extension_date": extension_str,
                "extension_date_timestamp": extension_ts,
                "allows_late_submissions": bool(cutoff_ts > due_ts > 0),
                "opened": opened_str,
                "moodle_link": moodle_link,
                "instructions": intro_text,
                "attachments": intro_files,
                "submitted_at": submission_date
            }

        # Gather tasks
        tasks = []
        for c in courses_data:
            c_id = c.get("id")
            c_name = course_names.get(c_id, c.get("fullname", f"Course {c_id}"))
            for assign in c.get("assignments", []):
                tasks.append((c_id, c_name, assign))

        if tasks:
            with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
                futures = [executor.submit(process_assign, cid, cname, a) for cid, cname, a in tasks]
                for future in as_completed(futures):
                    try:
                        results.append(future.result())
                    except Exception as e:
                        logger.debug(f"Error processing assignment: {e}")


        # Sort by deadline
        results.sort(key=lambda x: x.get("deadline_timestamp") or 9999999999)
        self.cache.set(cache_key, results)
        return results

    def get_upcoming_assignments(self, days_ahead: int = 7, refresh: bool = False) -> List[Dict[str, Any]]:
        """Retrieves assignments due within the next N days."""
        all_assignments = self.get_assignments(refresh=refresh)
        now_dt = datetime.datetime.now(self.tz)
        cutoff_dt = now_dt + datetime.timedelta(days=days_ahead)

        upcoming = []
        for a in all_assignments:
            ts = a.get("deadline_timestamp", 0)
            if not ts or ts == 0:
                continue
            due_dt = datetime.datetime.fromtimestamp(ts, self.tz)
            if now_dt <= due_dt <= cutoff_dt and a.get("status") != "Submitted":
                upcoming.append(a)

        return upcoming

    def get_assignment_status(self, assign_id: int) -> Dict[str, Any]:
        """Retrieves comprehensive submission and feedback details for a specific assignment."""
        sub_info = self._call_ws("mod_assign_get_submission_status", {"assignid": assign_id})
        lastattempt = sub_info.get("lastattempt", {})
        submission = lastattempt.get("submission", {})
        feedback = sub_info.get("feedback", {})

        # Extract submitted files
        submitted_files = []
        for plugin in submission.get("plugins", []):
            if plugin.get("type") == "file":
                for filearea in plugin.get("fileareas", []):
                    for f in filearea.get("files", []):
                        submitted_files.append({
                            "filename": f.get("filename"),
                            "fileurl": f.get("fileurl"),
                            "filesize": f.get("filesize"),
                            "mimetype": f.get("mimetype"),
                            "timemodified": f.get("timemodified")
                        })

        # Feedback grade
        grade_info = feedback.get("grade", {})
        grade_val = grade_info.get("grade")
        
        return {
            "assign_id": assign_id,
            "status": submission.get("status", "new"),
            "grading_status": lastattempt.get("gradingstatus", "notgraded"),
            "can_submit": lastattempt.get("cansubmit", False),
            "can_edit": lastattempt.get("canedit", False),
            "extension_due_date": lastattempt.get("extensionduedate", 0),
            "submitted_files": submitted_files,
            "feedback_grade": grade_val,
            "feedback_comments": feedback.get("plugins", [])
        }

    def submit_assignment(
        self,
        assign_id: int,
        file_path_or_bytes: Optional[Any] = None,
        filename: Optional[str] = None,
        online_text: Optional[str] = None,
        submit_for_grading: bool = False
    ) -> Dict[str, Any]:
        """
        Uploads a solution file to Moodle's draft area and/or provides online text,
        linking them to an assignment submission.
        Optionally submits the assignment for final grading.
        """
        if not self.auth.ensure_authenticated():
            raise MoodleClientError("Not authenticated.")

        if not file_path_or_bytes and not online_text:
            raise MoodleClientError("Must provide at least one of file_path_or_bytes or online_text.")

        itemid = None
        fname = None

        if file_path_or_bytes:
            # Prepare file bytes and name
            if isinstance(file_path_or_bytes, (str, Path)) and os.path.exists(str(file_path_or_bytes)):
                file_path = Path(file_path_or_bytes)
                fname = filename or file_path.name
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
            elif isinstance(file_path_or_bytes, bytes):
                content_bytes = file_path_or_bytes
                fname = filename or "submission_file.pdf"
            else:
                raise MoodleClientError("file_path_or_bytes must be an existing file path or bytes.")

            # Option 1: Try multipart upload to /webservice/upload.php if token is available
            uploaded = False
            if self.auth.token:
                try:
                    upload_url = f"{self.auth.moodle_url}/webservice/upload.php"
                    files_payload = {
                        "file": (fname, content_bytes, "application/octet-stream")
                    }
                    data_payload = {
                        "token": self.auth.token,
                        "filearea": "draft",
                        "itemid": 0
                    }
                    upload_resp = self.auth.session.post(
                        upload_url,
                        data=data_payload,
                        files=files_payload,
                        timeout=30
                    )
                    if upload_resp.status_code == 200:
                        res_list = upload_resp.json()
                        if isinstance(res_list, list) and len(res_list) > 0 and "itemid" in res_list[0]:
                            itemid = res_list[0]["itemid"]
                            uploaded = True
                except Exception as e:
                    logger.debug(f"Direct multipart upload failed, falling back to core_files_upload: {e}")

            # Option 2: Fall back to core_files_upload
            if not uploaded:
                b64_content = base64.b64encode(content_bytes).decode("utf-8")
                upload_params = {
                    "component": "user",
                    "filearea": "draft",
                    "itemid": 0,
                    "filepath": "/",
                    "filename": fname,
                    "filecontent": b64_content
                }
                upload_res = self._call_ws("core_files_upload", upload_params, method="POST")
                itemid = upload_res.get("itemid")
                if not itemid:
                    raise MoodleClientError(f"Failed to get draft item ID from Moodle upload: {upload_res}")

        # 2. Save submission draft
        save_params: Dict[str, Any] = {"assignmentid": assign_id}
        if itemid:
            save_params["plugindata[files_filemanager]"] = itemid
        if online_text:
            save_params["plugindata[onlinetext_editor][text]"] = online_text
            save_params["plugindata[onlinetext_editor][format]"] = 1
            save_params["plugindata[onlinetext_editor][itemid]"] = 0

        self._call_ws("mod_assign_save_submission", save_params, method="POST")

        # 3. Lock for grading if requested
        if submit_for_grading:
            submit_params = {
                "assignmentid": assign_id,
                "acceptsubmissionstatement": 1
            }
            self._call_ws("mod_assign_submit_for_grading", submit_params, method="POST")
            return {
                "success": True,
                "message": f"Successfully submitted assignment {assign_id} for grading.",
                "draft_itemid": itemid,
                "file_uploaded": fname,
                "online_text_submitted": bool(online_text),
                "status": "Submitted"
            }

        return {
            "success": True,
            "message": f"Successfully saved draft submission for assignment {assign_id}.",
            "draft_itemid": itemid,
            "file_uploaded": fname,
            "online_text_submitted": bool(online_text),
            "status": "Draft"
        }


    def get_grades(self, course_id: Optional[int] = None, refresh: bool = False) -> List[Dict[str, Any]]:
        """Retrieves grades for the current user across all courses or a single course."""
        cache_key = f"grades_{course_id}" if course_id else "grades_all"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_GRADES)
            if cached is not None:
                return cached

        if not self.auth.user_id:
            info = self.get_site_info()
            self.auth.user_id = info.get("userid")

        courses = self.get_enrolled_courses(refresh=refresh)
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        all_grades = []

        def fetch_course_grades(course_info: Dict[str, Any]) -> List[Dict[str, Any]]:
            c_id = course_info["id"]
            c_name = course_info["display_name"]
            c_grades = []
            try:
                data = self._call_ws("gradereport_user_get_grade_items", {
                    "courseid": c_id,
                    "userid": self.auth.user_id
                })
                for usergrade in data.get("usergrades", []):
                    for item in usergrade.get("gradeitems", []):
                        raw_grade = item.get("graderaw")
                        max_grade = item.get("grademax", 100)
                        formatted = item.get("gradeformatted", "-")
                        
                        percentage = None
                        if raw_grade is not None and max_grade and max_grade > 0:
                            percentage = round((float(raw_grade) / float(max_grade)) * 100, 2)

                        item_name = item.get("itemname") or ("Course Total" if item.get("itemtype") == "course" else "Item")
                        c_grades.append({
                            "course_id": c_id,
                            "course_name": c_name,
                            "item_name": item_name,
                            "item_type": item.get("itemtype"),
                            "item_module": item.get("itemmodule"),
                            "cmid": item.get("cmid"),
                            "grade_raw": raw_grade,
                            "grade_max": max_grade,
                            "grade_formatted": formatted,
                            "percentage": percentage,
                            "is_hidden": bool(item.get("gradeishidden", False))
                        })
            except Exception as e:
                logger.debug(f"Could not fetch grades for course {c_id}: {e}")
            return c_grades

        if courses:
            with ThreadPoolExecutor(max_workers=min(len(courses), 8)) as executor:
                futures = [executor.submit(fetch_course_grades, c) for c in courses]
                for future in as_completed(futures):
                    try:
                        all_grades.extend(future.result())
                    except Exception as e:
                        logger.debug(f"Error fetching course grades: {e}")

        self.cache.set(cache_key, all_grades)
        return all_grades


    def get_grades_summary(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """Calculates GPA and grade summaries grouped by course."""
        all_grades = self.get_grades(refresh=refresh)
        courses_map = {}

        for g in all_grades:
            cid = g["course_id"]
            if cid not in courses_map:
                courses_map[cid] = {
                    "course_id": cid,
                    "course_name": g["course_name"],
                    "total_items": 0,
                    "graded_items": 0,
                    "sum_percentages": 0.0,
                    "course_total": None
                }

            if g["item_type"] == "course":
                courses_map[cid]["course_total"] = g["grade_formatted"]
            else:
                courses_map[cid]["total_items"] += 1
                if g["percentage"] is not None:
                    courses_map[cid]["graded_items"] += 1
                    courses_map[cid]["sum_percentages"] += g["percentage"]

        summaries = []
        for cid, data in courses_map.items():
            avg = None
            if data["graded_items"] > 0:
                avg = round(data["sum_percentages"] / data["graded_items"], 2)
            summaries.append({
                "course_id": cid,
                "course_name": data["course_name"],
                "course_total": data["course_total"],
                "average_percentage": avg,
                "graded_items_count": data["graded_items"],
                "total_items_count": data["total_items"]
            })

        return summaries

    def get_course_files(self, course_id: int, refresh: bool = False) -> List[Dict[str, Any]]:
        """Extracts all downloadable resources and files in a course."""
        cache_key = f"files_{course_id}"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_FILES)
            if cached is not None:
                return cached

        contents = self.get_course_contents(course_id, refresh=refresh)
        files = []

        for section in contents:
            sec_name = section.get("name", "General")
            for module in section.get("modules", []):
                if module.get("modname") == "resource" and "contents" in module:
                    for content in module["contents"]:
                        if content.get("type") == "file":
                            files.append({
                                "course_id": course_id,
                                "section_name": sec_name,
                                "module_name": module.get("name", ""),
                                "filename": content.get("filename", ""),
                                "fileurl": content.get("fileurl", ""),
                                "filesize": content.get("filesize", 0),
                                "mimetype": content.get("mimetype", "application/octet-stream"),
                                "time_modified": content.get("timemodified", 0)
                            })
        self.cache.set(cache_key, files)
        return files

    def download_file(self, file_url: str, output_path: Optional[str] = None) -> Dict[str, Any]:
        """Downloads a file from Moodle using active token or session cookies."""
        if not self.auth.ensure_authenticated():
            raise MoodleClientError("Not authenticated.")

        url = file_url
        if self.auth.token and "token=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={self.auth.token}"

        resp = self.auth.session.get(url, stream=True, timeout=30)
        resp.raise_for_status()

        # Determine filename
        fname = "downloaded_file"
        cd = resp.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            match = re.search(r'filename=["\']?([^"\';]+)["\']?', cd)
            if match:
                fname = match.group(1)
        else:
            path_part = file_url.split("?")[0].rstrip("/")
            if "/" in path_part:
                fname = path_part.split("/")[-1]

        target_file = Path(output_path) if output_path else Path(fname)
        if target_file.is_dir():
            target_file = target_file / fname

        with open(target_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return {
            "success": True,
            "filename": target_file.name,
            "saved_path": str(target_file.resolve()),
            "file_size": target_file.stat().st_size
        }

    def read_file_content(self, file_url: str, max_chars: int = 15000) -> Dict[str, Any]:
        """
        Fetches a course file or document directly into memory and extracts plain text
        for immediate AI analysis. Supports PDF, TXT, MD, HTML, and code files.
        """
        if not self.auth.ensure_authenticated():
            raise MoodleClientError("Not authenticated.")

        url = file_url
        if self.auth.token and "token=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={self.auth.token}"

        resp = self.auth.session.get(url, timeout=30)
        resp.raise_for_status()

        content_bytes = resp.content
        content_type = resp.headers.get("Content-Type", "").lower()

        # Determine extension
        path_clean = file_url.split("?")[0].lower()
        is_pdf = path_clean.endswith(".pdf") or "pdf" in content_type
        is_docx = path_clean.endswith(".docx") or "officedocument.wordprocessingml" in content_type
        is_pptx = path_clean.endswith(".pptx") or "officedocument.presentationml" in content_type

        extracted_text = ""
        doc_type = "text"

        if is_pdf:
            doc_type = "pdf"
            try:
                import pymupdf
                doc = pymupdf.open(stream=content_bytes, filetype="pdf")
                pages = []
                for p_num in range(min(len(doc), 20)):  # First 20 pages max
                    pages.append(doc[p_num].get_text())
                extracted_text = "\n\n--- Page Break ---\n\n".join(pages)
            except Exception as e:
                extracted_text = f"[Could not parse PDF using PyMuPDF: {e}]"
        elif is_docx:
            doc_type = "docx"
            try:
                import io, zipfile, xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    texts = [node.text for node in tree.iter() if node.tag.endswith("}t") and node.text]
                    extracted_text = " ".join(texts)
            except Exception as e:
                extracted_text = f"[Could not parse DOCX: {e}]"
        elif is_pptx:
            doc_type = "pptx"
            try:
                import io, zipfile, xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                    slide_files = sorted([f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
                    slides_text = []
                    for idx, sfile in enumerate(slide_files):
                        s_xml = z.read(sfile)
                        tree = ET.fromstring(s_xml)
                        texts = [node.text for node in tree.iter() if node.tag.endswith("}t") and node.text]
                        if texts:
                            slides_text.append(f"--- Slide {idx+1} ---\n" + "\n".join(texts))
                    extracted_text = "\n\n".join(slides_text)
            except Exception as e:
                extracted_text = f"[Could not parse PPTX: {e}]"
        else:
            # Attempt decoding as text / html
            try:
                raw_text = content_bytes.decode("utf-8", errors="replace")
                if "html" in content_type or "<html" in raw_text.lower():
                    doc_type = "html"
                    extracted_text = BeautifulSoup(raw_text, "html.parser").get_text(separator="\n").strip()
                else:
                    extracted_text = raw_text
            except Exception as e:
                extracted_text = f"[Binary or undecodable file: {e}]"

        truncated = len(extracted_text) > max_chars
        preview = extracted_text[:max_chars]

        return {
            "url": file_url,
            "document_type": doc_type,
            "content_length": len(extracted_text),
            "is_truncated": truncated,
            "text": preview
        }

    def get_course_meetings(self, course_id: Optional[int] = None, refresh: bool = False) -> List[Dict[str, Any]]:
        """Extracts Zoom meetings and online session links from course contents."""
        cache_key = f"meetings_{course_id}" if course_id else "meetings_all"
        if not refresh:
            cached = self.cache.get(cache_key, max_age=CACHE_TTL_MEETINGS)
            if cached is not None:
                return cached

        courses = self.get_enrolled_courses(refresh=refresh)
        if course_id:
            courses = [c for c in courses if c["id"] == course_id]

        all_meetings = []

        for c in courses:
            c_id = c["id"]
            c_name = c["display_name"]
            contents = self.get_course_contents(c_id, refresh=refresh)

            for section in contents:
                sec_name = section.get("name", "General")
                for mod in section.get("modules", []):
                    modname = mod.get("modname")
                    name = mod.get("name", "").strip()
                    name_lower = name.lower()

                    is_zoom = False
                    meeting_url = ""

                    if modname == "lti" and ("zoom" in name_lower or "הרצאה" in name_lower or "מפגש" in name_lower):
                        is_zoom = True
                        meeting_url = mod.get("url", f"{self.auth.moodle_url}/mod/lti/view.php?id={mod.get('id')}")
                    elif modname == "url":
                        for cnt in mod.get("contents", []):
                            m_url = cnt.get("fileurl", "")
                            if "zoom.us" in m_url or "zoom." in m_url or any(k in name_lower for k in ["zoom", "meeting", "שיעור", "הרצאה", "תרגול"]):
                                is_zoom = True
                                meeting_url = m_url
                                break

                    if is_zoom and meeting_url:
                        all_meetings.append({
                            "course_id": c_id,
                            "course_name": c_name,
                            "title": name,
                            "section": sec_name,
                            "meeting_url": meeting_url,
                            "type": "zoom"
                        })

        self.cache.set(cache_key, all_meetings)
        return all_meetings

    def clear_cache(self, category: Optional[str] = None) -> int:
        """
        Clears cached API responses.
        Args:
            category: Optional category filter ('courses', 'contents', 'assignments', 'grades', 'files', 'meetings').
                      If None, clears the entire cache.
        """
        if category:
            return self.cache.clear(prefix=f"{category.lower().strip()}_")
        return self.cache.clear()


    def get_quizzes(self, course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves quizzes across all courses or a single course.
        Includes open/close dates, time limits, and attempt limits.
        """
        enrolled = self.get_enrolled_courses()
        course_names = {c["id"]: c["display_name"] for c in enrolled}

        courses_to_query = [course_id] if course_id else [c["id"] for c in enrolled]
        if not courses_to_query:
            return []

        params: Dict[str, Any] = {}
        for idx, cid in enumerate(courses_to_query):
            params[f"courseids[{idx}]"] = cid

        try:
            data = self._call_ws("mod_quiz_get_quizzes_by_courses", params)
        except Exception as e:
            logger.debug(f"mod_quiz_get_quizzes_by_courses failed: {e}")
            return []

        quizzes_raw = data.get("quizzes", []) if isinstance(data, dict) else []
        now_dt = datetime.datetime.now(self.tz)
        quizzes = []

        for q in quizzes_raw:
            cid = q.get("course")
            cname = course_names.get(cid, f"Course {cid}")
            open_ts = q.get("timeopen", 0)
            close_ts = q.get("timeclose", 0)

            open_str = ""
            if open_ts and open_ts > 0:
                open_str = datetime.datetime.fromtimestamp(open_ts, self.tz).strftime("%Y-%m-%d %H:%M:%S")

            close_str = ""
            is_active = True
            is_closed = False
            if close_ts and close_ts > 0:
                close_dt = datetime.datetime.fromtimestamp(close_ts, self.tz)
                close_str = close_dt.strftime("%Y-%m-%d %H:%M:%S")
                if close_dt < now_dt:
                    is_active = False
                    is_closed = True

            intro_html = q.get("intro", "")
            intro_text = BeautifulSoup(intro_html, "html.parser").get_text(separator="\n").strip() if intro_html else ""

            quizzes.append({
                "id": q.get("id"),
                "course_id": cid,
                "course_name": cname,
                "name": q.get("name", "").strip(),
                "instructions": intro_text,
                "time_open": open_str,
                "time_open_timestamp": open_ts,
                "time_close": close_str,
                "time_close_timestamp": close_ts,
                "time_limit_minutes": round(q.get("timelimit", 0) / 60, 1) if q.get("timelimit") else None,
                "attempts_allowed": q.get("attempts", 0),
                "grade": q.get("grade", 0),
                "is_active": is_active,
                "is_closed": is_closed
            })

        return quizzes

    def get_calendar_events(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Retrieves upcoming calendar events (deadlines, exams, scheduled classes) across courses.
        """
        now_dt = datetime.datetime.now(self.tz)
        start_ts = int(now_dt.timestamp())
        end_ts = int((now_dt + datetime.timedelta(days=days_ahead)).timestamp())

        params = {
            "events[categoryids][0]": 0,
            "options[timestart]": start_ts,
            "options[timeend]": end_ts
        }

        try:
            data = self._call_ws("core_calendar_get_calendar_events", params)
        except Exception as e:
            logger.debug(f"core_calendar_get_calendar_events failed: {e}")
            return []

        events_raw = data.get("events", []) if isinstance(data, dict) else []
        enrolled = self.get_enrolled_courses()
        course_names = {c["id"]: c["display_name"] for c in enrolled}

        events = []
        for ev in events_raw:
            cid = ev.get("courseid")
            cname = course_names.get(cid, ev.get("course", {}).get("fullname", f"Course {cid}"))
            ts = ev.get("timestart", 0)
            ev_dt_str = datetime.datetime.fromtimestamp(ts, self.tz).strftime("%Y-%m-%d %H:%M:%S") if ts else ""

            desc_html = ev.get("description", "")
            desc_text = BeautifulSoup(desc_html, "html.parser").get_text(separator="\n").strip() if desc_html else ""

            events.append({
                "id": ev.get("id"),
                "name": ev.get("name", ""),
                "course_id": cid,
                "course_name": cname,
                "event_type": ev.get("eventtype", ""),
                "modulename": ev.get("modulename", ""),
                "instance": ev.get("instance"),
                "start_time": ev_dt_str,
                "start_timestamp": ts,
                "duration_seconds": ev.get("timeduration", 0),
                "description": desc_text
            })

        events.sort(key=lambda x: x.get("start_timestamp") or 0)
        return events

    def get_course_announcements(self, course_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Retrieves recent course announcements and forum notices.
        """
        enrolled = self.get_enrolled_courses()
        course_names = {c["id"]: c["display_name"] for c in enrolled}

        courses_to_query = [course_id] if course_id else [c["id"] for c in enrolled]
        all_announcements = []

        params: Dict[str, Any] = {}
        for idx, cid in enumerate(courses_to_query):
            params[f"courseids[{idx}]"] = cid

        try:
            forums_data = self._call_ws("mod_forum_get_forums_by_courses", params)
        except Exception as e:
            logger.debug(f"mod_forum_get_forums_by_courses failed: {e}")
            return []

        if not isinstance(forums_data, list):
            return []

        for forum in forums_data:
            f_type = forum.get("type", "")
            f_name = forum.get("name", "").lower()
            # News/announcements forums
            if f_type == "news" or any(k in f_name for k in ["הודעות", "announcement", "חדשות", "news"]):
                fid = forum.get("id")
                cid = forum.get("course")
                cname = course_names.get(cid, f"Course {cid}")
                try:
                    disc_data = self._call_ws("mod_forum_get_forum_discussions_paginated", {
                        "forumid": fid,
                        "sortby": "timemodified",
                        "sortdirection": "DESC",
                        "page": 0,
                        "perpage": 5
                    })
                    for d in disc_data.get("discussions", []):
                        ts = d.get("timemodified", 0)
                        post_dt = datetime.datetime.fromtimestamp(ts, self.tz).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
                        msg_html = d.get("message", "")
                        msg_text = BeautifulSoup(msg_html, "html.parser").get_text(separator="\n").strip() if msg_html else ""

                        all_announcements.append({
                            "id": d.get("discussion"),
                            "course_id": cid,
                            "course_name": cname,
                            "forum_name": forum.get("name"),
                            "subject": d.get("subject", d.get("name", "")),
                            "author": d.get("userfullname", ""),
                            "date": post_dt,
                            "timestamp": ts,
                            "message": msg_text
                        })
                except Exception as e:
                    logger.debug(f"Error fetching discussions for forum {fid}: {e}")

        all_announcements.sort(key=lambda x: x.get("timestamp") or 0, reverse=True)
        return all_announcements

    def get_course_participants(self, course_id: int) -> List[Dict[str, Any]]:
        """
        Retrieves lecturers, teaching assistants, and enrolled participants of a course.
        """
        try:
            data = self._call_ws("core_enrol_get_enrolled_users", {"courseid": course_id})
        except Exception as e:
            logger.debug(f"core_enrol_get_enrolled_users failed: {e}")
            return []

        if not isinstance(data, list):
            return []

        participants = []
        for u in data:
            roles = [r.get("shortname", "") for r in u.get("roles", [])]
            is_staff = any(r in ("editingteacher", "teacher", "manager") for r in roles)
            participants.append({
                "id": u.get("id"),
                "fullname": u.get("fullname", ""),
                "roles": roles,
                "is_staff": is_staff,
                "email": u.get("email", ""),
                "department": u.get("department", "")
            })

        # Put lecturers and TAs first
        participants.sort(key=lambda x: not x["is_staff"])
        return participants

    def get_dashboard(self, days_ahead: int = 14) -> Dict[str, Any]:
        """
        Retrieves a unified high-level academic briefing in a single call:
        active academic courses, upcoming assignment deadlines, active quizzes,
        upcoming calendar events, and recent course announcements.
        """
        academic_courses = self.get_enrolled_courses(academic_only=True)
        upcoming_assigns = self.get_upcoming_assignments(days_ahead=days_ahead)
        quizzes = self.get_quizzes()
        active_quizzes = [q for q in quizzes if q.get("is_active", True) and not q.get("is_closed", False)]
        calendar_events = self.get_calendar_events(days_ahead=days_ahead)
        announcements = self.get_course_announcements()[:5]

        return {
            "academic_courses_count": len(academic_courses),
            "academic_courses": [
                {"id": c["id"], "name": c["display_name"], "semester": c.get("semester")}
                for c in academic_courses
            ],
            "upcoming_deadlines_count": len(upcoming_assigns),
            "upcoming_deadlines": upcoming_assigns,
            "active_quizzes_count": len(active_quizzes),
            "active_quizzes": active_quizzes,
            "upcoming_events_count": len(calendar_events),
            "upcoming_events": calendar_events,
            "recent_announcements": announcements
        }

