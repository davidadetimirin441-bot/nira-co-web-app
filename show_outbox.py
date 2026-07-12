import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "ratada.sqlite3"


def main():
    if not DB_PATH.exists():
        print("No database found yet.")
        return
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, recipient, subject, body, created_at FROM email_outbox ORDER BY id DESC LIMIT 10"
    ).fetchall()
    if not rows:
        print("Email outbox is empty.")
        return
    for row in rows:
        print("=" * 72)
        print(f"ID: {row['id']}")
        print(f"To: {row['recipient']}")
        print(f"Subject: {row['subject']}")
        print(f"Created: {row['created_at']}")
        print()
        print(row["body"])
        print()


if __name__ == "__main__":
    main()
