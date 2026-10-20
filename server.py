"""
Moodle MCP Server entry point.
Exposes Moodle tools, resources, and prompts to AI assistants via Model Context Protocol (MCP).
Supports stdio, SSE, streamable-http transports, as well as OpenAPI REST gateway mode.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Tuple

# Ensure package directory is always on sys.path
_pkg_parent = str(Path(__file__).resolve().parent.parent)
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

# Compatibility across MCP v1 and v2
try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        raise ImportError("The 'mcp' package is required. Install it with: pip install mcp")

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager
from moodle_mcp.tools import register_all_tools

logger = logging.getLogger("moodle_mcp")


def create_server() -> Tuple[Any, Any, Any]:
    """Initializes and configures the Moodle MCP server."""
    server = MCPServer(
        name="moodle_mcp"
    )

    auth = MoodleAuth()
    client = MoodleClient(auth=auth)
    panopto = PanoptoManager(moodle_client=client)

    # Register all tools (courses, assignments, grades, files, meetings, recordings, quizzes, calendar, forums, participants, search)
    register_all_tools(server, client, panopto)

    # Register MCP Resources
    @server.resource("moodle://profile")
    def get_profile_resource() -> str:
        """User profile and Moodle connection state."""
        info = client.get_site_info()
        return json.dumps(info, indent=2, ensure_ascii=False)

    @server.resource("moodle://courses")
    def get_courses_resource() -> str:
        """List of currently enrolled Moodle courses."""
        courses = client.get_enrolled_courses()
        return json.dumps(courses, indent=2, ensure_ascii=False)

    @server.resource("moodle://upcoming")
    def get_upcoming_resource() -> str:
        """Upcoming assignments due in the next 7 days."""
        upcoming = client.get_upcoming_assignments(days_ahead=7)
        return json.dumps(upcoming, indent=2, ensure_ascii=False)

    @server.resource("moodle://grades")
    def get_grades_resource() -> str:
        """Current course grade summary and GPAs."""
        summary = client.get_grades_summary()
        return json.dumps(summary, indent=2, ensure_ascii=False)

    @server.resource("moodle://quizzes")
    def get_quizzes_resource() -> str:
        """Active and upcoming quizzes and tests."""
        quizzes = client.get_quizzes()
        return json.dumps(quizzes, indent=2, ensure_ascii=False)

    @server.resource("moodle://calendar")
    def get_calendar_resource() -> str:
        """Academic calendar events for the next 14 days."""
        events = client.get_calendar_events(days_ahead=14)
        return json.dumps(events, indent=2, ensure_ascii=False)

    @server.resource("moodle://announcements")
    def get_announcements_resource() -> str:
        """Recent course announcements and forum updates."""
        announcements = client.get_course_announcements()
        return json.dumps(announcements, indent=2, ensure_ascii=False)

    @server.resource("moodle://saved")
    def get_saved_data_resource() -> str:
        """List of all named saved items and metadata in persistent storage."""
        items = client.data_store.list_keys()
        return json.dumps(items, indent=2, ensure_ascii=False)

    @server.resource("moodle://cache")
    def get_cache_status_resource() -> str:
        """Current status and statistics of the local API response cache."""
        stats = client.cache.get_stats()
        return json.dumps(stats, indent=2, ensure_ascii=False)

    # Register MCP Prompts
    @server.prompt()
    def study_briefing() -> str:
        """
        Prompt template to summarize enrolled courses, upcoming deadlines, and study priorities.
        """
        return (
            "You are an academic study assistant connected to my university Moodle account. "
            "Please call `moodle_get_enrolled_courses` and `moodle_get_upcoming_assignments` "
            "to summarize what courses I am taking this semester, list my upcoming deadlines in chronological order, "
            "and suggest study priorities for the coming days."
        )

    @server.prompt()
    def assignment_analysis(assignment_id: int) -> str:
        """
        Prompt template to deeply analyze a specific assignment's requirements and guide preparation.
        """
        return (
            f"Please inspect assignment {assignment_id} using `moodle_get_assignment_status`. "
            "If there are any instruction attachments, use `moodle_read_file_content` to read them, "
            "and provide a clear breakdown of requirements, rubric, deadline, and recommended steps to complete it."
        )

    @server.prompt()
    def exam_preparation(course_id: int) -> str:
        """
        Prompt template to organize revision, past materials, and announcements for an upcoming exam.
        """
        return (
            f"Please inspect course {course_id} using `moodle_get_course_contents`, "
            "`moodle_get_quizzes`, and `moodle_get_course_announcements`. "
            "Identify exam dates, relevant lecture slides/recitations, and summarize key topics to study."
        )

    return server, client, panopto


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Moodle MCP Server — Connect AI assistants to Moodle")

    parser.add_argument(
        "--mode",
        choices=["mcp", "openapi"],
        default="mcp",
        help="Server mode: 'mcp' (standard MCP server) or 'openapi' (FastAPI REST server compliant with OpenAPI 3.1)"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport protocol (default: stdio)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE, streamable-http, or OpenAPI server (default: 8000)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind for HTTP/SSE/OpenAPI servers (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check and print current authentication status and exit"
    )
    parser.add_argument(
        "--login-sso",
        action="store_true",
        help="Run interactive SSO login and save session"
    )
    parser.add_argument(
        "--export-openapi",
        nargs="?",
        const=".",
        default=None,
        help="Export OpenAPI 3.1 schema (openapi.json and openapi.yaml) to directory and exit"
    )

    args = parser.parse_args()

    # Handle OpenAPI export
    if args.export_openapi is not None:
        from moodle_mcp.openapi_server import export_openapi_spec
        out_dir = Path(args.export_openapi).resolve()
        json_file = export_openapi_spec(out_dir)
        print(f"[OK] Exported OpenAPI specification to {json_file}")
        sys.exit(0)

    # Handle OpenAPI server mode
    if args.mode == "openapi":
        import uvicorn
        from moodle_mcp.openapi_server import create_app
        print(f"Starting Moodle OpenAPI Server on http://{args.host}:{args.port}")
        print(f"Interactive Swagger UI: http://{args.host}:{args.port}/docs")
        print(f"OpenAPI Specification: http://{args.host}:{args.port}/openapi.json")
        uvicorn.run(create_app(), host=args.host, port=args.port)
        sys.exit(0)

    server, client, _ = create_server()

    if args.status:
        status_info = client.auth.get_status()
        print(json.dumps(status_info, indent=2, ensure_ascii=False))
        sys.exit(0)

    if args.login_sso:
        import getpass
        print("=== Moodle MCP — Interactive SSO Session Login ===")
        user = input("SSO Username: ").strip()
        student_id = input("Student ID (Israeli ID): ").strip()
        pwd = getpass.getpass("Password: ").strip()
        url = input("Moodle URL [https://moodle.tau.ac.il]: ").strip() or "https://moodle.tau.ac.il"

        try:
            res = client.auth.login_with_sso(user, pwd, student_id, moodle_url=url)
            print("\n[SUCCESS] Session created and saved!")
            print(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"\n[ERROR] Login failed: {e}")
            sys.exit(1)
        sys.exit(0)

    # Configure logging
    if args.transport == "stdio":
        # Direct all logs to stderr so stdout remains clean for MCP JSON-RPC protocol
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)
        server.run(transport="stdio")
    elif args.transport == "streamable-http":
        logging.basicConfig(level=logging.INFO)
        server.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        logging.basicConfig(level=logging.INFO)
        server.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
