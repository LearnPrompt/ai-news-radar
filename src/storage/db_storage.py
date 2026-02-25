"""Database storage implementation supporting SQLite, MySQL, and PostgreSQL.

This module provides a storage backend that uses relational databases for
persistence, supporting SQLite (file-based), MySQL, and PostgreSQL.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from . import (
    NewsItem,
    StatusRecord,
    SnapshotMetadata,
    StorageBackend,
    StorageError,
    ConnectionError,
    InitializationError,
    QueryError,
)

logger = logging.getLogger(__name__)


# Database type definitions
DB_TYPE_SQLITE = "sqlite"
DB_TYPE_MYSQL = "mysql"
DB_TYPE_POSTGRESQL = "postgresql"
DB_TYPES = [DB_TYPE_SQLITE, DB_TYPE_MYSQL, DB_TYPE_POSTGRESQL]

# Default SQLite database file
DEFAULT_SQLITE_DB = "data/ai_news_radar.db"


def get_connection_params(db_type: str, db_file: str | Path | None = None) -> dict[str, Any]:
    """Get database connection parameters based on environment variables.

    Args:
        db_type: Type of database ("sqlite", "mysql", "postgresql")
        db_file: Path to SQLite database file (for sqlite type)

    Returns:
        Dictionary of connection parameters

    Environment Variables:
        DB_HOST: Database host (for mysql/postgresql)
        DB_PORT: Database port (for mysql/postgresql)
        DB_NAME: Database name (for mysql/postgresql)
        DB_USER: Database user (for mysql/postgresql)
        DB_PASSWORD: Database password (for mysql/postgresql)
    """
    import os

    if db_type == DB_TYPE_SQLITE:
        db_path = db_file or os.getenv("DB_FILE", DEFAULT_SQLITE_DB)
        return {"database": str(Path(db_path).expanduser())}

    if db_type in (DB_TYPE_MYSQL, DB_TYPE_POSTGRESQL):
        host = os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("DB_PORT", "3306" if db_type == DB_TYPE_MYSQL else "5432"))
        name = os.getenv("DB_NAME", "ai_news_radar")
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")

        return {
            "host": host,
            "port": port,
            "database": name,
            "user": user,
            "password": password,
        }

    raise StorageError(f"Unsupported database type: {db_type}")


class DatabaseStorage(StorageBackend):
    """Database-based storage supporting SQLite, MySQL, and PostgreSQL."""

    def __init__(self, db_type: str = DB_TYPE_SQLITE, db_file: str | Path | None = None):
        """Initialize database storage.

        Args:
            db_type: Type of database ("sqlite", "mysql", "postgresql")
            db_file: Path to SQLite database file (for sqlite type)
        """
        if db_type not in DB_TYPES:
            raise StorageError(f"Unsupported database type: {db_type}")

        self.db_type = db_type
        self.conn_params = get_connection_params(db_type, db_file)
        self._connection = None
        self._cursor = None

        logger.info(
            f"DatabaseStorage initialized with type={db_type}, "
            f"params={self._safe_conn_params()}"
        )

    def _safe_conn_params(self) -> dict[str, Any]:
        """Return connection params with password masked."""
        params = dict(self.conn_params)
        if "password" in params:
            params["password"] = "***"
        return params

    def initialize(self) -> None:
        """Initialize the database and create tables."""
        try:
            self._connect()
            self._create_tables()
            logger.debug(f"Database tables created for {self.db_type}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise InitializationError(f"Failed to initialize database: {e}") from e

    def _connect(self) -> None:
        """Connect to the database."""
        import os

        try:
            if self.db_type == DB_TYPE_SQLITE:
                import sqlite3

                db_path = Path(self.conn_params["database"])
                db_path.parent.mkdir(parents=True, exist_ok=True)
                self._connection = sqlite3.connect(db_path, check_same_thread=False)
                self._connection.row_factory = sqlite3.Row
                logger.debug(f"Connected to SQLite at {db_path}")

            elif self.db_type == DB_TYPE_MYSQL:
                try:
                    import mysql.connector
                except ImportError:
                    raise InitializationError(
                        "MySQL connector not installed. Install with: pip install mysql-connector-python"
                    )
                self._connection = mysql.connector.connect(**self.conn_params)
                logger.debug(f"Connected to MySQL at {self.conn_params['host']}")

            elif self.db_type == DB_TYPE_POSTGRESQL:
                try:
                    import psycopg2
                except ImportError:
                    raise InitializationError(
                        "PostgreSQL connector not installed. Install with: pip install psycopg2-binary"
                    )
                self._connection = psycopg2.connect(**self.conn_params)
                logger.debug(f"Connected to PostgreSQL at {self.conn_params['host']}")

            else:
                raise StorageError(f"Unsupported database type: {self.db_type}")

            self._cursor = self._connection.cursor()

        except ImportError as e:
            raise InitializationError(f"Database driver not available: {e}") from e
        except Exception as e:
            raise ConnectionError(f"Failed to connect to database: {e}") from e

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        if self.db_type == DB_TYPE_SQLITE:
            self._create_sqlite_tables()
        elif self.db_type == DB_TYPE_MYSQL:
            self._create_mysql_tables()
        elif self.db_type == DB_TYPE_POSTGRESQL:
            self._create_postgresql_tables()

    def _create_sqlite_tables(self) -> None:
        """Create SQLite tables."""
        self._execute("""
            CREATE TABLE IF NOT EXISTS news_items (
                id TEXT PRIMARY KEY,
                site_id TEXT NOT NULL,
                site_name TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                meta TEXT,
                title_zh TEXT,
                summary TEXT,
                categories TEXT
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS status_records (
                site_id TEXT PRIMARY KEY,
                site_name TEXT NOT NULL,
                ok INTEGER NOT NULL,
                item_count INTEGER NOT NULL,
                last_check_at TEXT NOT NULL,
                error_message TEXT,
                response_time_ms INTEGER,
                metadata TEXT
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_type TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_site_id ON news_items(site_id)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_published_at ON news_items(published_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_first_seen_at ON news_items(first_seen_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_snapshots_type ON snapshots(snapshot_type)")

    def _create_mysql_tables(self) -> None:
        """Create MySQL tables."""
        self._execute("""
            CREATE TABLE IF NOT EXISTS news_items (
                id VARCHAR(255) PRIMARY KEY,
                site_id VARCHAR(100) NOT NULL,
                site_name VARCHAR(200) NOT NULL,
                source VARCHAR(200) NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at VARCHAR(50),
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                meta JSON,
                title_zh TEXT,
                summary TEXT,
                categories JSON,
                INDEX idx_site_id (site_id),
                INDEX idx_published_at (published_at),
                INDEX idx_first_seen_at (first_seen_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS status_records (
                site_id VARCHAR(100) PRIMARY KEY,
                site_name VARCHAR(200) NOT NULL,
                ok BOOLEAN NOT NULL,
                item_count INT NOT NULL,
                last_check_at DATETIME NOT NULL,
                error_message TEXT,
                response_time_ms INT,
                metadata JSON
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INT AUTO_INCREMENT PRIMARY KEY,
                snapshot_type VARCHAR(50) NOT NULL,
                generated_at DATETIME NOT NULL,
                data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_type (snapshot_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

    def _create_postgresql_tables(self) -> None:
        """Create PostgreSQL tables."""
        self._execute("""
            CREATE TABLE IF NOT EXISTS news_items (
                id VARCHAR(255) PRIMARY KEY,
                site_id VARCHAR(100) NOT NULL,
                site_name VARCHAR(200) NOT NULL,
                source VARCHAR(200) NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at VARCHAR(50),
                first_seen_at TIMESTAMP NOT NULL,
                last_seen_at TIMESTAMP NOT NULL,
                meta JSONB,
                title_zh TEXT,
                summary TEXT,
                categories JSONB
            )
        """)

        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_site_id ON news_items(site_id)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_published_at ON news_items(published_at)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_news_items_first_seen_at ON news_items(first_seen_at)")

        self._execute("""
            CREATE TABLE IF NOT EXISTS status_records (
                site_id VARCHAR(100) PRIMARY KEY,
                site_name VARCHAR(200) NOT NULL,
                ok BOOLEAN NOT NULL,
                item_count INT NOT NULL,
                last_check_at TIMESTAMP NOT NULL,
                error_message TEXT,
                response_time_ms INT,
                metadata JSONB
            )
        """)

        self._execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id SERIAL PRIMARY KEY,
                snapshot_type VARCHAR(50) NOT NULL,
                generated_at TIMESTAMP NOT NULL,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._execute("CREATE INDEX IF NOT EXISTS idx_snapshots_type ON snapshots(snapshot_type)")

    def _execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a database query."""
        try:
            if params:
                self._cursor.execute(query, params)
            else:
                self._cursor.execute(query)
            return self._cursor
        except Exception as e:
            logger.error(f"Query failed: {query[:100]}... Error: {e}")
            raise QueryError(f"Query failed: {e}") from e

    def _execute_fetchall(self, query: str, params: tuple[Any, ...] | None = None) -> list[Any]:
        """Execute a query and fetch all results."""
        self._execute(query, params)
        return self._cursor.fetchall()

    def _execute_fetchone(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a query and fetch one result."""
        self._execute(query, params)
        return self._cursor.fetchone()

    def close(self) -> None:
        """Close the database connection."""
        try:
            if self._cursor:
                self._cursor.close()
            if self._connection:
                self._connection.commit()
                self._connection.close()
            logger.debug("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")

    def save_news_items(self, items: list[NewsItem]) -> int:
        """Save news items to database."""
        if not items:
            return 0

        try:
            saved = 0
            for item in items:
                # Use INSERT OR REPLACE for SQLite, ON DUPLICATE KEY UPDATE for MySQL,
                # and ON CONFLICT for PostgreSQL
                if self.db_type == DB_TYPE_SQLITE:
                    query = """
                        INSERT OR REPLACE INTO news_items
                        (id, site_id, site_name, source, title, url, published_at,
                         first_seen_at, last_seen_at, meta, title_zh, summary, categories)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                elif self.db_type == DB_TYPE_MYSQL:
                    query = """
                        INSERT INTO news_items
                        (id, site_id, site_name, source, title, url, published_at,
                         first_seen_at, last_seen_at, meta, title_zh, summary, categories)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        title=VALUES(title), published_at=VALUES(published_at),
                        last_seen_at=VALUES(last_seen_at), meta=VALUES(meta),
                        title_zh=VALUES(title_zh), summary=VALUES(summary), categories=VALUES(categories)
                    """
                else:  # PostgreSQL
                    query = """
                        INSERT INTO news_items
                        (id, site_id, site_name, source, title, url, published_at,
                         first_seen_at, last_seen_at, meta, title_zh, summary, categories)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                        title=EXCLUDED.title, published_at=EXCLUDED.published_at,
                        last_seen_at=EXCLUDED.last_seen_at, meta=EXCLUDED.meta,
                        title_zh=EXCLUDED.title_zh, summary=EXCLUDED.summary, categories=EXCLUDED.categories
                    """

                meta_json = json.dumps(item.meta) if item.meta else None
                categories_json = json.dumps(item.categories) if item.categories else None

                params = (
                    item.id,
                    item.site_id,
                    item.site_name,
                    item.source,
                    item.title,
                    item.url,
                    item.published_at,
                    item.first_seen_at,
                    item.last_seen_at,
                    meta_json,
                    item.title_zh,
                    item.summary,
                    categories_json,
                )

                self._execute(query, params)
                saved += 1

            self._connection.commit()
            logger.info(f"Saved {saved} news items to database")
            return saved
        except Exception as e:
            logger.error(f"Failed to save news items: {e}")
            raise StorageError(f"Failed to save news items: {e}") from e

    def save_archive_items(self, items: list[NewsItem]) -> int:
        """Save archive items to database."""
        return self.save_news_items(items)

    def load_archive(self) -> dict[str, NewsItem]:
        """Load all archive items from database."""
        try:
            query = "SELECT * FROM news_items"
            rows = self._execute_fetchall(query)

            result: dict[str, NewsItem] = {}
            for row in rows:
                item = self._row_to_news_item(row)
                if item:
                    result[item.id] = item

            logger.debug(f"Loaded {len(result)} archive items from database")
            return result
        except Exception as e:
            logger.error(f"Failed to load archive: {e}")
            raise StorageError(f"Failed to load archive: {e}") from e

    def load_latest_items(self, since: datetime | None = None) -> list[NewsItem]:
        """Load latest items, optionally filtered by time."""
        try:
            if since:
                if self.db_type == DB_TYPE_SQLITE:
                    query = "SELECT * FROM news_items WHERE first_seen_at >= ? ORDER BY first_seen_at DESC"
                    params = (since.isoformat(),)
                else:
                    query = "SELECT * FROM news_items WHERE first_seen_at >= %s ORDER BY first_seen_at DESC"
                    params = (since,)
            else:
                query = "SELECT * FROM news_items ORDER BY first_seen_at DESC LIMIT 1000"
                params = None

            rows = self._execute_fetchall(query, params)
            return [self._row_to_news_item(row) for row in rows if self._row_to_news_item(row)]
        except Exception as e:
            logger.error(f"Failed to load latest items: {e}")
            raise StorageError(f"Failed to load latest items: {e}") from e

    def save_snapshot(
        self,
        snapshot_type: str,
        metadata: SnapshotMetadata,
        items: list[NewsItem],
        items_ai: list[NewsItem] | None = None,
        items_all_raw: list[NewsItem] | None = None,
        items_all: list[NewsItem] | None = None,
        site_stats: list[dict[str, Any]] | None = None,
    ) -> None:
        """Save a snapshot to database."""
        try:
            data = metadata.to_dict()
            data.update({
                "items": [item.to_dict() for item in items],
                "items_ai": [item.to_dict() for item in (items_ai or items)],
                "items_all_raw": [item.to_dict() for item in (items_all_raw or [])],
                "items_all": [item.to_dict() for item in (items_all or [])],
                "site_stats": site_stats or [],
            })

            if self.db_type == DB_TYPE_SQLITE:
                query = """
                    INSERT INTO snapshots (snapshot_type, generated_at, data)
                    VALUES (?, ?, ?)
                """
                params = (snapshot_type, metadata.generated_at, json.dumps(data))
            else:
                query = """
                    INSERT INTO snapshots (snapshot_type, generated_at, data)
                    VALUES (%s, %s, %s)
                """
                params = (snapshot_type, metadata.generated_at, json.dumps(data))

            self._execute(query, params)
            self._connection.commit()
            logger.info(f"Saved snapshot '{snapshot_type}' to database")
        except Exception as e:
            logger.error(f"Failed to save snapshot '{snapshot_type}': {e}")
            raise StorageError(f"Failed to save snapshot '{snapshot_type}': {e}") from e

    def load_snapshot(self, snapshot_type: str) -> dict[str, Any] | None:
        """Load a snapshot by type."""
        try:
            if self.db_type == DB_TYPE_SQLITE:
                query = """
                    SELECT data FROM snapshots
                    WHERE snapshot_type = ?
                    ORDER BY id DESC LIMIT 1
                """
                params = (snapshot_type,)
            else:
                query = """
                    SELECT data FROM snapshots
                    WHERE snapshot_type = %s
                    ORDER BY id DESC LIMIT 1
                """
                params = (snapshot_type,)

            row = self._execute_fetchone(query, params)
            if not row:
                return None

            data_json = row[0] if isinstance(row[0], str) else json.dumps(row[0])
            return json.loads(data_json)
        except Exception as e:
            logger.error(f"Failed to load snapshot '{snapshot_type}': {e}")
            raise StorageError(f"Failed to load snapshot '{snapshot_type}': {e}") from e

    def save_status_records(self, records: list[StatusRecord]) -> int:
        """Save site status records."""
        if not records:
            return 0

        try:
            saved = 0
            for record in records:
                if self.db_type == DB_TYPE_SQLITE:
                    query = """
                        INSERT OR REPLACE INTO status_records
                        (site_id, site_name, ok, item_count, last_check_at, error_message, response_time_ms, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                elif self.db_type == DB_TYPE_MYSQL:
                    query = """
                        INSERT INTO status_records
                        (site_id, site_name, ok, item_count, last_check_at, error_message, response_time_ms, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        site_name=VALUES(site_name), ok=VALUES(ok), item_count=VALUES(item_count),
                        last_check_at=VALUES(last_check_at), error_message=VALUES(error_message),
                        response_time_ms=VALUES(response_time_ms), metadata=VALUES(metadata)
                    """
                else:  # PostgreSQL
                    query = """
                        INSERT INTO status_records
                        (site_id, site_name, ok, item_count, last_check_at, error_message, response_time_ms, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (site_id) DO UPDATE SET
                        site_name=EXCLUDED.site_name, ok=EXCLUDED.ok, item_count=EXCLUDED.item_count,
                        last_check_at=EXCLUDED.last_check_at, error_message=EXCLUDED.error_message,
                        response_time_ms=EXCLUDED.response_time_ms, metadata=EXCLUDED.metadata
                    """

                metadata_json = json.dumps(record.metadata) if record.metadata else None

                params = (
                    record.site_id,
                    record.site_name,
                    1 if record.ok else 0,
                    record.item_count,
                    record.last_check_at,
                    record.error_message,
                    record.response_time_ms,
                    metadata_json,
                )

                self._execute(query, params)
                saved += 1

            self._connection.commit()
            logger.info(f"Saved {saved} status records to database")
            return saved
        except Exception as e:
            logger.error(f"Failed to save status records: {e}")
            raise StorageError(f"Failed to save status records: {e}") from e

    def load_status_records(self) -> list[StatusRecord]:
        """Load all status records."""
        try:
            query = "SELECT * FROM status_records"
            rows = self._execute_fetchall(query)

            return [self._row_to_status_record(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to load status records: {e}")
            raise StorageError(f"Failed to load status records: {e}") from e

    def save_waytoagi_data(self, data: dict[str, Any]) -> None:
        """Save WaytoAGI data as a snapshot."""
        metadata = SnapshotMetadata(
            generated_at=data.get("generated_at", datetime.now().isoformat()),
            window_hours=0,
            total_items=data.get("count_7d", 0),
            total_items_raw=0,
            site_count=0,
            source_count=0,
            topic_filter="waytoagi",
            archive_total=0,
        )
        self.save_snapshot("waytoagi", metadata, [])

    def load_waytoagi_data(self) -> dict[str, Any] | None:
        """Load WaytoAGI data."""
        return self.load_snapshot("waytoagi")

    def save_title_cache(self, cache: dict[str, str]) -> None:
        """Save title translation cache as a snapshot."""
        metadata = SnapshotMetadata(
            generated_at=datetime.now().isoformat(),
            window_hours=0,
            total_items=len(cache),
            total_items_raw=0,
            site_count=0,
            source_count=0,
            topic_filter="title_cache",
            archive_total=0,
        )
        self.save_snapshot("title_cache", metadata, [], site_stats=[{"cache": cache}])

    def load_title_cache(self) -> dict[str, str]:
        """Load title translation cache."""
        try:
            snapshot = self.load_snapshot("title_cache")
            if not snapshot:
                return {}

            site_stats = snapshot.get("site_stats", [])
            if site_stats and "cache" in site_stats[0]:
                return site_stats[0]["cache"]
            return {}
        except Exception as e:
            logger.error(f"Failed to load title cache: {e}")
            return {}

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        try:
            query = "SELECT COUNT(*) as count FROM news_items"
            row = self._execute_fetchone(query)
            news_count = row[0] if row else 0

            query = "SELECT COUNT(*) as count FROM status_records"
            row = self._execute_fetchone(query)
            status_count = row[0] if row else 0

            query = "SELECT COUNT(*) as count FROM snapshots"
            row = self._execute_fetchone(query)
            snapshot_count = row[0] if row else 0

            return {
                "backend": "database",
                "db_type": self.db_type,
                "news_items_count": news_count,
                "status_records_count": status_count,
                "snapshots_count": snapshot_count,
                "connection_params": self._safe_conn_params(),
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {
                "backend": "database",
                "db_type": self.db_type,
                "error": str(e),
            }

    def is_healthy(self) -> bool:
        """Check if database connection is healthy."""
        try:
            self._execute("SELECT 1")
            return True
        except Exception:
            return False

    def _row_to_news_item(self, row: Any) -> NewsItem | None:
        """Convert database row to NewsItem."""
        try:
            # Handle different row types (sqlite3.Row vs dict vs tuple)
            if hasattr(row, "keys"):
                data = dict(row)
            elif isinstance(row, dict):
                data = row
            else:
                # Assume tuple in column order
                columns = [
                    "id", "site_id", "site_name", "source", "title", "url",
                    "published_at", "first_seen_at", "last_seen_at", "meta",
                    "title_zh", "summary", "categories"
                ]
                data = {col: row[i] for i, col in enumerate(columns) if i < len(row)}

            # Parse JSON fields
            meta = data.get("meta")
            if isinstance(meta, str):
                meta = json.loads(meta)
            elif meta is None:
                meta = {}

            categories = data.get("categories")
            if isinstance(categories, str):
                categories = json.loads(categories)

            return NewsItem(
                id=data["id"],
                site_id=data["site_id"],
                site_name=data["site_name"],
                source=data["source"],
                title=data["title"],
                url=data["url"],
                published_at=data["published_at"],
                first_seen_at=data["first_seen_at"],
                last_seen_at=data["last_seen_at"],
                meta=meta,
                title_zh=data.get("title_zh"),
                summary=data.get("summary"),
                categories=categories,
            )
        except Exception as e:
            logger.error(f"Failed to convert row to NewsItem: {e}")
            return None

    def _row_to_status_record(self, row: Any) -> StatusRecord:
        """Convert database row to StatusRecord."""
        try:
            if hasattr(row, "keys"):
                data = dict(row)
            elif isinstance(row, dict):
                data = row
            else:
                columns = [
                    "site_id", "site_name", "ok", "item_count", "last_check_at",
                    "error_message", "response_time_ms", "metadata"
                ]
                data = {col: row[i] for i, col in enumerate(columns) if i < len(row)}

            metadata = data.get("metadata")
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            return StatusRecord(
                site_id=data["site_id"],
                site_name=data["site_name"],
                ok=bool(data["ok"]),
                item_count=data["item_count"],
                last_check_at=data["last_check_at"],
                error_message=data.get("error_message"),
                response_time_ms=data.get("response_time_ms"),
                metadata=metadata,
            )
        except Exception as e:
            logger.error(f"Failed to convert row to StatusRecord: {e}")
            raise QueryError(f"Failed to convert row to StatusRecord: {e}") from e


__all__ = [
    "DatabaseStorage",
    "get_connection_params",
    "DB_TYPE_SQLITE",
    "DB_TYPE_MYSQL",
    "DB_TYPE_POSTGRESQL",
]
