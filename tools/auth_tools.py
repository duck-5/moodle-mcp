"""
Authentication and status MCP tools.
"""

from typing import Any, Dict, Optional
from moodle_mcp.client import MoodleClient


def register_auth_tools(server: Any, client: MoodleClient) -> None:
    @server.tool()
    def moodle_login(
        auth_type: str = "sso",
        username: Optional[str] = None,
        password: Optional[str] = None,
        student_id: Optional[str] = None,
        token: Optional[str] = None,
        session_cookie: Optional[str] = None,
        moodle_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate with Moodle and start an active session.
        
        Args:
            auth_type: The authentication mode:
                - 'sso': Zero-token university SSO login using username, password, and student_id.
                - 'token': Direct Web Service wstoken (master token).
                - 'cookie': Browser MoodleSession cookie string.
                - 'standard': Standard Moodle login via /login/token.php (username + password).
            username: SSO or Moodle username (required for 'sso' and 'standard').
            password: Password (required for 'sso' and 'standard').
            student_id: Israeli ID / Student ID number (required for TAU SSO).
            token: Moodle Web Service token (required for 'token').
            session_cookie: MoodleSession cookie value (required for 'cookie').
            moodle_url: Base Moodle URL (e.g. 'https://moodle.tau.ac.il'). Defaults to configured URL.
        """
        if auth_type == "token":
            if not token:
                raise ValueError("Must provide 'token' for token authentication.")
            return client.auth.login_with_token(token, moodle_url)

        elif auth_type == "cookie":
            if not session_cookie:
                raise ValueError("Must provide 'session_cookie' for cookie authentication.")
            return client.auth.login_with_cookie(session_cookie, moodle_url)

        elif auth_type == "standard":
            if not username or not password:
                raise ValueError("Must provide 'username' and 'password' for standard credentials login.")
            return client.auth.login_with_standard_credentials(username, password, moodle_url=moodle_url)

        elif auth_type == "sso":
            if not username or not password:
                raise ValueError("Must provide 'username' and 'password' for SSO authentication.")
            return client.auth.login_with_sso(username, password, student_id, moodle_url=moodle_url)

        else:
            raise ValueError(f"Unknown auth_type '{auth_type}'. Supported: 'sso', 'token', 'cookie', 'standard'.")

    @server.tool()
    def moodle_logout() -> Dict[str, Any]:
        """
        Terminates the active Moodle session and deletes cached session credentials.
        """
        return client.auth.logout()

    @server.tool()
    def moodle_get_status() -> Dict[str, Any]:
        """
        Checks the current authentication status, active user profile, and session validity.
        """
        return client.auth.get_status()

    @server.tool()
    def moodle_get_user_profile() -> Dict[str, Any]:
        """
        Retrieves full profile details of the currently logged-in Moodle student.
        """
        return client.get_site_info()
