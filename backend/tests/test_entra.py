"""Exercise OIDC validation with signed ID tokens and mocked Microsoft endpoints."""
import base64
import hashlib
import os
import time
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

os.environ.update({
    "Q_CENTRAL_SECRET_KEY": "qcentral-test-signing-key-at-least-32-chars",
    "Q_CENTRAL_AUTH_MODE": "entra",
    "Q_CENTRAL_EXTERNAL_URL": "https://central.example.test",
    "Q_CENTRAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
    "Q_CENTRAL_ENTRA_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
    "Q_CENTRAL_ENTRA_CLIENT_SECRET": "test-client-secret",
    "Q_CENTRAL_DB_PATH": "/tmp/qcentral-entra-test.db",
})

from authlib.jose import JsonWebKey, jwt
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jose import jwt as session_jwt
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.pool import StaticPool
from qcentral.config import Settings
from qcentral.db import get_session
from qcentral.entra import issuer, oauth, settings
from qcentral.main import app
from qcentral.security import SESSION_COOKIE_NAME, create_admin_session, hash_secret, verify_admin_session


class EntraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test"})

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.engine)
        def session_override():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[get_session] = session_override
        self.client = TestClient(app, base_url="https://central.example.test", follow_redirects=False)
        self.remote = oauth.entra
        metadata = {"issuer": issuer, "authorization_endpoint": issuer + "/authorize",
                    "token_endpoint": issuer + "/token", "jwks_uri": issuer + "/keys",
                    "id_token_signing_alg_values_supported": ["RS256"]}
        self.metadata_patch = patch.object(self.remote, "load_server_metadata", AsyncMock(return_value=metadata))
        self.jwk_patch = patch.object(self.remote, "fetch_jwk_set", AsyncMock(return_value={"keys": [self.key.as_dict()]}))
        self.metadata_patch.start()
        self.jwk_patch.start()

    def tearDown(self):
        self.metadata_patch.stop()
        self.jwk_patch.stop()
        app.dependency_overrides.clear()
        self.client.close()
        self.engine.dispose()

    def start_flow(self):
        response = self.client.get("/api/auth/entra/login")
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["redirect_uri"], [settings.entra_redirect_uri])
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertIn("secure", response.headers["set-cookie"].lower())
        return params

    def callback(self, changes=None, *, signing_key=None, state=None):
        flow = self.start_flow()
        now = int(time.time())
        claims = {"iss": issuer, "aud": str(settings.entra_client_id), "sub": "subject",
                  "tid": str(settings.entra_tenant_id), "oid": "33333333-3333-3333-3333-333333333333",
                  "iat": now, "nbf": now - 1, "exp": now + 3600,
                  "nonce": flow["nonce"][0], "roles": ["QCentral.Admin"], "name": "Test Admin"}
        claims.update(changes or {})
        for name in list(claims):
            if claims[name] is None:
                del claims[name]
        id_token = jwt.encode({"alg": "RS256", "kid": "test"}, claims, signing_key or self.key).decode()
        fetch = AsyncMock(return_value={"access_token": "test-access-token", "id_token": id_token})
        with patch.object(self.remote, "fetch_access_token", fetch):
            response = self.client.get("/api/auth/entra/callback", params={"code": "test-code", "state": state or flow["state"][0]})
        return response, fetch, flow

    def test_login_session_and_pkce(self):
        response, fetch, flow = self.callback()
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("auth_error", response.headers["location"])
        verifier = fetch.call_args.kwargs["code_verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(challenge, flow["code_challenge"][0])
        cookie = response.headers["set-cookie"]
        self.assertIn("SameSite=strict", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["auth_provider"], "entra")
        self.assertEqual(me.json()["role"], "admin")
        self.assertTrue(me.json()["username"].startswith("entra:"))
        replay = self.client.get("/api/auth/entra/callback", params={"code": "test-code", "state": flow["state"][0]})
        self.assertIn("auth_error", replay.headers["location"])

    def test_invalid_signed_claims(self):
        for changes in [{"iss": "https://evil.test"}, {"aud": "wrong-client"},
                        {"tid": "44444444-4444-4444-4444-444444444444"},
                        {"oid": None}, {"oid": "invalid"}, {"roles": []},
                        {"roles": ["Portal.Admin"]}, {"roles": "QCentral.Admin"},
                        {"nonce": "wrong"}, {"exp": int(time.time()) - 300},
                        {"nbf": int(time.time()) + 600}, {"exp": None}, {"nbf": None}]:
            with self.subTest(changes=changes):
                response, _, _ = self.callback(changes)
                self.assertIn("auth_error", response.headers["location"])
                self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_wrong_signature(self):
        other = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test"})
        response, _, _ = self.callback(signing_key=other)
        self.assertIn("auth_error", response.headers["location"])

    def test_wrong_state_never_exchanges_code(self):
        response, fetch, _ = self.callback(state="wrong-state")
        self.assertIn("auth_error", response.headers["location"])
        fetch.assert_not_awaited()

    def test_missing_role_is_reported_in_server_log(self):
        with self.assertLogs("qcentral.entra", level="WARNING") as logged:
            response, _, _ = self.callback({"roles": ["Portal.Admin"]})
        self.assertIn("auth_error", response.headers["location"])
        self.assertIn("reason=missing_qcentral_role", " ".join(logged.output))

    def test_invalid_secret_diagnostic_does_not_log_upstream_description(self):
        from authlib.integrations.base_client.errors import OAuthError
        flow = self.start_flow()
        error = OAuthError(error="invalid_client", description="sensitive-secret-and-token")
        with patch.object(self.remote, "fetch_access_token", AsyncMock(side_effect=error)):
            with self.assertLogs("qcentral.entra", level="WARNING") as logged:
                self.client.get("/api/auth/entra/callback", params={"code": "private-code", "state": flow["state"][0]})
        output = " ".join(logged.output)
        self.assertIn("reason=invalid_client", output)
        self.assertNotIn("sensitive-secret-and-token", output)
        self.assertNotIn("private-code", output)

    def test_superadmin_and_short_token_lifetime(self):
        response, _, _ = self.callback({"roles": ["QCentral.SuperAdmin"], "exp": int(time.time()) + 120})
        self.assertNotIn("auth_error", response.headers["location"])
        self.assertEqual(self.client.get("/api/auth/me").json()["role"], "superadmin")
        claims = session_jwt.get_unverified_claims(self.client.cookies.get(SESSION_COOKIE_NAME))
        self.assertLessEqual(claims["exp"] - int(time.time()), 120)

    def test_local_credentials_and_account_mutations_blocked(self):
        self.assertEqual(self.client.post("/api/auth/login", json={"username": "admin", "password": "test"}).status_code, 403)
        self.callback()
        for path, method, body in [("/api/profile/change-password", "POST", {"current_value": "test", "new_value": "test-test-test"}),
                                   ("/api/users", "POST", {"username": "test", "initial_value": "test-test-test"}),
                                   ("/api/users/test", "PATCH", {"role": "superadmin"})]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, json=body).status_code, 403)

    def test_provider_and_expiry_reject_old_sessions(self):
        for token in [create_admin_session("admin"), create_admin_session("entra:test", provider="entra", expires_at=int(time.time()) - 10)]:
            with self.assertRaises(HTTPException):
                verify_admin_session(token)

    def test_logout(self):
        self.callback()
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_identity_survives_email_change_and_role_is_refreshed(self):
        self.callback({"roles": ["QCentral.SuperAdmin"], "email": "old@example.test"})
        original = self.client.get("/api/auth/me").json()
        self.callback({"roles": ["QCentral.Admin"], "email": "new@example.test"})
        current = self.client.get("/api/auth/me").json()
        self.assertEqual(current["username"], original["username"])
        self.assertEqual(current["role"], "admin")
        self.assertEqual(current["email"], "new@example.test")

    def test_explicit_local_mode_still_works(self):
        with patch.object(settings, "auth_mode", "local"), patch.object(settings, "admin_credential_hash", hash_secret("test-local-password")):
            response = self.client.post("/api/auth/login", json={"username": "admin", "password": "test-local-password"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get("/api/auth/me").json()["auth_provider"], "local")
            self.assertEqual(self.client.get("/api/auth/entra/login").status_code, 503)

    def test_missing_config_and_no_silent_local_fallback(self):
        with patch.object(settings, "entra_client_secret", None):
            self.assertFalse(self.client.get("/api/auth/config").json()["configured"])
            self.assertEqual(self.client.get("/api/auth/entra/login").status_code, 503)
        blank = Settings(_env_file=None, entra_tenant_id="", entra_client_id="", entra_client_secret="")
        self.assertFalse(blank.entra_configured)

    def test_websocket_requires_session(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/api/software/ws"):
                pass


if __name__ == "__main__":
    unittest.main()
