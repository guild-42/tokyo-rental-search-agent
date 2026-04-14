#!/usr/bin/env python3
"""Tokyo Rental Search Agent - CLI entry point.

Environment variables for server mode:
  FETCH_SCHEDULE_HOURS  - Fetch hours, comma-separated (default: "9,12,15,18,21")
  FETCH_MAX_PAGES       - Max pages per scraper per fetch (default: 10)
  FETCH_WARD_CODES      - Comma-separated ward codes (default: all 23 wards)
  DB_PATH               - SQLite database path (default: data/rental.db)
  MAX_AGE_DAYS          - Show properties within N days (default: 7)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
DATA_DIR = PROJECT_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "rental.db"

sys.path.insert(0, str(PROJECT_DIR))


def cmd_fetch(args):
    """Fetch latest rental listings into SQLite."""
    from src.orchestrator import fetch_all
    from src.scrapers.suumo import TOKYO_WARD_CODES

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH

    ward_codes = None
    if args.wards:
        ward_codes = []
        for w in args.wards.split(","):
            w = w.strip()
            if w in TOKYO_WARD_CODES:
                ward_codes.append(TOKYO_WARD_CODES[w])
            else:
                print(f"Unknown ward: {w}")
                print(f"Available: {', '.join(TOKYO_WARD_CODES.keys())}")
                return

    result = asyncio.run(fetch_all(db_path, ward_codes=ward_codes, max_pages=args.pages))

    print(f"\n{'='*50}")
    print(f"  Fetch complete")
    print(f"  Sources:    {', '.join(result.sources_searched)}")
    print(f"  Total:      {result.total_results} properties")
    print(f"  New:        {result.new_inserted} inserted")
    print(f"  Deduped:    {result.duplicates_removed} removed")
    if result.errors:
        print(f"  Errors:     {len(result.errors)}")
        for e in result.errors:
            print(f"    - [{e['source']}] {e['error']}")
    print(f"  Database:   {db_path}")
    print(f"{'='*50}\n")


def cmd_serve(args):
    """Start the FastAPI web server."""
    import uvicorn

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH

    # Set env vars for the server
    os.environ.setdefault("DB_PATH", str(db_path))
    os.environ.setdefault("FETCH_SCHEDULE_HOURS", args.schedule)
    os.environ.setdefault("MAX_AGE_DAYS", str(args.max_age))

    print(f"\n  いい物件は7日まで")
    print(f"  http://localhost:{args.port}")
    print(f"  DB: {db_path}")
    print(f"  Fetch schedule: {args.schedule}" if args.schedule else "  Fetch schedule: disabled")
    print(f"  Max age: {args.max_age} days\n")

    uvicorn.run(
        "src.server:app",
        host="0.0.0.0",
        port=args.port,
        log_level="info",
    )


def cmd_stats(args):
    """Display database statistics."""
    from src.db import get_stats, init_db

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run 'python main.py fetch' first.")
        return

    conn = init_db(db_path)
    stats = get_stats(conn)
    conn.close()

    print(f"\n{'='*50}")
    print(f"  Database: {db_path}")
    print(f"  Total properties: {stats['total']}")
    print(f"  Active (7 days):  {stats['active_7d']}")
    print(f"  By status:")
    for status, count in stats.get("by_status", {}).items():
        print(f"    {status}: {count}")
    print(f"  By source:")
    for source, count in stats.get("by_source", {}).items():
        print(f"    {source}: {count}")
    if stats.get("last_fetch"):
        print(f"  Last fetch: {stats['last_fetch']}")
    print(f"{'='*50}\n")


def cmd_verify(args):
    """Compare advertised total counts vs. actually-scraped counts per source."""
    from src.scrapers.suumo import TOKYO_WARD_CODES
    from src.verify import format_report, verify_coverage

    ward_codes = None
    if args.wards:
        ward_codes = []
        for w in args.wards.split(","):
            w = w.strip()
            if w in TOKYO_WARD_CODES:
                ward_codes.append(TOKYO_WARD_CODES[w])
            else:
                print(f"Unknown ward: {w}")
                return

    print(f"Running coverage check (pages={args.pages}, wards={ward_codes or 'default'})...\n")
    reports = asyncio.run(verify_coverage(ward_codes, max_pages=args.pages))
    print(format_report(reports))


def cmd_prune(args):
    """Delete DB rows outside the allowed wards and above the rent cap."""
    from src.db import init_db, prune_rent_cap, prune_wards
    from src.orchestrator import ALLOWED_WARD_NAMES
    from src.scrapers.constants import RENT_MAX_YEN

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    conn = init_db(db_path)
    by_ward = prune_wards(conn, list(ALLOWED_WARD_NAMES))
    by_rent = prune_rent_cap(conn, RENT_MAX_YEN)
    conn.close()
    print(f"Pruned {by_ward} outside {list(ALLOWED_WARD_NAMES)}, {by_rent} with rent > {RENT_MAX_YEN}")


def cmd_migrate(args):
    """Migrate existing JSON data to SQLite (one-time)."""
    from src.db import init_db, upsert_properties
    from src.models import Property

    db_path = Path(args.db) if args.db else DEFAULT_DB_PATH
    latest_json = DATA_DIR / "latest.json"

    if not latest_json.exists():
        print(f"No JSON data found at {latest_json}")
        return

    # Load JSON data
    raw_list = json.loads(latest_json.read_text())
    print(f"Loaded {len(raw_list)} properties from {latest_json}")

    # Convert to Property models
    properties = []
    for raw in raw_list:
        try:
            properties.append(Property(**raw))
        except Exception as e:
            print(f"  Skipping invalid entry: {e}")

    # Insert into SQLite
    conn = init_db(db_path)
    stats = upsert_properties(conn, properties)
    conn.close()

    print(f"\nMigration complete:")
    print(f"  Inserted:     {stats['inserted']}")
    print(f"  Deduplicated: {stats['deduplicated']}")
    print(f"  Database:     {db_path}")

    # Also try history files
    history_dir = DATA_DIR / "history"
    if history_dir.exists():
        history_files = sorted(history_dir.glob("*.json"))
        print(f"\n  Found {len(history_files)} history files (not migrated - latest.json is sufficient)")


def main():
    parser = argparse.ArgumentParser(
        description="いい物件は7日まで - Tokyo Rental Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py fetch                           # Fetch all Tokyo 23 wards
  python main.py fetch --wards "渋谷区,目黒区"     # Specific wards
  python main.py fetch --pages 5                 # Limit pages per source
  python main.py serve                           # Start web server
  python main.py serve --port 3000               # Custom port
  python main.py serve --schedule "9,12,15,18,21" # Fetch at specific hours
  python main.py stats                           # Show DB statistics
  python main.py verify                          # Check advertised vs actual count per source
  python main.py prune                           # Delete properties outside 新宿/渋谷/中野
  python main.py migrate                         # Migrate JSON → SQLite

Environment variables:
  FETCH_SCHEDULE_HOURS  Fetch hours, comma-separated (default: 9,12,15,18,21)
  FETCH_MAX_PAGES       Pages per scraper (default: 10)
  FETCH_WARD_CODES      Ward codes, comma-separated
  DB_PATH               SQLite path (default: data/rental.db)
  MAX_AGE_DAYS          Property display age (default: 7)
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    sub = parser.add_subparsers(dest="command", required=True)

    # fetch
    fetch_p = sub.add_parser("fetch", help="Fetch latest rental listings")
    fetch_p.add_argument("--wards", type=str, default=None, help="Comma-separated ward names (e.g. '渋谷区,目黒区')")
    fetch_p.add_argument("--pages", type=int, default=None, help="(Ignored — each scraper uses its own max_pages; kept for backward compat)")
    fetch_p.add_argument("--db", type=str, default=None, help="Database path (default: data/rental.db)")
    fetch_p.set_defaults(func=cmd_fetch)

    # serve
    serve_p = sub.add_parser("serve", help="Start web server")
    serve_p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")), help="Server port (default: 8080)")
    serve_p.add_argument("--schedule", type=str, default=os.environ.get("FETCH_SCHEDULE_HOURS", "9,12,15,18,21"), help="Fetch schedule hours, comma-separated (default: 9,12,15,18,21)")
    serve_p.add_argument("--max-age", type=int, default=int(os.environ.get("MAX_AGE_DAYS", "7")), help="Max property age in days (default: 7)")
    serve_p.add_argument("--db", type=str, default=None, help="Database path (default: data/rental.db)")
    serve_p.set_defaults(func=cmd_serve)

    # stats
    stats_p = sub.add_parser("stats", help="Show database statistics")
    stats_p.add_argument("--db", type=str, default=None, help="Database path (default: data/rental.db)")
    stats_p.set_defaults(func=cmd_stats)

    # migrate
    migrate_p = sub.add_parser("migrate", help="Migrate JSON data to SQLite (one-time)")
    migrate_p.add_argument("--db", type=str, default=None, help="Database path (default: data/rental.db)")
    migrate_p.set_defaults(func=cmd_migrate)

    # prune
    prune_p = sub.add_parser("prune", help="Delete properties outside 新宿/渋谷/中野 (one-time)")
    prune_p.add_argument("--db", type=str, default=None, help="Database path (default: data/rental.db)")
    prune_p.set_defaults(func=cmd_prune)

    # verify
    verify_p = sub.add_parser("verify", help="Compare advertised vs. scraped counts per source")
    verify_p.add_argument("--wards", type=str, default=None, help="Comma-separated ward names (default: the configured set)")
    verify_p.add_argument("--pages", type=int, default=None, help="Max pages per source (default: use each scraper's own setting)")
    verify_p.set_defaults(func=cmd_verify)

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    args.func(args)


if __name__ == "__main__":
    main()
