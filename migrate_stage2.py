from pathlib import Path
import shutil
import time

import server


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "ratada.sqlite3"


def main():
    if DB_PATH.exists():
        backup = ROOT / f"ratada.sqlite3.stage2-backup-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup created: {backup}")
    server.init_db()
    print("Stage 2 role and admin migration complete.")


if __name__ == "__main__":
    main()
