# AI News Radar - Test Plan

## Overview

This document outlines the comprehensive test plan for the AI News Radar project, covering both existing functionality and proposed new features.

## Test Categories

### 1. Database Storage Layer Tests

#### 1.1 SQLite Storage
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| DB-001 | SQLite Initialization | Verify SQLite database is created with correct schema | Database file created, tables exist |
| DB-002 | Save Item to SQLite | Insert a single news item | Item saved with correct fields |
| DB-003 | Batch Save Items | Insert multiple items in transaction | All items saved efficiently |
| DB-004 | Load Items by Date Range | Query items within time window | Only items in range returned |
| DB-005 | Update Existing Item | Update an item that already exists | Record updated, not duplicated |
| DB-006 | Archive Pruning | Delete items older than retention period | Old items removed, recent kept |
| DB-007 | SQLite Connection Error | Test behavior when connection fails | Graceful fallback to file storage |

#### 1.2 MySQL Storage
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| DB-010 | MySQL Connection Check | Verify connection with valid credentials | Connection established |
| DB-011 | Missing MySQL Credentials | Test with empty/invalid credentials | Graceful error, fallback to file |
| DB-012 | MySQL Schema Creation | Create tables in MySQL | Tables created correctly |
| DB-013 | MySQL Save/Load Roundtrip | Save and retrieve from MySQL | Data integrity maintained |

#### 1.3 PostgreSQL Storage
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| DB-020 | PostgreSQL Connection Check | Verify connection with valid credentials | Connection established |
| DB-021 | Missing PostgreSQL Credentials | Test with empty/invalid credentials | Graceful error, fallback to file |
| DB-022 | PostgreSQL Schema Creation | Create tables in PostgreSQL | Tables created correctly |
| DB-023 | PostgreSQL Save/Load Roundtrip | Save and retrieve from PostgreSQL | Data integrity maintained |

#### 1.4 Fallback to File Storage
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| DB-030 | DB Failure Fallback | Simulate DB failure during save | File storage used instead |
| DB-031 | File Storage Load | Load from existing JSON files | Data loaded correctly |
| DB-032 | File Storage Save | Save to JSON files | Files written with correct format |
| DB-033 | DB Recover After Failure | Test resume after DB connection restored | DB used again for subsequent ops |

### 2. GitHub Workflow Tests

#### 2.1 Concurrency Control
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| GH-001 | Single Workflow Run | Run one workflow instance | Completes successfully |
| GH-002 | Concurrent Workflow Runs | Trigger two workflows simultaneously | One cancels the other cleanly |
| GH-003 | Concurrency Group Check | Verify `concurrency` group in config | Properly configured |

#### 2.2 Dependency Caching
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| GH-010 | First Run - Cache Miss | Run without existing cache | Dependencies installed from scratch |
| GH-011 | Second Run - Cache Hit | Run with existing cache | Dependencies loaded from cache (faster) |
| GH-012 | Cache Invalidation | Force cache refresh | New cache created |

#### 2.3 Conditional Commits
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| GH-020 | No Changes - No Commit | Run with unchanged data | No commit created, workflow exits cleanly |
| GH-021 | With Changes - Commit Made | Run with new data | Commit created and pushed |
| GH-022 | Git Diff Check | Verify `git diff --quiet` behavior | Correctly detects changes |

#### 2.4 Telegram Notifications
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| GH-030 | Success Notification | Send notification on successful update | Message delivered to Telegram |
| GH-031 | Failure Notification | Send notification on error | Error details delivered |
| GH-032 | No Notification on No Changes | Skip notification when no data updated | No message sent |
| GH-033 | Missing Telegram Token | Test with missing TELEGRAM_BOT_TOKEN | Workflow continues without notification |

### 3. Environment Variable Configuration Tests

#### 3.1 DB_TYPE Configuration
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| ENV-001 | DB_TYPE=sqlite | Set DB type to SQLite | SQLite storage used |
| ENV-002 | DB_TYPE=mysql | Set DB type to MySQL | MySQL storage attempted |
| ENV-003 | DB_TYPE=postgresql | Set DB type to PostgreSQL | PostgreSQL storage attempted |
| ENV-004 | DB_TYPE not set | No DB_TYPE environment variable | Default to file storage |
| ENV-005 | Invalid DB_TYPE | Set to invalid value | Fallback to file storage with warning |

#### 3.2 Database Credentials
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| ENV-010 | Valid MySQL Credentials | All MySQL env vars set | Connection successful |
| ENV-011 | Missing MySQL Password | Missing MYSQL_PASSWORD | Graceful error, fallback |
| ENV-012 | Missing PostgreSQL Credentials | All PG env vars missing | Fallback to file storage |
| ENV-013 | Partial Credentials | Some but not all required vars | Clear error message about missing vars |

### 4. Integration Tests - update_news.py

#### 4.1 Main Function Flow
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| INT-001 | Full Run with Mock Data | Complete execution with mocked APIs | All JSON files generated |
| INT-002 | Archive Loading | Load existing archive on startup | Previous data preserved |
| INT-003 | New Items Added | Add items that don't exist | Items added to archive |
| INT-004 | Existing Items Updated | Process existing items with new data | Last seen timestamp updated |
| INT-005 | Old Items Pruned | Archive exceeds retention days | Old items removed |

#### 4.2 RSS OPML Processing
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| INT-010 | Valid OPML File | Process feeds from OPML | RSS items added to results |
| INT-011 | Missing OPML File | Run without OPML path | Workflow continues without error |
| INT-012 | Invalid OPML File | Malformed XML in OPML | Error logged, workflow continues |

#### 4.3 Output Files Validation
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| INT-020 | latest-24h.json Structure | Validate JSON schema | Valid structure, all required fields |
| INT-021 | archive.json Structure | Validate JSON schema | Valid structure, items within retention |
| INT-022 | source-status.json Structure | Validate JSON schema | Valid structure, all sources reported |
| INT-023 | waytoagi-7d.json Structure | Validate JSON schema | Valid structure or error field set |
| INT-024 | title-zh-cache.json Structure | Validate JSON schema | Valid structure, translations cached |

### 5. Source Configuration Tests

#### 5.1 Source Registry
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| SRC-001 | Register Source | Register a new source config | Source added to registry |
| SRC-002 | Get Source Config | Retrieve config by ID | Correct config returned |
| SRC-003 | Get Enabled Sources | Filter for enabled sources | Only enabled sources returned |
| SRC-004 | Get Sources by Category | Filter by category | Correct category sources returned |

#### 5.2 Source Filtering
| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| SRC-010 | Filter Keywords | Items matching keywords pass | Filtered items returned |
| SRC-011 | Block Keywords | Items with blocked terms excluded | Blocked items not in results |
| SRC-012 | Max Items Limit | Respect max_items_per_source | No more than limit returned |

### 6. Unit Tests - Utilities

| Test ID | Test Case | Description | Expected Result |
|---------|-----------|-------------|----------------|
| UTIL-001 | URL Normalization | Remove tracking parameters | Clean URL returned |
| UTIL-002 | Item ID Generation | Create stable ID from item | Same input produces same ID |
| UTIL-003 | Date Parsing | Parse various date formats | Correct datetime object |
| UTIL-004 | Relative Time Parsing | Parse "X minutes ago" | Correct datetime calculated |
| UTIL-005 | Mojibake Fixing | Fix character encoding issues | Corrected text returned |

## Test Execution Order

### Phase 1: Unit Tests
1. Utility functions (test_utils.py)
2. Topic filtering (test_topic_filter.py)
3. WaytoAGI utilities (test_waytoagi_utils.py)
4. Storage layer (test_storage.py)

### Phase 2: Integration Tests
1. Source configuration tests
2. update_news.py main flow tests
3. Output file validation tests

### Phase 3: Manual Testing
1. GitHub workflow execution
2. Environment variable configurations
3. Database setup and fallback scenarios

## Test Environment Setup

### Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Install test dependencies
pip install pytest pytest-mock pytest-cov pytest-timeout

# Optional: Install database drivers
pip install pysqlite3-binary  # Usually built-in
pip install mysql-connector-python
pip install psycopg2-binary
```

### Test Database Setup
```bash
# SQLite: No setup required (uses file)
# MySQL: Create test database
mysql -u root -p -e "CREATE DATABASE ai_news_test;"

# PostgreSQL: Create test database
psql -U postgres -c "CREATE DATABASE ai_news_test;"
```

## Mock Data

### Sample RawItem
```python
RawItem(
    site_id="test",
    site_name="Test Source",
    source="test-section",
    title="Test Article",
    url="https://example.com/article",
    published_at=datetime.now(UTC),
    extra={"author": "Test Author"}
)
```

### Sample Status Response
```python
{
    "site_id": "test",
    "site_name": "Test Source",
    "ok": True,
    "item_count": 10,
    "duration_ms": 500,
    "error": None
}
```

## Expected Test Coverage

- Unit Tests: > 80%
- Integration Tests: > 60%
- Critical Paths: 100%

## Test Automation

### Run All Tests
```bash
pytest tests/ -v --cov=scripts --cov-report=html
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest tests/test_*.py -v

# Storage tests
pytest tests/test_storage.py -v

# Integration tests
pytest tests/test_update_news.py -v
```

### CI/CD Integration
Tests should run in GitHub Actions on:
- Pull requests
- Push to main branch
- Release tags

## Failure Handling

### Test Failure Investigation
1. Check test output for specific assertion
2. Review mock setup if external dependencies involved
3. Verify environment variables are set correctly for DB tests
4. Check for race conditions in concurrent tests

### Known Limitations
- MySQL/PostgreSQL tests require local database or Docker
- Some integration tests may require network access
- Telegram notifications cannot be tested in CI (use mocks)

## Test Maintenance

- Update tests when adding new sources
- Review test coverage monthly
- Update test data to match current API responses
- Archive tests for deprecated features
