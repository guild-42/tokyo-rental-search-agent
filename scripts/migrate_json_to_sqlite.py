#!/usr/bin/env python3
"""One-time migration: JSON data → SQLite.

Usage:
  python scripts/migrate_json_to_sqlite.py
  python scripts/migrate_json_to_sqlite.py --db data/rental.db
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.db import init_db, upsert_properties
from src.models import Property

import argparse
import json


def main():
    parser = argparse.ArgumentParser(description="Migrate JSON data to SQLite")
    parser.add_argument("--db", type=str, default=str(PROJECT_DIR / "data" / "rental.db"))
    parser.add_argument("--json", type=str, default=str(PROJECT_DIR / "data" / "latest.json"))
    args = parser.parse_args()

    json_path = Path(args.json)
    db_path = Path(args.db)

    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        sys.exit(1)

    raw_list = json.loads(json_path.read_text())
    print(f"Loaded {len(raw_list)} properties from {json_path}")

    properties = []
    for raw in raw_list:
        try:
            properties.append(Property(**raw))
        except Exception as e:
            print(f"  Skipping: {e}")

    conn = init_db(db_path)
    stats = upsert_properties(conn, properties)
    conn.close()

    print(f"\nMigration complete:")
    print(f"  Inserted:     {stats['inserted']}")
    print(f"  Updated:      {stats['updated']}")
    print(f"  Deduplicated: {stats['deduplicated']}")
    print(f"  Database:     {db_path}")


if __name__ == "__main__":
    main()
