import importlib.util
import json
import re
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("server", ROOT / "server.py")
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


class Stage1AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        server.DB_PATH = Path(self.tmp.name) / "test.sqlite3"
        server.PROFILE_PHOTO_DIR = Path(self.tmp.name) / "profile-photos"
        server.RATE_LIMITS.clear()
        server.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_password_hash_is_not_plain_text(self):
        digest = server.password_hash("StrongPassword123")
        self.assertNotIn("StrongPassword123", digest)
        self.assertTrue(server.verify_password("StrongPassword123", digest))
        self.assertFalse(server.verify_password("WrongPassword123", digest))

    def test_users_table_has_stage1_columns(self):
        with sqlite3.connect(server.DB_PATH) as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        for name in {
            "first_name",
            "last_name",
            "profile_photo",
            "email_verified",
            "verification_token_hash",
            "verification_token_expires_at",
            "password_reset_token_hash",
            "password_reset_token_expires_at",
            "created_at",
            "last_login_at",
        }:
            self.assertIn(name, cols)

    def test_token_hash_does_not_expose_token(self):
        token = "raw-secret-token"
        hashed = server.token_hash(token)
        self.assertNotEqual(token, hashed)
        self.assertEqual(hashed, server.token_hash(token))

    def test_full_account_flow(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookies = {}

        def request(path, payload=None):
            headers = {"Content-Type": "application/json"}
            if cookies:
                headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
            if payload is not None and "nira_csrf" in cookies:
                headers["X-CSRF-Token"] = cookies["nira_csrf"]
                payload = {**payload, "csrfToken": cookies["nira_csrf"]}
            data = None if payload is None else json.dumps(payload).encode()
            req = urllib.request.Request(base + path, data=data, headers=headers, method="POST" if payload is not None else "GET")
            try:
                res = urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode()
                raise AssertionError(f"{path} failed {exc.code}: {body}") from exc
            for header in res.headers.get_all("Set-Cookie") or []:
                name, value = header.split(";", 1)[0].split("=", 1)
                cookies[name] = value
            return json.loads(res.read().decode())

        try:
            request("/api/csrf")
            signup = request("/api/signup", {
                "firstName": "Test",
                "lastName": "User",
                "name": "Test User",
                "email": "test@example.com",
                "password": "StrongPassword123",
                "newsletter": True,
            })
            self.assertIn("verify", signup["message"].lower())
            with sqlite3.connect(server.DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                user = conn.execute("SELECT * FROM users WHERE email = ?", ("test@example.com",)).fetchone()
                self.assertIsNotNone(user)
                self.assertEqual(user["email_verified"], 0)
                outbox = conn.execute("SELECT body FROM email_outbox WHERE recipient = ? ORDER BY id DESC LIMIT 1", ("test@example.com",)).fetchone()
            token = re.search(r"token=([A-Za-z0-9_-]+)", outbox["body"]).group(1)
            urllib.request.urlopen(base + f"/verify-email?token={token}", timeout=5).read()
            with sqlite3.connect(server.DB_PATH) as conn:
                verified = conn.execute("SELECT email_verified FROM users WHERE email = ?", ("test@example.com",)).fetchone()[0]
            self.assertEqual(verified, 1)

            with self.assertRaises(AssertionError):
                request("/api/signup", {
                    "firstName": "Other",
                    "lastName": "User",
                    "name": "Other User",
                    "email": "test@example.com",
                    "password": "StrongPassword123",
                })

            login = request("/api/signin", {"email": "test@example.com", "password": "StrongPassword123"})
            self.assertEqual(login["user"]["email"], "test@example.com")
            profile = request("/api/profile", {
                "firstName": "Updated",
                "lastName": "User",
                "name": "Updated User",
                "phone": "07123456789",
                "newsletter": True,
            })
            self.assertEqual(profile["user"]["firstName"], "Updated")
            request("/api/signout", {})
            request("/api/csrf")
            request("/api/signin", {"email": "test@example.com", "password": "StrongPassword123"})
            session = request("/api/session")
            self.assertEqual(session["user"]["firstName"], "Updated")

            reset = request("/api/password-reset/request", {"email": "test@example.com"})
            self.assertIn("If an account exists", reset["message"])
            with sqlite3.connect(server.DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                body = conn.execute("SELECT body FROM email_outbox WHERE subject LIKE 'Reset%' ORDER BY id DESC LIMIT 1").fetchone()["body"]
            reset_token = re.search(r"token=([A-Za-z0-9_-]+)", body).group(1)
            request("/api/password-reset/confirm", {"token": reset_token, "password": "NewStrongPassword123"})
            request("/api/signout", {})
            request("/api/csrf")
            request("/api/signin", {"email": "test@example.com", "password": "NewStrongPassword123"})
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
