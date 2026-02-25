"""File-based storage implementation using JSON files.

This module provides a storage backend that uses JSON files for persistence,
maintaining backward compatibility with the existing file-based format.
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
)

logger = logging.getLogger(__name__)


class FileStorage(StorageBackend):
    """File-based storage using JSON files."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        latest_filename: str = "latest-24h.json",
        archive_filename: str = "archive.json",
        status_filename: str = "source-status.json",
        waytoagi_filename: str = "waytoagi-7d.json",
        title_cache_filename: str = "title-zh-cache.json",
    ):
        """Initialize file storage.

        Args:
            data_dir: Directory containing data files
            latest_filename: Name of the latest snapshot file
            archive_filename: Name of the archive file
            status_filename: Name of the status file
            waytoagi_filename: Name of the WaytoAGI data file
            title_cache_filename: Name of the title cache file
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.latest_path = self.data_dir / latest_filename
        self.archive_path = self.data_dir / archive_filename
        self.status_path = self.data_dir / status_filename
        self.waytoagi_path = self.data_dir / waytoagi_filename
        self.title_cache_path = self.data_dir / title_cache_filename

        logger.info(f"FileStorage initialized with data_dir: {self.data_dir}")

    def initialize(self) -> None:
        """Initialize the file storage (ensure directory exists)."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("FileStorage directory ensured")

    def close(self) -> None:
        """Close file storage (no-op for file-based)."""
        logger.debug("FileStorage closed")

    def save_news_items(self, items: list[NewsItem]) -> int:
        """Save news items to latest snapshot."""
        try:
            if not items:
                return 0

            # Load existing snapshot to preserve metadata
            existing = self.load_snapshot("latest") or {}

            now = datetime.now()
            latest_payload = {
                "generated_at": existing.get("generated_at") or now.isoformat(),
                "window_hours": existing.get("window_hours", 24),
                "total_items": len(items),
                "total_items_raw": existing.get("total_items_raw", len(items)),
                "site_count": existing.get("site_count", 0),
                "source_count": existing.get("source_count", 0),
                "topic_filter": existing.get("topic_filter", ""),
                "archive_total": existing.get("archive_total", 0),
                "site_stats": existing.get("site_stats", []),
                "items": [item.to_dict() for item in items],
                "items_ai": [item.to_dict() for item in items],
            }

            self._write_json(self.latest_path, latest_payload)
            logger.info(f"Saved {len(items)} news items to {self.latest_path}")
            return len(items)
        except Exception as e:
            logger.error(f"Failed to save news items: {e}")
            raise StorageError(f"Failed to save news items: {e}") from e

    def save_archive_items(self, items: list[NewsItem]) -> int:
        """Save archive items."""
        try:
            archive_payload = {
                "generated_at": datetime.now().isoformat(),
                "total_items": len(items),
                "items": [item.to_dict() for item in items],
            }
            self._write_json(self.archive_path, archive_payload)
            logger.info(f"Saved {len(items)} archive items to {self.archive_path}")
            return len(items)
        except Exception as e:
            logger.error(f"Failed to save archive items: {e}")
            raise StorageError(f"Failed to save archive items: {e}") from e

    def load_archive(self) -> dict[str, NewsItem]:
        """Load archive items from file."""
        try:
            if not self.archive_path.exists():
                logger.debug(f"Archive file not found: {self.archive_path}")
                return {}

            payload = self._read_json(self.archive_path)
            items = payload.get("items", [])

            out: dict[str, NewsItem] = {}
            for it in items:
                item_id = it.get("id")
                if item_id:
                    out[item_id] = NewsItem(**it)
            return out
        except Exception as e:
            logger.error(f"Failed to load archive: {e}")
            raise StorageError(f"Failed to load archive: {e}") from e

    def load_latest_items(self, since: datetime | None = None) -> list[NewsItem]:
        """Load latest items."""
        try:
            snapshot = self.load_snapshot("latest")
            if not snapshot:
                return []

            items_data = snapshot.get("items", [])
            items = [NewsItem(**it) for it in items_data]

            if since:
                items = [
                    item
                    for item in items
                    if datetime.fromisoformat(item.first_seen_at) >= since
                ]

            return items
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
        """Save a snapshot by type."""
        try:
            if snapshot_type == "latest":
                path = self.latest_path
            elif snapshot_type == "status":
                path = self.status_path
            else:
                raise StorageError(f"Unknown snapshot type: {snapshot_type}")

            payload = metadata.to_dict()

            if snapshot_type == "latest":
                payload.update({
                    "items": [item.to_dict() for item in items],
                    "items_ai": [item.to_dict() for item in (items_ai or items)],
                    "items_all_raw": [item.to_dict() for item in (items_all_raw or [])],
                    "items_all": [item.to_dict() for item in (items_all or [])],
                    "site_stats": site_stats or [],
                })
            elif snapshot_type == "status":
                payload.update({
                    "sites": [record.to_dict() for record in items],
                    "successful_sites": sum(1 for r in items if r.ok),
                    "failed_sites": [r.site_id for r in items if not r.ok],
                    "zero_item_sites": [r.site_id for r in items if r.ok and r.item_count == 0],
                })

            self._write_json(path, payload)
            logger.info(f"Saved snapshot '{snapshot_type}' to {path}")
        except Exception as e:
            logger.error(f"Failed to save snapshot '{snapshot_type}': {e}")
            raise StorageError(f"Failed to save snapshot '{snapshot_type}': {e}") from e

    def load_snapshot(self, snapshot_type: str) -> dict[str, Any] | None:
        """Load a snapshot by type."""
        try:
            if snapshot_type == "latest":
                path = self.latest_path
            elif snapshot_type == "status":
                path = self.status_path
            elif snapshot_type == "waytoagi":
                path = self.waytoagi_path
            else:
                raise StorageError(f"Unknown snapshot type: {snapshot_type}")

            if not path.exists():
                logger.debug(f"Snapshot file not found: {path}")
                return None

            return self._read_json(path)
        except Exception as e:
            logger.error(f"Failed to load snapshot '{snapshot_type}': {e}")
            raise StorageError(f"Failed to load snapshot '{snapshot_type}': {e}") from e

    def save_status_records(self, records: list[StatusRecord]) -> int:
        """Save site status records."""
        try:
            status_payload = {
                "generated_at": datetime.now().isoformat(),
                "sites": [record.to_dict() for record in records],
                "successful_sites": sum(1 for r in records if r.ok),
                "failed_sites": [r.site_id for r in records if not r.ok],
                "zero_item_sites": [r.site_id for r in records if r.ok and r.item_count == 0],
            }
            self._write_json(self.status_path, status_payload)
            logger.info(f"Saved {len(records)} status records to {self.status_path}")
            return len(records)
        except Exception as e:
            logger.error(f"Failed to save status records: {e}")
            raise StorageError(f"Failed to save status records: {e}") from e

    def load_status_records(self) -> list[StatusRecord]:
        """Load all status records."""
        try:
            snapshot = self.load_snapshot("status")
            if not snapshot:
                return []

            sites = snapshot.get("sites", [])
            return [StatusRecord(**site) for site in sites]
        except Exception as e:
            logger.error(f"Failed to load status records: {e}")
            raise StorageError(f"Failed to load status records: {e}") from e

    def save_waytoagi_data(self, data: dict[str, Any]) -> None:
        """Save WaytoAGI data."""
        try:
            self._write_json(self.waytoagi_path, data)
            logger.info(f"Saved WaytoAGI data to {self.waytoagi_path}")
        except Exception as e:
            logger.error(f"Failed to save WaytoAGI data: {e}")
            raise StorageError(f"Failed to save WaytoAGI data: {e}") from e

    def load_waytoagi_data(self) -> dict[str, Any] | None:
        """Load WaytoAGI data."""
        return self.load_snapshot("waytoagi")

    def save_title_cache(self, cache: dict[str, str]) -> None:
        """Save title translation cache."""
        try:
            self._write_json(self.title_cache_path, cache)
            logger.info(f"Saved title cache ({len(cache)} entries) to {self.title_cache_path}")
        except Exception as e:
            logger.error(f"Failed to save title cache: {e}")
            raise StorageError(f"Failed to save title cache: {e}") from e

    def load_title_cache(self) -> dict[str, str]:
        """Load title translation cache."""
        try:
            if not self.title_cache_path.exists():
                return {}

            payload = self._read_json(self.title_cache_path)
            if isinstance(payload, dict):
                return {str(k): str(v) for k, v in payload.items()}
            return {}
        except Exception as e:
            logger.error(f"Failed to load title cache: {e}")
            raise StorageError(f"Failed to load title cache: {e}") from e

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        return {
            "backend": "file",
            "data_dir": str(self.data_dir),
            "latest_file": str(self.latest_path),
            "archive_file": str(self.archive_path),
            "status_file": str(self.status_path),
            "waytoagi_file": str(self.waytoagi_path),
            "title_cache_file": str(self.title_cache_path),
            "latest_exists": self.latest_path.exists(),
            "archive_exists": self.archive_path.exists(),
            "status_exists": self.status_path.exists(),
            "waytoagi_exists": self.waytoagi_path.exists(),
            "title_cache_exists": self.title_cache_path.exists(),
        }

    def is_healthy(self) -> bool:
        """Check if file storage is healthy."""
        try:
            self.data_dir.exists() or self.data_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    def _read_json(self, path: Path) -> dict[str, Any]:
        """Read JSON file safely."""
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {path}: {e}")
            raise StorageError(f"Invalid JSON in {path}: {e}") from e
        except Exception as e:
            logger.error(f"Failed to read {path}: {e}")
            raise StorageError(f"Failed to read {path}: {e}") from e

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Write JSON file safely."""
        try:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to write {path}: {e}")
            raise StorageError(f"Failed to write {path}: {e}") from e


__all__ = ["FileStorage"]
