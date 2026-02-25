"""Storage abstraction layer for AI News Radar.

This module provides a unified interface for storing and retrieving news data,
supporting multiple backends:
- SQLite (default, file-based)
- MySQL (via environment variables)
- PostgreSQL (via environment variables)
- File-based JSON (fallback)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Protocol, runtime_checkable, TYPE_CHECKING

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """Represents a single news item."""

    id: str
    site_id: str
    site_name: str
    source: str
    title: str
    url: str
    published_at: str | None
    first_seen_at: str
    last_seen_at: str
    meta: dict[str, Any]
    title_zh: str | None = None
    summary: str | None = None
    categories: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class StatusRecord:
    """Represents a site/source status record."""

    site_id: str
    site_name: str
    ok: bool
    item_count: int
    last_check_at: str
    error_message: str | None = None
    response_time_ms: int | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class SnapshotMetadata:
    """Metadata about a generated snapshot."""

    generated_at: str
    window_hours: int
    total_items: int
    total_items_raw: int
    site_count: int
    source_count: int
    topic_filter: str
    archive_total: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the storage backend interface."""

    def initialize(self) -> None:
        """Initialize the storage backend (create tables, etc.)."""
        ...

    def close(self) -> None:
        """Close the storage connection."""
        ...

    def save_news_items(self, items: list[NewsItem]) -> int:
        """Save news items to storage. Returns count of saved items."""
        ...

    def save_archive_items(self, items: list[NewsItem]) -> int:
        """Save archive items to storage. Returns count of saved items."""
        ...

    def load_archive(self) -> dict[str, NewsItem]:
        """Load all archive items from storage."""
        ...

    def load_latest_items(self, since: datetime | None = None) -> list[NewsItem]:
        """Load latest items, optionally filtered by time."""
        ...

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
        """Save a snapshot (latest, status, etc.)."""
        ...

    def load_snapshot(self, snapshot_type: str) -> dict[str, Any] | None:
        """Load a snapshot by type."""
        ...

    def save_status_records(self, records: list[StatusRecord]) -> int:
        """Save site status records. Returns count of saved records."""
        ...

    def load_status_records(self) -> list[StatusRecord]:
        """Load all status records."""
        ...

    def save_waytoagi_data(self, data: dict[str, Any]) -> None:
        """Save WaytoAGI data."""
        ...

    def load_waytoagi_data(self) -> dict[str, Any] | None:
        """Load WaytoAGI data."""
        ...

    def save_title_cache(self, cache: dict[str, str]) -> None:
        """Save title translation cache."""
        ...

    def load_title_cache(self) -> dict[str, str]:
        """Load title translation cache."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        ...

    def is_healthy(self) -> bool:
        """Check if storage backend is healthy."""
        ...


class StorageError(Exception):
    """Base exception for storage errors."""

    pass


class ConnectionError(StorageError):
    """Exception raised when connection to storage fails."""

    pass


class InitializationError(StorageError):
    """Exception raised when storage initialization fails."""

    pass


class QueryError(StorageError):
    """Exception raised when a query fails."""

    pass


__all__ = [
    "NewsItem",
    "StatusRecord",
    "SnapshotMetadata",
    "StorageBackend",
    "StorageError",
    "ConnectionError",
    "InitializationError",
    "QueryError",
    "create_storage",
    "create_storage_with_retry",
    "get_storage_info",
    "get_db_type",
    "get_db_file",
    "get_data_dir",
    "FileStorage",
    "DatabaseStorage",
]

# Lazy imports for factory functions to avoid circular imports
def _get_factory():
    """Import and return factory module."""
    from . import factory
    return factory

def create_storage(
    db_type: str | None = None,
    db_file: str | None = None,
    enable_fallback: bool = True,
    data_dir: str | None = None,
):
    """Create a storage backend based on configuration."""
    return _get_factory().create_storage(db_type, db_file, enable_fallback, data_dir)

def create_storage_with_retry(max_retries: int = 3, retry_delay: float = 1.0, **kwargs):
    """Create a storage backend with retry logic."""
    return _get_factory().create_storage_with_retry(max_retries, retry_delay, **kwargs)

def get_storage_info(storage):
    """Get information about a storage backend."""
    return _get_factory().get_storage_info(storage)

def get_db_type() -> str:
    """Get the configured database type from environment variables."""
    return _get_factory().get_db_type()

def get_db_file() -> str:
    """Get the SQLite database file path from environment."""
    return _get_factory().get_db_file()

def get_data_dir():
    """Get the data directory for file storage."""
    from pathlib import Path
    return Path(_get_factory().get_data_dir())

# Import storage implementations at module level
from .file_storage import FileStorage
from .db_storage import DatabaseStorage
