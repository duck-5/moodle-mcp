"""
OpenAPI REST API Server for Moodle MCP.
Exposes standard RESTful endpoints backed by MoodleClient, compliant with OpenAPI 3.1.
Enables Anthropic's mcp-server-openapi approach for dynamic tool discovery by LLMs.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Ensure package is on sys.path
_pkg_root = Path(__file__).resolve().parent
if str(_pkg_root.parent) not in sys.path:
    sys.path.insert(0, str(_pkg_root.parent))

from fastapi import FastAPI, HTTPException, Query, Body, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager

logger = logging.getLogger("moodle_mcp.openapi")


# ==========================================
# Pydantic Request Models
# ==========================================

class LoginRequest(BaseModel):
    auth_type: str = Field("sso", description="Mode: 'sso', 'token', 'cookie', or 'standard'")
    username: Optional[str] = Field(None, description="Username for SSO or standard credentials")
    password: Optional[str] = Field(None, description="Password for SSO or standard credentials")
    student_id: Optional[str] = Field(None, description="Student ID / Israeli ID for TAU SSO")
    token: Optional[str] = Field(None, description="Direct Moodle Web Service token")
    session_cookie: Optional[str] = Field(None, description="Browser MoodleSession cookie")
    moodle_url: Optional[str] = Field(None, description="Custom Moodle instance base URL")


class SubmitAssignmentRequest(BaseModel):
    file_path: Optional[str] = Field(None, description="Local path to solution file to upload")
    filename: Optional[str] = Field(None, description="Optional custom filename in Moodle")
    online_text: Optional[str] = Field(None, description="Online text response (HTML/Markdown/Text)")
    submit_for_grading: bool = Field(False, description="If True, locks and submits for grading. If False, saves as draft.")


class ReadFileRequest(BaseModel):
    file_url: str = Field(..., description="Moodle pluginfile.php URL to fetch and parse")
    max_chars: int = Field(15000, description="Max plain-text characters to extract")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search term across courses, files, tasks, and lectures")
    search_types: Optional[List[str]] = Field(
        default=["courses", "assignments", "files", "meetings", "recordings"],
        description="Domains to search"
    )


# ==========================================
# FastAPI Factory
# ==========================================

def create_app(client: Optional[MoodleClient] = None) -> FastAPI:
    """Builds and configures the FastAPI application."""
    if client is None:
        auth = MoodleAuth()
        client = MoodleClient(auth=auth)

    panopto = PanoptoManager(moodle_client=client)

    app = FastAPI(
        title="Moodle MCP OpenAPI Server",
        description=(
            "Standard RESTful OpenAPI specification and gateway for Moodle LMS. "
            "Designed for Anthropic's mcp-server-openapi approach, allowing AI assistants "
            "(Claude Desktop, Cursor, Antigravity) to dynamically discover, inspect, "
            "and execute Moodle tools via OpenAPI 3.1."
        ),
        version="1.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------
    # Health & System
    # ------------------------------------------
    @app.get("/health", tags=["System"], summary="Health check", operation_id="healthCheck")
    def health_check() -> Dict[str, Any]:
        return {"status": "ok", "service": "moodle_mcp_openapi", "version": "1.1.0"}

    @app.get("/api/v1/status", tags=["Auth"], summary="Authentication status", operation_id="moodle_get_status")
    def get_status() -> Dict[str, Any]:
        """Checks authentication status and active user profile."""
        return client.auth.get_status()

    @app.post("/api/v1/auth/login", tags=["Auth"], summary="Authenticate with Moodle", operation_id="moodle_login")
    def login(req: LoginRequest) -> Dict[str, Any]:
        """Authenticates via SSO, token, cookie, or standard credentials."""
        try:
            if req.auth_type == "token":
                if not req.token:
                    raise HTTPException(status_code=400, detail="Missing required 'token' parameter.")
                return client.auth.login_with_token(req.token, moodle_url=req.moodle_url)
            elif req.auth_type == "cookie":
                if not req.session_cookie:
                    raise HTTPException(status_code=400, detail="Missing required 'session_cookie' parameter.")
                return client.auth.login_with_cookie(req.session_cookie, moodle_url=req.moodle_url)
            elif req.auth_type == "standard":
                if not req.username or not req.password:
                    raise HTTPException(status_code=400, detail="Missing username or password.")
                return client.auth.login_with_standard_credentials(req.username, req.password, moodle_url=req.moodle_url)
            elif req.auth_type == "sso":
                if not req.username or not req.password:
                    raise HTTPException(status_code=400, detail="Missing username or password for SSO.")
                return client.auth.login_with_sso(req.username, req.password, student_id=req.student_id, moodle_url=req.moodle_url)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported auth_type: {req.auth_type}")
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))

    @app.post("/api/v1/auth/logout", tags=["Auth"], summary="Log out and clear session", operation_id="moodle_logout")
    def logout() -> Dict[str, Any]:
        """Terminates active session and removes local session cache."""
        return client.auth.logout()

    @app.get("/api/v1/user/profile", tags=["User"], summary="Get student profile", operation_id="moodle_get_user_profile")
    def get_user_profile() -> Dict[str, Any]:
        """Retrieves full profile of the logged-in student."""
        try:
            return client.get_site_info()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Courses
    # ------------------------------------------
    @app.get("/api/v1/courses", tags=["Courses"], summary="List enrolled courses", operation_id="moodle_get_enrolled_courses")
    def get_enrolled_courses(semester: Optional[str] = Query(None, description="Optional semester filter (e.g. 'Semester A')")) -> List[Dict[str, Any]]:
        """Retrieves enrolled courses with academic year and semester breakdown."""
        try:
            courses = client.get_enrolled_courses()
            if semester:
                courses = [c for c in courses if semester.lower() in c.get("semester", "").lower()]
            return courses
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/courses/{course_id}/contents", tags=["Courses"], summary="Get full course syllabus & modules", operation_id="moodle_get_course_contents")
    def get_course_contents(course_id: int) -> List[Dict[str, Any]]:
        """Retrieves complete section-by-section contents, materials, and links of a course."""
        try:
            return client.get_course_contents(course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/courses/{course_id}/files", tags=["Courses"], summary="List course files & slides", operation_id="moodle_get_course_files")
    def get_course_files(course_id: int, section_name: Optional[str] = Query(None, description="Section filter")) -> List[Dict[str, Any]]:
        """Lists all downloadable course files, slides, and handouts."""
        try:
            files = client.get_course_files(course_id)
            if section_name:
                files = [f for f in files if section_name.lower() in f.get("section_name", "").lower()]
            return files
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/courses/{course_id}/participants", tags=["Courses"], summary="Get course teachers and participants", operation_id="moodle_get_course_participants")
    def get_course_participants(course_id: int) -> List[Dict[str, Any]]:
        """Retrieves lecturers, teaching assistants (TAs), and enrolled students."""
        try:
            return client.get_course_participants(course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/courses/announcements", tags=["Courses"], summary="Get course announcements", operation_id="moodle_get_course_announcements")
    def get_course_announcements(course_id: Optional[int] = Query(None, description="Course filter")) -> List[Dict[str, Any]]:
        """Retrieves official announcements and news posted by instructors."""
        try:
            return client.get_course_announcements(course_id=course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Assignments & Submissions
    # ------------------------------------------
    @app.get("/api/v1/assignments", tags=["Assignments"], summary="List assignments with True Deadlines", operation_id="moodle_get_assignments")
    def get_assignments(
        course_id: Optional[int] = Query(None, description="Course filter"),
        status_filter: Optional[str] = Query(None, description="Filter: 'Submitted', 'Assigned', 'Not submitted'")
    ) -> List[Dict[str, Any]]:
        """Retrieves assignments with True Deadlines and personal extensions."""
        try:
            assignments = client.get_assignments(course_id=course_id)
            if status_filter:
                assignments = [a for a in assignments if a.get("status", "").lower() == status_filter.lower()]
            return assignments
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/assignments/upcoming", tags=["Assignments"], summary="Get upcoming deadlines", operation_id="moodle_get_upcoming_assignments")
    def get_upcoming_assignments(days_ahead: int = Query(7, description="Days to check ahead")) -> List[Dict[str, Any]]:
        """Retrieves pending assignments due within the next N days."""
        try:
            return client.get_upcoming_assignments(days_ahead=days_ahead)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/assignments/{assignment_id}/status", tags=["Assignments"], summary="Get assignment submission status & feedback", operation_id="moodle_get_assignment_status")
    def get_assignment_status(assignment_id: int) -> Dict[str, Any]:
        """Retrieves submission details, feedback grade, comments, and uploaded files."""
        try:
            return client.get_assignment_status(assignment_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/v1/assignments/{assignment_id}/submit", tags=["Assignments"], summary="Submit solution or save draft", operation_id="moodle_submit_assignment")
    def submit_assignment(assignment_id: int, req: SubmitAssignmentRequest) -> Dict[str, Any]:
        """Uploads a file and/or enters online text for an assignment submission."""
        try:
            return client.submit_assignment(
                assign_id=assignment_id,
                file_path_or_bytes=req.file_path,
                filename=req.filename,
                online_text=req.online_text,
                submit_for_grading=req.submit_for_grading
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Quizzes & Calendar
    # ------------------------------------------
    @app.get("/api/v1/quizzes", tags=["Quizzes"], summary="List quizzes and exams", operation_id="moodle_get_quizzes")
    def get_quizzes(course_id: Optional[int] = Query(None, description="Course filter")) -> List[Dict[str, Any]]:
        """Retrieves course quizzes, open/close windows, and time limits."""
        try:
            return client.get_quizzes(course_id=course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/calendar/events", tags=["Calendar"], summary="Get upcoming academic events", operation_id="moodle_get_calendar_events")
    def get_calendar_events(days_ahead: int = Query(14, description="Days ahead to search")) -> List[Dict[str, Any]]:
        """Retrieves upcoming calendar events, exams, and deadlines."""
        try:
            return client.get_calendar_events(days_ahead=days_ahead)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Grades
    # ------------------------------------------
    @app.get("/api/v1/grades", tags=["Grades"], summary="Get student grades", operation_id="moodle_get_grades")
    def get_grades(course_id: Optional[int] = Query(None, description="Course filter")) -> List[Dict[str, Any]]:
        """Retrieves raw grades, max grades, percentages, and course totals."""
        try:
            return client.get_grades(course_id=course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/grades/summary", tags=["Grades"], summary="Get grade summary and GPA stats", operation_id="moodle_get_grades_summary")
    def get_grades_summary() -> List[Dict[str, Any]]:
        """Calculates course averages, graded item counts, and totals."""
        try:
            return client.get_grades_summary()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Files & Document Reader
    # ------------------------------------------
    @app.post("/api/v1/files/read", tags=["Files"], summary="In-memory document reader (PDF/TXT/HTML)", operation_id="moodle_read_file_content")
    def read_file_content(req: ReadFileRequest) -> Dict[str, Any]:
        """Downloads document into memory and parses text directly for LLM context."""
        try:
            return client.read_file_content(req.file_url, max_chars=req.max_chars)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/files/download", tags=["Files"], summary="Download file to disk", operation_id="moodle_download_file")
    def download_file(file_url: str = Query(..., description="Moodle file URL"), output_path: Optional[str] = Query(None, description="Destination directory")) -> Dict[str, Any]:
        """Downloads a course resource to local storage."""
        try:
            return client.download_file(file_url, output_path=output_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Meetings & Recordings
    # ------------------------------------------
    @app.get("/api/v1/meetings", tags=["Meetings"], summary="Discover live Zoom lecture links", operation_id="moodle_get_course_meetings")
    def get_course_meetings(course_id: Optional[int] = Query(None, description="Course filter")) -> List[Dict[str, Any]]:
        """Discovers recurring class sessions and Zoom links across courses."""
        try:
            return client.get_course_meetings(course_id=course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/v1/recordings", tags=["Recordings"], summary="List Panopto lecture videos", operation_id="moodle_get_recordings")
    def get_recordings(course_id: Optional[int] = Query(None, description="Course filter")) -> List[Dict[str, Any]]:
        """Lists Panopto lecture recordings and recitation (tirgul) videos."""
        try:
            return panopto.get_course_recordings(course_id=course_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ------------------------------------------
    # Global Search
    # ------------------------------------------
    @app.post("/api/v1/search", tags=["Search"], summary="Global search across all Moodle content", operation_id="moodle_search")
    def search_moodle(req: SearchRequest) -> Dict[str, Any]:
        """Performs global fuzzy/keyword search across courses, tasks, files, and lectures."""
        try:
            from moodle_mcp.tools.search_tools import register_search_tools
            # Use search logic
            q = req.query.lower().strip()
            types = [t.lower() for t in (req.search_types or ["courses", "assignments", "files", "meetings", "recordings"])]
            results: Dict[str, List[Any]] = {"courses": [], "assignments": [], "files": [], "meetings": [], "recordings": []}

            if "courses" in types:
                for c in client.get_enrolled_courses():
                    if q in c.get("fullname", "").lower() or q in c.get("display_name", "").lower():
                        results["courses"].append(c)

            if "assignments" in types:
                for a in client.get_assignments():
                    if q in a.get("name", "").lower() or q in a.get("course_name", "").lower():
                        results["assignments"].append(a)

            if "files" in types:
                for c in client.get_enrolled_courses():
                    for f in client.get_course_files(c["id"]):
                        if q in f.get("filename", "").lower():
                            results["files"].append(f)

            if "meetings" in types:
                for m in client.get_course_meetings():
                    if q in m.get("title", "").lower() or q in m.get("course_name", "").lower():
                        results["meetings"].append(m)

            if "recordings" in types:
                for r in panopto.get_course_recordings():
                    if q in r.get("lecture_title", "").lower():
                        results["recordings"].append(r)

            return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


def export_openapi_spec(output_dir: Optional[Path] = None) -> Path:
    """Exports the OpenAPI 3.1 schema to openapi.json and openapi.yaml."""
    app = create_app()
    spec = app.openapi()
    target_dir = output_dir or Path(__file__).resolve().parent

    json_path = target_dir / "openapi.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    logger.info(f"Exported OpenAPI JSON spec to {json_path}")

    # Also export YAML if PyYAML is installed
    try:
        import yaml
        yaml_path = target_dir / "openapi.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, sort_keys=False, allow_unicode=True)
        logger.info(f"Exported OpenAPI YAML spec to {yaml_path}")
    except ImportError:
        pass

    return json_path


def main() -> None:
    """CLI runner for OpenAPI REST server."""
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Moodle MCP OpenAPI Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--export-only", action="store_true", help="Export openapi.json and openapi.yaml and exit")
    parser.add_argument("--export-dir", default=None, help="Directory to export OpenAPI files to")

    args = parser.parse_args()

    if args.export_only or args.export_dir:
        exp_dir = Path(args.export_dir) if args.export_dir else _pkg_root
        exported = export_openapi_spec(exp_dir)
        print(f"[OK] OpenAPI spec successfully exported to {exported}")
        sys.exit(0)

    app = create_app()
    print(f"Starting Moodle OpenAPI Server on http://{args.host}:{args.port}")
    print(f"Swagger Documentation available at: http://{args.host}:{args.port}/docs")
    print(f"OpenAPI Specification available at: http://{args.host}:{args.port}/openapi.json")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
