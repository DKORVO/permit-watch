import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path

from .lifecycle import lifecycle_fields


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self):
        with self.connection() as conn:
            conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS items (
              id INTEGER PRIMARY KEY, source_name TEXT NOT NULL, title TEXT NOT NULL,
              url TEXT NOT NULL, published_text TEXT, excerpt TEXT NOT NULL,
              fingerprint TEXT NOT NULL UNIQUE, relevant INTEGER NOT NULL,
              enrichment TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS runs (
              id INTEGER PRIMARY KEY, started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              finished_at TEXT, status TEXT NOT NULL, message TEXT
            );
            CREATE TABLE IF NOT EXISTS enrichment_attempts (
              id INTEGER PRIMARY KEY,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              context TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS location_cache (
              query TEXT PRIMARY KEY,
              latitude REAL,
              longitude REAL,
              precision TEXT NOT NULL DEFAULT 'unknown',
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(items)")}
            if "metadata" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN metadata TEXT")
            if "enrichment_status" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN enrichment_status TEXT NOT NULL DEFAULT 'awaiting'")
                conn.execute("""
                    UPDATE items
                    SET enrichment_status = CASE
                        WHEN enrichment IS NULL OR TRIM(enrichment) = '' THEN 'awaiting'
                        WHEN LOWER(enrichment) LIKE 'enrichment unavailable%'
                          OR LOWER(enrichment) LIKE 'enrichment returned no summary%' THEN 'failed'
                        ELSE 'enriched'
                    END
                """)
            if "closing_at" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN closing_at TEXT")
            if "lifecycle_status" not in columns:
                conn.execute("ALTER TABLE items ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'unknown'")
            rows = conn.execute("SELECT id, source_name, metadata FROM items").fetchall()
            for row in rows:
                closing_at, lifecycle_status = lifecycle_fields(row["source_name"], row["metadata"])
                conn.execute(
                    "UPDATE items SET closing_at = ?, lifecycle_status = ? WHERE id = ?",
                    (closing_at, lifecycle_status, row["id"]),
                )

            run_columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            if "source_scope" not in run_columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN source_scope TEXT NOT NULL DEFAULT 'All sources'"
                )

    def add_item(self, item):
        item["closing_at"], item["lifecycle_status"] = lifecycle_fields(
            item["source_name"], item.get("metadata")
        )
        with self.connection() as conn:
            existing = conn.execute("SELECT id FROM items WHERE fingerprint = ?", (item["fingerprint"],)).fetchone()
            # Ottawa's detail URL is a stable application identifier.  Reuse
            # the original card when its title gains a resolved address.
            if not existing:
                existing = conn.execute("SELECT id FROM items WHERE url = ?", (item["url"],)).fetchone()
            if existing:
                # Public source data can gain/correct fields after first import.
                # Preserve the stored enrichment, but refresh the source fields.
                conn.execute("""
                    UPDATE items
                    SET source_name = :source_name, title = :title, url = :url,
                        published_text = :published_text, excerpt = :excerpt,
                        fingerprint = :fingerprint, relevant = :relevant, metadata = :metadata,
                        closing_at = :closing_at, lifecycle_status = :lifecycle_status
                    WHERE id = :id
                """, {**item, "id": existing["id"]})
                return False
            cursor = conn.execute("""
                INSERT OR IGNORE INTO items
                (source_name, title, url, published_text, excerpt, fingerprint, relevant, enrichment,
                 metadata, enrichment_status, closing_at, lifecycle_status)
                VALUES (:source_name, :title, :url, :published_text, :excerpt, :fingerprint, :relevant,
                        :enrichment, :metadata, :enrichment_status, :closing_at, :lifecycle_status)
            """, item)
            return cursor.rowcount == 1

    def stored_security_items(self):
        """Return stored MERX and CanadaBuys rows for matcher migrations."""
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT id, source_name, title, excerpt, relevant, metadata
                FROM items
                WHERE LOWER(source_name) LIKE 'merx%'
                   OR LOWER(source_name) LIKE 'canadabuys%'
                """
            ).fetchall()

    def update_item_relevance(self, item_id, relevant, metadata):
        """Update matcher-owned fields without altering saved enrichment."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE items SET relevant = ?, metadata = ? WHERE id = ?",
                (int(bool(relevant)), metadata, item_id),
            )

    def item_exists(self, fingerprint, url=None):
        """Return whether a finding already exists by content or stable URL."""
        with self.connection() as conn:
            return conn.execute(
                "SELECT 1 FROM items WHERE fingerprint = ? OR (? IS NOT NULL AND url = ?)",
                (fingerprint, url, url),
            ).fetchone() is not None

    def resolved_addresses_by_url(self):
        """Return previously resolved human-readable addresses keyed by URL."""
        addresses = {}
        with self.connection() as conn:
            rows = conn.execute("SELECT url, metadata FROM items WHERE metadata IS NOT NULL").fetchall()
        for row in rows:
            try:
                value = json.loads(row["metadata"]).get("Addresses", "").strip()
            except (AttributeError, TypeError, json.JSONDecodeError):
                continue
            if value and not value.startswith("Not provided by City of Ottawa") and not re.fullmatch(r"_[A-Za-z0-9_]+", value):
                addresses[row["url"]] = value
        return addresses

    def map_items(self, limit=3000):
        """Return recent relevant findings used by the dashboard map."""
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT id, source_name, title, url, relevant, enrichment_status, metadata
                FROM items
                WHERE lifecycle_status != 'closed'
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def cached_coordinates(self):
        """Return persistent geocoder results keyed by normalized query."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT query, latitude, longitude, precision FROM location_cache"
            ).fetchall()
        return {row["query"]: dict(row) for row in rows}

    def cache_coordinates(self, query, latitude, longitude, precision):
        """Persist a geocoder result, including unresolved queries."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO location_cache(query, latitude, longitude, precision)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(query) DO UPDATE SET
                  latitude=excluded.latitude,
                  longitude=excluded.longitude,
                  precision=excluded.precision,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (query, latitude, longitude, precision),
            )

    def recent_items(self, limit=100):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def recent_items_for_source(self, source_prefix, limit=1000, relevant_only=True):
        """Return one source's findings, optionally including reviewable non-matches."""
        relevance_clause = "AND relevant = 1" if relevant_only else ""
        with self.connection() as conn:
            return conn.execute(
                f"""
                SELECT * FROM items
                WHERE LOWER(source_name) LIKE ? {relevance_clause}
                ORDER BY id DESC
                LIMIT ?
                """,
                (f"{source_prefix.lower()}%", limit),
            ).fetchall()

    def source_summary(self, source_prefix):
        """Counts and latest collected finding for one dashboard source."""
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT
                  COALESCE(SUM(CASE WHEN lifecycle_status != 'closed' THEN 1 ELSE 0 END), 0) AS total,
                  COALESCE(SUM(CASE WHEN relevant = 1 AND lifecycle_status != 'closed' THEN 1 ELSE 0 END), 0) AS matched,
                  COALESCE(SUM(CASE WHEN relevant = 1 AND lifecycle_status != 'closed' AND enrichment_status = 'awaiting' THEN 1 ELSE 0 END), 0) AS awaiting,
                  COALESCE(SUM(CASE WHEN relevant = 1 AND lifecycle_status != 'closed' AND enrichment_status = 'enriched' THEN 1 ELSE 0 END), 0) AS enriched,
                  COALESCE(SUM(CASE WHEN relevant = 1 AND lifecycle_status != 'closed' AND enrichment_status = 'failed' THEN 1 ELSE 0 END), 0) AS failed,
                  MAX(created_at) AS latest_collected
                FROM items
                WHERE LOWER(source_name) LIKE ?
                """,
                (f"{source_prefix.lower()}%",),
            ).fetchone()
        return dict(row)

    def refresh_lifecycle_statuses(self):
        """Re-evaluate deadlines so records close without requiring a re-scrape."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT id, source_name, metadata FROM items WHERE lifecycle_status != 'closed'"
            ).fetchall()
            for row in rows:
                closing_at, status = lifecycle_fields(row["source_name"], row["metadata"])
                conn.execute(
                    "UPDATE items SET closing_at = ?, lifecycle_status = ? WHERE id = ?",
                    (closing_at, status, row["id"]),
                )

    def purge_closed_items(self, retention_days):
        """Delete tender records after the configured closed-record retention."""
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        with self.connection() as conn:
            cursor = conn.execute(
                """DELETE FROM items
                   WHERE lifecycle_status = 'closed'
                     AND closing_at IS NOT NULL
                     AND closing_at < ?""",
                (cutoff,),
            )
            return cursor.rowcount

    def enrichment_budget(self, limit):
        """Return the current UTC-day request allowance used by OpenRouter."""
        with self.connection() as conn:
            used = conn.execute(
                "SELECT COUNT(*) FROM enrichment_attempts WHERE created_at >= date('now')"
            ).fetchone()[0]
        return {"limit": limit, "used": used, "remaining": max(0, limit - used)}

    def record_enrichment_attempt(self, context):
        with self.connection() as conn:
            conn.execute(
                "INSERT INTO enrichment_attempts(context) VALUES (?)",
                (context,),
            )

    def failed_enrichment_items(self, limit):
        with self.connection() as conn:
            return conn.execute("""
                SELECT * FROM items
                WHERE relevant = 1 AND lifecycle_status != 'closed' AND enrichment_status = 'failed'
                ORDER BY id ASC LIMIT ?
            """, (limit,)).fetchall()

    def enrichment_items_by_ids(self, item_ids, source_prefix):
        """Return selected findings only when they belong to the active tab."""
        ids = sorted({int(item_id) for item_id in item_ids if int(item_id) > 0})
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        with self.connection() as conn:
            return conn.execute(
                f"""
                SELECT * FROM items
                WHERE id IN ({placeholders}) AND LOWER(source_name) LIKE ? AND lifecycle_status != 'closed'
                ORDER BY id ASC
                """,
                (*ids, f"{source_prefix.lower()}%"),
            ).fetchall()

    def update_enrichment(self, item_id, summary, status):
        with self.connection() as conn:
            conn.execute(
                "UPDATE items SET enrichment = ?, enrichment_status = ? WHERE id = ?",
                (summary, status, item_id),
            )

    def queue_run(self, source_scope, message):
        """Create a visible status row before a background action starts."""
        with self.connection() as conn:
            return conn.execute(
                "INSERT INTO runs(status, message, source_scope) VALUES ('queued', ?, ?)",
                (message, source_scope),
            ).lastrowid

    def keep_run_queued(self, run_id, message):
        """Keep a requested action visible while it waits for the scheduler lock."""
        with self.connection() as conn:
            conn.execute(
                "UPDATE runs SET status='queued', finished_at=NULL, message=? WHERE id=?",
                (message, run_id),
            )

    def start_run(self, run_id, message):
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE runs
                SET started_at=CURRENT_TIMESTAMP, finished_at=NULL,
                    status='running', message=?
                WHERE id=?
                """,
                (message, run_id),
            )

    def begin_run(self, source_scope="All sources"):
        with self.connection() as conn:
            return conn.execute(
                "INSERT INTO runs(status, source_scope) VALUES ('running', ?)",
                (source_scope,),
            ).lastrowid

    def finish_run(self, run_id, status, message):
        with self.connection() as conn:
            conn.execute("UPDATE runs SET finished_at=CURRENT_TIMESTAMP, status=?, message=? WHERE id=?", (status, message, run_id))

    def latest_run(self, source_scope=None):
        with self.connection() as conn:
            if source_scope:
                return conn.execute(
                    "SELECT * FROM runs WHERE source_scope = ? ORDER BY id DESC LIMIT 1",
                    (source_scope,),
                ).fetchone()
            return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
