from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "ratada.sqlite3"
ASSETS = ROOT / "assets"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("RATADA_PORT", "8088"))

SOURCERS = [
    {"name": "Aisha Bello", "market": "UK North", "role": "Senior UK sourcer", "closeRate": 31, "saved": 14, "markets": 12, "tags": ["BTL", "HMO", "Off-market"]},
    {"name": "Callum Price", "market": "Midlands", "role": "Auction specialist", "closeRate": 24, "saved": 9, "markets": 8, "tags": ["Auction", "Flip", "Refurb"]},
    {"name": "Maya Khan", "market": "Dubai", "role": "GCC short-let sourcer", "closeRate": 28, "saved": 11, "markets": 7, "tags": ["Developer", "Short let", "Luxury"]},
    {"name": "Tunde Okafor", "market": "Lagos", "role": "Africa market sourcer", "closeRate": 36, "saved": 18, "markets": 10, "tags": ["Off-market", "Villas", "Legal review"]},
    {"name": "Sofia Martins", "market": "Algarve", "role": "Europe coastal sourcer", "closeRate": 22, "saved": 7, "markets": 5, "tags": ["Holiday let", "Coastal", "Yield"]},
]

DEALS = [
    {"title": "Three-bed terrace near tram expansion", "location": "Manchester, UK", "region": "UK", "strategy": "Buy-to-let", "source": "Agent", "price": 185000, "yield": 7.6, "discount": 14, "status": "Mortgageable", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/manchester/"},
    {"title": "Auction semi with permitted development angle", "location": "Birmingham, UK", "region": "UK", "strategy": "Flip", "source": "Auction", "price": 142000, "yield": 9.1, "discount": 22, "status": "Refurb", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1570129477492-45c003edd2be?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/birmingham/"},
    {"title": "Short-let apartment in marina district", "location": "Dubai, UAE", "region": "Middle East", "strategy": "Short let", "source": "Developer", "price": 315000, "yield": 8.8, "discount": 11, "status": "Ready Q4", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1512453979798-5ea266f8880c?auto=format&fit=crop&w=640&q=80", "link": "https://www.propertyfinder.ae/en/search?c=1&l=50"},
    {"title": "Student HMO conversion candidate", "location": "Liverpool, UK", "region": "UK", "strategy": "HMO", "source": "Off-market", "price": 236000, "yield": 10.4, "discount": 19, "status": "Planning check", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/liverpool/"},
    {"title": "Two-unit villa close to new airport road", "location": "Lagos, Nigeria", "region": "Africa", "strategy": "Buy-to-let", "source": "Off-market", "price": 128000, "yield": 11.2, "discount": 27, "status": "Legal review", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=640&q=80", "link": "https://nigeriapropertycentre.com/for-sale/houses/lagos"},
    {"title": "Coastal townhouse with holiday-let demand", "location": "Algarve, Portugal", "region": "Europe", "strategy": "Short let", "source": "Agent", "price": 410000, "yield": 6.9, "discount": 9, "status": "Viewing slots", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=640&q=80", "link": "https://www.idealista.pt/en/comprar-casas/faro-distrito/algarve/"},
]


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            sourcer_index INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    salt, digest = stored.split("$", 1)
    return hmac.compare_digest(password_hash(password, salt).split("$", 1)[1], digest)


def sourcer_index(email):
    return sum(ord(ch) for ch in email.lower()) % len(SOURCERS)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.send_file(ROOT / "index.html", "text/html")
        if path == "/app":
            return self.send_file(ROOT / "app.html", "text/html")
        if path == "/api/session":
            return self.send_json({"user": self.current_user()})
        if path == "/api/deals":
            return self.send_json({"deals": DEALS, "sourcers": SOURCERS})
        if path.startswith("/assets/"):
            return self.send_asset(path.replace("/assets/", "", 1))
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
        except ValueError:
            return self.send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
        if path == "/api/signup":
            return self.signup(data)
        if path == "/api/signin":
            return self.signin(data)
        if path == "/api/signout":
            return self.signout()
        self.send_error(HTTPStatus.NOT_FOUND)

    def signup(self, data):
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not name or "@" not in email or len(password) < 6:
            return self.send_json({"error": "Enter name, valid email, and 6+ character password."}, HTTPStatus.BAD_REQUEST)
        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO users (name, email, password_hash, provider, sourcer_index) VALUES (?, ?, ?, ?, ?)",
                    (name, email, password_hash(password), "Email", sourcer_index(email)),
                )
        except sqlite3.IntegrityError:
            return self.send_json({"error": "Account already exists. Sign in instead."}, HTTPStatus.CONFLICT)
        return self.create_session(email)

    def signin(self, data):
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return self.send_json({"error": "Email or password is incorrect."}, HTTPStatus.UNAUTHORIZED)
        return self.create_session(email)

    def signout(self):
        token = self.session_token()
        if token:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.send_response(HTTPStatus.OK)
        self.send_header("Set-Cookie", "ratada_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def create_session(self, email):
        token = secrets.token_urlsafe(32)
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.execute("INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user["id"]))
        self.send_response(HTTPStatus.OK)
        self.send_header("Set-Cookie", f"ratada_session={token}; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"user": self.user_payload(user)}).encode())

    def current_user(self):
        token = self.session_token()
        if not token:
            return None
        with db() as conn:
            row = conn.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
                (token,),
            ).fetchone()
        return self.user_payload(row) if row else None

    def user_payload(self, row):
        profile = SOURCERS[row["sourcer_index"]]
        return {"name": row["name"], "email": row["email"], "provider": row["provider"], "profile": profile}

    def session_token(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        morsel = cookie.get("ratada_session")
        return morsel.value if morsel else None

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode() or "{}")

    def send_json(self, payload, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def send_file(self, path, content_type):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def send_asset(self, name):
        path = (ASSETS / name).resolve()
        if not str(path).startswith(str(ASSETS.resolve())) or not path.exists():
            return self.send_error(HTTPStatus.NOT_FOUND)
        types = {".svg": "image/svg+xml", ".png": "image/png"}
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", types.get(path.suffix, "application/octet-stream"))
        self.end_headers()
        self.wfile.write(path.read_bytes())


if __name__ == "__main__":
    init_db()
    print(f"NIRA & CO running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
