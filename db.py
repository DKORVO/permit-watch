import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path


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

    def add_item(self, item):
        with self.connection() as conn:
            existing = conn.execute("SELECT id FROM items WHERE fingerprint = ?", (item["fingerprint"],)).fetchone()
            if existing:
                # Public source data can gain/correct fields after first import.
                # Preserve the stored enrichment, but refresh the source fields.
                conn.execute("""
                    UPDATE items
                    SET source_name = :source_name, title = :title, url = :url,
                        published_text = :published_text, excerpt = :excerpt,
                        relevant = :relevant, metadata = :metadata
                    WHERE id = :id
                """, {**item, "id": existing["id"]})
                return False
            cursor = conn.execute("""
                INSERT OR IGNORE INTO items
                (source_name, title, url, published_text, excerpt, fingerprint, relevant, enrichment, metadata, enrichment_status)
                VALUES (:source_name, :title, :url, :published_text, :excerpt, :fingerprint, :relevant, :enrichment, :metadata, :enrichment_status)
            """, item)
            return cursor.rowcount == 1

    def item_exists(self, fingerprint):
        with self.connection() as conn:
            return conn.execute("SELECT 1 FROM items WHERE fingerprint = ?", (fingerprint,)).fetchone() is not None

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

    def ottawa_missing_address_items(self, limit):
        """Return a capped, newest-first batch of Ottawa records needing an address."""
        missing = []
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT id, url, metadata FROM items
                WHERE url LIKE 'https://devapps.ottawa.ca/en/applications/%/details'
                  AND metadata IS NOT NULL
                ORDER BY id DESC
            """).fetchall()
        for row in rows:
            try:
                metadata = json.loads(row["metadata"])
                address = str(metadata.get("Addresses", "")).strip()
            except (AttributeError, TypeError, json.JSONDecodeError):
                continue
            if not address or address.startswith("Not provided by City of Ottawa") or re.fullmatch(r"_[A-Za-z0-9_]+", address):
                missing.append({"id": row["id"], "url": row["url"], "metadata": metadata})
                if len(missing) >= limit:
                    break
        return missing

    def update_metadata(self, item_id, metadata):
        with self.connection() as conn:
            conn.execute("UPDATE items SET metadata = ? WHERE id = ?", (json.dumps(metadata), item_id))

    def ottawa_address_counts(self):
        resolved = missing = 0
        with self.connection() as conn:
            rows = conn.execute("""
                SELECT metadata FROM items
                WHERE url LIKE 'https://devapps.ottawa.ca/en/applications/%/details'
                  AND metadata IS NOT NULL
            """).fetchall()
        for row in rows:
            try:
                address = str(json.loads(row["metadata"]).get("Addresses", "")).strip()
            except (AttributeError, TypeError, json.JSONDecodeError):
                continue
            if address and not address.startswith("Not provided by City of Ottawa") and not re.fullmatch(r"_[A-Za-z0-9_]+", address):
                resolved += 1
            else:
                missing += 1
        return {"resolved": resolved, "missing": missing}

    def recent_items(self, limit=100):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM items ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def failed_enrichment_items(self, limit):
        with self.connection() as conn:
            return conn.execute("""
                SELECT * FROM items
                WHERE relevant = 1 AND enrichment_status = 'failed'
                ORDER BY id ASC LIMIT ?
            """, (limit,)).fetchall()

    def update_enrichment(self, item_id, summary, status):
        with self.connection() as conn:
            conn.execute(
                "UPDATE items SET enrichment = ?, enrichment_status = ? WHERE id = ?",
                (summary, status, item_id),
            )

    def begin_run(self):
        with self.connection() as conn:
            return conn.execute("INSERT INTO runs(status) VALUES ('running')").lastrowid

    def finish_run(self, run_id, status, message):
        with self.connection() as conn:
            conn.execute("UPDATE runs SET finished_at=CURRENT_TIMESTAMP, status=?, message=? WHERE id=?", (status, message, run_id))

    def latest_run(self):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
