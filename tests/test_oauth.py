"""
Unit tests for OAuth 2.1, TokenManager, ClientProxy, and BearerAuthMiddleware.
"""

import base64
import hashlib
import json
import os
import time
import unittest
from unittest.mock import MagicMock

from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from moodle_mcp.oauth import (
    TokenManager,
    ClientProxy,
    current_client_var,
    create_oauth_routes,
    BearerAuthMiddleware,
    render_login_page,
)
from moodle_mcp.client import MoodleClient
from moodle_mcp.auth import MoodleAuth


class TestOAuthComponents(unittest.TestCase):
    def setUp(self):
        self.tm = TokenManager()

    def test_token_encryption_decryption(self):
        payload = {"user": "tester", "id": 12345, "courses": [1, 2, 3]}
        encrypted = self.tm.encrypt_payload(payload)
        self.assertIsInstance(encrypted, str)
        self.assertNotEqual(encrypted, json.dumps(payload))

        decrypted = self.tm.decrypt_payload(encrypted)
        self.assertEqual(decrypted, payload)

    def test_pkce_s256_verification(self):
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        session_data = {"username": "test_user", "student_id": "111222333"}
        code = self.tm.create_auth_code(
            session_data=session_data,
            client_id="gemini-client-1",
            redirect_uri="https://gemini.google.com/callback",
            code_challenge=challenge,
            code_challenge_method="S256"
        )

        # Wrong verifier must fail
        bad_result = self.tm.exchange_code(
            code=code,
            code_verifier="wrong_verifier"
        )
        self.assertIsNone(bad_result)

        # Code can only be used once (must re-issue for good attempt)
        code2 = self.tm.create_auth_code(
            session_data=session_data,
            client_id="gemini-client-1",
            redirect_uri="https://gemini.google.com/callback",
            code_challenge=challenge,
            code_challenge_method="S256"
        )
        good_result = self.tm.exchange_code(
            code=code2,
            code_verifier=verifier
        )
        self.assertIsNotNone(good_result)
        self.assertEqual(good_result["username"], "test_user")

    def test_token_creation_and_client_reconstruction(self):
        session_data = {
            "username": "alice",
            "student_id": "987654321",
            "password": "secret_password",
            "moodle_url": "https://moodle.tau.ac.il",
            "token": "mock_wstoken_123",
            "sesskey": "mock_sesskey_abc",
            "user_id": 9999,
            "cookies": {"MoodleSession": "mock_cookie_val"}
        }

        tokens = self.tm.create_tokens(session_data)
        self.assertIn("access_token", tokens)
        self.assertIn("refresh_token", tokens)
        self.assertEqual(tokens["token_type"], "Bearer")

        # Client reconstruction from access token
        client = self.tm.get_or_create_client(tokens["access_token"])
        self.assertIsNotNone(client)
        self.assertEqual(client.auth.user_id, 9999)
        self.assertEqual(client.auth.token, "mock_wstoken_123")
        self.assertEqual(client.auth._sso_username, "alice")
        self.assertEqual(client.auth.session.cookies.get("MoodleSession"), "mock_cookie_val")

    def test_client_proxy_dynamic_routing(self):
        base_auth = MoodleAuth(profile="default")
        base_client = MoodleClient(auth=base_auth, profile="default")

        user_auth = MoodleAuth(profile="user_bob")
        user_client = MoodleClient(auth=user_auth, profile="user_bob")

        proxy = ClientProxy(base_client)

        # Out of context: proxy routes to base_client
        self.assertEqual(proxy.profile, "default")
        self.assertTrue(isinstance(proxy, MoodleClient))

        # Within context of user_bob: proxy routes to user_client
        token = current_client_var.set(user_client)
        try:
            self.assertEqual(proxy.profile, "user_bob")
        finally:
            current_client_var.reset(token)

        # Context reset: routes back to base_client
        self.assertEqual(proxy.profile, "default")


class TestOAuthHTTPFlow(unittest.TestCase):
    def setUp(self):
        self.tm = TokenManager()
        self.app = Starlette()

        # Mount OAuth routes
        for r in create_oauth_routes(self.tm):
            self.app.routes.append(r)

        # Protected test MCP route
        async def mock_mcp(req):
            return JSONResponse({"status": "ok", "user": getattr(current_client_var.get(), "profile", "default")})

        self.app.routes.append(Route("/mcp", mock_mcp, methods=["POST", "GET"]))

        # Health endpoint
        async def health(req):
            return JSONResponse({"status": "ok"})

        self.app.routes.append(Route("/health", health, methods=["GET"]))

        # Middlewares
        self.app.add_middleware(
            BearerAuthMiddleware,
            token_manager=self.tm,
            require_auth=True
        )
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["mcp-session-id", "www-authenticate", "authorization"],
        )

        self.client = TestClient(self.app)

    def test_public_metadata_endpoints(self):
        # RFC 9470 protected resource metadata
        res = self.client.get("/.well-known/oauth-protected-resource")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("resource", data)
        self.assertIn("authorization_servers", data)

        # RFC 8414 authorization server metadata
        res2 = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertIn("authorization_endpoint", data2)
        self.assertIn("token_endpoint", data2)
        self.assertIn("registration_endpoint", data2)

        # OpenID configuration alias
        res3 = self.client.get("/.well-known/openid-configuration")
        self.assertEqual(res3.status_code, 200)

        # Health check
        res4 = self.client.get("/health")
        self.assertEqual(res4.status_code, 200)

    def test_dynamic_client_registration(self):
        res = self.client.post("/register", json={"client_name": "Gemini Web Client"})
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("client_id", data)
        self.assertIn("client_secret", data)
        self.assertEqual(data["client_name"], "Gemini Web Client")

    def test_authorize_get_renders_html(self):
        res = self.client.get("/authorize?client_id=gemini-1&redirect_uri=https://gemini.google.com")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers.get("content-type", ""))
        self.assertIn("TAU SSO Username", res.text)
        self.assertIn("Student ID", res.text)

    def test_unauthenticated_request_triggers_401_challenge(self):
        res = self.client.post("/mcp", headers={"Origin": "https://gemini.google.com"})
        self.assertEqual(res.status_code, 401)
        self.assertIn(res.headers.get("access-control-allow-origin"), ("*", "https://gemini.google.com"))
        self.assertIn("www-authenticate", res.headers.get("access-control-expose-headers", "").lower())
        auth_hdr = res.headers.get("www-authenticate", "")
        self.assertIn("Bearer", auth_hdr)
        self.assertIn('resource_metadata="/.well-known/oauth-protected-resource"', auth_hdr)

    def test_authenticated_request_succeeds_with_bearer_token(self):
        session_data = {
            "username": "shuki",
            "student_id": "123456789",
            "password": "pwd",
            "moodle_url": "https://moodle.tau.ac.il",
            "token": "tok_xyz",
            "user_id": 5555
        }
        tokens = self.tm.create_tokens(session_data)
        access_tok = tokens["access_token"]

        res = self.client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {access_tok}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["user"], "oauth_shuki")

    def test_token_exchange_via_authorization_code(self):
        session_data = {
            "username": "noa",
            "student_id": "333222111",
            "password": "noa_pass",
            "user_id": 7777
        }
        code = self.tm.create_auth_code(
            session_data=session_data,
            client_id="gemini-client-abc",
            redirect_uri="https://gemini.google.com/callback"
        )

        res = self.client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "gemini-client-abc",
            "redirect_uri": "https://gemini.google.com/callback"
        })
        self.assertEqual(res.status_code, 200)
        token_data = res.json()
        self.assertIn("access_token", token_data)
        self.assertIn("refresh_token", token_data)
        self.assertEqual(token_data["token_type"], "Bearer")


if __name__ == "__main__":
    unittest.main()
