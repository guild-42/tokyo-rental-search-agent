"""SQLite database layer for property storage and lifecycle management."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from .dedup import dedup_key
from .models import Property

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS properties (
    id TEXT PRIMARY KEY,
    dedup_key TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    data TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_properties_status ON properties(status);
CREATE INDEX IF NOT EXISTS idx_properties_last_seen ON properties(last_seen);
CREATE INDEX IF NOT EXISTS idx_properties_first_seen ON properties(first_seen);
CREATE INDEX IF NOT EXISTS idx_properties_source ON properties(source);
CREATE INDEX IF NOT EXISTS idx_properties_dedup_key ON properties(dedup_key);
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create tables, indexes, and enable WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    logger.info(f"Database initialized: {db_path}")
    return conn


def upsert_properties(conn: sqlite3.Connection, properties: list[Property]) -> dict:
    """Insert new properties or update last_seen for existing ones.

    Returns dict with counts: inserted, updated, deduplicated.
    """
    now = datetime.now().isoformat()
    inserted = 0
    updated = 0
    dedup_skipped = 0

    for p in properties:
        dk = dedup_key(p)
        data_json = p.model_dump_json()

        # Check if this exact ID exists
        row = conn.execute(
            "SELECT id, status FROM properties WHERE id = ?", (p.id,)
        ).fetchone()

        if row:
            # Update last_seen and reactivate if stale
            conn.execute(
                "UPDATE properties SET last_seen = ?, status = 'active', data = ? WHERE id = ?",
                (now, data_json, p.id),
            )
            updated += 1
        else:
            # Check dedup_key to avoid cross-source duplicates
            existing = conn.execute(
                "SELECT id FROM properties WHERE dedup_key = ? AND status != 'gone'",
                (dk,),
            ).fetchone()

            if existing:
                # Update existing with this source's data if it has more info
                conn.execute(
                    "UPDATE properties SET last_seen = ?, data = ? WHERE id = ?",
                    (now, data_json, existing[0]),
                )
                dedup_skipped += 1
            else:
                conn.execute(
                    "INSERT INTO properties (id, dedup_key, source, source_url, first_seen, last_seen, status, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
                    (p.id, dk, p.source, p.source_url, now, now, data_json),
                )
                inserted += 1

    conn.commit()
    stats = {"inserted": inserted, "updated": updated, "deduplicated": dedup_skipped}
    logger.info(f"Upsert complete: {stats}")
    return stats


def get_active_properties(conn: sqlite3.Connection, max_age_days: int = 7) -> list[dict]:
    """Return active properties seen within max_age_days, sorted by first_seen desc."""
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
    rows = conn.execute(
        "SELECT data, first_seen, last_seen, status FROM properties "
        "WHERE status = 'active' AND last_seen >= ? "
        "ORDER BY last_seen DESC",
        (cutoff,),
    ).fetchall()

    results = []
    for data_json, first_seen, last_seen, status in rows:
        prop = json.loads(data_json)
        prop["first_seen"] = first_seen
        prop["last_seen"] = last_seen
        prop["status"] = status
        results.append(prop)

    return results


def run_lifecycle(conn: sqlite3.Connection) -> dict:
    """Clean up old properties not seen in recent fetches.

    Properties are kept active as long as they appear in fetches (last_seen updated).
    Only deletes properties not seen for 60+ days to free disk space.
    """
    sixty_days_ago = (datetime.now() - timedelta(days=60)).isoformat()

    deleted_result = conn.execute(
        "DELETE FROM properties WHERE last_seen < ?",
        (sixty_days_ago,),
    )
    deleted_count = deleted_result.rowcount

    conn.commit()
    stats = {"deleted_old": deleted_count}
    logger.info(f"Lifecycle: {stats}")
    return stats


def mark_stale(conn: sqlite3.Connection, current_ids: set[str], fetched_sources: list[str] | None = None, fetched_wards: list[str] | None = None) -> int:
    """Mark active properties not in current_ids as stale.

    Only considers properties matching the fetched sources/wards so that
    a ward-filtered fetch does not mark unrelated properties as stale.
    """
    if not current_ids:
        return 0

    # Build query scoped to what we actually fetched
    query = "SELECT id FROM properties WHERE status = 'active'"
    params: list = []

    if fetched_sources:
        placeholders = ",".join("?" for _ in fetched_sources)
        query += f" AND source IN ({placeholders})"
        params.extend(fetched_sources)

    if fetched_wards:
        ward_placeholders = ",".join("?" for _ in fetched_wards)
        query += f" AND json_extract(data, '$.ward') IN ({ward_placeholders})"
        params.extend(fetched_wards)

    rows = conn.execute(query, params).fetchall()
    active_ids = {row[0] for row in rows}

    missing = active_ids - current_ids
    if not missing:
        return 0

    placeholders = ",".join("?" for _ in missing)
    conn.execute(
        f"UPDATE properties SET status = 'stale' WHERE id IN ({placeholders})",
        list(missing),
    )
    conn.commit()
    logger.info(f"Marked {len(missing)} properties as stale")
    return len(missing)


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return aggregated statistics."""
    stats = {}

    # Count by status
    rows = conn.execute(
        "SELECT status, COUNT(*) FROM properties GROUP BY status"
    ).fetchall()
    stats["by_status"] = {row[0]: row[1] for row in rows}
    stats["total"] = sum(stats["by_status"].values())

    # Count by source
    rows = conn.execute(
        "SELECT source, COUNT(*) FROM properties GROUP BY source"
    ).fetchall()
    stats["by_source"] = {row[0]: row[1] for row in rows}

    # Active within 7 days
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE status = 'active' AND first_seen >= ?",
        (cutoff,),
    ).fetchone()
    stats["active_7d"] = row[0]

    # Latest fetch time
    row = conn.execute(
        "SELECT MAX(last_seen) FROM properties"
    ).fetchone()
    stats["last_fetch"] = row[0]

    return stats
