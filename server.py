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
    {"title": "Six-bed HMO near university corridor", "location": "Leeds, UK", "region": "UK", "strategy": "HMO", "source": "Agent", "price": 285000, "yield": 11.6, "discount": 16, "status": "Article 4 check", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/leeds/"},
    {"title": "Licensed HMO with seven letting rooms", "location": "Nottingham, UK", "region": "UK", "strategy": "HMO", "source": "Off-market", "price": 352000, "yield": 12.3, "discount": 13, "status": "Licensed", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1572120360610-d971b9d7767c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/nottingham/"},
    {"title": "Victorian terrace conversion candidate", "location": "Sheffield, UK", "region": "UK", "strategy": "HMO", "source": "Auction", "price": 178000, "yield": 10.9, "discount": 21, "status": "Refurb", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1560184897-ae75f418493e?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/sheffield/"},
    {"title": "Commuter belt buy-to-let semi", "location": "Luton, UK", "region": "UK", "strategy": "Buy-to-let", "source": "Agent", "price": 248000, "yield": 7.4, "discount": 10, "status": "Tenant demand", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/luton/"},
    {"title": "Below-market repossession terrace", "location": "Cardiff, UK", "region": "UK", "strategy": "Flip", "source": "Auction", "price": 164000, "yield": 8.1, "discount": 24, "status": "Legal pack", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1598228723793-52759bba239c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/cardiff/"},
    {"title": "Short-let apartment close to business bay", "location": "Dubai, UAE", "region": "Middle East", "strategy": "Short let", "source": "Developer", "price": 275000, "yield": 9.4, "discount": 12, "status": "Payment plan", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1546412414-e1885259563a?auto=format&fit=crop&w=640&q=80", "link": "https://www.propertyfinder.ae/en/search?c=1&l=41"},
    {"title": "Serviced apartment near metro hub", "location": "Doha, Qatar", "region": "Middle East", "strategy": "Short let", "source": "Agent", "price": 226000, "yield": 8.6, "discount": 8, "status": "Furnished", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=640&q=80", "link": "https://www.propertyfinder.qa/en/search?c=1"},
    {"title": "Two-flat conversion near lagoon district", "location": "Accra, Ghana", "region": "Africa", "strategy": "Buy-to-let", "source": "Off-market", "price": 148000, "yield": 10.7, "discount": 18, "status": "Title review", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1605276374104-dee2a0ed3cd6?auto=format&fit=crop&w=640&q=80", "link": "https://meqasa.com/houses-for-sale-in-ghana"},
    {"title": "Lekki short-let duplex", "location": "Lagos, Nigeria", "region": "Africa", "strategy": "Short let", "source": "Developer", "price": 210000, "yield": 12.8, "discount": 15, "status": "Finishing stage", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1600607688969-a5bfcd646154?auto=format&fit=crop&w=640&q=80", "link": "https://nigeriapropertycentre.com/for-sale/houses/lagos/lekki"},
    {"title": "Lisbon commuter apartment block unit", "location": "Lisbon, Portugal", "region": "Europe", "strategy": "Buy-to-let", "source": "Agent", "price": 295000, "yield": 6.8, "discount": 7, "status": "Rent review", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=640&q=80", "link": "https://www.idealista.pt/en/comprar-casas/lisboa/"},
    {"title": "Valencia coastal refurb apartment", "location": "Valencia, Spain", "region": "Europe", "strategy": "Flip", "source": "Auction", "price": 188000, "yield": 7.2, "discount": 17, "status": "Refurb", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=640&q=80", "link": "https://www.idealista.com/en/venta-viviendas/valencia-valencia/"},
    {"title": "Atlanta duplex with rent uplift", "location": "Atlanta, USA", "region": "Americas", "strategy": "Buy-to-let", "source": "Agent", "price": 238000, "yield": 8.9, "discount": 11, "status": "Occupied", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=640&q=80", "link": "https://www.zillow.com/atlanta-ga/duplex/"},
    {"title": "Bali villa management opportunity", "location": "Bali, Indonesia", "region": "Asia Pacific", "strategy": "Short let", "source": "Developer", "price": 165000, "yield": 13.1, "discount": 9, "status": "Management included", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=640&q=80", "link": "https://www.rumah123.com/en/sale/bali/villa/"},
]

CHAT_MESSAGES = [
    {"from": "Aisha Bello", "role": "sourcer", "text": "I can help with UK HMO checks, Article 4 areas, and rent comparables."},
    {"from": "Technical Team", "role": "support", "text": "Ask us about subscriptions, deal uploads, bugs, or account access."},
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
            sourcer_index INTEGER NOT NULL,
            subscribed INTEGER DEFAULT 0,
            subscription_price INTEGER DEFAULT 15
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "subscribed" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN subscribed INTEGER DEFAULT 0")
        if "subscription_price" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN subscription_price INTEGER DEFAULT 15")


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
        if path == "/api/chat":
            return self.send_json({"messages": CHAT_MESSAGES})
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
        if path == "/api/subscribe":
            return self.subscribe()
        if path == "/api/chat":
            return self.chat(data)
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

    def subscribe(self):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before subscribing."}, HTTPStatus.UNAUTHORIZED)
        with db() as conn:
            conn.execute("UPDATE users SET subscribed = 1, subscription_price = 15 WHERE id = ?", (user["id"],))
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return self.send_json({"user": self.user_payload(updated), "message": "Full sourcing unlocked at £15/month."})

    def chat(self, data):
        user = self.current_user()
        name = user["name"] if user else "Guest"
        text = (data.get("text") or "").strip()
        if not text:
            return self.send_json({"error": "Enter a question or message."}, HTTPStatus.BAD_REQUEST)
        CHAT_MESSAGES.append({"from": name, "role": "user", "text": text})
        reply = self.ai_reply(text)
        CHAT_MESSAGES.append({"from": "NIRA AI Assistant", "role": "ai", "text": reply})
        return self.send_json({"messages": CHAT_MESSAGES, "reply": reply})

    def ai_reply(self, text):
        lower = text.lower()
        if "hmo" in lower:
            return "For HMO deals, check Article 4 restrictions, room sizes, licence rules, fire safety, local demand, and bills-inclusive rent assumptions before sending it to an investor."
        if "subscription" in lower or "pay" in lower or "15" in lower:
            return "Full sourcing access is £15 per person per month in this prototype. Use the Subscription page to unlock all deals for the signed-in account."
        if "yield" in lower or "roi" in lower:
            return "Start with gross yield, then stress-test net yield after voids, management, repairs, insurance, utilities, finance costs, and licensing fees."
        if "technical" in lower or "bug" in lower:
            return "I have logged this for the technical team. Include the page name, what you clicked, and what you expected to happen so they can resolve it faster."
        return "Thanks. I can help with deal checks, HMO rules, sourcing workflow, subscriptions, technical questions, and investor pack preparation."

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
        row = self.current_user_row()
        return self.user_payload(row) if row else None

    def current_user_row(self):
        token = self.session_token()
        if not token:
            return None
        with db() as conn:
            row = conn.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
                (token,),
            ).fetchone()
        return row

    def user_payload(self, row):
        profile = SOURCERS[row["sourcer_index"]]
        return {"name": row["name"], "email": row["email"], "provider": row["provider"], "subscribed": bool(row["subscribed"]), "subscriptionPrice": row["subscription_price"], "profile": profile}

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
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", "8088"))
    print(f"NIRA & CO running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
