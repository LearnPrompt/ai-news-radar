# Storage Layer Documentation

## Overview

The storage layer provides a unified abstraction for storing and retrieving AI news data, supporting multiple backends:

- **SQLite** (default, file-based) - No external dependencies
- **MySQL** - Requires `mysql-connector-python`
- **PostgreSQL** - Requires `psycopg2-binary`
- **File** (JSON fallback) - Maintains backward compatibility with existing files

## Architecture

```
src/storage/
├── __init__.py       # Data models, interfaces, and exports
├── file_storage.py    # JSON file-based storage
├── db_storage.py     # Database storage (SQLite, MySQL, PostgreSQL)
└── factory.py        # Storage factory with fallback logic
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DB_TYPE` | Database type | `sqlite` |
| `DB_FILE` | SQLite database file path | `data/ai_news_radar.db` |
| `DB_HOST` | Database host (MySQL/PostgreSQL) | `localhost` |
| `DB_PORT` | Database port (MySQL/PostgreSQL) | `3306` (MySQL), `5432` (PostgreSQL) |
| `DB_NAME` | Database name (MySQL/PostgreSQL) | `ai_news_radar` |
| `DB_USER` | Database user (MySQL/PostgreSQL) | `root` |
| `DB_PASSWORD` | Database password (MySQL/PostgreSQL) | - |
| `DATA_DIR` | Data directory for file storage | `data` |

## Usage

### Basic Usage

```python
from storage import create_storage

# Auto-detect storage type from environment variables
storage = create_storage()
storage.initialize()

# Save news items
from storage import NewsItem
items = [
    NewsItem(
        id="item-1",
        site_id="example",
        site_name="Example Site",
        source="news",
        title="Breaking News",
        url="https://example.com/news",
        published_at="2025-02-25T12:00:00Z",
        first_seen_at="2025-02-25T12:00:00Z",
        last_seen_at="2025-02-25T12:00:00Z",
        meta={},
    )
]
storage.save_news_items(items)

# Load archive
archive = storage.load_archive()

# Close connection
storage.close()
```

### Manual Backend Selection

```python
from storage.db_storage import DatabaseStorage
from storage.file_storage import FileStorage

# Use SQLite explicitly
storage = DatabaseStorage(db_type="sqlite", db_file="data/news.db")

# Use file storage
storage = FileStorage(data_dir="data")

# Use MySQL
storage = DatabaseStorage(db_type="mysql")
```

## Data Models

### NewsItem

```python
@dataclass
class NewsItem:
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
```

### StatusRecord

```python
@dataclass
class StatusRecord:
    site_id: str
    site_name: str
    ok: bool
    item_count: int
    last_check_at: str
    error_message: str | None = None
    response_time_ms: int | None = None
    metadata: dict[str, Any] | None = None
```

### SnapshotMetadata

```python
@dataclass
class SnapshotMetadata:
    generated_at: str
    window_hours: int
    total_items: int
    total_items_raw: int
    site_count: int
    source_count: int
    topic_filter: str
    archive_total: int
```

## Fallback Logic

The storage layer implements automatic fallback:

1. **Primary backend** - Try to initialize the configured storage type
2. **File fallback** - If primary fails, fall back to JSON file storage
3. **Graceful degradation** - Errors are logged, file I/O continues

```python
# With fallback enabled (default)
storage = create_storage(enable_fallback=True)

# Without fallback (raises exception on failure)
storage = create_storage(enable_fallback=False)
```

## Migration from JSON Files

Existing JSON files in the `data/` directory remain compatible:

- `archive.json` - Archive of all news items
- `latest-24h.json` - Latest 24-hour snapshot
- `source-status.json` - Source status records
- `waytoagi-7d.json` - WaytoAGI data
- `title-zh-cache.json` - Title translation cache

When you first run with database storage, the system will:
1. Read existing JSON files
2. Migrate data to the database
3. Continue using database for future operations
4. Keep JSON files as backup

## Testing

Run the storage layer tests:

```bash
python3 tests/test_storage.py
```

All tests should pass:
- File storage operations
- SQLite database operations
- Storage factory behavior
- Data model serialization

## Database Schema

### SQLite

```sql
CREATE TABLE news_items (
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
);

CREATE TABLE status_records (
    site_id TEXT PRIMARY KEY,
    site_name TEXT NOT NULL,
    ok INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    last_check_at TEXT NOT NULL,
    error_message TEXT,
    response_time_ms INTEGER,
    metadata TEXT
);

CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_type TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### MySQL / PostgreSQL

Similar schema with appropriate data types:
- `TEXT` -> `TEXT` (MySQL) / `TEXT` (PostgreSQL)
- `INTEGER` -> `INT` (MySQL) / `INT` (PostgreSQL)
- JSON fields use `JSON` (MySQL) / `JSONB` (PostgreSQL)

## Performance Considerations

- **SQLite**: Best for single-instance deployments, no network overhead
- **MySQL**: Good for production with existing MySQL infrastructure
- **PostgreSQL**: Best for high-concurrency, complex queries
- **File**: Simplest, no dependencies, good for small datasets

## Troubleshooting

### Database Connection Failed

```bash
# Check environment variables
env | grep DB_

# Test database connectivity
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME
psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

### SQLite Database Locked

```bash
# Check for existing processes
lsof data/ai_news_radar.db

# Use a different database file
export DB_FILE=data/ai_news_radar_v2.db
```

### Fallback to File Storage

Check logs for initialization errors:

```bash
python3 scripts/update_news.py 2>&1 | grep -i storage
```

If database initialization fails, the system will automatically fall back to file storage.
