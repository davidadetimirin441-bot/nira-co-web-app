import importlib.util
import json
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


class Stage2RoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        server.DB_PATH = Path(self.tmp.name) / "test.sqlite3"
        server.PROFILE_PHOTO_DIR = Path(self.tmp.name) / "profile-photos"
        server.RATE_LIMITS.clear()
        server.ADMIN_EMAILS.clear()
        server.ADMIN_EMAILS.add("admin@example.com")
        server.init_db()
        with sqlite3.connect(server.DB_PATH) as conn:
            conn.execute(
                "INSERT INTO users (name, first_name, last_name, email, password_hash, provider, sourcer_index, email_verified, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("Normal User", "Normal", "User", "normal@example.com", server.password_hash("StrongPassword123"), "Email", 0, 1, "investor"),
            )
            conn.execute(
                "INSERT INTO users (name, first_name, last_name, email, password_hash, provider, sourcer_index, email_verified, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("Admin User", "Admin", "User", "admin@example.com", server.password_hash("StrongPassword123"), "Email", 0, 1, "admin"),
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_role_mapping(self):
        self.assertEqual(server.role_from_type("Deal sourcer"), "deal_sourcer")
        self.assertEqual(server.role_from_type("Agent"), "estate_agent")
        self.assertEqual(server.role_from_type("Developer"), "developer")
        self.assertEqual(server.role_from_type("Investor"), "investor")
        self.assertEqual(server.role_from_type("Investor", "admin@example.com"), "admin")

    def test_admin_apis_require_admin(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        cookies = {}

        def request(path, payload=None, expect_error=False):
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
                for header in res.headers.get_all("Set-Cookie") or []:
                    name, value = header.split(";", 1)[0].split("=", 1)
                    cookies[name] = value
                return json.loads(res.read().decode())
            except urllib.error.HTTPError as exc:
                if expect_error:
                    return {"status": exc.code, "body": exc.read().decode()}
                raise

        try:
            request("/api/csrf")
            request("/api/signin", {"email": "normal@example.com", "password": "StrongPassword123"})
            self.assertEqual(request("/api/admin/stats", expect_error=True)["status"], 403)
            self.assertEqual(request("/api/ads", expect_error=True)["status"], 403)
            self.assertEqual(request("/api/newsletter/send", {}, expect_error=True)["status"], 403)
            request("/api/signout", {})

            request("/api/csrf")
            login = request("/api/signin", {"email": "admin@example.com", "password": "StrongPassword123"})
            self.assertTrue(login["user"]["isAdmin"])
            stats = request("/api/admin/stats")
            self.assertGreaterEqual(stats["stats"]["users"], 2)
            self.assertIn("roles", stats["stats"])
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
