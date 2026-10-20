"""Initialise the SQLite database and seed the example plants.

    python init_db.py            create tables and seed example plants (safe to re-run)
    python init_db.py --reset    DELETE the database file first, then recreate it
"""
import argparse
import os

from app.config import DEFAULT_DB_PATH
from app.db import connect, init_db
from app.seed import seed_example_plants


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the existing database first")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="database file path")
    args = parser.parse_args()
    if args.reset:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(args.db + suffix):
                os.remove(args.db + suffix)
        print("Existing database removed.")
    init_db(args.db)
    conn = connect(args.db)
    try:
        added = seed_example_plants(conn)
    finally:
        conn.close()
    print(f"Database ready at {args.db} ({added} example plant(s) added).")


if __name__ == "__main__":
    main()
