# `moodle_mcp` Architecture & Design

`moodle_mcp` is a Model Context Protocol (MCP) server that connects Large Language Model (LLM) agents, copilots, and AI providers directly to Tel Aviv University's Moodle learning management system.

---

## 1. System Architecture

```mermaid
graph TD
    Client[AI Client: Claude Desktop / Cursor / Antigravity / Cline] -->|stdio or SSE / JSON-RPC| Server[server.py - MCPServer / FastMCP]
    
    subgraph moodle_mcp Server
        Server --> Router[Tools & Resources Dispatcher]
        Router --> AuthTools[tools/auth_tools.py]
        Router --> CourseTools[tools/courses_tools.py]
        Router --> AssignTools[tools/assignments_tools.py]
        Router --> GradeTools[tools/grades_tools.py]
        Router --> FileTools[tools/files_tools.py]
        Router --> MeetingTools[tools/meetings_tools.py]
        Router --> RecTools[tools/recordings_tools.py]
        Router --> SearchTools[tools/search_tools.py]
        
        AuthTools & CourseTools & AssignTools & GradeTools & FileTools & MeetingTools & SearchTools --> ClientEngine[client.py - MoodleClient]
        AuthTools --> AuthEngine[auth.py - MoodleAuth]
        RecTools --> PanoptoEngine[panopto.py - PanoptoScraper]
        
        AuthEngine --> Cache[(~/.moodle_mcp/session.json)]
    end

    AuthEngine -->|Zero-Token SAML Handshake| SSO[TAU SSO nidp.tau.ac.il]
    AuthEngine -->|Scrape/Reset wstoken| MoodleWeb[moodle.tau.ac.il/user/managetoken.php]
    ClientEngine -->|Parallel REST Calls (ThreadPoolExecutor)| MoodleWS[moodle.tau.ac.il/webservice/rest/server.php]
    ClientEngine -->|In-Memory PyMuPDF Document Reader| MoodleFiles[moodle.tau.ac.il/pluginfile.php]
```

---

## 2. Key Modules & Responsibilities

### `server.py`
- Initializes the MCP server using `FastMCP` (with fallback to `MCPServer` depending on `mcp` library version).
- Registers all 18 tools, 4 dynamic resources, and 2 prompt templates.
- Provides CLI entry point with flags:
  - `--status`: Check connection state and current user without starting stdio server.
  - `--login-sso`: Run interactive/automated SSO login.
  - `--transport stdio|sse`: Select communication transport.
  - `--port`: Port for SSE transport (default: 8000).

### `auth.py`
- Implements the complete SAML 2.0 WebSSO handshake against `nidp.tau.ac.il`.
- Implements `/user/managetoken.php` parsing, isolating `Moodle mobile web service` from auxiliary tokens, and resetting `wstoken`.
- Manages session lifecycle and serialization to `~/.moodle_mcp/session.json`.

### `client.py`
- Parallelized Moodle REST client.
- Uses `concurrent.futures.ThreadPoolExecutor(max_workers=8)` to query assignments and grades across dozens of courses concurrently (reducing query latency from 40+ seconds to ~2 seconds).
- Computes True Deadlines ($\max(\text{due}, \text{cutoff}, \text{extension})$).
- Parses documents directly in-memory using PyMuPDF (`fitz`) and BeautifulSoup without writing temporary files to disk.

### `tools/`
Modular tool definitions registered with the MCP server:
1. `auth_tools.py`: `moodle_login`, `moodle_logout`, `moodle_get_status`, `moodle_get_user_profile`.
2. `courses_tools.py`: `moodle_get_enrolled_courses`, `moodle_get_course_contents`.
3. `assignments_tools.py`: `moodle_get_assignments`, `moodle_get_upcoming_assignments`, `moodle_get_assignment_status`, `moodle_submit_assignment`.
4. `grades_tools.py`: `moodle_get_grades`, `moodle_get_grades_summary`.
5. `files_tools.py`: `moodle_get_course_files`, `moodle_download_file`, `moodle_read_file_content`.
6. `meetings_tools.py`: `moodle_get_course_meetings`.
7. `recordings_tools.py`: `moodle_get_recordings`.
8. `search_tools.py`: `moodle_search`.

---

## 3. Resources & Prompts

### Dynamic Resources
- `moodle://profile`: Summary of the student's identity, email, and campus metadata.
- `moodle://courses`: JSON representation of all currently enrolled courses.
- `moodle://upcoming`: List of assignments due in the next 7 days.
- `moodle://grades`: GPA breakdown and graded assignment scores.

### Prompt Templates
- `study_briefing`: Generates a prioritized executive briefing of upcoming tasks, meetings, and deadlines.
- `assignment_analysis`: Performs deep AI analysis of an assignment handout, extracting key deliverables and breaking them into actionable milestones.
