# AI Client Integration Guide for `moodle_mcp`

This guide explains how to connect `moodle_mcp` to various AI assistants, IDEs, and agentic platforms.

---

## 1. Claude Desktop

Edit your Claude Desktop configuration file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Add `moodle` to `mcpServers`:

```json
{
  "mcpServers": {
    "moodle": {
      "command": "python",
      "args": ["-m", "moodle_mcp"],
      "cwd": "D:\\ProgramFiles\\Projects\\random_stuff\\moodle_mcp",
      "env": {
        "MOODLE_USERNAME": "your_username",
        "MOODLE_PASSWORD": "your_password",
        "MOODLE_ID_NUMBER": "your_id_number"
      }
    }
  }
}
```

---

## 2. Cursor IDE

In Cursor IDE, open your project settings or create `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "moodle": {
      "command": "python",
      "args": ["-m", "moodle_mcp"],
      "cwd": "D:/ProgramFiles/Projects/random_stuff/moodle_mcp"
    }
  }
}
```

---

## 3. Google Antigravity

In Antigravity, add to your MCP server registry (`~/.gemini/antigravity/mcp/moodle_mcp`):

```json
{
  "name": "moodle_mcp",
  "command": "python",
  "args": ["-m", "moodle_mcp"],
  "cwd": "D:/ProgramFiles/Projects/random_stuff/moodle_mcp",
  "transport": "stdio"
}
```

---

## 4. Cline / Roo-Code (VS Code Extension)

In VS Code with Cline installed, click the MCP icon in Cline settings, or edit `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`:

```json
{
  "mcpServers": {
    "moodle": {
      "command": "python",
      "args": ["-m", "moodle_mcp"],
      "cwd": "D:/ProgramFiles/Projects/random_stuff/moodle_mcp",
      "autoApprove": [
        "moodle_get_status",
        "moodle_get_user_profile",
        "moodle_get_enrolled_courses",
        "moodle_get_course_contents",
        "moodle_get_assignments",
        "moodle_get_upcoming_assignments",
        "moodle_get_assignment_status",
        "moodle_get_grades",
        "moodle_get_course_files",
        "moodle_read_file_content",
        "moodle_get_course_meetings",
        "moodle_search"
      ]
    }
  }
}
```

---

## 5. SSE Remote Agent Configuration (FastAPI / LangChain)

If you are running `moodle_mcp` on a remote server or in Docker:

1. Launch server with SSE:
   ```bash
   python -m moodle_mcp --transport sse --port 8000 --host 0.0.0.0
   ```

2. Connect via LangChain:
   ```python
   from langchain_mcp_adapters.client import MultiServerMCPClient

   client = MultiServerMCPClient()
   await client.connect_to_server("moodle", url="http://localhost:8000/sse")
   tools = client.get_tools()
   ```
