#!/usr/bin/env python3
"""
Inspect and debug Moodle Web Service tokens in /user/managetoken.php.

Useful for diagnosing permissions, missing tokens, and discovering
which services are configured on the Moodle instance.
"""

import os
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

# Fix Windows console UTF-8 encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure moodle_mcp package is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.config import Config


def main():
    print("=" * 65)
    print("Moodle /user/managetoken.php Token Inspector & Diagnostic Tool")
    print("=" * 65)

    auth = MoodleAuth(base_url=Config.BASE_URL)

    if not auth.is_authenticated() or not auth.session.cookies.get("MoodleSession"):
        print("\nNo cached session cookies found. Performing SSO login...")
        username = Config.USERNAME or os.environ.get("MOODLE_USERNAME")
        password = Config.PASSWORD or os.environ.get("MOODLE_PASSWORD")
        id_number = Config.ID_NUMBER or os.environ.get("MOODLE_ID_NUMBER")

        if not username or not password:
            username = input("Enter TAU Username: ").strip()
            import getpass
            password = getpass.getpass("Enter TAU Password: ").strip()
            id_number = input("Enter ID Number (optional): ").strip() or None

        auth.login_sso(username=username, password=password, id_number=id_number)

    print(f"\nTarget Moodle: {auth.moodle_url}")
    print(f"Requesting: {auth.moodle_url}/user/managetoken.php...")

    http_session = auth.session

    resp = http_session.get(f"{Config.BASE_URL}/user/managetoken.php", allow_redirects=True)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch managetoken.php: HTTP {resp.status_code}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        print("[WARNING] No <table> found on managetoken.php. Response preview:")
        print(resp.text[:500])
        sys.exit(1)

    print(f"\nDiscovered {len(tables)} tables on page.\n")

    # Extract sesskey
    sesskey_match = re.search(r'sesskey["\']?\s*[:=]\s*["\']([a-zA-Z0-9]+)["\']', resp.text)
    sesskey = sesskey_match.group(1) if sesskey_match else "Unknown"
    print(f"User Sesskey: {sesskey}\n")

    for i, table in enumerate(tables, 1):
        print(f"--- Table #{i} ---")
        rows = table.find_all("tr")
        for row in rows:
            cells = [c.get_text(strip=True) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            
            # Check for reset link
            reset_link = row.find("a", href=re.compile(r"action=resetwstoken"))
            reset_url = reset_link["href"] if reset_link else "None"
            
            row_text = " | ".join(cells)
            is_mobile = bool(re.search(r"moodle\s+mobile\s+web\s+service|moodle_mobile_app", row_text, re.I))
            
            marker = " [PRIMARY MOBILE WS]" if is_mobile else ""
            print(f"  {row_text}{marker}")
            if reset_url != "None":
                print(f"    Reset URL: {reset_url}")

    print("\n" + "=" * 65)
    print("Done inspecting tokens.")


if __name__ == "__main__":
    main()
