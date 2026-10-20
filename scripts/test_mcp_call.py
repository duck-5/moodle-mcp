import anyio
import json
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

async def main():
    async with streamable_http_client("http://localhost:8000/yuval/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Session initialized successfully!")
            
            # 1. Enrolled courses
            res_courses = await session.call_tool("moodle_get_enrolled_courses", arguments={})
            assert len(res_courses.content) == 1, f"Expected 1 content block, got {len(res_courses.content)}"
            courses = json.loads(res_courses.content[0].text)
            print(f"moodle_get_enrolled_courses returned {len(courses)} courses in content[0]!")

            # 2. Upcoming assignments
            res_up = await session.call_tool("moodle_get_upcoming_assignments", arguments={})
            assert len(res_up.content) == 1, f"Expected 1 content block, got {len(res_up.content)}"
            up = json.loads(res_up.content[0].text)
            print(f"moodle_get_upcoming_assignments returned {len(up)} items in content[0]!")

            # 3. Grades summary
            res_grades = await session.call_tool("moodle_get_grades_summary", arguments={})
            assert len(res_grades.content) == 1, f"Expected 1 content block, got {len(res_grades.content)}"
            grades = json.loads(res_grades.content[0].text)
            print(f"moodle_get_grades_summary returned {len(grades)} items in content[0]!")

            # 4. Calendar events
            res_cal = await session.call_tool("moodle_get_calendar_events", arguments={})
            assert len(res_cal.content) == 1, f"Expected 1 content block, got {len(res_cal.content)}"
            cal = json.loads(res_cal.content[0].text)
            print(f"moodle_get_calendar_events returned {len(cal)} items in content[0]!")

            # 5. Quizzes
            res_quiz = await session.call_tool("moodle_get_quizzes", arguments={})
            assert len(res_quiz.content) == 1, f"Expected 1 content block, got {len(res_quiz.content)}"
            quiz = json.loads(res_quiz.content[0].text)
            print(f"moodle_get_quizzes returned {len(quiz)} items in content[0]!")

            print("\nALL MCP TOOLS RETURNING LISTS PROVEN TO RETURN EXACTLY 1 CONTENT BLOCK WITH FULL DATA!")

anyio.run(main)
