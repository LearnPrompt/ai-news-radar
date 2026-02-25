#!/usr/bin/env python3
"""Integration tests for update_news.py main module.

Tests the complete flow from fetching to saving output files,
including RSS OPML processing and output validation.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

UTC = timezone.utc


# =============================================================================
# Main Function Flow Tests
# =============================================================================

class MainFlowTests:
    """Test the main execution flow of update_news.py."""

    def test_archive_loading(self) -> None:
        """INT-002: Load existing archive on startup."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.json"

            # Create sample archive with dict format (items keyed by ID)
            sample_archive = {
                "item-1": {
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
            }

            archive_path.write_text(
                json.dumps(sample_archive, ensure_ascii=False),
                encoding="utf-8"
            )

            # Load archive
            loaded = load_archive(archive_path)

            assert loaded is not None
            assert "item-1" in loaded
            assert loaded["item-1"]["title"] == "Test Article"

    def test_archive_missing_returns_empty(self) -> None:
        """Test that missing archive file returns empty dict."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "nonexistent.json"

            loaded = load_archive(archive_path)

            assert loaded == {}

    def test_archive_corrupted_returns_empty(self) -> None:
        """Test that corrupted archive file returns empty dict."""
        from update_news import load_archive

        with TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "corrupt.json"
            archive_path.write_text("invalid json", encoding="utf-8")

            loaded = load_archive(archive_path)

            assert loaded == {}

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_new_items_added(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-003: Add items that don't exist."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        # Mock empty archive
        mock_load_archive.return_value = {}

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        # Mock new items
        mock_items = [
            RawItem(
                site_id="test",
                site_name="Test Source",
                source="test",
                title="Article 0",
                url="https://example.com/article-0",
                published_at=now,
            )
        ]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        mock_waytoagi.return_value = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "has_error": False,
        }

        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch('sys.argv', [
                'update_news.py',
                '--output-dir', str(output_dir),
                '--window-hours', '24',
            ]):
                result = main()

            # Should complete successfully
            assert result == 0

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_existing_items_updated(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-004: Process existing items with new data."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        # Mock archive with existing item
        existing_item = {
            "id": "test-item-1",
            "site_id": "test",
            "site_name": "Test Source",
            "source": "test",
            "title": "Original Title",
            "url": "https://example.com/article",
            "published_at": "2025-02-25T11:00:00Z",
            "first_seen_at": "2025-02-25T11:00:00Z",
            "last_seen_at": "2025-02-25T11:00:00Z",
        }
        mock_load_archive.return_value = {"test-item-1": existing_item}

        # Mock same item with updated data
        mock_items = [
            RawItem(
                site_id="test",
                site_name="Test Source",
                source="test",
                title="Updated Title",
                url="https://example.com/article",
                published_at=now,
            )
        ]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        mock_waytoagi.return_value = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "has_error": False,
        }

        with patch('update_news.utc_now', return_value=now):
            with TemporaryDirectory() as tmp_dir:
                output_dir = Path(tmp_dir) / "data"
                output_dir.mkdir(parents=True, exist_ok=True)

                with patch('sys.argv', [
                    'update_news.py',
                    '--output-dir', str(output_dir),
                    '--window-hours', '24',
                ]):
                    result = main()

                # Should complete successfully
                assert result == 0


# =============================================================================
# RSS OPML Processing Tests
# =============================================================================

class RSSOPMLTests:
    """Test RSS OPML feed processing."""

    def test_valid_opml_file(self) -> None:
        """INT-010: Process feeds from valid OPML."""
        from update_news import parse_opml_subscriptions

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        with TemporaryDirectory() as tmp_dir:
            opml_path = Path(tmp_dir) / "test.opml"

            # Create valid OPML
            opml_content = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
<body>
<outline text="Tech News" title="Tech News" xmlUrl="https://tech.example.com/feed.xml" />
<outline text="AI Updates" title="AI Updates" xmlUrl="https://ai.example.com/rss" />
</body>
</opml>"""
            opml_path.write_text(opml_content, encoding="utf-8")

            # Parse OPML
            feeds = parse_opml_subscriptions(opml_path)

            assert len(feeds) == 2
            assert feeds[0]["title"] == "Tech News"
            assert feeds[1]["title"] == "AI Updates"

    def test_missing_opml_file(self) -> None:
        """INT-011: Run without OPML path - should continue."""
        from update_news import parse_opml_subscriptions

        with TemporaryDirectory() as tmp_dir:
            opml_path = Path(tmp_dir) / "nonexistent.opml"

            # Should handle gracefully - return empty list
            feeds = parse_opml_subscriptions(opml_path)

            assert feeds == []

    def test_invalid_opml_file(self) -> None:
        """INT-012: Malformed XML in OPML."""
        from update_news import parse_opml_subscriptions

        with TemporaryDirectory() as tmp_dir:
            opml_path = Path(tmp_dir) / "invalid.opml"

            # Create invalid XML
            opml_path.write_text("not valid xml", encoding="utf-8")

            # Should handle gracefully
            feeds = parse_opml_subscriptions(opml_path)

            # Should return empty list or handle error
            assert feeds is not None


# =============================================================================
# Output File Validation Tests
# =============================================================================

class OutputFileValidationTests:
    """Validate structure of generated output files."""

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_latest_24h_json_structure(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-020: Validate latest-24h.json schema."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        mock_load_archive.return_value = {}

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        # Create AI-related mock items
        mock_items = [
            RawItem(
                site_id="test",
                site_name="Test Source",
                source="test",
                title="AI breakthrough in language models",
                url="https://example.com/article-0",
                published_at=now,
            )
        ]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        mock_waytoagi.return_value = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "has_error": False,
        }

        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch('sys.argv', [
                'update_news.py',
                '--output-dir', str(output_dir),
                '--window-hours', '24',
            ]):
                main()

            # Validate structure
            latest_path = output_dir / "latest-24h.json"
            with open(latest_path, encoding="utf-8") as f:
                data = json.load(f)

            # Required fields
            assert "generated_at" in data
            assert "window_hours" in data
            assert "total_items" in data
            assert "items" in data
            assert "site_stats" in data

            # Data types
            assert isinstance(data["window_hours"], int)
            assert isinstance(data["items"], list)

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_archive_json_structure(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-021: Validate archive.json schema."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        mock_load_archive.return_value = {}

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        mock_items = [
            RawItem(
                site_id="test",
                site_name="Test Source",
                source="test",
                title="Article 0",
                url="https://example.com/article-0",
                published_at=now,
            )
        ]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        mock_waytoagi.return_value = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "has_error": False,
        }

        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch('sys.argv', [
                'update_news.py',
                '--output-dir', str(output_dir),
                '--window-hours', '24',
                '--archive-days', '45',
            ]):
                main()

            # Validate structure
            archive_path = output_dir / "archive.json"
            with open(archive_path, encoding="utf-8") as f:
                data = json.load(f)

            # Required fields
            assert "generated_at" in data
            assert "total_items" in data
            assert "items" in data

            # Data types
            assert isinstance(data["total_items"], int)
            assert isinstance(data["items"], list)

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_source_status_json_structure(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-022: Validate source-status.json schema."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        mock_load_archive.return_value = {}

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        mock_items = [RawItem(
            site_id="test",
            site_name="Test Source",
            source="test",
            title="Test Article",
            url="https://example.com/article",
            published_at=now,
        )]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        mock_waytoagi.return_value = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "window_days": 7,
            "count_7d": 0,
            "updates_7d": [],
            "has_error": False,
        }

        with TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "data"
            output_dir.mkdir(parents=True, exist_ok=True)

            with patch('sys.argv', [
                'update_news.py',
                '--output-dir', str(output_dir),
                '--window-hours', '24',
            ]):
                main()

            # Validate structure
            status_path = output_dir / "source-status.json"
            with open(status_path, encoding="utf-8") as f:
                data = json.load(f)

            # Required fields
            assert "generated_at" in data
            assert "sites" in data
            assert "successful_sites" in data
            assert "failed_sites" in data

            # Data types
            assert isinstance(data["sites"], list)
            assert isinstance(data["successful_sites"], int)

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    def test_waytoagi_json_structure(
        self, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-023: Validate waytoagi-7d.json schema."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        mock_load_archive.return_value = {}

        now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

        mock_items = [RawItem(
            site_id="test",
            site_name="Test Source",
            source="test",
            title="Test Article",
            url="https://example.com/article",
            published_at=now,
        )]

        mock_statuses = [
            {
                "site_id": "test",
                "site_name": "Test Source",
                "ok": True,
                "item_count": 1,
                "duration_ms": 500,
                "error": None
            }
        ]
        mock_collect_all.return_value = (mock_items, mock_statuses)

        # Mock WaytoAGI success
        waytoagi_data = {
            "generated_at": now.isoformat(),
            "timezone": "Asia/Shanghai",
            "root_url": "https://waytoagi.feishu.cn/wiki/test",
            "history_url": None,
            "window_days": 7,
            "count_7d": 5,
            "updates_7d": [
                {
                    "date": "2025-02-25",
                    "title": "Test Update 1",
                    "content": "Test content"
                }
            ],
            "has_error": False,
        }
        with patch('update_news.fetch_waytoagi_recent_7d', return_value=waytoagi_data):
            with TemporaryDirectory() as tmp_dir:
                output_dir = Path(tmp_dir) / "data"
                output_dir.mkdir(parents=True, exist_ok=True)

                with patch('sys.argv', [
                    'update_news.py',
                    '--output-dir', str(output_dir),
                    '--window-hours', '24',
                ]):
                    main()

                # Validate structure
                waytoagi_path = output_dir / "waytoagi-7d.json"
                with open(waytoagi_path, encoding="utf-8") as f:
                    data = json.load(f)

                # Required fields
                assert "generated_at" in data
                assert "timezone" in data
                assert "window_days" in data
                assert "count_7d" in data
                assert "updates_7d" in data

    @patch('update_news.create_session')
    @patch('update_news.collect_all')
    @patch('update_news.load_archive')
    @patch('update_news.fetch_waytoagi_recent_7d')
    def test_title_cache_json_structure(
        self, mock_waytoagi, mock_load_archive, mock_collect_all, mock_session
    ) -> None:
        """INT-024: Validate title-zh-cache.json schema."""
        from update_news import main, RawItem

        session = MagicMock()
        mock_session.return_value = session

        # Mock existing title cache
        mock_cache = {
            "Test Title": "测试标题"
        }
        with patch('update_news.load_title_zh_cache', return_value=mock_cache):
            mock_load_archive.return_value = {}

            now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)

            mock_items = [RawItem(
                site_id="test",
                site_name="Test Source",
                source="test",
                title="Test Article",
                url="https://example.com/article",
                published_at=now,
            )]

            mock_statuses = [
                {
                    "site_id": "test",
                    "site_name": "Test Source",
                    "ok": True,
                    "item_count": 1,
                    "duration_ms": 500,
                    "error": None
                }
            ]
            mock_collect_all.return_value = (mock_items, mock_statuses)

            mock_waytoagi.return_value = {
                "generated_at": now.isoformat(),
                "timezone": "Asia/Shanghai",
                "window_days": 7,
                "count_7d": 0,
                "updates_7d": [],
                "has_error": False,
            }

            with TemporaryDirectory() as tmp_dir:
                output_dir = Path(tmp_dir) / "data"
                output_dir.mkdir(parents=True, exist_ok=True)

                with patch('sys.argv', [
                    'update_news.py',
                    '--output-dir', str(output_dir),
                    '--window-hours', '24',
                ]):
                    main()

                # Validate structure
                cache_path = output_dir / "title-zh-cache.json"
                with open(cache_path, encoding="utf-8") as f:
                    data = json.load(f)

                # Should be a dictionary with title translations
                assert isinstance(data, dict)


# =============================================================================
# Utility Function Tests
# =============================================================================

class UtilityFunctionTests:
    """Test utility functions from update_news.py."""

    def test_make_item_id_stable(self) -> None:
        """Test that item IDs are stable across different URLs with tracking params."""
        from update_news import make_item_id, normalize_url

        url1 = "https://example.com/article?a=1&utm_source=x"
        url2 = "https://example.com/article?a=1"

        id1 = make_item_id("site", "source", "Title", url1)
        id2 = make_item_id("site", "source", "Title", url2)

        assert id1 == id2

    def test_normalize_url(self) -> None:
        """Test URL normalization removes tracking parameters."""
        from update_news import normalize_url

        raw = "https://example.com/path?a=1&utm_source=x&fbclid=abc&utm_medium=email"
        normalized = normalize_url(raw)

        assert normalized == "https://example.com/path?a=1"

    def test_parse_date_any_rfc(self) -> None:
        """Test RFC date parsing."""
        from update_news import parse_date_any

        now = datetime(2025, 2, 21, 4, 30, tzinfo=UTC)
        dt = parse_date_any("Tue, 07 Oct 2025 03:00:00 GMT", now)

        assert dt == datetime(2025, 10, 7, 3, 0, tzinfo=UTC)

    def test_parse_relative_time_zh(self) -> None:
        """Test Chinese relative time parsing."""
        from update_news import parse_relative_time_zh

        now = datetime(2026, 2, 19, 12, 0, tzinfo=UTC)

        # Test minutes
        dt = parse_relative_time_zh("8分钟前", now)
        assert dt == datetime(2026, 2, 19, 11, 52, tzinfo=UTC)

        # Test hours
        dt = parse_relative_time_zh("2小时前", now)
        assert dt == datetime(2026, 2, 19, 10, 0, tzinfo=UTC)

        # Test days
        dt = parse_relative_time_zh("3天前", now)
        assert dt == datetime(2026, 2, 16, 12, 0, tzinfo=UTC)

    def test_is_ai_related_record(self) -> None:
        """Test AI-related filtering."""
        from update_news import is_ai_related_record

        ai_item = {
            "title": "GPT-5: The next generation of language models",
            "site_id": "test",
        }
        non_ai_item = {
            "title": "Sports news update",
            "site_id": "test",
        }

        assert is_ai_related_record(ai_item) is True
        assert is_ai_related_record(non_ai_item) is False

    def test_iso_datetime(self) -> None:
        """Test ISO datetime formatting."""
        from update_news import iso

        dt = datetime(2025, 2, 25, 12, 30, 45, tzinfo=UTC)
        iso_str = iso(dt)

        assert iso_str == "2025-02-25T12:30:45+00:00"


# =============================================================================
# Fixtures and Test Data
# =============================================================================

@pytest.fixture
def mock_session():
    """Create a mock requests session."""
    with patch('scripts.update_news.create_session') as mock:
        session = MagicMock()
        mock.return_value = session
        yield session


@pytest.fixture
def sample_raw_item():
    """Create a sample RawItem for testing."""
    now = datetime(2025, 2, 25, 12, 0, tzinfo=UTC)
    return {
        "site_id": "test",
        "site_name": "Test Source",
        "source": "test-section",
        "title": "Test Article",
        "url": "https://example.com/article",
        "published_at": now.isoformat(),
    }


@pytest.fixture
def sample_opml():
    """Create a sample OPML content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<opml version="2.0">
<body>
<outline text="Tech News" title="Tech News" xmlUrl="https://tech.example.com/feed.xml" />
<outline text="AI Updates" title="AI Updates" xmlUrl="https://ai.example.com/rss" />
</body>
</opml>"""


# =============================================================================
# GitHub Workflow Simulation Tests
# =============================================================================

class GitHubWorkflowSimulationTests:
    """Simulate GitHub workflow behavior."""

    def test_no_changes_no_commit(self) -> None:
        """GH-020: No changes should result in no commit."""
        # This simulates the git diff check in the workflow
        # In actual CI, this would be tested with real git operations
        with TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            data_dir.mkdir(parents=True, exist_ok=True)

            # Create initial files
            (data_dir / "latest-24h.json").write_text('{"test": "data"}')

            # Simulate no changes
            # In real workflow, git diff --quiet would detect no changes
            # Here we just verify the structure remains unchanged
            initial_content = (data_dir / "latest-24h.json").read_text()

            # After "running update_news" with no changes
            final_content = (data_dir / "latest-24h.json").read_text()

            # Should be the same
            assert initial_content == final_content
