"""
Gemini AI Client for Moodle MCP.
Connects Google Gemini (via official google-genai SDK or direct REST API)
to your Moodle LMS tools using function calling.

Enables asking Gemini questions about courses, deadlines, grades, quizzes,
and study materials, with Gemini dynamically invoking Moodle tools.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Ensure package directory is always on sys.path
_pkg_root = Path(__file__).resolve().parent
if str(_pkg_root) not in sys.path:
    sys.path.insert(0, str(_pkg_root))
if str(_pkg_root.parent) not in sys.path:
    sys.path.insert(0, str(_pkg_root.parent))

# Robust import pattern (works installed or standalone)
try:
    from moodle_mcp.client import MoodleClient
    from moodle_mcp.auth import MoodleAuth
    from moodle_mcp.panopto import PanoptoManager
except ImportError:
    from client import MoodleClient
    from auth import MoodleAuth
    from panopto import PanoptoManager

logger = logging.getLogger("moodle_mcp.gemini")

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def find_gemini_api_key() -> Optional[str]:
    """
    Finds Gemini API key from environment or multiple .env locations.
    """
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()

    search_paths = [
        Path.cwd() / ".env",
        _pkg_root / ".env",
        Path.home() / ".moodle_mcp" / ".env",
        _pkg_root.parent / "infrastructure" / ".env",
    ]

    for p in search_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except Exception:
                pass

    return None


class MoodleGeminiAgent:
    """
    Agent connecting Google Gemini to Moodle tools.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[MoodleClient] = None,
    ):
        self.api_key = api_key or find_gemini_api_key()
        self.model_name = model_name or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        
        if client is None:
            auth = MoodleAuth()
            self.client = MoodleClient(auth=auth)
        else:
            self.client = client

        self.panopto = PanoptoManager(moodle_client=self.client)
        self._init_tools()

    def _init_tools(self) -> None:
        """
        Builds the tool dictionary and callables available to Gemini.
        """
        c = self.client
        p = self.panopto

        def moodle_get_enrolled_courses(semester: str = "", refresh: bool = False) -> str:
            """
            Retrieves all courses the user is currently enrolled in, including course IDs,
            course codes, names, semester breakdowns, and course links.
            
            Args:
                semester: Optional semester filter (e.g. 'Semester A', 'Semester B', 'Yearly').
                refresh: If True, fetches live data bypassing the cache.
            """
            courses = c.get_enrolled_courses(refresh=refresh)
            if semester:
                courses = [x for x in courses if semester.lower() in x.get("semester", "").lower()]
            return json.dumps(courses, ensure_ascii=False, indent=2)

        def moodle_get_upcoming_assignments(days_ahead: int = 14, refresh: bool = False) -> str:
            """
            Retrieves pending assignments due within the next specified number of days (default 14 days),
            including course names, assignment titles, deadlines, remaining time, and submission status.
            
            Args:
                days_ahead: Number of days ahead to search (default 14).
                refresh: If True, forces fresh fetch from Moodle.
            """
            upcoming = c.get_upcoming_assignments(days_ahead=days_ahead, refresh=refresh)
            return json.dumps(upcoming, ensure_ascii=False, indent=2)

        def moodle_get_course_assignments(course_id: int, refresh: bool = False) -> str:
            """
            Retrieves all assignments for a specific course with due dates, cut-off dates,
            and submission status.
            
            Args:
                course_id: The integer Moodle course ID (e.g. 12345).
                refresh: If True, bypasses cache.
            """
            assignments = c.get_assignments(course_id=course_id, refresh=refresh)
            return json.dumps(assignments, ensure_ascii=False, indent=2)

        def moodle_get_assignment_status(assignment_id: int) -> str:
            """
            Retrieves detailed submission status, instructions, grading rubric, extension dates,
            and attached files for a single assignment.
            
            Args:
                assignment_id: The Moodle assignment ID.
            """
            status = c.get_assignment_status(assignment_id=assignment_id)
            return json.dumps(status, ensure_ascii=False, indent=2)

        def moodle_get_course_contents(course_id: int, refresh: bool = False) -> str:
            """
            Retrieves the full syllabus and structure of a course, listing modules, sections,
            lecture notes, file downloads, links, and quizzes.
            
            Args:
                course_id: The integer Moodle course ID.
                refresh: If True, fetches live data.
            """
            contents = c.get_course_contents(course_id=course_id, refresh=refresh)
            return json.dumps(contents, ensure_ascii=False, indent=2)

        def moodle_get_grades_summary(refresh: bool = False) -> str:
            """
            Retrieves the grades summary across all enrolled courses, including current grade
            percentages, letter grades, and rank when available.
            
            Args:
                refresh: If True, fetches fresh grades from Moodle.
            """
            summary = c.get_grades_summary(refresh=refresh)
            return json.dumps(summary, ensure_ascii=False, indent=2)

        def moodle_get_course_grades(course_id: int, refresh: bool = False) -> str:
            """
            Retrieves specific itemized grades, weights, and instructor feedback for a specific course.
            
            Args:
                course_id: The Moodle course ID.
                refresh: If True, fetches fresh grades.
            """
            grades = c.get_course_grades(course_id=course_id, refresh=refresh)
            return json.dumps(grades, ensure_ascii=False, indent=2)

        def moodle_get_quizzes(course_id: int = 0, refresh: bool = False) -> str:
            """
            Retrieves upcoming or past quizzes and online tests, including open/close dates and time limits.
            
            Args:
                course_id: Optional course ID filter (0 for all courses).
                refresh: If True, fetches fresh data.
            """
            cid = course_id if course_id > 0 else None
            quizzes = c.get_quizzes(course_id=cid, refresh=refresh)
            return json.dumps(quizzes, ensure_ascii=False, indent=2)

        def moodle_get_calendar_events(days_ahead: int = 14, refresh: bool = False) -> str:
            """
            Retrieves calendar events, deadlines, and schedule notices for the specified period.
            
            Args:
                days_ahead: Number of days ahead (default: 14).
                refresh: If True, bypasses cache.
            """
            events = c.get_calendar_events(days_ahead=days_ahead, refresh=refresh)
            return json.dumps(events, ensure_ascii=False, indent=2)

        def moodle_get_course_announcements(course_id: int = 0, limit: int = 10) -> str:
            """
            Retrieves latest forum announcements and messages posted by lecturers and TAs.
            
            Args:
                course_id: Course ID (0 for all courses).
                limit: Maximum number of announcements to return.
            """
            cid = course_id if course_id > 0 else None
            announcements = c.get_course_announcements(course_id=cid, limit=limit)
            return json.dumps(announcements, ensure_ascii=False, indent=2)

        def moodle_read_file_content(file_url: str, max_chars: int = 10000) -> str:
            """
            Reads and extracts plain text from a Moodle file attachment (PDF, DOCX, TXT, code).
            
            Args:
                file_url: Full URL of the file from Moodle.
                max_chars: Maximum characters to return (default: 10000).
            """
            content = c.read_file_content(file_url=file_url, max_chars=max_chars)
            return json.dumps({"content": content}, ensure_ascii=False)

        def moodle_search(query: str) -> str:
            """
            Searches across all courses, assignments, downloadable files, and lecture recordings.
            
            Args:
                query: Search query text (e.g. 'assignment 2', 'exam', 'fourier').
            """
            results = c.search(query=query)
            return json.dumps(results, ensure_ascii=False, indent=2)

        def moodle_search_recordings(query: str, folder_name: str = "") -> str:
            """
            Searches Panopto video recordings and lectures by title or transcription.
            
            Args:
                query: Search keyword.
                folder_name: Optional folder/course name filter.
            """
            recs = p.search_recordings(query=query, folder_name=folder_name or None)
            return json.dumps(recs, ensure_ascii=False, indent=2)

        self.tool_functions: List[Callable[..., Any]] = [
            moodle_get_enrolled_courses,
            moodle_get_upcoming_assignments,
            moodle_get_course_assignments,
            moodle_get_assignment_status,
            moodle_get_course_contents,
            moodle_get_grades_summary,
            moodle_get_course_grades,
            moodle_get_quizzes,
            moodle_get_calendar_events,
            moodle_get_course_announcements,
            moodle_read_file_content,
            moodle_search,
            moodle_search_recordings,
        ]

        self.tool_map: Dict[str, Callable[..., Any]] = {
            fn.__name__: fn for fn in self.tool_functions
        }

    def _get_system_instruction(self) -> str:
        return (
            "You are an expert academic assistant connected directly to the user's Moodle LMS. "
            "You have access to tools that fetch live information on enrolled courses, upcoming assignments, "
            "grades, quizzes, lecture recordings, syllabus contents, and announcements.\n\n"
            "Key instructions:\n"
            "1. When asked about deadlines, upcoming work, or courses, ALWAYS invoke the corresponding Moodle tool "
            "to retrieve fresh and accurate information.\n"
            "2. Group assignments clearly by urgency and course. Emphasize imminent deadlines.\n"
            "3. Format all responses cleanly using Markdown lists and tables.\n"
            "4. If an assignment has attached instructions or rubric, offer to read them with `moodle_read_file_content`.\n"
            "5. Answer in the language the user addresses you in (Hebrew or English)."
        )

    def run_chat(self) -> None:
        """
        Starts an interactive CLI chat session with Gemini.
        """
        if not self.api_key:
            print("\n" + "=" * 60)
            print("❌ GEMINI_API_KEY NOT FOUND")
            print("=" * 60)
            print("Please set your Gemini API key in an environment variable or .env file:")
            print("  export GEMINI_API_KEY='AIzaSy...'")
            print("You can get a free Gemini API key from:")
            print("  https://aistudio.google.com/app/apikey")
            print("=" * 60 + "\n")
            return

        print("\n" + "=" * 60)
        print(f"🎓 Moodle Gemini Assistant — Active (Model: {self.model_name})")
        print("Connected to Moodle instance:", self.client.auth.moodle_url)
        print("Type your questions below. Type 'exit' or 'quit' to end.")
        print("=" * 60 + "\n")

        # Try Google GenAI SDK
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            chat = client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=self._get_system_instruction(),
                    tools=self.tool_functions,
                    temperature=0.2,
                )
            )

            while True:
                try:
                    user_input = input("\n👤 You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("Goodbye!")
                    break
                if user_input.lower() == "clear":
                    os.system("clear" if os.name == "posix" else "cls")
                    continue

                print("\n🤖 Gemini is thinking...\n")
                try:
                    response = chat.send_message(user_input)
                    print(response.text)
                except Exception as e:
                    print(f"❌ Error during request: {e}")

        except ImportError:
            # Fallback to direct requests-based loop if google-genai package is not present
            print("Notice: 'google-genai' SDK not found, using direct API caller...")
            self._run_chat_direct_api()

    def query_once(self, prompt: str) -> str:
        """
        Sends a single prompt to Gemini with Moodle tools and returns the text response.
        """
        if not self.api_key:
            return (
                "Error: GEMINI_API_KEY is not set. "
                "Please configure GEMINI_API_KEY in your environment or .env file."
            )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            chat = client.chats.create(
                model=self.model_name,
                config=types.GenerateContentConfig(
                    system_instruction=self._get_system_instruction(),
                    tools=self.tool_functions,
                    temperature=0.2,
                )
            )
            response = chat.send_message(prompt)
            return response.text or ""
        except Exception as e:
            return f"Error executing Gemini query: {e}"

    def _run_chat_direct_api(self) -> None:
        """
        Direct REST fallback implementation for Gemini API.
        """
        import requests
        print("Direct API fallback active.")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        while True:
            try:
                user_input = input("\n👤 You: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_input or user_input.lower() in ("exit", "quit"):
                break
            
            payload = {
                "contents": [{"parts": [{"text": user_input}]}],
                "systemInstruction": {"parts": [{"text": self._get_system_instruction()}]}
            }
            try:
                r = requests.post(url, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                print(f"\n🤖 Gemini: {text}")
            except Exception as e:
                print(f"❌ API Error: {e}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Moodle MCP Gemini Client")
    parser.add_argument("--prompt", "-p", type=str, help="Single query prompt to run and exit")
    parser.add_argument("--model", "-m", type=str, default=DEFAULT_MODEL, help="Gemini model name")
    args = parser.parse_args()

    agent = MoodleGeminiAgent(model_name=args.model)

    if args.prompt:
        res = agent.query_once(args.prompt)
        print(res)
    else:
        agent.run_chat()


if __name__ == "__main__":
    main()
