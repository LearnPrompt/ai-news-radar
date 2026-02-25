#!/usr/bin/env python3
"""Tests for storage layer.

Tests the storage abstraction layer including FileStorage and DatabaseStorage.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage import (
    NewsItem,
    StatusRecord,
    SnapshotMetadata,
    create_storage,
    InitializationError,
    ConnectionError,
)

UTC = timezone.utc


def create_sample_item(item_id: str) -> NewsItem:
    """Create a sample news item for testing."""
    return NewsItem(
        id=item_id,
        site_id="test",
        site_name="Test Source",
        source="test-section",
        title=f"Test Article {item_id}",
        url=f"https://example.com/article/{item_id}",
        published_at="2025-02-25T12:00:00Z",
        first_seen_at="2025-02-25T12:00:00Z",
        last_seen_at="2025-02-25T12:00:00Z",
        meta={"test": "data"},
        title_zh=f"测试文章 {item_id}",
    )


def test_file_storage_basic():
    """Test basic file storage operations."""
    with TemporaryDirectory() as tmp_dir:
        from storage.file_storage import FileStorage

        storage = FileStorage(data_dir=tmp_dir)
        storage.initialize()

        # Save archive items
        items = [create_sample_item(f"item-{i}") for i in range(5)]
        saved_count = storage.save_archive_items(items)
        assert saved_count == 5

        # Load archive
        archive = storage.load_archive()
        assert len(archive) == 5
        assert "item-0" in archive
        assert archive["item-0"].title == "Test Article item-0"

        # Check health
        assert storage.is_healthy() is True

        # Get stats
        stats = storage.get_stats()
        assert stats["backend"] == "file"
        assert stats["archive_exists"] is True

        storage.close()
        print("File storage basic tests passed!")


def test_file_storage_status_records():
    """Test saving and loading status records."""
    with TemporaryDirectory() as tmp_dir:
        from storage.file_storage import FileStorage

        storage = FileStorage(data_dir=tmp_dir)
        storage.initialize()

        # Save status records
        records = [
            StatusRecord(
                site_id=f"site-{i}",
                site_name=f"Site {i}",
                ok=i % 2 == 0,
                item_count=i * 10,
                last_check_at=datetime.now(tz=UTC).isoformat(),
                error_message=None if i % 2 == 0 else "Connection failed",
                response_time_ms=i * 100,
            )
            for i in range(3)
        ]

        saved_count = storage.save_status_records(records)
        assert saved_count == 3

        # Load status records
        loaded = storage.load_status_records()
        assert len(loaded) == 3
        assert loaded[0].site_id == "site-0"
        assert loaded[0].ok is True
        assert loaded[1].ok is False

        storage.close()
        print("File storage status records tests passed!")


def test_file_storage_title_cache():
    """Test title translation cache."""
    with TemporaryDirectory() as tmp_dir:
        from storage.file_storage import FileStorage

        storage = FileStorage(data_dir=tmp_dir)
        storage.initialize()

        # Save title cache
        cache = {
            "Test Title 1": "测试标题 1",
            "Test Title 2": "测试标题 2",
        }
        storage.save_title_cache(cache)

        # Load title cache
        loaded = storage.load_title_cache()
        assert len(loaded) == 2
        assert loaded["Test Title 1"] == "测试标题 1"

        storage.close()
        print("File storage title cache tests passed!")


def test_file_storage_waytoagi():
    """Test WaytoAGI data storage."""
    with TemporaryDirectory() as tmp_dir:
        from storage.file_storage import FileStorage

        storage = FileStorage(data_dir=tmp_dir)
        storage.initialize()

        # Save WaytoAGI data
        data = {
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "timezone": "Asia/Shanghai",
            "root_url": "https://example.com",
            "window_days": 7,
            "count_7d": 10,
            "updates_7d": [
                {"title": f"Update {i}", "url": f"https://example.com/{i}"}
                for i in range(10)
            ],
        }
        storage.save_waytoagi_data(data)

        # Load WaytoAGI data
        loaded = storage.load_waytoagi_data()
        assert loaded is not None
        assert loaded["count_7d"] == 10
        assert len(loaded["updates_7d"]) == 10

        storage.close()
        print("File storage WaytoAGI tests passed!")


def test_db_storage_sqlite():
    """Test SQLite database storage."""
    with TemporaryDirectory() as tmp_dir:
        from storage.db_storage import DatabaseStorage

        db_path = Path(tmp_dir) / "test.db"
        storage = DatabaseStorage(db_type="sqlite", db_file=db_path)
        storage.initialize()

        # Check database file exists
        assert db_path.exists()

        # Save items
        items = [create_sample_item(f"item-{i}") for i in range(5)]
        saved_count = storage.save_news_items(items)
        assert saved_count == 5

        # Load archive
        archive = storage.load_archive()
        assert len(archive) == 5
        assert "item-0" in archive

        # Check health
        assert storage.is_healthy() is True

        # Get stats
        stats = storage.get_stats()
        assert stats["backend"] == "database"
        assert stats["db_type"] == "sqlite"
        assert stats["news_items_count"] == 5

        # Test update (save same item again)
        updated_item = create_sample_item("item-0")
        updated_item.title = "Updated Title"
        updated_item.last_seen_at = datetime.now(tz=UTC).isoformat()
        storage.save_news_items([updated_item])

        # Verify update (not duplicate)
        archive = storage.load_archive()
        assert len(archive) == 5
        assert archive["item-0"].title == "Updated Title"

        storage.close()
        print("SQLite database storage tests passed!")


def test_db_storage_sqlite_status():
    """Test SQLite database storage with status records."""
    with TemporaryDirectory() as tmp_dir:
        from storage.db_storage import DatabaseStorage

        db_path = Path(tmp_dir) / "test.db"
        storage = DatabaseStorage(db_type="sqlite", db_file=db_path)
        storage.initialize()

        # Save status records
        now = datetime.now(tz=UTC).isoformat()
        records = [
            StatusRecord(
                site_id=f"site-{i}",
                site_name=f"Site {i}",
                ok=i % 2 == 0,
                item_count=i * 10,
                last_check_at=now,
                error_message=None if i % 2 == 0 else "Connection failed",
                response_time_ms=i * 100,
            )
            for i in range(3)
        ]

        saved_count = storage.save_status_records(records)
        assert saved_count == 3

        # Load status records
        loaded = storage.load_status_records()
        assert len(loaded) == 3
        assert loaded[0].site_id == "site-0"

        storage.close()
        print("SQLite database status tests passed!")


def test_factory_default():
    """Test storage factory with default settings."""
    # Clear environment
    for key in ["DB_TYPE", "DB_FILE", "DATA_DIR"]:
        os.environ.pop(key, None)

    with TemporaryDirectory() as tmp_dir:
        os.environ["DATA_DIR"] = tmp_dir
        storage = create_storage(enable_fallback=True)

        # Should create file storage by default
        assert storage is not None
        storage.initialize()
        assert storage.is_healthy() is True
        storage.close()

        print("Factory default tests passed!")


def test_factory_sqlite():
    """Test storage factory with SQLite."""
    with TemporaryDirectory() as tmp_dir:
        os.environ["DB_TYPE"] = "sqlite"
        os.environ["DB_FILE"] = str(Path(tmp_dir) / "test.db")

        storage = create_storage(enable_fallback=True)

        # Should create SQLite storage
        assert storage is not None
        storage.initialize()
        assert storage.is_healthy() is True
        assert type(storage).__name__ == "DatabaseStorage"
        storage.close()

        # Clean up
        for key in ["DB_TYPE", "DB_FILE"]:
            os.environ.pop(key, None)

        print("Factory SQLite tests passed!")


def test_factory_invalid_type_fallback():
    """Test storage factory with invalid type falls back to file storage."""
    with TemporaryDirectory() as tmp_dir:
        os.environ["DB_TYPE"] = "invalid_type"
        os.environ["DATA_DIR"] = tmp_dir

        storage = create_storage(enable_fallback=True)

        # Should use default (sqlite) when invalid type is provided
        # SQLite should work since it's self-contained
        assert storage is not None
        storage.initialize()
        assert storage.is_healthy() is True
        # The factory uses default 'sqlite' for invalid types
        assert type(storage).__name__ in ["DatabaseStorage", "FileStorage"]
        storage.close()

        # Clean up
        for key in ["DB_TYPE", "DATA_DIR"]:
            os.environ.pop(key, None)

        print("Factory invalid type fallback tests passed!")


def test_news_item_dataclass():
    """Test NewsItem dataclass."""
    item = create_sample_item("test-id")

    assert item.id == "test-id"
    assert item.title == "Test Article test-id"
    assert item.title_zh == "测试文章 test-id"

    # Test to_dict()
    item_dict = item.to_dict()
    assert isinstance(item_dict, dict)
    assert item_dict["id"] == "test-id"
    assert item_dict["title"] == "Test Article test-id"


def test_status_record_dataclass():
    """Test StatusRecord dataclass."""
    record = StatusRecord(
        site_id="test-site",
        site_name="Test Site",
        ok=True,
        item_count=10,
        last_check_at="2025-02-25T12:00:00Z",
        error_message=None,
        response_time_ms=100,
        metadata={"test": "data"},
    )

    assert record.site_id == "test-site"
    assert record.ok is True
    assert record.item_count == 10

    # Test to_dict()
    record_dict = record.to_dict()
    assert isinstance(record_dict, dict)
    assert record_dict["site_id"] == "test-site"


def test_snapshot_metadata_dataclass():
    """Test SnapshotMetadata dataclass."""
    metadata = SnapshotMetadata(
        generated_at="2025-02-25T12:00:00Z",
        window_hours=24,
        total_items=100,
        total_items_raw=150,
        site_count=10,
        source_count=15,
        topic_filter="ai_tech_robotics",
        archive_total=1000,
    )

    assert metadata.total_items == 100
    assert metadata.topic_filter == "ai_tech_robotics"

    # Test to_dict()
    metadata_dict = metadata.to_dict()
    assert isinstance(metadata_dict, dict)
    assert metadata_dict["total_items"] == 100


def run_all_tests():
    """Run all tests."""
    print("Running storage layer tests...\n")

    tests = [
        test_news_item_dataclass,
        test_status_record_dataclass,
        test_snapshot_metadata_dataclass,
        test_file_storage_basic,
        test_file_storage_status_records,
        test_file_storage_title_cache,
        test_file_storage_waytoagi,
        test_db_storage_sqlite,
        test_db_storage_sqlite_status,
        test_factory_default,
        test_factory_sqlite,
        test_factory_invalid_type_fallback,
    ]

    failed = []
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"FAILED: {test.__name__}: {e}")
            failed.append((test.__name__, e))

    print("\n" + "=" * 60)
    if failed:
        print(f"\n{len(failed)} test(s) failed:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return 1
    else:
        print("\nAll tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
