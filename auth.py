"""
Authentication and session management for Moodle MCP.
Supports:
1. Zero-token TAU SSO automated session starting (Username + Password + Student ID)
2. Standard Moodle token.php login (Username + Password)
3. Direct Web Service token (wstoken)
4. Browser session cookie (MoodleSession)
5. Persistent local session caching
"""

import json
import logging
import os
import re
import html
from pathlib import Path
from typing import Any, Dict, Optional
import requests

from moodle_mcp.config import (
    MOODLE_URL,
    MOODLE_TOKEN,
    MOODLE_USERNAME,
    MOODLE_PASSWORD,
    MOODLE_STUDENT_ID,
    MOODLE_SESSION_COOKIE,
    SESSION_FILE,
    SESSION_DIR,
    USER_AGENT,
    sanitize_profile_name,
    get_profile_paths,
)

logger = logging.getLogger("moodle_mcp.auth")


class MoodleAuthError(Exception):
    """Raised when authentication with Moodle fails."""
    pass


class MoodleAuth:
    def __init__(
        self,
        moodle_url: Optional[str] = None,
        base_url: Optional[str] = None,
        profile: Optional[str] = None,
        session_file: Optional[Path] = None,
    ):
        self.moodle_url = (base_url or moodle_url or MOODLE_URL).rstrip("/")
        self.profile = sanitize_profile_name(profile)
        if session_file:
            self.session_file = Path(session_file)
        elif profile:
            self.session_file = get_profile_paths(self.profile)["session_file"]
        else:
            self.session_file = Path(os.getenv("MOODLE_SESSION_FILE", str(get_profile_paths(self.profile)["session_file"])))
        self.token: Optional[str] = None
        self.session: requests.Session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.sesskey: Optional[str] = None
        self.user_id: Optional[int] = None
        self.user_profile: Optional[Dict[str, Any]] = None
        self.auth_type: Optional[str] = None
        
        # Attempt to load persistent session on initialization
        self.load_cached_session()

    def _save_session(self) -> None:
        """Saves current authentication session to the profile's local cache."""
        if self.profile.startswith("oauth_") or self.profile == "stateless":
            return
        try:
            self.session_file.parent.mkdir(parents=True, exist_ok=True)
            cookies_dict = self.session.cookies.get_dict()
            payload = {
                "profile": self.profile,
                "moodle_url": self.moodle_url,
                "token": self.token,
                "sesskey": self.sesskey,
                "user_id": self.user_id,
                "user_profile": self.user_profile,
                "auth_type": self.auth_type,
                "cookies": cookies_dict
            }
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved Moodle session cache for profile '{self.profile}' to {self.session_file}")
        except Exception as e:
            logger.warning(f"Could not save session cache: {e}")

    def load_cached_session(self) -> bool:
        """Loads and validates a cached session from disk if available."""
        target_file = self.session_file
        if not target_file.exists():
            # Fallback to legacy root session.json if migrating a single-user setup
            legacy_file = SESSION_DIR / "session.json"
            if legacy_file.exists():
                try:
                    with open(legacy_file, "r", encoding="utf-8") as lf:
                        legacy_data = json.load(lf)
                    legacy_user = (legacy_data.get("user_profile") or {}).get("username", "")
                    if self.profile == "default" or (legacy_user and sanitize_profile_name(legacy_user) == self.profile):
                        target_file = legacy_file
                    else:
                        return False
                except Exception:
                    return False
            else:
                return False
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            cached_url = data.get("moodle_url", "").rstrip("/")
            if cached_url and self.moodle_url and cached_url.lower() != self.moodle_url.lower():
                # Cached session belongs to a different Moodle instance
                return False

            if not self.moodle_url and cached_url:
                self.moodle_url = cached_url

            self.token = data.get("token")
            self.sesskey = data.get("sesskey")
            self.user_id = data.get("user_id")
            self.user_profile = data.get("user_profile")
            self.auth_type = data.get("auth_type")
            
            cookies = data.get("cookies", {})
            for k, v in cookies.items():
                self.session.cookies.set(k, v)

            
            # Validate if token is present
            if self.token:
                try:
                    profile = self._fetch_site_info(self.token)
                    if profile and "userid" in profile:
                        self.user_profile = profile
                        self.user_id = profile["userid"]
                        logger.info(f"Loaded valid cached session for user ID {self.user_id}")
                        return True
                except Exception as e:
                    logger.debug(f"Cached token validation failed: {e}")
                    self.token = None

            # If cookies are present, check if session is active
            if cookies.get("MoodleSession"):
                try:
                    resp = self.session.get(f"{self.moodle_url}/my/", allow_redirects=True, timeout=10)
                    if resp.status_code == 200 and "Ecom_User_ID" not in resp.text and 'login/index.php' not in resp.url:
                        uid_match = re.search(r'"userid"\s*:\s*(\d+)', resp.text)
                        if uid_match and int(uid_match.group(1)) > 1:
                            self.user_id = int(uid_match.group(1))
                            logger.info(f"Loaded valid cached cookie session for user ID {self.user_id}")
                            return True
                except Exception as e:
                    logger.debug(f"Cached cookie validation failed: {e}")

            # Clear any stale fields if cache was invalid
            self.token = None
            self.user_id = None
            self.user_profile = None
            return False
        except Exception as e:
            logger.warning(f"Failed to read session cache: {e}")
            return False

    def logout(self) -> Dict[str, Any]:
        """Clears local session and deletes cache file."""
        self.token = None
        self.sesskey = None
        self.user_id = None
        self.user_profile = None
        self.auth_type = None
        self.session.cookies.clear()
        
        if self.session_file.exists():
            try:
                self.session_file.unlink()
            except Exception as e:
                logger.warning(f"Could not remove session file: {e}")
                
        return {"success": True, "profile": self.profile, "message": "Successfully logged out and cleared session cache."}

    def _fetch_site_info(self, token: str) -> Dict[str, Any]:
        """Calls core_webservice_get_site_info using wstoken."""
        endpoint = f"{self.moodle_url}/webservice/rest/server.php"
        params = {
            "wstoken": token,
            "wsfunction": "core_webservice_get_site_info",
            "moodlewsrestformat": "json"
        }
        res = self.session.get(endpoint, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        if isinstance(data, dict) and ("exception" in data or "errorcode" in data):
            raise MoodleAuthError(f"Moodle API Error ({data.get('errorcode')}): {data.get('message')}")
        return data

    def login_with_token(self, token: str, moodle_url: Optional[str] = None) -> Dict[str, Any]:
        """Authenticate directly using a Moodle Web Service token."""
        if moodle_url:
            self.moodle_url = moodle_url.rstrip("/")
        
        clean_token = token.strip()
        profile = self._fetch_site_info(clean_token)
        self.token = clean_token
        self.user_profile = profile
        self.user_id = profile.get("userid")
        self.auth_type = "token"
        self._save_session()
        
        return {
            "success": True,
            "auth_type": "token",
            "user_id": self.user_id,
            "username": profile.get("username"),
            "fullname": profile.get("fullname"),
            "sitename": profile.get("sitename")
        }

    def _extract_and_reset_mobile_token(self) -> Optional[str]:
        """
        Parses user/managetoken.php to locate the specific table row for
        'Moodle mobile web service' (or moodle_mobile_app), resets it with sesskey,
        and returns the active wstoken.
        """
        if not self.sesskey:
            return None
        try:
            manage_url = f"{self.moodle_url}/user/managetoken.php"
            manage_res = self.session.get(manage_url, allow_redirects=True, timeout=15)
            trs = manage_res.text.split("<tr")
            target_tr = None
            for tr in trs:
                if re.search(r"moodle\s+mobile\s+web\s+service|moodle_mobile_app", tr, re.IGNORECASE):
                    target_tr = tr
                    break

            if not target_tr:
                logger.debug("No row found matching 'moodle mobile web service' in managetoken.php")
                return None

            m = re.search(r'action=resetwstoken(?:&amp;|&)tokenid=(\d+)', target_tr)
            if not m:
                return None

            token_id = m.group(1)
            reset_res = self.session.post(
                manage_url,
                data={
                    "tokenid": token_id,
                    "action": "resetwstoken",
                    "confirm": "1",
                    "sesskey": self.sesskey
                },
                allow_redirects=True,
                timeout=15
            )
            final_token_match = re.search(r'id="copytoclipboardtoken"[^>]*>([^<]+)</div>', reset_res.text, re.IGNORECASE)
            if final_token_match:
                return final_token_match.group(1).strip()
        except Exception as e:
            logger.warning(f"Failed to extract and reset mobile token: {e}")
        return None

    def login_with_sso(
        self,
        username: str,
        password: str,
        student_id: Optional[str] = None,
        moodle_url: Optional[str] = None,
        id_number: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Starts a live Moodle session via TAU SSO authentication without requiring a master token.
        Automatically logs in, negotiates SAML assertions, extracts MoodleSession cookies and sesskey,
        and retrieves/refreshes the Web Service token from managetoken.php.
        """
        if moodle_url:
            self.moodle_url = moodle_url.rstrip("/")
            
        username = username.strip()
        password = password.strip()
        student_id = (student_id or id_number or "").strip()
        
        logger.info(f"Starting SSO session for user: {username[:2]}*** on {self.moodle_url}")
        
        # 1. Access login page
        login_url = f"{self.moodle_url}/login/index.php"
        res1 = self.session.get(login_url, allow_redirects=True, timeout=15)
        sso_url = res1.url

        # Check if already authenticated via valid session cookies
        if (sso_url.rstrip("/") == self.moodle_url or "/my" in sso_url) and "nidp.tau.ac.il" not in sso_url:
            sesskey_match = re.search(r'"sesskey":"([^"]+)"', res1.text)
            if sesskey_match:
                self.sesskey = sesskey_match.group(1)
            token = self._extract_and_reset_mobile_token()
            if token:
                self.token = token
                try:
                    profile = self._fetch_site_info(self.token)
                    self.user_profile = profile
                    self.user_id = profile.get("userid")
                except Exception:
                    pass
                self.auth_type = "sso"
                self._save_session()
                return {
                    "success": True,
                    "auth_type": "sso",
                    "token_available": True,
                    "user_id": self.user_id,
                    "username": self.user_profile.get("username") if self.user_profile else username,
                    "fullname": self.user_profile.get("fullname") if self.user_profile else username,
                    "sitename": self.user_profile.get("sitename") if self.user_profile else "Moodle"
                }

        # Otherwise, clear cookies to guarantee a clean SSO redirect to nidp.tau.ac.il
        if "nidp.tau.ac.il" not in sso_url:
            self.session.cookies.clear()
            res1 = self.session.get(login_url, allow_redirects=True, timeout=15)
            sso_url = res1.url

        if "/auth/saml2/login.php" in sso_url:
            res_saml = self.session.get(sso_url, allow_redirects=True, timeout=15)
            sso_url = res_saml.url

        # Check for intermediate SAML form
        form_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', res1.text, re.IGNORECASE)
        if form_match and "nidp.tau.ac.il" in res1.url:
            action = form_match.group(1)
            if not action.startswith("http"):
                action = requests.compat.urljoin("https://nidp.tau.ac.il", action)
            inputs = dict(re.findall(r'<input[^>]+name=["\']([^"\']+)["\'][^>]+value=["\']([^"\']*)["\']', res1.text, re.IGNORECASE))
            sso_url = action
            if inputs:
                self.session.post(action, data=inputs, timeout=15)

        # 2. Initiate login sequence
        self.session.post(
            sso_url,
            data="option=credential&initiateLoginSequence=true&isAjax=true",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )

        # 3. Submit credentials
        cred_data = {
            "option": "credential",
            "isAjax": "true",
            "Ecom_User_ID": username,
            "Ecom_User_Pid": student_id,
            "Ecom_Password": password
        }
        cred_res = self.session.post(
            sso_url,
            data=cred_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )

        if '"isError":true' in cred_res.text.replace(" ", ""):
            raise MoodleAuthError("Invalid username, student ID, or password during TAU SSO authentication.")

        # 4. Fetch SAML assertion page
        saml_page = self.session.get(sso_url, timeout=15)
        action_match = re.search(r'<form[^>]+action=["\']([^"\']+)["\']', saml_page.text, re.IGNORECASE)
        saml_match = re.search(r'<input[^>]+name=["\']SAMLResponse["\'][^>]+value=["\']([^"\']+)["\']', saml_page.text, re.IGNORECASE)

        if not action_match or not saml_match:
            raise MoodleAuthError("Failed to parse SAML response from SSO identity provider.")

        action_url = html.unescape(action_match.group(1))
        saml_response = html.unescape(saml_match.group(1))

        # 5. POST SAMLResponse back to Moodle
        moodle_res = self.session.post(
            action_url,
            data={"SAMLResponse": saml_response},
            allow_redirects=True,
            timeout=15
        )
        
        # Extract sesskey
        sesskey_match = re.search(r'"sesskey":"([^"]+)"', moodle_res.text)
        if sesskey_match:
            self.sesskey = sesskey_match.group(1)

        # 6. Retrieve Web Service token from managetoken.php
        extracted_token = self._extract_and_reset_mobile_token()

        if extracted_token:
            self.token = extracted_token
            try:
                self.user_profile = self._fetch_site_info(extracted_token)
                self.user_id = self.user_profile.get("userid")
            except Exception as e:
                logger.warning(f"Could not fetch site info via extracted token: {e}")

        # If token was not extractable, extract userid from landing page
        if not self.user_id:
            uid_match = re.search(r'"userid"\s*:\s*(\d+)', moodle_res.text) or re.search(r'data-userid="(\d+)"', moodle_res.text)
            if uid_match:
                self.user_id = int(uid_match.group(1))

        self.auth_type = "sso"
        self._save_session()


        
        return {
            "success": True,
            "auth_type": "sso",
            "token_available": bool(self.token),
            "user_id": self.user_id,
            "username": self.user_profile.get("username") if self.user_profile else username,
            "fullname": self.user_profile.get("fullname") if self.user_profile else username,
            "sitename": self.user_profile.get("sitename") if self.user_profile else "Moodle"
        }

    login_sso = login_with_sso

    def login_with_standard_credentials(
        self,
        username: str,
        password: str,
        service: str = "moodle_mobile_app",
        moodle_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Authenticate using standard Moodle /login/token.php."""
        if moodle_url:
            self.moodle_url = moodle_url.rstrip("/")
            
        token_url = f"{self.moodle_url}/login/token.php"
        params = {
            "username": username.strip(),
            "password": password.strip(),
            "service": service.strip()
        }
        res = self.session.post(token_url, data=params, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        if "error" in data:
            raise MoodleAuthError(f"Standard login failed: {data.get('error')}")
            
        token = data.get("token")
        if not token:
            raise MoodleAuthError(f"Failed to obtain token from {token_url}")
            
        return self.login_with_token(token)

    def login_with_cookie(self, cookie_string: str, moodle_url: Optional[str] = None) -> Dict[str, Any]:
        """Authenticate by providing a MoodleSession cookie directly."""
        if moodle_url:
            self.moodle_url = moodle_url.rstrip("/")
            
        clean_cookie = cookie_string.strip()
        if "MoodleSession=" in clean_cookie:
            val = clean_cookie.split("MoodleSession=")[1].split(";")[0].strip()
        else:
            val = clean_cookie
            
        self.session.cookies.set("MoodleSession", val)
        
        # Test session by loading /my/
        resp = self.session.get(f"{self.moodle_url}/my/", allow_redirects=True, timeout=15)
        if "Ecom_User_ID" in resp.text or 'login/index.php' in resp.url:
            raise MoodleAuthError("Provided session cookie is expired or invalid.")
            
        sesskey_match = re.search(r'"sesskey":"([^"]+)"', resp.text)
        if sesskey_match:
            self.sesskey = sesskey_match.group(1)
            
        uid_match = re.search(r'"userid"\s*:\s*(\d+)', resp.text)
        if uid_match:
            self.user_id = int(uid_match.group(1))

        self.auth_type = "cookie"
        
        # Try getting a token from managetoken.php if possible
        extracted_token = self._extract_and_reset_mobile_token()
        if extracted_token:
            self.token = extracted_token
            try:
                self.user_profile = self._fetch_site_info(self.token)
            except Exception as e:
                logger.debug(f"Could not fetch site info: {e}")


        self._save_session()
        
        return {
            "success": True,
            "auth_type": "cookie",
            "token_available": bool(self.token),
            "user_id": self.user_id,
            "moodle_url": self.moodle_url
        }

    def is_authenticated(self) -> bool:
        """Returns True if the client has an active authenticated session."""
        return self.ensure_authenticated()

    def ensure_authenticated(self, force_refresh: bool = False) -> bool:
        """
        Ensures an active session exists.
        If already authenticated and not forcing refresh, returns True.
        Else attempts cached session, direct MOODLE_TOKEN, or SSO credentials from environment.
        """
        if not force_refresh and ((self.token and self.user_id) or (self.session.cookies.get("MoodleSession") and self.user_id)):
            return True

        if force_refresh:
            self.token = None
            self.sesskey = None
            self.user_id = None
            self.user_profile = None

        if not force_refresh and self.load_cached_session():
            return True

        # Check instance-stored SSO credentials (e.g. from decrypted OAuth session)
        if getattr(self, "_sso_username", None) and getattr(self, "_sso_password", None):
            try:
                self.login_with_sso(
                    self._sso_username,
                    self._sso_password,
                    getattr(self, "_sso_student_id", None)
                )
                return True
            except Exception as e:
                logger.warning(f"Failed to auto-relogin with instance SSO credentials: {e}")

        prof_prefix = f"{self.profile.upper()}_MOODLE" if self.profile != "default" else ""
        prof_suffix = f"MOODLE_{self.profile.upper()}" if self.profile != "default" else ""

        # Check environment for direct token
        token = (
            (os.getenv(f"{prof_prefix}_TOKEN") or os.getenv(f"{prof_suffix}_TOKEN"))
            if prof_prefix else None
        ) or (MOODLE_TOKEN if self.profile == "default" else None) or os.getenv("MOODLE_TOKEN")
        if token:
            try:
                self.login_with_token(token)
                return True
            except Exception as e:
                logger.warning(f"Failed to login with token for profile '{self.profile}': {e}")

        # Check environment for cookie
        cookie = (
            (os.getenv(f"{prof_prefix}_SESSION_COOKIE") or os.getenv(f"{prof_suffix}_SESSION_COOKIE"))
            if prof_prefix else None
        ) or (MOODLE_SESSION_COOKIE if self.profile == "default" else None) or os.getenv("MOODLE_SESSION_COOKIE")
        if cookie:
            try:
                self.login_with_cookie(cookie)
                return True
            except Exception as e:
                logger.warning(f"Failed to login with cookie for profile '{self.profile}': {e}")

        # Check environment for SSO credentials
        username = (
            (os.getenv(f"{prof_prefix}_USERNAME") or os.getenv(f"{prof_suffix}_USERNAME"))
            if prof_prefix else None
        ) or (MOODLE_USERNAME if self.profile == "default" else None) or os.getenv("MOODLE_TESTING_USERNAME")

        password = (
            (os.getenv(f"{prof_prefix}_PASSWORD") or os.getenv(f"{prof_suffix}_PASSWORD"))
            if prof_prefix else None
        ) or (MOODLE_PASSWORD if self.profile == "default" else None) or os.getenv("MOODLE_TESTING_PASSWORD")

        student_id = (
            (os.getenv(f"{prof_prefix}_STUDENT_ID") or os.getenv(f"{prof_suffix}_STUDENT_ID"))
            if prof_prefix else None
        ) or (MOODLE_STUDENT_ID if self.profile == "default" else None) or os.getenv("MOODLE_TESTING_ID")

        if username and password:
            try:
                self.login_with_sso(username, password, student_id)
                return True
            except Exception as e:
                logger.warning(f"Failed to auto-login with SSO credentials for profile '{self.profile}': {e}")

        return False

    def is_authenticated(self) -> bool:
        """Alias for ensure_authenticated."""
        return self.ensure_authenticated()

    def login_sso(
        self,
        username: str,
        password: str,
        id_number: Optional[str] = None,
        moodle_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Alias for login_with_sso accepting id_number."""
        return self.login_with_sso(username=username, password=password, student_id=id_number, moodle_url=moodle_url)

    def get_status(self) -> Dict[str, Any]:
        """Returns current authentication status and user details."""
        is_auth = self.ensure_authenticated()
        return {
            "authenticated": is_auth,
            "profile": self.profile,
            "session_file": str(self.session_file),
            "moodle_url": self.moodle_url,
            "auth_type": self.auth_type,
            "has_token": bool(self.token),
            "has_session_cookie": bool(self.session.cookies.get("MoodleSession")),
            "user_id": self.user_id,
            "user_profile": self.user_profile
        }

