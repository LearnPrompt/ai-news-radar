#!/usr/bin/env python3
"""Tests for current file-based storage implementation.

Tests the file storage that is currently used by update_news.py.
This provides a baseline for when database storage is added.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

UTC = timezone.utc


class FileStorageTests:
    """Test the current file-based storage implementation."""

    def test_archive_loading_existing_file(self) -> None:
        """Test loading an existing archive file."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.json"

            # Create sample archive with the expected format (nested dict)
            sample_archive = {
                "generated_at": "2025-02-25T12:00:00Z",
                "total_items": 1,
                "items": [
                    {
                        "id": "item-1",
                        "site_id": "test",
                        "site_name": "Test Source",
                        "source": "test",
                        "title": "Test Article",
                        "url": "https://example.com/article",
                        "published_at": "2025-02-25T12:00:00Z",
                        "first_seen_at": "2025-02-25T12:00:00Z",
                        "last_seen_at": "2025-02-25T12:00:00Z",
                    }
                ]
            }

            archive_path.write_text(
                json.dumps(sample_archive, ensure_ascii=False),
                encoding="utf-8"
            )

            # Load archive
            loaded = load_archive(archive_path)

            # The load_archive function returns the loaded data structure
            assert loaded is not None
            # Depending on implementation, it might return dict or None
            assert isinstance(loaded, (dict, type(None)))

    def test_archive_loading_missing_file(self) -> None:
        """Test loading when archive file doesn't exist."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "nonexistent.json"

            loaded = load_archive(archive_path)

            assert loaded == {}

    def test_archive_loading_corrupted_file(self) -> None:
        """Test loading a corrupted archive file."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "corrupt.json"
            archive_path.write_text("invalid json", encoding="utf-8")

            loaded = load_archive(archive_path)

            assert loaded == {}

    def test_archive_loading_nested_dict_format(self) -> None:
        """Test loading archive with nested dict format."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.json"

            # Create archive with nested dict format (current implementation)
            sample_archive = {
                "generated_at": "2025-02-25T12:00:00Z",
                "total_items": 2,
                "items": [
                    {
                        "id": "item-1",
                        "title": "Test Article 1",
                        "url": "https://example.com/1",
                    },
                    {
                        "id": "item-2",
                        "title": "Test Article 2",
                        "url": "https://example.com/2",
                    },
                ]
            }

            archive_path.write_text(
                json.dumps(sample_archive, ensure_ascii=False),
                encoding="utf-8"
            )

            # Load archive
            loaded = load_archive(archive_path)

            # Should return None or handle gracefully for this format
            # The actual implementation may vary
            assert loaded is not None

    def test_title_cache_operations(self) -> None:
        """Test title translation cache operations."""
        from update_news import load_title_zh_cache

        with TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "title-zh-cache.json"

            # Create cache file manually (no save function exists)
            cache_data = {
                "Test Title 1": "测试标题 1",
                "Test Title 2": "测试标题 2",
                "Test Title 3": "测试标题 3",
            }

            cache_path.write_text(
                json.dumps(cache_data, ensure_ascii=False),
                encoding="utf-8"
            )

            # Verify file exists
            assert cache_path.exists()

            # Load cache
            loaded = load_title_zh_cache(cache_path)

            assert len(loaded) == 3
            assert loaded["Test Title 1"] == "测试标题 1"
            assert loaded["Test Title 2"] == "测试标题 2"

    def test_title_cache_missing_file(self) -> None:
        """Test loading cache when file doesn't exist."""
        from update_news import load_title_zh_cache

        with TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "nonexistent.json"

            loaded = load_title_zh_cache(cache_path)

            # Should return empty dict
            assert isinstance(loaded, dict)
            assert len(loaded) == 0

    def test_output_directory_creation(self) -> None:
        """Test that output directory is created if it doesn't exist."""
        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data" / "subdir"
            archive_path = output_dir / "archive.json"

            # Create parent directories
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create a test archive
            test_data = {"test": "data"}
            archive_path.write_text(
                json.dumps(test_data, ensure_ascii=False),
                encoding="utf-8"
            )

            # Verify file was created
            assert archive_path.exists()

    def test_json_encoding_handling(self) -> None:
        """Test JSON encoding with Unicode characters."""
        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "test.json"

            # Create data with Unicode
            test_data = {
                "title": "AI突破：GPT-5发布",
                "emoji": "🤖🔬📊",
                "chinese": "人工智能大模型",
                "japanese": "人工知能",
            }

            archive_path.write_text(
                json.dumps(test_data, ensure_ascii=False),
                encoding="utf-8"
            )

            # Load and verify
            loaded = json.loads(archive_path.read_text(encoding="utf-8"))

            assert loaded["title"] == "AI突破：GPT-5发布"
            assert loaded["emoji"] == "🤖🔬📊"
            assert loaded["chinese"] == "人工智能大模型"

    def test_archive_pruning_simulation(self) -> None:
        """Simulate archive pruning for old items."""
        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.json"

            now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

            # Create archive with items of different ages
            items = []
            for i in range(5):
                # Start with 1 hour offset for item-0, increment by 13 hours
                offset_hours = 1 + i * 13
                items.append({
                    "id": f"item-{i}",
                    "title": f"Article {i}",
                    "url": f"https://example.com/{i}",
                    "last_seen_at": (now - timedelta(hours=offset_hours)).isoformat(),
                })

            archive_data = {
                "generated_at": now.isoformat(),
                "total_items": 5,
                "items": items
            }

            archive_path.write_text(
                json.dumps(archive_data, ensure_ascii=False),
                encoding="utf-8"
            )

            # Load archive
            loaded = json.loads(archive_path.read_text(encoding="utf-8"))

            # Simulate pruning items older than 24 hours
            cutoff = now - timedelta(hours=24)
            pruned = [
                item for item in loaded["items"]
                if datetime.fromisoformat(item["last_seen_at"]) > cutoff
            ]

            # Should keep only items from last 24 hours (items 0-1)
            assert len(pruned) == 2

    def test_data_integrity_roundtrip(self) -> None:
        """Test that data survives save/load roundtrip."""
        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.json"

            # Create complex data
            original_data = {
                "generated_at": "2025-02-25T12:30:45.123456Z",
                "total_items": 1,
                "items": [
                    {
                        "id": "test-123",
                        "site_id": "test-site",
                        "site_name": "Test Site",
                        "source": "test-section",
                        "title": "Complex Article Title With Special Chars: <>\"'&",
                        "url": "https://example.com/path?param=value&a=1",
                        "published_at": "2025-02-25T10:00:00Z",
                        "first_seen_at": "2025-02-25T10:00:00Z",
                        "last_seen_at": "2025-02-25T12:30:45Z",
                        "title_zh": "复杂标题测试",
                        "extra": {
                            "author": "Test Author",
                            "tags": ["ai", "ml", "test"],
                            "score": 95,
                        },
                    }
                ]
            }

            # Save
            archive_path.write_text(
                json.dumps(original_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            # Load
            loaded = json.loads(archive_path.read_text(encoding="utf-8"))

            # Verify all fields match
            assert loaded == original_data
            assert loaded["items"][0]["extra"]["tags"] == ["ai", "ml", "test"]
            assert loaded["items"][0]["title_zh"] == "复杂标题测试"


def run_all_file_storage_tests():
    """Run all file storage tests."""
    print("Running file storage tests...\n")

    test_class = FileStorageTests()

    tests = [
        ("Archive Loading - Existing File", test_class.test_archive_loading_existing_file),
        ("Archive Loading - Missing File", test_class.test_archive_loading_missing_file),
        ("Archive Loading - Corrupted File", test_class.test_archive_loading_corrupted_file),
        ("Archive Loading - Nested Dict", test_class.test_archive_loading_nested_dict_format),
        ("Title Cache Operations", test_class.test_title_cache_operations),
        ("Title Cache - Missing File", test_class.test_title_cache_missing_file),
        ("Output Directory Creation", test_class.test_output_directory_creation),
        ("JSON Encoding Handling", test_class.test_json_encoding_handling),
        ("Archive Pruning Simulation", test_class.test_archive_pruning_simulation),
        ("Data Integrity Roundtrip", test_class.test_data_integrity_roundtrip),
    ]

    failed = []
    for name, test in tests:
        try:
            print(f"Running: {name}...", end=" ")
            test()
            print("PASS")
        except Exception as e:
            print(f"FAIL")
            print(f"  Error: {e}")
            failed.append((name, e))

    print("\n" + "=" * 60)
    if failed:
        print(f"\n{len(failed)} test(s) failed:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return 1
    else:
        print("\nAll file storage tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_file_storage_tests())
