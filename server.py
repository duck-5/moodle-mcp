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
from typing import Any, Optional, Tuple

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


def patch_mcp_list_serialization() -> None:
    """
    Ensures that MCPServer / FastMCP serializes list tool outputs into a single TextContent block.
    By default, FastMCP decomposes a Python list into individual TextContent blocks (one per item).
    Many MCP clients (notably Google Gemini Web) only read content[0], causing tools returning lists
    (e.g., enrolled courses, assignments, grades summary, calendar events) to display only the first item.
    """
    import pydantic_core
    from mcp.types import ContentBlock, TextContent

    modules = []
    try:
        import mcp.server.mcpserver.utilities.func_metadata as fm2
        modules.append(fm2)
    except ImportError:
        pass

    try:
        import mcp.server.fastmcp.utilities.func_metadata as fm1
        modules.append(fm1)
    except ImportError:
        pass

    try:
        import mcp.server.fastmcp.tools.base as tb1
        modules.append(tb1)
    except ImportError:
        pass

    for mod in modules:
        if hasattr(mod, "_convert_to_content"):
            orig = getattr(mod, "_convert_to_content")
            if getattr(orig, "_is_single_block_patched", False):
                continue

            img_cls = getattr(mod, "Image", None)
            aud_cls = getattr(mod, "Audio", None)

            def make_patched(original_func, img_t, aud_t):
                def patched(result):
                    if result is None:
                        return []
                    if isinstance(result, ContentBlock):
                        return [result]
                    if img_t and isinstance(result, img_t):
                        return [result.to_image_content()]
                    if aud_t and isinstance(result, aud_t):
                        return [result.to_audio_content()]
                    if isinstance(result, (list, tuple)):
                        if len(result) == 0:
                            return [TextContent(type="text", text="[]")]
                        special_types = [ContentBlock]
                        if img_t:
                            special_types.append(img_t)
                        if aud_t:
                            special_types.append(aud_t)
                        special_tuple = tuple(special_types)
                        if all(isinstance(x, special_tuple) for x in result):
                            return original_func(result)
                        text = pydantic_core.to_json(result, fallback=str, indent=2).decode("utf-8")
                        return [TextContent(type="text", text=text)]
                    return original_func(result)

                patched._is_single_block_patched = True
                return patched

            setattr(mod, "_convert_to_content", make_patched(orig, img_cls, aud_cls))


# Apply list serialization patch immediately on import
patch_mcp_list_serialization()

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.client import MoodleClient
from moodle_mcp.panopto import PanoptoManager
from moodle_mcp.tools import register_all_tools

logger = logging.getLogger("moodle_mcp")


def create_server(profile: Optional[str] = None) -> Tuple[Any, Any, Any]:
    """Initializes and configures the Moodle MCP server for a specific user profile."""
    prof_name = profile or "default"
    server = MCPServer(
        name=f"moodle_mcp_{prof_name}" if prof_name != "default" else "moodle_mcp"
    )

    # Automatically annotate tools with MCP read_only_hint / destructive_hint
    # so clients (Gemini, Claude, Cursor) know which tools can be safely auto-approved.
    orig_add_tool = getattr(server, "add_tool", None)
    if callable(orig_add_tool):
        def add_tool_with_annotations(fn: Any, *args: Any, **kwargs: Any) -> Any:
            if kwargs.get("annotations") is None:
                fn_name = kwargs.get("name") or getattr(fn, "__name__", "")
                read_only_prefixes = ("moodle_get_", "moodle_search", "moodle_read_", "moodle_list_", "moodle_load_")
                destructive_prefixes = ("moodle_delete_", "moodle_clear_")
                try:
                    from mcp.types import ToolAnnotations
                    if fn_name.startswith(destructive_prefixes):
                        kwargs["annotations"] = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False)
                    elif fn_name.startswith(read_only_prefixes):
                        kwargs["annotations"] = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True)
                    else:
                        kwargs["annotations"] = ToolAnnotations(read_only_hint=False, destructive_hint=False)
                except Exception:
                    pass
            return orig_add_tool(fn, *args, **kwargs)

        server.add_tool = add_tool_with_annotations

    auth = MoodleAuth(profile=profile)
    client = MoodleClient(auth=auth, profile=profile)
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


def run_streamable_http_server(server: Any, host: str = "0.0.0.0", port: int = 8000) -> None:
    """
    Runs the multi-profile Streamable HTTP server configured for reverse proxies,
    web browsers, and cloud tunnels (e.g. Cloudflare Tunnel at moodle-mcp.mantin.dev).
    Provides:
    - Default profile on / and /mcp
    - Dedicated profile routes on /{profile} and /{profile}/mcp (e.g. /yuval, /yaeli)
    - Full CORS headers and health checks
    """
    import anyio
    import uvicorn
    from contextlib import asynccontextmanager, AsyncExitStack
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.responses import JSONResponse, RedirectResponse
    from starlette.routing import Route, Mount
    from mcp.server.transport_security import TransportSecuritySettings
    from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
    from moodle_mcp.config import get_configured_profiles, sanitize_profile_name

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
        allowed_hosts=["*"],
        allowed_origins=["*"]
    )

    profiles = get_configured_profiles()
    if "default" not in profiles:
        profiles.append("default")

    session_managers = []
    routes = []

    def make_profile_app(prof_name: str, prof_server: Any) -> Starlette:
        async def prof_info(req: Any) -> JSONResponse:
            return JSONResponse({
                "service": "moodle_mcp",
                "profile": prof_name,
                "version": "1.1.0",
                "protocol": "Model Context Protocol (Streamable HTTP)",
                "endpoints": {
                    "mcp": f"/{prof_name}/mcp" if prof_name != "default" else "/mcp",
                    "health": "/health"
                },
                "status": "online"
            })

        custom_routes = [
            Route("/mcp", endpoint=prof_info, methods=["GET"]),
            Route("/", endpoint=prof_info, methods=["GET"]),
        ]

        app = prof_server._lowlevel_server.streamable_http_app(
            streamable_http_path="/mcp",
            host=host,
            transport_security=security,
            custom_starlette_routes=custom_routes,
        )

        prof_mgr = prof_server._lowlevel_server._session_manager
        if prof_mgr:
            session_managers.append(prof_mgr)
            app.routes.append(Route("/", endpoint=StreamableHTTPASGIApp(prof_mgr), methods=["POST"]))
            app.routes.append(Route("/mcp", endpoint=StreamableHTTPASGIApp(prof_mgr), methods=["POST"]))

        return app

    # Build default app using the passed server
    default_app = make_profile_app("default", server)

    # Health check endpoint
    async def health(req: Any) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "service": "moodle-mcp-multi-profile",
            "profiles": [p for p in profiles if p != "default"],
            "transport": "streamable-http"
        })

    routes.append(Route("/health", health, methods=["GET"]))

    # Build and mount all other discovered profiles
    for prof in profiles:
        if prof == "default":
            continue
        p_server, _, _ = create_server(profile=prof)
        p_app = make_profile_app(prof, p_server)
        routes.append(Mount(f"/{prof}", p_app))
        routes.append(Mount(f"/u/{prof}", p_app))
        routes.append(Route(f"/{prof}", lambda req, p=prof: RedirectResponse(f"/{p}/")))
        routes.append(Route(f"/u/{prof}", lambda req, p=prof: RedirectResponse(f"/u/{p}/")))

    # Mount default app at root (must be last)
    routes.append(Mount("/", default_app))

    @asynccontextmanager
    async def lifespan(app: Starlette):
        async with AsyncExitStack() as stack:
            for mgr in session_managers:
                await stack.enter_async_context(mgr.run())
            yield

    master_app = Starlette(routes=routes, lifespan=lifespan)
    master_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )

    print(f"🚀 Starting Moodle MCP Multi-Profile Server on http://{host}:{port}")
    print(f"   Default Endpoint: http://{host}:{port}/mcp (or root /)")
    for prof in profiles:
        if prof != "default":
            print(f"   Profile '{prof}': http://{host}:{port}/{prof}/mcp (or /{prof})")
    print(f"   Health Check: http://{host}:{port}/health")

    config = uvicorn.Config(master_app, host=host, port=port, log_level="info")
    uv_server = uvicorn.Server(config)
    anyio.run(uv_server.serve)


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
        choices=["mcp", "openapi", "gemini"],
        default="mcp",
        help="Server mode: 'mcp' (standard MCP server), 'openapi' (FastAPI REST server compliant with OpenAPI 3.1), or 'gemini' (Gemini AI agent with Moodle tools)"
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Prompt query for Gemini mode (runs single question and exits)"
    )
    parser.add_argument(
        "--gemini-model",
        type=str,
        default=None,
        help="Model name for Gemini agent (default: gemini-2.5-flash or $GEMINI_MODEL)"
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

    # Handle Gemini mode
    if args.mode == "gemini":
        try:
            from moodle_mcp.gemini_client import MoodleGeminiAgent
        except ImportError:
            from gemini_client import MoodleGeminiAgent
        agent = MoodleGeminiAgent(model_name=args.gemini_model)
        if args.prompt:
            res = agent.query_once(args.prompt)
            print(res)
        else:
            agent.run_chat()
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
        run_streamable_http_server(server, host=args.host, port=args.port)
    else:
        logging.basicConfig(level=logging.INFO)
        server.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
