#!/usr/bin/env python3
"""
TAU SSO SAML 2.0 WebSSO & Token Scraping Test Script.

Validates the full zero-token authentication sequence:
1. Negotiates the SAML handshake with nidp.tau.ac.il.
2. Extracts MoodleSession cookie.
3. Navigates to /user/managetoken.php.
4. Locates the 'Moodle mobile web service' table row and extracts/resets wstoken.
5. Validates wstoken via core_webservice_get_site_info.
"""

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
    print("=" * 60)
    print("Tel Aviv University Moodle SSO Authentication Test")
    print("=" * 60)

    username = Config.USERNAME or os.environ.get("MOODLE_USERNAME")
    password = Config.PASSWORD or os.environ.get("MOODLE_PASSWORD")
    id_number = Config.ID_NUMBER or os.environ.get("MOODLE_ID_NUMBER")

    if not username or not password:
        print("\nCredentials not found in environment or .env file.")
        username = input("Enter TAU Username: ").strip()
        import getpass
        password = getpass.getpass("Enter TAU Password: ").strip()
        id_number = input("Enter Israeli ID Number (optional, press Enter if not needed): ").strip() or None

    print(f"\n[1] Initiating SSO Handshake for user '{username}'...")
    auth = MoodleAuth(base_url=Config.BASE_URL)
    
    try:
        res = auth.login_sso(
            username=username,
            password=password,
            id_number=id_number
        )
        print("  -> SSO Handshake SUCCESSFUL!")
        print(f"  -> User ID: {auth.user_id}")
        print(f"  -> Full Name: {auth.user_profile.get('fullname') if auth.user_profile else 'Unknown'}")
        if auth.token:
            print(f"  -> Web Service Token: {auth.token[:6]}...{auth.token[-6:]}")
        print(f"  -> Session Cookies: {list(auth.session.cookies.get_dict().keys())}")
        print(f"  -> Sesskey: {auth.sesskey}")

        print("\n[2] Validating Web Service Token against core_webservice_get_site_info...")
        client = MoodleClient(auth=auth)
        site_info = client.get_site_info()
        print(f"  -> Site Name: {site_info.get('sitename')}")
        print(f"  -> Release: {site_info.get('release')}")
        print(f"  -> Moodle Version: {site_info.get('version')}")

        print("\n[3] Session saved to cache successfully.")
        print(f"  -> Cache path: ~/.moodle_mcp/session.json")
        print("\nALL SSO & TOKEN VERIFICATION CHECKS PASSED! 🎉")

    except Exception as e:
        print(f"\n[ERROR] Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
