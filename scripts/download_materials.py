#!/usr/bin/env python3
"""
CLI Helper to download course materials, slides, and assignment files locally.

Usage:
  python download_materials.py --course-id 12345 --output-dir ./downloads
  python download_materials.py --assignment-id 6789 --output-dir ./downloads
"""

import argparse
import os
import sys
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
    parser = argparse.ArgumentParser(description="Download Moodle Course Materials & Files")
    parser.add_argument("--course-id", type=int, help="Moodle Course ID to download materials for")
    parser.add_argument("--assignment-id", type=int, help="Moodle Assignment ID to download instructions/attachments for")
    parser.add_argument("--output-dir", type=str, default="./downloads", help="Directory to save downloaded files")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of files to download (default: 10)")
    args = parser.parse_args()

    if not args.course_id and not args.assignment_id:
        parser.print_help()
        print("\n[!] Please specify either --course-id or --assignment-id.")
        sys.exit(1)

    auth = MoodleAuth(base_url=Config.BASE_URL)
    session = auth.get_session()

    if not session or not session.token:
        print("[!] No active session found. Running SSO login...")
        username = Config.USERNAME or os.environ.get("MOODLE_USERNAME")
        password = Config.PASSWORD or os.environ.get("MOODLE_PASSWORD")
        id_number = Config.ID_NUMBER or os.environ.get("MOODLE_ID_NUMBER")

        if not username or not password:
            print("[ERROR] Credentials not configured in .env")
            sys.exit(1)

        session = auth.login_sso(username=username, password=password, id_number=id_number)

    client = MoodleClient(
        base_url=session.base_url,
        token=session.token,
        cookies=session.cookies,
        sesskey=session.sesskey
    )

    out_path = Path(args.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if args.course_id:
        print(f"Fetching materials for Course ID {args.course_id}...")
        files = client.get_course_files(args.course_id)
        if not files:
            print("No downloadable files found in this course.")
            return

        print(f"Found {len(files)} files. Downloading up to {args.limit} files to {out_path.resolve()}...\n")
        downloaded = 0
        for f in files[:args.limit]:
            fname = f.get("filename")
            furl = f.get("fileurl")
            dest = out_path / fname
            print(f"  [{downloaded + 1}/{min(len(files), args.limit)}] Downloading: {fname}...")
            try:
                client.download_file(furl, str(dest))
                size_kb = dest.stat().st_size / 1024
                print(f"    ✓ Saved: {dest.name} ({size_kb:.1f} KB)")
                downloaded += 1
            except Exception as e:
                print(f"    ✗ Failed to download {fname}: {e}")

        print(f"\nCompleted! Downloaded {downloaded} files to {out_path.resolve()}.")

    elif args.assignment_id:
        print(f"Fetching status & attachments for Assignment ID {args.assignment_id}...")
        status = client.get_assignment_status(args.assignment_id)
        sub_files = status.get("submission_files", [])
        if not sub_files:
            print("No submission attachments found for this assignment.")
            return

        for sf in sub_files:
            fname = sf.get("filename")
            furl = sf.get("fileurl")
            dest = out_path / fname
            print(f"Downloading submission file: {fname}...")
            try:
                client.download_file(furl, str(dest))
                print(f"  ✓ Saved to {dest.resolve()}")
            except Exception as e:
                print(f"  ✗ Error: {e}")


if __name__ == "__main__":
    main()
