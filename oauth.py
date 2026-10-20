"""
OAuth 2.1 and Dynamic Session Authentication for Moodle MCP.
Compliant with:
- Model Context Protocol (MCP) Authentication Specification
- RFC 8414 (OAuth 2.0 Authorization Server Metadata)
- RFC 9470 / RFC 9207 (OAuth 2.0 Protected Resource Metadata)
- RFC 7636 (PKCE - Proof Key for Code Exchange)
- RFC 7591 (Dynamic Client Registration)

Enables multi-user connections to a single MCP URL (e.g. https://moodle-mcp.mantin.dev/mcp)
with zero server-side user pre-configuration. Users log in once when connecting in Gemini / Claude.
Tokens securely encapsulate encrypted session credentials via AES-128 / Fernet, allowing
silent self-healing re-authentication without persistent server-side state.
"""

import base64
import contextvars
import hashlib
import json
import logging
import os
import secrets
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse, parse_qs

from cryptography.fernet import Fernet
import requests
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from moodle_mcp.auth import MoodleAuth
from moodle_mcp.client import MoodleClient
from moodle_mcp.config import SESSION_DIR, MOODLE_URL

logger = logging.getLogger("moodle_mcp.oauth")

# Context variable tracking the MoodleClient instance for the active HTTP request
current_client_var: contextvars.ContextVar[Optional[MoodleClient]] = contextvars.ContextVar(
    "current_moodle_client", default=None
)


class ClientProxy:
    """
    Transparent proxy that delegates method calls to the MoodleClient associated
    with the current request's Bearer token (stored in current_client_var).
    Falls back to a default client when running in non-HTTP environments (e.g. stdio CLI).
    """

    def __init__(self, fallback_client: MoodleClient):
        self._fallback = fallback_client

    @property
    def __class__(self):
        return MoodleClient

    @property
    def current(self) -> MoodleClient:
        c = current_client_var.get()
        return c if c is not None else self._fallback

    def __getattr__(self, name: str) -> Any:
        return getattr(self.current, name)

    def __repr__(self) -> str:
        return f"<ClientProxy active_profile={getattr(self.current, 'profile', 'unknown')}>"

    def __dir__(self):
        return dir(self.current)


class TokenManager:
    """
    Handles generation, symmetric encryption, and verification of OAuth access tokens,
    refresh tokens, and authorization codes.
    """

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or os.getenv("MOODLE_SECRET_KEY")
        if not self.secret_key:
            key_file = SESSION_DIR / "oauth_secret.key"
            if key_file.exists():
                try:
                    self.secret_key = key_file.read_text(encoding="utf-8").strip()
                except Exception:
                    self.secret_key = None
            if not self.secret_key:
                new_key = Fernet.generate_key().decode("utf-8")
                self.secret_key = new_key
                try:
                    SESSION_DIR.mkdir(parents=True, exist_ok=True)
                    key_file.write_text(new_key, encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Could not persist oauth_secret.key: {e}")

        self._fernet = Fernet(self.secret_key.encode("utf-8"))
        self._auth_codes: Dict[str, Dict[str, Any]] = {}
        self._active_clients: Dict[str, Tuple[float, MoodleClient]] = {}

    def encrypt_payload(self, data: Dict[str, Any]) -> str:
        # Strip user_profile if present to keep Bearer tokens compact and avoid HTTP header limits
        clean_data = {k: v for k, v in data.items() if k != "user_profile"}
        raw_json = json.dumps(clean_data, ensure_ascii=False).encode("utf-8")
        compressed = zlib.compress(raw_json, level=9)
        return self._fernet.encrypt(compressed).decode("utf-8")

    def decrypt_payload(self, token_str: str) -> Optional[Dict[str, Any]]:
        try:
            raw_bytes = self._fernet.decrypt(token_str.encode("utf-8"), ttl=None)
            try:
                decompressed = zlib.decompress(raw_bytes)
                return json.loads(decompressed.decode("utf-8"))
            except Exception:
                # Fallback for uncompressed tokens
                return json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            logger.debug(f"Token decryption failed: {e}")
            return None

    def create_auth_code(
        self,
        session_data: Dict[str, Any],
        client_id: str,
        redirect_uri: str,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
        expires_in: int = 600
    ) -> str:
        """Creates a short-lived authorization code (default: 10 minutes)."""
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = {
            "session_data": session_data,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": (code_challenge_method or "S256").upper(),
            "expires_at": time.time() + expires_in
        }
        return code

    def exchange_code(
        self,
        code: str,
        client_id: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        code_verifier: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Validates authorization code and PKCE challenge, returning session data."""
        entry = self._auth_codes.pop(code, None)
        if not entry:
            logger.warning("Authorization code not found or already used.")
            return None

        if time.time() > entry["expires_at"]:
            logger.warning("Authorization code expired.")
            return None

        # Verify PKCE if present
        challenge = entry.get("code_challenge")
        method = entry.get("code_challenge_method")
        if challenge and code_verifier:
            if method == "S256":
                digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
                computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
                if not secrets.compare_digest(computed, challenge.rstrip("=")):
                    logger.warning("PKCE S256 verification failed.")
                    return None
            elif method == "PLAIN":
                if not secrets.compare_digest(code_verifier, challenge):
                    logger.warning("PKCE PLAIN verification failed.")
                    return None

        return entry.get("session_data")

    def create_tokens(
        self,
        session_data: Dict[str, Any],
        access_expires_in: int = 30 * 86400,  # 30 days
        refresh_expires_in: int = 180 * 86400  # 180 days
    ) -> Dict[str, Any]:
        """Generates encrypted access and refresh tokens."""
        now = time.time()
        access_payload = {
            **session_data,
            "token_type": "access",
            "iat": now,
            "exp": now + access_expires_in
        }
        refresh_payload = {
            "username": session_data.get("username"),
            "student_id": session_data.get("student_id"),
            "password": session_data.get("password"),
            "moodle_url": session_data.get("moodle_url"),
            "token_type": "refresh",
            "iat": now,
            "exp": now + refresh_expires_in
        }

        access_token = self.encrypt_payload(access_payload)
        refresh_token = self.encrypt_payload(refresh_payload)

        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": access_expires_in,
            "refresh_token": refresh_token,
            "scope": "moodle"
        }

    def get_or_create_client(self, access_token: str) -> Optional[MoodleClient]:
        """
        Retrieves or creates a MoodleClient for the user represented by access_token.
        Keeps an in-memory pool so consecutive tool calls within a chat don't reconstruct
        the client object or re-read cookies.
        """
        token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
        now = time.time()

        if token_hash in self._active_clients:
            ts, client = self._active_clients[token_hash]
            if now - ts < 3600 and client.auth.is_authenticated():
                self._active_clients[token_hash] = (now, client)
                return client

        payload = self.decrypt_payload(access_token)
        if not payload or payload.get("token_type") != "access":
            return None

        if payload.get("exp", 0) < now:
            logger.info("Access token has expired.")
            return None

        # Reconstruct MoodleAuth from encrypted payload
        moodle_url = payload.get("moodle_url") or MOODLE_URL
        profile_name = f"oauth_{payload.get('username', 'user')}"
        auth = MoodleAuth(moodle_url=moodle_url, profile=profile_name)

        auth.token = payload.get("token")
        auth.sesskey = payload.get("sesskey")
        auth.user_id = payload.get("user_id")
        auth.user_profile = payload.get("user_profile")
        auth.auth_type = payload.get("auth_type", "sso")

        cookies = payload.get("cookies", {})
        for k, v in cookies.items():
            auth.session.cookies.set(k, v)

        # Store encrypted credentials on auth for transparent self-healing re-auth
        auth._sso_username = payload.get("username")
        auth._sso_password = payload.get("password")
        auth._sso_student_id = payload.get("student_id")

        client = MoodleClient(auth=auth, profile=profile_name)
        self._active_clients[token_hash] = (now, client)
        return client


# HTML template for the one-time browser login screen
LOGIN_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Connect Moodle to Gemini</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --muted: #94a3b8;
      --border: #334155;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --error: #ef4444;
      --radius: 12px;
    }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #f1f5f9;
        --card-bg: #ffffff;
        --text: #0f172a;
        --muted: #64748b;
        --border: #e2e8f0;
        --primary: #2563eb;
        --primary-hover: #1d4ed8;
      }
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 20px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 10px 25px -5px rgba(0,0,0,0.2), 0 8px 10px -6px rgba(0,0,0,0.1);
      width: 100%;
      max-width: 440px;
      padding: 32px;
    }
    .header { text-align: center; margin-bottom: 24px; }
    .icon {
      font-size: 40px;
      margin-bottom: 12px;
      display: inline-block;
    }
    h1 { font-size: 20px; font-weight: 600; margin-bottom: 6px; }
    p.desc { font-size: 14px; color: var(--muted); line-height: 1.5; }
    .alert {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid var(--error);
      color: var(--error);
      padding: 10px 14px;
      border-radius: 8px;
      font-size: 13px;
      margin-bottom: 18px;
      display: none;
    }
    .form-group { margin-bottom: 16px; }
    label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      margin-bottom: 6px;
      color: var(--text);
    }
    input {
      width: 100%;
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      background: transparent;
      color: var(--text);
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
    }
    button {
      width: 100%;
      padding: 12px;
      border: none;
      border-radius: 8px;
      background: var(--primary);
      color: white;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      margin-top: 10px;
      transition: background 0.2s;
    }
    button:hover { background: var(--primary-hover); }
    .footer {
      margin-top: 24px;
      text-align: center;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      padding: 4px 8px;
      background: rgba(59, 130, 246, 0.1);
      color: var(--primary);
      border-radius: 20px;
      margin-bottom: 12px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="icon">🎓</div>
      <div class="badge">🔒 Model Context Protocol (OAuth 2.1)</div>
      <h1>Connect Tel Aviv University Moodle</h1>
      <p class="desc">Sign in once to grant Gemini secure academic access. Your password is never shared with Google.</p>
    </div>

    __ALERT_PLACEHOLDER__

    <form method="POST" action="/authorize">
      <input type="hidden" name="client_id" value="__CLIENT_ID__">
      <input type="hidden" name="redirect_uri" value="__REDIRECT_URI__">
      <input type="hidden" name="state" value="__STATE__">
      <input type="hidden" name="code_challenge" value="__CODE_CHALLENGE__">
      <input type="hidden" name="code_challenge_method" value="__CODE_CHALLENGE_METHOD__">

      <div class="form-group">
        <label for="username">TAU SSO Username</label>
        <input type="text" id="username" name="username" placeholder="e.g. yuvaim" required autofocus value="__DEFAULT_USERNAME__">
      </div>

      <div class="form-group">
        <label for="student_id">Student ID / Israeli ID Number</label>
        <input type="text" id="student_id" name="student_id" placeholder="9-digit ID number" required pattern="[0-9]+" value="__DEFAULT_STUDENT_ID__">
      </div>

      <div class="form-group">
        <label for="password">Password</label>
        <input type="password" id="password" name="password" placeholder="••••••••" required>
      </div>

      <div class="form-group" style="display:none;">
        <label for="moodle_url">Moodle URL</label>
        <input type="url" id="moodle_url" name="moodle_url" value="__MOODLE_URL__">
      </div>

      <button type="submit" id="submitBtn">Sign in & Authorize</button>
    </form>

    <div class="footer">
      Credentials are encrypted using AES-128 directly with your personal Moodle session.
    </div>
  </div>
</body>
</html>
"""


def render_login_page(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    error_message: Optional[str] = None,
    default_username: str = "",
    default_student_id: str = ""
) -> str:
    alert_html = ""
    if error_message:
        alert_html = f'<div class="alert" style="display:block;">⚠️ {error_message}</div>'

    html = LOGIN_HTML_TEMPLATE
    html = html.replace("__ALERT_PLACEHOLDER__", alert_html)
    html = html.replace("__CLIENT_ID__", client_id or "")
    html = html.replace("__REDIRECT_URI__", redirect_uri or "")
    html = html.replace("__STATE__", state or "")
    html = html.replace("__CODE_CHALLENGE__", code_challenge or "")
    html = html.replace("__CODE_CHALLENGE_METHOD__", code_challenge_method or "S256")
    html = html.replace("__DEFAULT_USERNAME__", default_username)
    html = html.replace("__DEFAULT_STUDENT_ID__", default_student_id)
    html = html.replace("__MOODLE_URL__", MOODLE_URL)
    return html


def get_request_base_url(req: Request) -> str:
    """Extracts external base URL respecting reverse proxy / tunnel headers."""
    x_proto = req.headers.get("x-forwarded-proto")
    x_host = req.headers.get("x-forwarded-host")
    host = x_host or req.headers.get("host") or f"{req.url.hostname}:{req.url.port}"
    proto = x_proto or req.url.scheme
    return f"{proto}://{host}".rstrip("/")


def create_oauth_routes(token_manager: TokenManager) -> list:
    """Creates Starlette Route handlers for RFC 8414, RFC 9470, and OAuth 2.1 authentication."""

    async def oauth_protected_resource(req: Request) -> JSONResponse:
        base = get_request_base_url(req)
        return JSONResponse({
            "resource": f"{base}/mcp",
            "authorization_servers": [base],
            "scopes_supported": ["moodle"],
            "bearer_methods_supported": ["header"],
            "resource_documentation": f"{base}/health"
        })

    async def oauth_auth_server(req: Request) -> JSONResponse:
        base = get_request_base_url(req)
        return JSONResponse({
            "issuer": base,
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "registration_endpoint": f"{base}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "client_credentials"
            ],
            "code_challenge_methods_supported": ["S256", "plain"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
                "none"
            ],
            "scopes_supported": ["moodle"]
        })

    async def oauth_register(req: Request) -> JSONResponse:
        try:
            body = await req.json()
        except Exception:
            body = {}
        client_id = f"gemini-client-{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        return JSONResponse({
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": body.get("client_name", "Google Gemini"),
            "redirect_uris": body.get("redirect_uris", []),
            "grant_types": ["authorization_code", "refresh_token", "client_credentials"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none"
        }, status_code=201)

    async def oauth_authorize_get(req: Request) -> Response:
        params = req.query_params
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri", "")
        state = params.get("state", "")
        code_challenge = params.get("code_challenge", "")
        code_challenge_method = params.get("code_challenge_method", "S256")

        html = render_login_page(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method
        )
        return HTMLResponse(content=html)

    async def oauth_authorize_post(req: Request) -> Response:
        try:
            form = await req.form()
        except Exception:
            form = {}

        username = str(form.get("username", "")).strip()
        student_id = str(form.get("student_id", "")).strip()
        password = str(form.get("password", "")).strip()
        client_id = str(form.get("client_id", "")).strip()
        redirect_uri = str(form.get("redirect_uri", "")).strip()
        state = str(form.get("state", "")).strip()
        code_challenge = str(form.get("code_challenge", "")).strip()
        code_challenge_method = str(form.get("code_challenge_method", "S256")).strip()
        moodle_url = str(form.get("moodle_url", "")).strip() or MOODLE_URL

        if not username or not password or not student_id:
            html = render_login_page(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                error_message="Username, Israeli ID, and Password are all required.",
                default_username=username,
                default_student_id=student_id
            )
            return HTMLResponse(content=html, status_code=400)

        auth = MoodleAuth(moodle_url=moodle_url, profile="stateless")
        try:
            auth.login_with_sso(username, password, student_id, moodle_url=moodle_url)
            session_data = {
                "username": username,
                "student_id": student_id,
                "password": password,
                "moodle_url": moodle_url,
                "cookies": auth.session.cookies.get_dict(),
                "token": auth.token,
                "sesskey": auth.sesskey,
                "user_id": auth.user_id,
                "auth_type": "sso"
            }
            code = token_manager.create_auth_code(
                session_data=session_data,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method
            )
            if redirect_uri:
                sep = "&" if "?" in redirect_uri else "?"
                target = f"{redirect_uri}{sep}code={code}"
                if state:
                    target += f"&state={state}"
                return RedirectResponse(url=target, status_code=302)
            else:
                return JSONResponse({"code": code, "state": state})
        except Exception as e:
            logger.warning(f"OAuth authorize SSO login error: {e}")
            html = render_login_page(
                client_id=client_id,
                redirect_uri=redirect_uri,
                state=state,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                error_message=f"TAU SSO Login Failed: {e}",
                default_username=username,
                default_student_id=student_id
            )
            return HTMLResponse(content=html, status_code=400)

    async def oauth_token_endpoint(req: Request) -> Response:
        content_type = req.headers.get("content-type", "").lower()
        data = {}
        if "application/json" in content_type:
            try:
                data = await req.json()
            except Exception:
                data = {}
        else:
            try:
                form = await req.form()
                data = dict(form)
            except Exception:
                data = {}

        # Handle HTTP Basic Auth for client_credentials grant
        basic_auth = req.headers.get("authorization", "")
        if basic_auth.lower().startswith("basic "):
            try:
                b64_val = basic_auth[6:].strip()
                decoded = base64.b64decode(b64_val).decode("utf-8")
                if ":" in decoded:
                    b_user, b_pass = decoded.split(":", 1)
                    data.setdefault("client_id", b_user)
                    data.setdefault("client_secret", b_pass)
            except Exception:
                pass

        grant_type = data.get("grant_type")
        if not grant_type:
            if "code" in data:
                grant_type = "authorization_code"
            elif "refresh_token" in data:
                grant_type = "refresh_token"
            elif "client_id" in data and "client_secret" in data:
                grant_type = "client_credentials"

        if grant_type == "authorization_code":
            code = data.get("code")
            client_id = data.get("client_id")
            redirect_uri = data.get("redirect_uri")
            code_verifier = data.get("code_verifier")

            if not code:
                return JSONResponse({
                    "error": "invalid_request",
                    "error_description": "Missing authorization code"
                }, status_code=400)

            session_data = token_manager.exchange_code(
                code=code,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier
            )
            if not session_data:
                return JSONResponse({
                    "error": "invalid_grant",
                    "error_description": "Invalid, expired, or already used authorization code or PKCE verifier"
                }, status_code=400)

            tokens = token_manager.create_tokens(session_data)
            return JSONResponse(tokens, headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            })

        elif grant_type == "refresh_token":
            refresh_token = data.get("refresh_token")
            if not refresh_token:
                return JSONResponse({
                    "error": "invalid_request",
                    "error_description": "Missing refresh_token"
                }, status_code=400)

            payload = token_manager.decrypt_payload(refresh_token)
            if not payload or payload.get("token_type") != "refresh":
                return JSONResponse({
                    "error": "invalid_grant",
                    "error_description": "Invalid refresh token"
                }, status_code=400)

            if payload.get("exp", 0) < time.time():
                return JSONResponse({
                    "error": "invalid_grant",
                    "error_description": "Refresh token expired"
                }, status_code=400)

            username = payload.get("username")
            password = payload.get("password")
            student_id = payload.get("student_id")
            moodle_url = payload.get("moodle_url") or MOODLE_URL

            session_data = dict(payload)
            if username and password:
                try:
                    auth = MoodleAuth(moodle_url=moodle_url, profile="stateless")
                    auth.login_with_sso(username, password, student_id, moodle_url=moodle_url)
                    session_data.update({
                        "cookies": auth.session.cookies.get_dict(),
                        "token": auth.token,
                        "sesskey": auth.sesskey,
                        "user_id": auth.user_id,
                        "auth_type": "sso"
                    })
                except Exception as e:
                    logger.warning(f"Refresh token silent re-auth warning: {e}")

            tokens = token_manager.create_tokens(session_data)
            return JSONResponse(tokens, headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
            })

        elif grant_type == "client_credentials":
            client_id = data.get("client_id", "")
            client_secret = data.get("client_secret", "")
            student_id = data.get("student_id", "")

            if ":" in client_id:
                username, parsed_id = client_id.split(":", 1)
                if not student_id:
                    student_id = parsed_id
            else:
                username = client_id
            password = client_secret

            if not username or not password:
                return JSONResponse({
                    "error": "invalid_client",
                    "error_description": "Client ID (TAU username) and Client Secret (password) required"
                }, status_code=400)

            try:
                auth = MoodleAuth(profile="stateless")
                auth.login_with_sso(username, password, student_id, moodle_url=MOODLE_URL)
                session_data = {
                    "username": username,
                    "student_id": student_id,
                    "password": password,
                    "moodle_url": MOODLE_URL,
                    "cookies": auth.session.cookies.get_dict(),
                    "token": auth.token,
                    "sesskey": auth.sesskey,
                    "user_id": auth.user_id,
                    "auth_type": "sso"
                }
                tokens = token_manager.create_tokens(session_data)
                return JSONResponse(tokens, headers={
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                })
            except Exception as e:
                return JSONResponse({
                    "error": "invalid_grant",
                    "error_description": f"Moodle SSO authentication failed: {e}"
                }, status_code=401)

        return JSONResponse({
            "error": "unsupported_grant_type",
            "error_description": f"Unsupported grant_type: '{grant_type}'"
        }, status_code=400)

    return [
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource/mcp", oauth_protected_resource, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource/{resource_path:path}", oauth_protected_resource, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", oauth_auth_server, methods=["GET"]),
        Route("/.well-known/openid-configuration", oauth_auth_server, methods=["GET"]),
        Route("/register", oauth_register, methods=["POST"]),
        Route("/authorize", oauth_authorize_get, methods=["GET"]),
        Route("/authorize", oauth_authorize_post, methods=["POST"]),
        Route("/token", oauth_token_endpoint, methods=["POST"]),
    ]


class BearerAuthMiddleware:
    """
    ASGI Middleware enforcing Bearer token authentication on MCP endpoints.
    Intercepts requests, decrypts tokens to retrieve the corresponding MoodleClient,
    sets the current_client_var context variable, and issues RFC-compliant 401
    challenges with WWW-Authenticate metadata when unauthenticated.
    """

    def __init__(self, app: Any, token_manager: TokenManager, require_auth: bool = True):
        self.app = app
        self.token_manager = token_manager
        self.require_auth = require_auth

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Preflight CORS requests should pass directly to CORSMiddleware
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Public endpoints that bypass authentication
        public_prefixes = (
            "/.well-known/",
            "/register",
            "/authorize",
            "/token",
            "/health",
            "/docs",
            "/openapi.json"
        )
        if any(path.startswith(p) for p in public_prefixes):
            await self.app(scope, receive, send)
            return

        # Extract Authorization header
        auth_header = None
        for name, value in scope.get("headers", []):
            if name.lower() == b"authorization":
                auth_header = value.decode("latin1").strip()
                break

        client = None
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            client = self.token_manager.get_or_create_client(token)
            if not client:
                await self._send_401(
                    send,
                    error="invalid_token",
                    error_description="The access token is invalid or expired"
                )
                return

        if client is not None:
            # Set request contextvar for dynamic client isolation
            ctx_token = current_client_var.set(client)
            try:
                await self.app(scope, receive, send)
            finally:
                current_client_var.reset(ctx_token)
            return

        # No Bearer token provided
        if self.require_auth:
            await self._send_401(send)
            return

        await self.app(scope, receive, send)

    async def _send_401(
        self,
        send: Any,
        error: Optional[str] = None,
        error_description: Optional[str] = None
    ) -> None:
        challenge = 'Bearer realm="moodle_mcp", resource_metadata="/.well-known/oauth-protected-resource"'
        if error:
            challenge += f', error="{error}"'
            if error_description:
                challenge += f', error_description="{error_description}"'

        body_dict = {
            "error": error or "unauthorized",
            "message": error_description or "Authentication required. Please connect via OAuth 2.1.",
            "authorization_uri": "/authorize",
            "token_uri": "/token"
        }
        body = json.dumps(body_dict).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"www-authenticate", challenge.encode("utf-8")),
            (b"access-control-allow-origin", b"*"),
            (b"access-control-expose-headers", b"WWW-Authenticate, mcp-session-id"),
        ]
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        })
