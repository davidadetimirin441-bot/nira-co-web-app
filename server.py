from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import base64
import binascii
import html
import hashlib
import hmac
import json
import logging
import re
import os
import secrets
import smtplib
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
except ImportError:
    PasswordHasher = None
    VerifyMismatchError = Exception

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "ratada.sqlite3"
ASSETS = ROOT / "assets"
PROFILE_PHOTO_DIR = ASSETS / "profile-photos"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT") or os.environ.get("RATADA_PORT", "8088"))
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", str(60 * 60 * 24 * 365)))
RESET_TOKEN_MINUTES = int(os.environ.get("RESET_TOKEN_MINUTES", "30"))
VERIFY_TOKEN_HOURS = int(os.environ.get("VERIFY_TOKEN_HOURS", "24"))
MAX_PROFILE_PHOTO_BYTES = 1024 * 1024
SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
PAYMENT_ACCOUNT_NAME = os.environ.get("PAYMENT_ACCOUNT_NAME", "")
PAYMENT_BANK_NAME = os.environ.get("PAYMENT_BANK_NAME", "")
PAYMENT_ACCOUNT_NUMBER = os.environ.get("PAYMENT_ACCOUNT_NUMBER", "")
PAYMENT_SORT_CODE = os.environ.get("PAYMENT_SORT_CODE", "")
ENABLE_DEMO_SUBSCRIPTIONS = os.environ.get("ENABLE_DEMO_SUBSCRIPTIONS", "0") == "1"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SAFE_TEXT_RE = re.compile(r"[^a-zA-Z0-9 .,'&@+()/#-]")
RATE_LIMITS = {}
PASSWORD_PEPPER = SECRET_KEY.encode()
PASSWORD_HASHER = PasswordHasher() if PasswordHasher else None
ROLES = {"investor", "deal_sourcer", "estate_agent", "developer", "admin"}
ADMIN_EMAILS = {email.strip().lower() for email in os.environ.get("ADMIN_EMAILS", "").split(",") if email.strip()}

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("nira-auth")
if "SECRET_KEY" not in os.environ:
    LOGGER.warning("SECRET_KEY is not set. A temporary development secret was generated for this process.")

SOURCERS = [
    {"name": "Aisha Bello", "market": "UK North", "role": "Senior UK sourcer", "closeRate": 31, "saved": 14, "markets": 12, "tags": ["BTL", "HMO", "Off-market"]},
    {"name": "Callum Price", "market": "Midlands", "role": "Auction specialist", "closeRate": 24, "saved": 9, "markets": 8, "tags": ["Auction", "Flip", "Refurb"]},
    {"name": "Maya Khan", "market": "London and South East", "role": "Short-let and corporate-let sourcer", "closeRate": 28, "saved": 11, "markets": 7, "tags": ["Short let", "Corporate let", "Commuter"]},
    {"name": "Tunde Okafor", "market": "Scotland and Wales", "role": "Off-market UK sourcer", "closeRate": 36, "saved": 18, "markets": 10, "tags": ["Off-market", "Title review", "Yield"]},
    {"name": "Sofia Martins", "market": "South West and coastal UK", "role": "Holiday-let and refurb sourcer", "closeRate": 22, "saved": 7, "markets": 5, "tags": ["Holiday let", "Coastal", "Yield"]},
]

DEALS = [
    {"title": "Three-bed terrace near tram expansion", "location": "Manchester, England", "postcode": "M14", "region": "England", "strategy": "Buy-to-let", "source": "Agent", "price": 185000, "yield": 7.6, "discount": 14, "status": "Mortgageable", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1564013799919-ab600027ffc6?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/manchester/"},
    {"title": "Auction semi with permitted development angle", "location": "Birmingham, England", "postcode": "B11", "region": "England", "strategy": "Flip", "source": "Auction", "price": 142000, "yield": 9.1, "discount": 22, "status": "Refurb", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1570129477492-45c003edd2be?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/birmingham/"},
    {"title": "Coventry city-centre corporate-let apartment", "location": "Coventry, England", "postcode": "CV1", "region": "England", "strategy": "Short let", "source": "Agent", "price": 165000, "yield": 8.8, "discount": 11, "status": "Furnished", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/coventry/"},
    {"title": "Student HMO conversion candidate", "location": "Liverpool, England", "postcode": "L7", "region": "England", "strategy": "HMO", "source": "Off-market", "price": 236000, "yield": 10.4, "discount": 19, "status": "Planning check", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/liverpool/"},
    {"title": "Glasgow tenement flat with rent uplift", "location": "Glasgow, Scotland", "postcode": "G12", "region": "Scotland", "strategy": "Buy-to-let", "source": "Off-market", "price": 128000, "yield": 9.8, "discount": 17, "status": "Home report", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/glasgow/"},
    {"title": "Cornwall coastal holiday-let cottage", "location": "Newquay, England", "postcode": "TR7", "region": "England", "strategy": "Short let", "source": "Agent", "price": 310000, "yield": 7.2, "discount": 9, "status": "Viewing slots", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/newquay/"},
    {"title": "Six-bed HMO near university corridor", "location": "Leeds, England", "postcode": "LS6", "region": "England", "strategy": "HMO", "source": "Agent", "price": 285000, "yield": 11.6, "discount": 16, "status": "Article 4 check", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/leeds/"},
    {"title": "Licensed HMO with seven letting rooms", "location": "Nottingham, England", "postcode": "NG7", "region": "England", "strategy": "HMO", "source": "Off-market", "price": 352000, "yield": 12.3, "discount": 13, "status": "Licensed", "owner": "Aisha Bello", "image": "https://images.unsplash.com/photo-1572120360610-d971b9d7767c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/nottingham/"},
    {"title": "Victorian terrace conversion candidate", "location": "Sheffield, England", "postcode": "S10", "region": "England", "strategy": "HMO", "source": "Auction", "price": 178000, "yield": 10.9, "discount": 21, "status": "Refurb", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1560184897-ae75f418493e?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/sheffield/"},
    {"title": "Commuter belt buy-to-let semi", "location": "Luton, England", "postcode": "LU1", "region": "England", "strategy": "Buy-to-let", "source": "Agent", "price": 248000, "yield": 7.4, "discount": 10, "status": "Tenant demand", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/luton/"},
    {"title": "Below-market repossession terrace", "location": "Cardiff, Wales", "postcode": "CF24", "region": "Wales", "strategy": "Flip", "source": "Auction", "price": 164000, "yield": 8.1, "discount": 24, "status": "Legal pack", "owner": "Callum Price", "image": "https://images.unsplash.com/photo-1598228723793-52759bba239c?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/cardiff/"},
    {"title": "Edinburgh professional let near tram route", "location": "Edinburgh, Scotland", "postcode": "EH11", "region": "Scotland", "strategy": "Buy-to-let", "source": "Agent", "price": 285000, "yield": 7.9, "discount": 10, "status": "Rental demand", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1546412414-e1885259563a?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/edinburgh/"},
    {"title": "Aberdeen serviced apartment near harbour", "location": "Aberdeen, Scotland", "postcode": "AB24", "region": "Scotland", "strategy": "Short let", "source": "Agent", "price": 156000, "yield": 8.6, "discount": 8, "status": "Furnished", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/aberdeen/"},
    {"title": "Swansea two-flat conversion candidate", "location": "Swansea, Wales", "postcode": "SA1", "region": "Wales", "strategy": "Buy-to-let", "source": "Off-market", "price": 148000, "yield": 10.1, "discount": 18, "status": "Title review", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1605276374104-dee2a0ed3cd6?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/swansea/"},
    {"title": "Bristol professional HMO near hospital", "location": "Bristol, England", "postcode": "BS2", "region": "England", "strategy": "HMO", "source": "Off-market", "price": 410000, "yield": 9.8, "discount": 12, "status": "Licence check", "owner": "Tunde Okafor", "image": "https://images.unsplash.com/photo-1600607688969-a5bfcd646154?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/bristol/"},
    {"title": "Norwich commuter buy-to-let flat", "location": "Norwich, England", "postcode": "NR2", "region": "England", "strategy": "Buy-to-let", "source": "Agent", "price": 175000, "yield": 7.1, "discount": 7, "status": "Rent review", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/norwich/"},
    {"title": "Newport refurb apartment close to station", "location": "Newport, Wales", "postcode": "NP20", "region": "Wales", "strategy": "Flip", "source": "Auction", "price": 118000, "yield": 7.5, "discount": 17, "status": "Refurb", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/newport/"},
    {"title": "Leicester duplex with rent uplift", "location": "Leicester, England", "postcode": "LE2", "region": "England", "strategy": "Buy-to-let", "source": "Agent", "price": 238000, "yield": 8.9, "discount": 11, "status": "Occupied", "owner": "Maya Khan", "image": "https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/leicester/"},
    {"title": "Dundee student HMO near university", "location": "Dundee, Scotland", "postcode": "DD1", "region": "Scotland", "strategy": "HMO", "source": "Developer", "price": 205000, "yield": 10.6, "discount": 9, "status": "Licence check", "owner": "Sofia Martins", "image": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=640&q=80", "link": "https://www.zoopla.co.uk/for-sale/property/dundee/"},
]

CHAT_MESSAGES = [
    {"from": "Aisha Bello", "role": "sourcer", "text": "I can help with UK HMO checks, Article 4 areas, and rent comparables."},
    {"from": "Technical Team", "role": "support", "text": "Ask us about subscriptions, deal uploads, bugs, or account access."},
]


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            first_name TEXT DEFAULT '',
            last_name TEXT DEFAULT '',
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            sourcer_index INTEGER NOT NULL,
            phone TEXT DEFAULT '',
            profile_photo TEXT DEFAULT '',
            role TEXT DEFAULT 'investor',
            email_verified INTEGER DEFAULT 0,
            verification_token_hash TEXT DEFAULT '',
            verification_token_expires_at TEXT DEFAULT '',
            password_reset_token_hash TEXT DEFAULT '',
            password_reset_token_expires_at TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_login_at TEXT DEFAULT '',
            company TEXT DEFAULT '',
            city TEXT DEFAULT '',
            investor_type TEXT DEFAULT '',
            newsletter_opt_in INTEGER DEFAULT 1,
            subscribed INTEGER DEFAULT 0,
            subscription_price INTEGER DEFAULT 15
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            csrf_token TEXT DEFAULT '',
            expires_at TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            expires_at TEXT DEFAULT '',
            used_at TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS email_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan_name TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            billing_name TEXT NOT NULL,
            billing_email TEXT NOT NULL,
            card_last4 TEXT NOT NULL,
            method TEXT DEFAULT 'card',
            reference TEXT DEFAULT '',
            recipient_name TEXT DEFAULT '',
            recipient_bank TEXT DEFAULT '',
            recipient_account TEXT DEFAULT '',
            recipient_sort_code TEXT DEFAULT '',
            billing_cycle TEXT DEFAULT 'monthly',
            status TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ad_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT DEFAULT 'Google AdSense',
            publisher_id TEXT DEFAULT '',
            ad_slot TEXT DEFAULT '',
            monthly_page_views INTEGER DEFAULT 0,
            estimated_rpm REAL DEFAULT 3.0,
            active INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        had_email_verified = "email_verified" in columns
        for name, definition in {
            "first_name": "TEXT DEFAULT ''",
            "last_name": "TEXT DEFAULT ''",
            "phone": "TEXT DEFAULT ''",
            "profile_photo": "TEXT DEFAULT ''",
            "role": "TEXT DEFAULT 'investor'",
            "email_verified": "INTEGER DEFAULT 0",
            "verification_token_hash": "TEXT DEFAULT ''",
            "verification_token_expires_at": "TEXT DEFAULT ''",
            "password_reset_token_hash": "TEXT DEFAULT ''",
            "password_reset_token_expires_at": "TEXT DEFAULT ''",
            "created_at": "TEXT DEFAULT ''",
            "last_login_at": "TEXT DEFAULT ''",
            "company": "TEXT DEFAULT ''",
            "city": "TEXT DEFAULT ''",
            "investor_type": "TEXT DEFAULT ''",
            "newsletter_opt_in": "INTEGER DEFAULT 1",
            "subscribed": "INTEGER DEFAULT 0",
            "subscription_price": "INTEGER DEFAULT 15",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
        if not had_email_verified:
            conn.execute("UPDATE users SET email_verified = 1 WHERE email_verified = 0")
        conn.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at = ''")
        conn.execute("UPDATE users SET role = 'deal_sourcer' WHERE lower(investor_type) = 'deal sourcer' AND role = 'investor'")
        conn.execute("UPDATE users SET role = 'estate_agent' WHERE lower(investor_type) IN ('agent', 'estate agent') AND role = 'investor'")
        conn.execute("UPDATE users SET role = 'developer' WHERE lower(investor_type) = 'developer' AND role = 'investor'")
        for email in ADMIN_EMAILS:
            conn.execute("UPDATE users SET role = 'admin' WHERE email = ?", (email,))
        conn.execute("""
            UPDATE users
            SET first_name = CASE WHEN first_name = '' THEN trim(substr(name, 1, instr(name || ' ', ' ') - 1)) ELSE first_name END,
                last_name = CASE WHEN last_name = '' THEN trim(substr(name, instr(name || ' ', ' ') + 1)) ELSE last_name END
        """)
        session_columns = [row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()]
        for name, definition in {
            "csrf_token": "TEXT DEFAULT ''",
            "expires_at": "TEXT DEFAULT ''",
        }.items():
            if name not in session_columns:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {definition}")
        reset_columns = [row["name"] for row in conn.execute("PRAGMA table_info(password_resets)").fetchall()]
        for name, definition in {
            "expires_at": "TEXT DEFAULT ''",
            "used_at": "TEXT DEFAULT ''",
        }.items():
            if name not in reset_columns:
                conn.execute(f"ALTER TABLE password_resets ADD COLUMN {name} {definition}")
        payment_columns = [row["name"] for row in conn.execute("PRAGMA table_info(payments)").fetchall()]
        if "method" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN method TEXT DEFAULT 'card'")
        if "reference" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN reference TEXT DEFAULT ''")
        if "recipient_name" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN recipient_name TEXT DEFAULT ''")
        if "recipient_bank" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN recipient_bank TEXT DEFAULT ''")
        if "recipient_account" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN recipient_account TEXT DEFAULT ''")
        if "recipient_sort_code" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN recipient_sort_code TEXT DEFAULT ''")
        if "billing_cycle" not in payment_columns:
            conn.execute("ALTER TABLE payments ADD COLUMN billing_cycle TEXT DEFAULT 'monthly'")


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.replace(microsecond=0).isoformat()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def clean_text(value, limit=120):
    value = html.escape((value or "").strip(), quote=False)
    value = SAFE_TEXT_RE.sub("", value)
    return value[:limit]


def split_name(full_name):
    parts = clean_text(full_name, 160).split()
    first = parts[0] if parts else ""
    last = " ".join(parts[1:]) if len(parts) > 1 else ""
    return first, last, " ".join(parts)


def valid_email(email):
    return bool(EMAIL_RE.match((email or "").strip().lower()))


def valid_password(password):
    return len(password or "") >= 8


def role_from_type(value, email=""):
    if (email or "").lower() in ADMIN_EMAILS:
        return "admin"
    normalized = (value or "").strip().lower().replace("-", " ").replace("_", " ")
    mapping = {
        "deal sourcer": "deal_sourcer",
        "sourcer": "deal_sourcer",
        "estate agent": "estate_agent",
        "agent": "estate_agent",
        "developer": "developer",
        "landlord": "investor",
        "investor": "investor",
    }
    return mapping.get(normalized, "investor")


def password_hash(password, salt=None):
    if PASSWORD_HASHER:
        return "argon2$" + PASSWORD_HASHER.hash((password or "") + SECRET_KEY)
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt((password or "").encode() + PASSWORD_PEPPER, salt=salt.encode(), n=2**14, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password, stored):
    if not stored:
        return False
    if stored.startswith("argon2$") and PASSWORD_HASHER:
        try:
            return PASSWORD_HASHER.verify(stored.split("$", 1)[1], (password or "") + SECRET_KEY)
        except VerifyMismatchError:
            return False
    if stored.startswith("scrypt$"):
        _, salt, digest = stored.split("$", 2)
        check = hashlib.scrypt((password or "").encode() + PASSWORD_PEPPER, salt=salt.encode(), n=2**14, r=8, p=1).hex()
        return hmac.compare_digest(check, digest)
    if "$" in stored:
        salt, digest = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt.encode(), 120_000).hex()
        return hmac.compare_digest(check, digest)
    return False


def sourcer_index(email):
    return sum(ord(ch) for ch in email.lower()) % len(SOURCERS)


def token_hash(token):
    return hmac.new(SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


def app_base_url(handler=None):
    configured = os.environ.get("BASE_URL")
    if configured:
        return configured.rstrip("/")
    if handler:
        host = handler.headers.get("Host", f"{HOST}:{PORT}")
        return f"http://{host}"
    return f"http://{HOST}:{PORT}"


def build_auth_email(title, message, link):
    text_body = f"{title}\n\n{message}\n\n{link}\n\nIf you did not request this, you can ignore this email."
    safe_link = html.escape(link, quote=True)
    html_body = f"""<!doctype html>
<html><body style="font-family:Arial,sans-serif;color:#1d2430">
  <h1>{html.escape(title)}</h1>
  <p>{html.escape(message)}</p>
  <p><a href="{safe_link}" style="background:#0c7a63;color:white;padding:12px 16px;text-decoration:none;border-radius:7px;font-weight:bold">Open secure link</a></p>
  <p style="color:#65707c">If the button does not work, copy this link:<br>{safe_link}</p>
</body></html>"""
    return text_body, html_body


def send_email(recipient, subject, text_body, html_body=None):
    host = os.environ.get("SMTP_HOST")
    sender = os.environ.get("FROM_EMAIL")
    if not host or not sender:
        return "outbox"

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    port = int(os.environ.get("SMTP_PORT", "587"))
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    use_tls = os.environ.get("SMTP_TLS", "1") != "0"

    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
    return "sent"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/pricing", "/about", "/contact"}:
            return self.send_file(ROOT / "index.html", "text/html")
        if path in {"/app", "/dashboard", "/login", "/register", "/deals", "/saved-deals", "/messages", "/subscription", "/settings"}:
            return self.send_file(ROOT / "app.html", "text/html")
        if path == "/profile":
            if not self.current_user_row():
                return self.redirect("/login")
            return self.send_file(ROOT / "app.html", "text/html")
        if path == "/admin":
            user = self.current_user_row()
            if not user:
                return self.redirect("/login")
            if not self.is_admin(user):
                return self.html_message("Access denied", "This area is only available to NIRA & CO administrators.", ok=False)
            return self.send_file(ROOT / "app.html", "text/html")
        if path == "/reset":
            return self.send_file(ROOT / "reset.html", "text/html")
        if path == "/verify-email":
            token = (parse_qs(parsed.query).get("token") or [""])[0]
            return self.verify_email(token)
        if path == "/api/csrf":
            return self.csrf_response()
        if path == "/api/session":
            return self.send_json({"user": self.current_user()})
        if path == "/api/deals":
            return self.deals_response()
        if path == "/api/chat":
            return self.send_json({"messages": CHAT_MESSAGES})
        if path == "/api/ads":
            return self.ads_settings()
        if path == "/api/admin/stats":
            return self.admin_stats()
        if path.startswith("/assets/"):
            return self.send_asset(path.replace("/assets/", "", 1))
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            data = self.read_json()
        except ValueError:
            return self.send_json({"error": "Invalid JSON"}, HTTPStatus.BAD_REQUEST)
        if path != "/api/csrf" and not self.valid_csrf(data):
            return self.send_json({"error": "Security check failed. Refresh the page and try again."}, HTTPStatus.FORBIDDEN)
        if path == "/api/signup":
            return self.signup(data)
        if path == "/api/signin":
            return self.signin(data)
        if path == "/api/verify-email/resend":
            return self.resend_verification(data)
        if path == "/api/signout":
            return self.signout()
        if path == "/api/password-reset/request":
            return self.request_password_reset(data)
        if path == "/api/password-reset/confirm":
            return self.confirm_password_reset(data)
        if path == "/api/subscribe":
            return self.subscribe(data)
        if path == "/api/profile":
            return self.update_profile(data)
        if path == "/api/newsletter/send":
            return self.send_weekly_newsletter()
        if path == "/api/ads":
            return self.save_ads_settings(data)
        if path == "/api/chat":
            return self.chat(data)
        self.send_error(HTTPStatus.NOT_FOUND)

    def signup(self, data):
        if not self.rate_limit("signup", 5, 600):
            return self.send_json({"error": "Too many sign-up attempts. Please wait and try again."}, HTTPStatus.TOO_MANY_REQUESTS)
        name = clean_text(data.get("name"), 160)
        first_name = clean_text(data.get("firstName"), 80)
        last_name = clean_text(data.get("lastName"), 80)
        if not first_name and not last_name:
            first_name, last_name, name = split_name(name)
        else:
            name = f"{first_name} {last_name}".strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        phone = clean_text(data.get("phone"), 40)
        company = clean_text(data.get("company"), 120)
        city = clean_text(data.get("city"), 80)
        investor_type = clean_text(data.get("investorType"), 60)
        role = role_from_type(investor_type, email)
        newsletter = 1 if data.get("newsletter", True) else 0
        if not first_name or not valid_email(email) or not valid_password(password):
            return self.send_json({"error": "Enter first name, valid email, and a password of at least 8 characters."}, HTTPStatus.BAD_REQUEST)
        verify_token = secrets.token_urlsafe(40)
        verify_expires = iso(now_utc() + timedelta(hours=VERIFY_TOKEN_HOURS))
        try:
            with db() as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        name, first_name, last_name, email, password_hash, provider, sourcer_index,
                        phone, company, city, investor_type, role, newsletter_opt_in, email_verified,
                        verification_token_hash, verification_token_expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, first_name, last_name, email, password_hash(password), "Email", sourcer_index(email), phone, company, city, investor_type, role, newsletter, 0, token_hash(verify_token), verify_expires),
                )
        except sqlite3.IntegrityError:
            return self.send_json({"error": "Account already exists. Use Sign in with the same email and password, or use Forgot password."}, HTTPStatus.CONFLICT)
        self.send_verification_email(email, verify_token)
        LOGGER.info("auth.signup email=%s", email)
        return self.send_json({"message": "Account created. Please check your email and verify your account before signing in."}, HTTPStatus.CREATED)

    def signin(self, data):
        if not self.rate_limit("signin", 8, 600):
            return self.send_json({"error": "Too many sign-in attempts. Please wait and try again."}, HTTPStatus.TOO_MANY_REQUESTS)
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user:
            LOGGER.info("auth.login_missing email=%s", email)
            return self.send_json({"error": "No account was found for this email address."}, HTTPStatus.UNAUTHORIZED)
        if not verify_password(password, user["password_hash"]):
            LOGGER.info("auth.login_bad_password user_id=%s", user["id"])
            return self.send_json({"error": "The password is incorrect."}, HTTPStatus.UNAUTHORIZED)
        if not user["email_verified"]:
            LOGGER.info("auth.login_unverified user_id=%s", user["id"])
            return self.send_json({"error": "Please verify your email before signing in.", "unverified": True}, HTTPStatus.FORBIDDEN)
        return self.create_session(email)

    def request_password_reset(self, data):
        if not self.rate_limit("password_reset", 5, 600):
            return self.send_json({"message": "If an account exists for this email, a reset link has been sent."})
        email = (data.get("email") or "").strip().lower()
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user:
                token = secrets.token_urlsafe(32)
                expires_at = iso(now_utc() + timedelta(minutes=RESET_TOKEN_MINUTES))
                hashed = token_hash(token)
                conn.execute(
                    "INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)",
                    (hashed, user["id"], expires_at),
                )
                conn.execute(
                    "UPDATE users SET password_reset_token_hash = ?, password_reset_token_expires_at = ? WHERE id = ?",
                    (hashed, expires_at, user["id"]),
                )
                reset_link = f"{app_base_url(self)}/reset?token={token}"
                text_body, html_body = build_auth_email(
                    "Reset your NIRA & CO password",
                    "Use this secure link to create a new password.",
                    reset_link,
                )
                conn.execute(
                    "INSERT INTO email_outbox (recipient, subject, body) VALUES (?, ?, ?)",
                    (email, "Reset your NIRA & CO password", text_body),
                )
                send_email(email, "Reset your NIRA & CO password", text_body, html_body)
                LOGGER.info("auth.password_reset_requested user_id=%s", user["id"])
        return self.send_json({"message": "If an account exists for this email, a reset link has been sent."})

    def confirm_password_reset(self, data):
        token = (data.get("token") or "").strip()
        password = data.get("password") or ""
        if not valid_password(password):
            return self.send_json({"error": "Use at least 8 characters for the new password."}, HTTPStatus.BAD_REQUEST)
        with db() as conn:
            reset = conn.execute("SELECT * FROM password_resets WHERE token = ? AND used = 0", (token_hash(token),)).fetchone()
            if not reset:
                reset = conn.execute("SELECT * FROM password_resets WHERE token = ? AND used = 0", (token,)).fetchone()
            if not reset:
                return self.send_json({"error": "Reset link is invalid or already used."}, HTTPStatus.BAD_REQUEST)
            expires = parse_dt(reset["expires_at"])
            if expires and expires < now_utc():
                return self.send_json({"error": "Reset link has expired. Please request a new one."}, HTTPStatus.BAD_REQUEST)
            conn.execute(
                "UPDATE users SET password_hash = ?, password_reset_token_hash = '', password_reset_token_expires_at = '' WHERE id = ?",
                (password_hash(password), reset["user_id"]),
            )
            conn.execute("UPDATE password_resets SET used = 1, used_at = CURRENT_TIMESTAMP WHERE token = ?", (reset["token"],))
            user = conn.execute("SELECT * FROM users WHERE id = ?", (reset["user_id"],)).fetchone()
        LOGGER.info("auth.password_reset_confirmed user_id=%s", user["id"])
        return self.create_session(user["email"])

    def signout(self):
        token = self.session_token()
        if token:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        LOGGER.info("auth.logout")
        self.send_response(HTTPStatus.OK)
        self.set_cookie("ratada_session", "", 0, http_only=True)
        self.set_cookie("nira_csrf", "", 0, http_only=False)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def subscribe(self, data):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before subscribing."}, HTTPStatus.UNAUTHORIZED)
        payer_name = clean_text(data.get("payerName") or user["name"], 120)
        payer_email = (data.get("payerEmail") or user["email"]).strip().lower()
        if not payer_name or not valid_email(payer_email):
            return self.send_json({"error": "Enter payer name and payer email."}, HTTPStatus.BAD_REQUEST)
        if not ENABLE_DEMO_SUBSCRIPTIONS:
            LOGGER.info("subscription.interest_recorded user_id=%s", user["id"])
            return self.send_json({
                "user": self.user_payload(user),
                "message": "Subscription interest saved. Secure Stripe Checkout will be connected before real payments are accepted."
            })
        with db() as conn:
            conn.execute("UPDATE users SET subscribed = 1, subscription_price = 15 WHERE id = ?", (user["id"],))
            conn.execute(
                "INSERT INTO payments (user_id, plan_name, amount, currency, billing_name, billing_email, card_last4, method, reference, recipient_name, recipient_bank, recipient_account, recipient_sort_code, billing_cycle, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user["id"], "Full sourcing monthly", 15, "GBP", payer_name, payer_email, "demo", "demo", "demo", "", "", "", "", "monthly", "active"),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        return self.send_json({"user": self.user_payload(updated), "message": "Demo subscription enabled for local testing only."})

    def ads_settings(self):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before viewing ad settings."}, HTTPStatus.UNAUTHORIZED)
        if not self.is_admin(user):
            return self.send_json({"error": "Admin permission is required."}, HTTPStatus.FORBIDDEN)
        with db() as conn:
            settings = conn.execute(
                "SELECT * FROM ad_settings WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user["id"],),
            ).fetchone()
        return self.send_json({"ads": self.ads_payload(settings)})

    def save_ads_settings(self, data):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before saving ad settings."}, HTTPStatus.UNAUTHORIZED)
        if not self.is_admin(user):
            return self.send_json({"error": "Admin permission is required."}, HTTPStatus.FORBIDDEN)
        publisher_id = (data.get("publisherId") or "").strip()
        ad_slot = (data.get("adSlot") or "").strip()
        try:
            monthly_page_views = max(0, int(data.get("monthlyPageViews") or 0))
            estimated_rpm = max(0, float(data.get("estimatedRpm") or 0))
        except (TypeError, ValueError):
            return self.send_json({"error": "Enter valid page views and RPM."}, HTTPStatus.BAD_REQUEST)
        active = 1 if data.get("active") else 0
        with db() as conn:
            existing = conn.execute("SELECT id FROM ad_settings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE ad_settings SET publisher_id = ?, ad_slot = ?, monthly_page_views = ?, estimated_rpm = ?, active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (publisher_id, ad_slot, monthly_page_views, estimated_rpm, active, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO ad_settings (user_id, publisher_id, ad_slot, monthly_page_views, estimated_rpm, active) VALUES (?, ?, ?, ?, ?, ?)",
                    (user["id"], publisher_id, ad_slot, monthly_page_views, estimated_rpm, active),
                )
            settings = conn.execute("SELECT * FROM ad_settings WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user["id"],)).fetchone()
        return self.send_json({"ads": self.ads_payload(settings), "message": "Google Ads earning setup saved."})

    def ads_payload(self, row):
        if not row:
            return {
                "provider": "Google AdSense",
                "publisherId": "",
                "adSlot": "",
                "monthlyPageViews": 0,
                "estimatedRpm": 3.0,
                "active": False,
                "estimatedMonthlyRevenue": 0,
            }
        revenue = (row["monthly_page_views"] / 1000) * row["estimated_rpm"]
        return {
            "provider": row["provider"],
            "publisherId": row["publisher_id"],
            "adSlot": row["ad_slot"],
            "monthlyPageViews": row["monthly_page_views"],
            "estimatedRpm": row["estimated_rpm"],
            "active": bool(row["active"]),
            "estimatedMonthlyRevenue": round(revenue, 2),
        }

    def update_profile(self, data):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before updating your profile."}, HTTPStatus.UNAUTHORIZED)
        first_name = clean_text(data.get("firstName"), 80)
        last_name = clean_text(data.get("lastName"), 80)
        full_name = clean_text(data.get("name") or f"{first_name} {last_name}", 160)
        if not first_name and full_name:
            first_name, last_name, full_name = split_name(full_name)
        try:
            profile_photo = self.save_profile_photo(data.get("profilePhoto"), user["id"]) if data.get("profilePhoto") else user["profile_photo"]
        except (ValueError, binascii.Error):
            return self.send_json({"error": "Profile photo must be PNG, JPEG or WEBP and under 1MB."}, HTTPStatus.BAD_REQUEST)
        fields = {
            "name": full_name or user["name"],
            "first_name": first_name or user["first_name"],
            "last_name": last_name,
            "phone": clean_text(data.get("phone"), 40),
            "profile_photo": profile_photo,
            "company": clean_text(data.get("company"), 120),
            "city": clean_text(data.get("city"), 80),
            "investor_type": clean_text(data.get("investorType"), 60),
            "role": user["role"] if user["role"] == "admin" else role_from_type(data.get("investorType"), user["email"]),
            "newsletter_opt_in": 1 if data.get("newsletter", False) else 0,
        }
        if not fields["name"]:
            return self.send_json({"error": "Name is required."}, HTTPStatus.BAD_REQUEST)
        with db() as conn:
            conn.execute(
                "UPDATE users SET name = ?, first_name = ?, last_name = ?, phone = ?, profile_photo = ?, company = ?, city = ?, investor_type = ?, role = ?, newsletter_opt_in = ? WHERE id = ?",
                (fields["name"], fields["first_name"], fields["last_name"], fields["phone"], fields["profile_photo"], fields["company"], fields["city"], fields["investor_type"], fields["role"], fields["newsletter_opt_in"], user["id"]),
            )
            updated = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        LOGGER.info("auth.profile_updated user_id=%s", user["id"])
        return self.send_json({"user": self.user_payload(updated), "message": "User details saved."})

    def send_weekly_newsletter(self):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before sending newsletters."}, HTTPStatus.UNAUTHORIZED)
        if not self.is_admin(user):
            return self.send_json({"error": "Admin permission is required."}, HTTPStatus.FORBIDDEN)
        featured = sorted(DEALS, key=lambda d: (d["yield"], d["discount"]), reverse=True)[:6]
        deal_lines = "\n".join(
            f"- {deal['title']} | {deal['location']} | {deal['strategy']} | {deal['yield']}% yield | {deal['link']}"
            for deal in featured
        )
        subject = "NIRA & CO weekly property deals"
        delivery_counts = {"sent": 0, "outbox": 0}
        with db() as conn:
            recipients = conn.execute("SELECT email, name FROM users WHERE newsletter_opt_in = 1").fetchall()
            for recipient in recipients:
                body = (
                    f"Hello {recipient['name']},\n\n"
                    "Here are this week's available NIRA & CO sourcing opportunities:\n\n"
                    f"{deal_lines}\n\n"
                    "Paid members unlock full sourcing packs, property links, sourcer chat and pipeline support.\n"
                    "Visit https://niraandco.co.uk/app to view deals.\n"
                )
                conn.execute("INSERT INTO email_outbox (recipient, subject, body) VALUES (?, ?, ?)", (recipient["email"], subject, body))
                delivery = send_email(recipient["email"], subject, body)
                delivery_counts["sent" if delivery == "sent" else "outbox"] += 1
        return self.send_json({"message": f"Weekly newsletter prepared for {len(recipients)} subscribed users.", "sent": delivery_counts["sent"], "outbox": delivery_counts["outbox"]})

    def admin_stats(self):
        user = self.current_user_row()
        if not user:
            return self.send_json({"error": "Sign in before opening admin."}, HTTPStatus.UNAUTHORIZED)
        if not self.is_admin(user):
            return self.send_json({"error": "Admin permission is required."}, HTTPStatus.FORBIDDEN)
        with db() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            verified = conn.execute("SELECT COUNT(*) FROM users WHERE email_verified = 1").fetchone()[0]
            subscribers = conn.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1").fetchone()[0]
            outbox = conn.execute("SELECT COUNT(*) FROM email_outbox").fetchone()[0]
            payments = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
            roles = [
                {"role": row["role"] or "investor", "count": row["count"]}
                for row in conn.execute("SELECT role, COUNT(*) AS count FROM users GROUP BY role ORDER BY count DESC").fetchall()
            ]
        return self.send_json({
            "stats": {
                "users": users,
                "verifiedUsers": verified,
                "subscribers": subscribers,
                "outboxEmails": outbox,
                "paymentRecords": payments,
                "dealCount": len(DEALS),
                "roles": roles,
            }
        })

    def deals_response(self):
        user = self.current_user_row()
        has_payment = False
        if user:
            with db() as conn:
                has_payment = conn.execute(
                    "SELECT 1 FROM payments WHERE user_id = ? AND status = 'active' LIMIT 1",
                    (user["id"],),
                ).fetchone() is not None
        return self.send_json({"deals": DEALS, "sourcers": SOURCERS, "fullAccess": bool(user and user["subscribed"] and has_payment)})

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
        csrf_token = secrets.token_urlsafe(32)
        expires_at = iso(now_utc() + timedelta(seconds=SESSION_MAX_AGE))
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
            conn.execute("INSERT INTO sessions (token, user_id, csrf_token, expires_at) VALUES (?, ?, ?, ?)", (token, user["id"], csrf_token, expires_at))
            conn.execute("UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        LOGGER.info("auth.login_success user_id=%s", user["id"])
        self.send_response(HTTPStatus.OK)
        self.set_cookie("ratada_session", token, SESSION_MAX_AGE, http_only=True)
        self.set_cookie("nira_csrf", csrf_token, SESSION_MAX_AGE, http_only=False)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"user": self.user_payload(user), "csrfToken": csrf_token}).encode())

    def send_verification_email(self, email, token):
        verify_link = f"{app_base_url(self)}/verify-email?token={token}"
        text_body, html_body = build_auth_email(
            "Verify your NIRA & CO email",
            "Please verify your email address before signing in.",
            verify_link,
        )
        with db() as conn:
            conn.execute(
                "INSERT INTO email_outbox (recipient, subject, body) VALUES (?, ?, ?)",
                (email, "Verify your NIRA & CO email", text_body),
            )
        return send_email(email, "Verify your NIRA & CO email", text_body, html_body)

    def verify_email(self, token):
        hashed = token_hash(token)
        with db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE verification_token_hash = ? AND email_verified = 0",
                (hashed,),
            ).fetchone()
            if not user:
                return self.html_message("Email verification failed", "This verification link is invalid or has already been used.", ok=False)
            expires = parse_dt(user["verification_token_expires_at"])
            if expires and expires < now_utc():
                return self.html_message("Email verification failed", "This verification link has expired. Open the app and request a new verification email.", ok=False)
            conn.execute(
                "UPDATE users SET email_verified = 1, verification_token_hash = '', verification_token_expires_at = '' WHERE id = ?",
                (user["id"],),
            )
        LOGGER.info("auth.email_verified user_id=%s", user["id"])
        return self.html_message("Email verified", "Your NIRA & CO account is verified. You can now sign in.", ok=True)

    def resend_verification(self, data):
        if not self.rate_limit("verify_resend", 5, 600):
            return self.send_json({"message": "If the account needs verification, a new email has been sent."})
        email = (data.get("email") or "").strip().lower()
        if valid_email(email):
            with db() as conn:
                user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
                if user and not user["email_verified"]:
                    token = secrets.token_urlsafe(40)
                    conn.execute(
                        "UPDATE users SET verification_token_hash = ?, verification_token_expires_at = ? WHERE id = ?",
                        (token_hash(token), iso(now_utc() + timedelta(hours=VERIFY_TOKEN_HOURS)), user["id"]),
                    )
                    self.send_verification_email(email, token)
                    LOGGER.info("auth.verification_resent user_id=%s", user["id"])
        return self.send_json({"message": "If the account needs verification, a new email has been sent."})

    def csrf_response(self):
        token = secrets.token_urlsafe(32)
        self.send_response(HTTPStatus.OK)
        self.set_cookie("nira_csrf", token, SESSION_MAX_AGE, http_only=False)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"csrfToken": token}).encode())

    def valid_csrf(self, data):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        expected = cookie.get("nira_csrf")
        provided = self.headers.get("X-CSRF-Token") or (data or {}).get("csrfToken")
        return bool(expected and provided and hmac.compare_digest(expected.value, provided))

    def rate_limit(self, action, limit, seconds):
        key = f"{self.client_address[0]}:{action}"
        current = time.time()
        attempts = [stamp for stamp in RATE_LIMITS.get(key, []) if current - stamp < seconds]
        if len(attempts) >= limit:
            RATE_LIMITS[key] = attempts
            return False
        attempts.append(current)
        RATE_LIMITS[key] = attempts
        return True

    def save_profile_photo(self, value, user_id):
        value = (value or "").strip()
        if not value:
            return ""
        if value.startswith("http://") or value.startswith("https://") or value.startswith("/assets/"):
            return html.escape(value[:500], quote=True)
        if not value.startswith("data:image/"):
            raise ValueError("Profile photo must be PNG, JPEG or WEBP.")
        header, encoded = value.split(",", 1)
        media_type = header.split(";", 1)[0].replace("data:", "")
        extensions = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if media_type not in extensions:
            raise ValueError("Profile photo must be PNG, JPEG or WEBP.")
        blob = base64.b64decode(encoded, validate=True)
        if len(blob) > MAX_PROFILE_PHOTO_BYTES:
            raise ValueError("Profile photo must be under 1MB.")
        filename = f"user-{user_id}-{secrets.token_hex(8)}{extensions[media_type]}"
        (PROFILE_PHOTO_DIR / filename).write_bytes(blob)
        return f"/assets/profile-photos/{filename}"

    def is_admin(self, user):
        return bool(user and (user["role"] == "admin" or user["email"].lower() in ADMIN_EMAILS))

    def current_user(self):
        row = self.current_user_row()
        return self.user_payload(row) if row else None

    def current_user_row(self):
        token = self.session_token()
        if not token:
            return None
        with db() as conn:
            row = conn.execute(
                "SELECT users.*, sessions.expires_at AS session_expires_at FROM sessions JOIN users ON users.id = sessions.user_id WHERE sessions.token = ?",
                (token,),
            ).fetchone()
            if row:
                expires = parse_dt(row["session_expires_at"])
                if expires and expires < now_utc():
                    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                    return None
        return row

    def user_payload(self, row):
        profile = SOURCERS[row["sourcer_index"]]
        with db() as conn:
            payment = conn.execute(
                "SELECT method, reference, recipient_name, recipient_bank, recipient_account, recipient_sort_code, billing_cycle, status FROM payments WHERE user_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "firstName": row["first_name"],
            "lastName": row["last_name"],
            "email": row["email"],
            "emailVerified": bool(row["email_verified"]),
            "role": "admin" if row["email"].lower() in ADMIN_EMAILS else row["role"],
            "isAdmin": bool(row["role"] == "admin" or row["email"].lower() in ADMIN_EMAILS),
            "provider": row["provider"],
            "phone": row["phone"],
            "profilePhoto": row["profile_photo"],
            "company": row["company"],
            "city": row["city"],
            "createdAt": row["created_at"],
            "lastLoginAt": row["last_login_at"],
            "investorType": row["investor_type"],
            "newsletter": bool(row["newsletter_opt_in"]),
            "subscribed": bool(row["subscribed"] and payment),
            "subscriptionPrice": row["subscription_price"],
            "paymentMethod": payment["method"] if payment else None,
            "paymentReference": None,
            "paymentRecipient": "Stripe Checkout",
            "paymentBank": None,
            "paymentAccountNumber": None,
            "paymentSortCode": None,
            "billingCycle": payment["billing_cycle"] if payment else "monthly",
            "profile": profile
        }

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

    def set_cookie(self, name, value, max_age, http_only=True):
        secure = "; Secure" if os.environ.get("COOKIE_SECURE", "0") == "1" or os.environ.get("BASE_URL", "").startswith("https://") else ""
        http_only_flag = "; HttpOnly" if http_only else ""
        self.send_header("Set-Cookie", f"{name}={value}; Path=/; Max-Age={max_age}{http_only_flag}; SameSite=Lax{secure}")

    def redirect(self, location):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def html_message(self, title, message, ok=True):
        color = "#0c7a63" if ok else "#bf7c1f"
        body = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} | NIRA & CO</title><style>body{{margin:0;min-height:100vh;display:grid;place-items:center;font-family:Inter,system-ui,sans-serif;background:#f6f2fa;color:#1d2430}}main{{width:min(480px,calc(100% - 32px));background:white;border:1px solid #e2d9ec;border-radius:8px;padding:24px;box-shadow:0 18px 42px rgba(23,33,28,.16)}}h1{{color:{color};margin-top:0}}a{{display:inline-flex;min-height:42px;align-items:center;padding:0 14px;border-radius:7px;background:#0c7a63;color:white;text-decoration:none;font-weight:900}}</style></head><body><main><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p><a href="/app">Open NIRA & CO</a></main></body></html>"""
        self.send_response(HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def send_file(self, path, content_type):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.end_headers()
        self.wfile.write(path.read_bytes())

    def send_asset(self, name):
        path = (ASSETS / name).resolve()
        if not str(path).startswith(str(ASSETS.resolve())) or not path.exists():
            return self.send_error(HTTPStatus.NOT_FOUND)
        types = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
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
