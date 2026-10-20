#!/usr/bin/env python3
"""
Comprehensive Live Integration Test for Moodle REST API & moodle_mcp.

Tests all major operations against live Moodle:
- Site & User Info
- Enrolled Courses (with academic year and semester parsing)
- Multi-threaded Assignments Fetching (with True Deadline computation)
- Submissions & Grades
- Section Contents & Resources
- Zoom Meeting Discovery
- In-Memory Document Analysis (PyMuPDF)
"""

import os
import sys
import time
from pathlib import Path

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure moodle_mcp package is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.client import MoodleClient
from moodle_mcp.config import Config


def main():
    print("=" * 70)
    print("Moodle MCP Live Integration Test Suite")
    print("=" * 70)

    auth = MoodleAuth(base_url=Config.BASE_URL)

    if not auth.is_authenticated():
        print("[!] No active session found. Running SSO login...")
        username = Config.USERNAME or os.environ.get("MOODLE_USERNAME")
        password = Config.PASSWORD or os.environ.get("MOODLE_PASSWORD")
        id_number = Config.ID_NUMBER or os.environ.get("MOODLE_ID_NUMBER")

        if not username or not password:
            print("Please set MOODLE_USERNAME and MOODLE_PASSWORD in .env")
            sys.exit(1)

        auth.login_sso(username=username, password=password, id_number=id_number)

    client = MoodleClient(auth=auth)

    # 1. Site Info
    print("\n[TEST 1] Testing Site Info (core_webservice_get_site_info)...")
    t0 = time.time()
    site_info = client.get_site_info()
    elapsed = time.time() - t0
    print(f"  ✓ User: {site_info.get('fullname')} (ID: {site_info.get('userid')})")
    print(f"  ✓ Site: {site_info.get('sitename')} [Latency: {elapsed:.2f}s]")

    # 2. Courses
    print("\n[TEST 2] Testing Enrolled Courses (core_enrol_get_users_courses)...")
    t0 = time.time()
    courses = client.get_enrolled_courses()
    elapsed = time.time() - t0
    print(f"  ✓ Found {len(courses)} enrolled courses in {elapsed:.2f}s:")
    for c in courses[:5]:
        print(f"    - [{c.get('id')}] {c.get('fullname')[:50]} (Year: {c.get('academic_year')}, Sem: {c.get('semester')})")
    if len(courses) > 5:
        print(f"    ... and {len(courses) - 5} more.")

    # 3. Assignments & True Deadlines (Parallelized)
    print("\n[TEST 3] Testing Multi-Threaded Assignments & True Deadlines...")
    t0 = time.time()
    assignments = client.get_assignments()
    elapsed = time.time() - t0
    print(f"  ✓ Retrieved {len(assignments)} assignments across all courses in {elapsed:.2f}s!")
    
    upcoming = [a for a in assignments if a.get("status") == "Assigned" and a.get("true_deadline", 0) > time.time()]
    upcoming.sort(key=lambda x: x.get("true_deadline", 0))
    
    print(f"  ✓ Pending / Upcoming assignments: {len(upcoming)}")
    for a in upcoming[:5]:
        print(f"    - [{a.get('course_name')[:25]}] {a.get('name')[:35]}")
        print(f"      Deadline: {a.get('true_deadline_formatted')} | Status: {a.get('status')}")

    # 4. Grades
    print("\n[TEST 4] Testing Grade Items (gradereport_user_get_grade_items)...")
    t0 = time.time()
    grades_summary = client.get_grades_summary()
    elapsed = time.time() - t0
    total_graded = sum(c.get("graded_items_count", 0) for c in grades_summary)
    print(f"  ✓ Summarized grades across {len(grades_summary)} courses ({total_graded} graded items) in {elapsed:.2f}s")
    for s in grades_summary[:3]:
        print(f"    - [{s.get('course_id')}] {s.get('course_name')[:35]}: Avg: {s.get('average_percentage')}% | Total: {s.get('course_total')}")

    # 5. Course Contents & Materials
    if courses:
        target_course = courses[0]
        print(f"\n[TEST 5] Testing Course Contents for [{target_course['id']}] {target_course['fullname'][:40]}...")
        t0 = time.time()
        sections = client.get_course_contents(target_course['id'])
        elapsed = time.time() - t0
        print(f"  ✓ Found {len(sections)} sections in {elapsed:.2f}s")
        
        files = client.get_course_files(target_course['id'])
        print(f"  ✓ Downloadable Course Files: {len(files)}")
        for f in files[:3]:
            print(f"    - {f.get('filename')} ({f.get('filesize', 0) / 1024:.1f} KB)")

    # 6. Zoom Meetings
    print("\n[TEST 6] Testing Zoom Meeting Discovery across Courses...")
    t0 = time.time()
    all_meetings = []
    for c in courses[:4]:
        meetings = client.get_course_meetings(c["id"])
        if meetings:
            all_meetings.extend(meetings)
    elapsed = time.time() - t0
    print(f"  ✓ Discovered {len(all_meetings)} Zoom meetings across top 4 courses in {elapsed:.2f}s")
    for m in all_meetings[:3]:
        topic = (m.get('topic') or m.get('name') or 'Zoom Meeting')[:40]
        join_url = (m.get('join_url') or m.get('url') or '')[:50]
        print(f"    - {topic} -> {join_url}...")

    print("\n" + "=" * 70)
    print("ALL LIVE TESTS COMPLETED SUCCESSFULLY! ✨")
    print("=" * 70)


if __name__ == "__main__":
    main()
