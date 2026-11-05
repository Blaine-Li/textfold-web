"""Exercise the login boundary over HTTP, including private files and remote origins.

Uses a temporary account and library, no user's configuration or model calls.
"""
import hashlib
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from textfold import local, server, store, web_auth

PASSWORD = "test-only-reading-passphrase"


class Login(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = mock.patch.object(store, "HOME", Path(cls.tmp.name) / "settings")
        cls.data = mock.patch.object(store, "DATA", Path(cls.tmp.name) / "data")
        cls.home.start(); cls.data.start()
        web_auth.set_account("reader", PASSWORD)
        cls.pid = local.import_text("# Private research\n\nThe library must remain private.")
        cls.access = web_auth.Access(required=True, origin="https://read.example.com")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(mock.Mock(), cls.access))
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close(); cls.thread.join(timeout=5)
        cls.home.stop(); cls.data.stop(); cls.tmp.cleanup()

    def setUp(self):
        self.access.attempts.clear(); self.access.global_attempts.clear(); self.access.sessions.clear()

    def request(self, path, method="GET", body=None, cookie=None, host="read.example.com", origin="https://read.example.com", raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host}
        if origin is not None:
            headers["Origin"] = origin
        if cookie:
            headers["Cookie"] = cookie
        if method == "POST":
            headers["Content-Type"] = "application/json"
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        connection.request(method, path, body=data, headers=headers)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def login(self, **options):
        status, headers, payload = self.request("/api/auth/login", "POST", {"username": "reader", "password": PASSWORD, **options})
        self.assertEqual(status, 200, payload)
        return headers["Set-Cookie"].split(";", 1)[0], headers, json.loads(payload)

    def test_anonymous_document_and_every_private_endpoint_are_protected(self):
        for path in ("/", f"/p/{self.pid}", "/f/f-00000000", f"/p/{self.pid}/img/secret.png", "/api/papers", "/api/models", "/api/jobs",
                     f"/api/doc/{self.pid}", f"/api/notes/{self.pid}", f"/api/text/{self.pid}", f"/api/pdf/{self.pid}", "/api/storage", "/static/app.js"):
            with self.subTest(path=path):
                status, headers, body = self.request(path)
                self.assertIn(status, (303, 401))
                self.assertNotIn(b"Private research", body)
        for path in ("/api/import", "/api/export", "/api/providers/save", "/api/ask", "/api/files"):
            self.assertEqual(self.request(path, "POST", {})[0], 401, path)

    def test_login_page_assets_are_public_but_never_contain_library_data(self):
        for path in ("/login", "/static/login.css", "/static/login.js", "/static/vendor/fonts/fonts.css", "/healthz"):
            status, headers, body = self.request(path)
            self.assertEqual(status, 200, path)
            self.assertNotIn(PASSWORD.encode(), body)
            self.assertNotIn(b"Private research", body)
        _, headers, body = self.request("/login")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn(b'data-ready="true"', body)

    def test_real_login_uses_secure_http_only_cookie_and_logout_revokes_replay(self):
        cookie, headers, payload = self.login()
        self.assertTrue(cookie.startswith("__Host-textfold_session="))
        for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, headers["Set-Cookie"])
        status, _, body = self.request(f"/api/text/{self.pid}", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(b"Private research", body)
        status, headers, _ = self.request("/api/auth/logout", "POST", {}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn("Max-Age=0", headers["Set-Cookie"])
        self.assertEqual(self.request(f"/api/text/{self.pid}", cookie=cookie)[0], 401)

    def test_bad_password_and_unknown_account_have_same_error(self):
        for username, password in (("reader", "wrong"), ("unknown", PASSWORD), ("读者", PASSWORD)):
            status, headers, payload = self.request("/api/auth/login", "POST", {"username": username, "password": password})
            self.assertEqual(status, 401)
            self.assertEqual(json.loads(payload)["error"], "invalid-credentials")
            self.assertNotIn("Set-Cookie", headers)

    def test_csrf_and_host_spoofing_cannot_write_even_with_a_valid_session(self):
        cookie, _, _ = self.login()
        for origin in (None, "https://attacker.example", "http://read.example.com", "https://read.example.com:444", "null"):
            self.assertEqual(self.request("/api/auth/logout", "POST", {}, cookie=cookie, origin=origin)[0], 403)
        for host in ("attacker.example", "read.example.com.attacker.example", "read.example.com:444"):
            self.assertEqual(self.request("/api/auth/session", host=host, cookie=cookie)[0], 421)
        self.assertEqual(self.request(f"/api/text/{self.pid}", cookie=cookie)[0], 200)

    def test_login_cannot_redirect_to_another_site(self):
        for target in ("https://attacker.example", "//attacker.example", "/\\attacker.example", "/login", "/\r\nLocation:evil"):
            cookie, _, payload = self.login(next=target)
            self.assertEqual(payload["next"], "/")
        _, _, payload = self.login(next=f"/p/{self.pid}?lang=en")
        self.assertEqual(payload["next"], f"/p/{self.pid}?lang=en")

    def test_login_rate_limit_expires(self):
        with mock.patch.object(web_auth.time, "time", return_value=1000):
            for _ in range(web_auth.LOGIN_ATTEMPTS):
                self.request("/api/auth/login", "POST", {"username": "reader", "password": "wrong"})
            status, headers, _ = self.request("/api/auth/login", "POST", {"username": "reader", "password": PASSWORD})
            self.assertEqual(status, 429)
            self.assertIn("Retry-After", headers)
        with mock.patch.object(web_auth.time, "time", return_value=1000 + web_auth.LOGIN_WINDOW + 1):
            self.login()

    def test_idle_and_absolute_expiry_reject_existing_token(self):
        cookie, _, _ = self.login()
        session = next(iter(self.access.sessions.values()))
        session["seen"] = time.time() - web_auth.IDLE_SECONDS - 1
        self.assertEqual(self.request(f"/api/text/{self.pid}", cookie=cookie)[0], 401)
        cookie, _, _ = self.login()
        next(iter(self.access.sessions.values()))["expires"] = time.time() - 1
        self.assertEqual(self.request(f"/api/text/{self.pid}", cookie=cookie)[0], 401)

    def test_unchecked_login_uses_a_browser_session_cookie(self):
        _, headers, _ = self.login(remember=False)
        self.assertNotIn("Max-Age", headers["Set-Cookie"])
        self.assertNotIn("Expires", headers["Set-Cookie"])

    def test_saved_login_survives_restart_and_stores_no_plain_token(self):
        cookie, headers, _ = self.login(remember=True)
        self.assertIn(f"Max-Age={web_auth.REMEMBER_SECONDS}", headers["Set-Cookie"])
        restarted = web_auth.Access(required=True, origin="https://read.example.com")
        request_headers = {"Host": "read.example.com", "Cookie": cookie}
        self.assertEqual(restarted.session(request_headers), {"username": "reader"})
        path = store.HOME / "web-sessions.sqlite3"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(cookie.split("=", 1)[1].encode(), path.read_bytes())
        self.assertNotIn(PASSWORD.encode(), path.read_bytes())
        restarted.logout(request_headers)
        self.assertIsNone(self.access.session(request_headers))

    def test_saved_login_does_not_expire_after_two_idle_hours_but_expires_at_thirty_days(self):
        now = time.time()
        cookie, _, _ = self.login(remember=True)
        headers = {"Host": "read.example.com", "Cookie": cookie}
        with mock.patch.object(web_auth.time, "time", return_value=now + web_auth.IDLE_SECONDS + 60):
            self.assertEqual(self.access.session(headers), {"username": "reader"})
        with mock.patch.object(web_auth.time, "time", return_value=now + web_auth.REMEMBER_SECONDS + 60):
            self.assertIsNone(self.access.session(headers))

    def test_account_reset_revokes_saved_login_and_string_flag_does_not_remember(self):
        cookie, _, _ = self.login(remember=True)
        web_auth.set_account("reader", PASSWORD, replace=True)
        headers = {"Host": "read.example.com", "Cookie": cookie}
        self.assertIsNone(web_auth.Access(required=True, origin="https://read.example.com").session(headers))
        _, response_headers, _ = self.login(remember="true")
        self.assertNotIn("Max-Age", response_headers["Set-Cookie"])

    def test_missing_account_is_closed_and_restart_invalidates_sessions(self):
        with mock.patch.object(web_auth, "credential_path", return_value=Path(self.tmp.name) / "missing"):
            self.assertEqual(self.request("/login")[0], 503)
            self.assertEqual(self.request("/api/auth/login", "POST", {"username": "reader", "password": PASSWORD})[0], 503)
            self.assertEqual(self.request("/api/papers")[0], 401)
        cookie, _, _ = self.login()
        restarted = web_auth.Access(required=True, origin="https://read.example.com")
        self.assertIsNone(restarted.session({"Host": "read.example.com", "Cookie": cookie}))

    def test_account_reset_changes_salt_and_revokes_existing_cookie(self):
        cookie, _, _ = self.login()
        before = web_auth.credential_path().read_bytes()
        web_auth.set_account("reader", PASSWORD, replace=True)
        self.assertNotEqual(before, web_auth.credential_path().read_bytes())
        self.assertEqual(self.request(f"/api/text/{self.pid}", cookie=cookie)[0], 401)
        self.assertNotIn(PASSWORD.encode(), web_auth.credential_path().read_bytes())
        self.assertEqual(web_auth.credential_path().stat().st_mode & 0o777, 0o600)

    def test_malformed_json_and_oversized_login_are_rejected(self):
        self.assertEqual(self.request("/api/auth/login", "POST", raw=b"[")[0], 400)
        self.assertEqual(self.request("/api/auth/login", "POST", raw=b"[]")[0], 400)
        self.assertEqual(self.request("/api/auth/login", "POST", raw=b"a" * 9000)[0], 413)

    def test_local_login_is_supported_without_trusting_forwarding_headers(self):
        status, headers, _ = self.request("/api/auth/login", "POST", {"username": "reader", "password": PASSWORD},
                                          host=f"localhost:{self.port}", origin=f"http://localhost:{self.port}")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Set-Cookie"].startswith("textfold_session="))
        self.assertNotIn("Secure", headers["Set-Cookie"])


class Configuration(unittest.TestCase):
    def test_public_origin_requires_https_and_exact_domain(self):
        self.assertEqual(web_auth.public_origin("https://Read.Example.com:443/"), "https://read.example.com")
        for origin in ("http://example.com", "https://*.example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?x=1"):
            with self.assertRaises(ValueError):
                web_auth.public_origin(origin)
        with self.assertRaises(ValueError):
            web_auth.Access(required=False, origin="https://read.example.com")


if __name__ == "__main__":
    unittest.main()
