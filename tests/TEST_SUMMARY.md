# Test Suite Summary for AI News Radar

## Overview

This document provides a summary of the test suite created for the AI News Radar project, including how to run the tests and what they cover.

## Test Files

### 1. Test Plan (`tests/TEST_PLAN.md`)

A comprehensive test plan document covering:
- Database Storage Layer tests (SQLite, MySQL, PostgreSQL)
- GitHub Workflow tests (concurrency, caching, commits, notifications)
- Environment Variable Configuration tests
- Integration tests for update_news.py
- Output file validation tests

**Status**: Complete
**Coverage**: All proposed new features

### 2. Storage Layer Tests (`tests/test_storage.py`)

Tests for the storage abstraction layer (when implemented):
- File storage operations
- Database storage (SQLite, MySQL, PostgreSQL)
- Storage factory pattern
- Fallback behavior
- Data model tests

**Status**: Ready (requires storage module implementation)
**Coverage**: DB-001 through DB-033

### 3. Current Storage Tests (`tests/test_storage_current.py`)

Tests for the current file-based storage:
- Archive loading and saving
- Title cache operations
- JSON encoding handling
- Data integrity validation

**Status**: Complete and runnable
**Coverage**: Current implementation

### 4. Update News Tests (`tests/test_update_news.py`)

Integration tests for the main update_news module:
- Main execution flow
- Archive operations
- RSS OPML processing
- Output file structure validation
- Utility function tests

**Status**: Complete and runnable
**Coverage**: INT-001 through GH-020

### 5. Existing Tests

- `tests/test_utils.py` - Utility functions (URL normalization, ID generation, date parsing)
- `tests/test_topic_filter.py` - Topic filtering logic
- `tests/test_waytoagi_utils.py` - WaytoAGI fetching utilities

## Running the Tests

### Prerequisites

Install test dependencies:
```bash
pip install -r requirements.txt
```

### Run All Tests

```bash
# Run all tests with pytest
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=scripts --cov-report=html

# Run specific test file
pytest tests/test_update_news.py -v

# Run specific test function
pytest tests/test_update_news.py::UtilityFunctionTests::test_make_item_id_stable -v
```

### Run Current Storage Tests

```bash
# Run as a standalone script
python tests/test_storage_current.py

# Or with pytest
pytest tests/test_storage_current.py -v
```

### Run Existing Tests

```bash
# Run all existing tests
pytest tests/test_utils.py tests/test_topic_filter.py tests/test_waytoagi_utils.py -v
```

### Run by Markers

```bash
# Run only unit tests (not integration)
pytest tests/ -m "not integration" -v

# Run only integration tests
pytest tests/ -m integration -v

# Run only storage tests
pytest tests/ -m storage -v
```

## Test Coverage

| Category | Test File | Tests | Status |
|----------|------------|--------|--------|
| File Storage (Current) | test_storage_current.py | 10 | Ready |
| Storage Layer (Proposed) | test_storage.py | 30+ | Pending implementation |
| Update News Integration | test_update_news.py | 15+ | Ready |
| Utilities | test_utils.py | 5 | Existing |
| Topic Filter | test_topic_filter.py | Existing | Existing |
| WaytoAGI Utils | test_waytoagi_utils.py | Existing | Existing |
| **Total** | - | **60+** | - |

## Manual Testing

For GitHub workflow manual testing, see `tests/MANUAL_TESTING.md` which covers:
- Concurrency control
- Dependency caching
- Conditional commits
- Telegram notifications
- Environment variable configuration
- OPML RSS processing

## Test Results Interpretation

### Unit Tests

- **PASS**: Test succeeded, function behaves as expected
- **FAIL**: Test failed, indicates bug or issue

### Integration Tests

- **PASS**: End-to-end flow works correctly
- **FAIL**: Issue in the integration or dependent components

### Manual Tests

- **PASS**: Feature works as documented
- **FAIL**: Feature does not work as expected or has issues

## Continuous Integration

The tests can be integrated into GitHub Actions:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run tests
        run: |
          pytest tests/ -v --cov=scripts --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Common Issues

**ImportError: No module named 'update_news'**
- Solution: Ensure you're running tests from the project root
- Or add scripts to PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:$(pwd)/scripts"`

**Tests fail with database connection errors**
- Solution: These tests require the storage module implementation
- Use `test_storage_current.py` for current implementation tests

**Coverage report shows low coverage**
- Solution: Ensure you're running with the correct source directory
- Use `--cov=scripts` flag

## Next Steps

1. **Implement Storage Module**: Add the storage abstraction layer to enable test_storage.py
2. **Add Database Tests**: Uncomment and configure MySQL/PostgreSQL tests
3. **Expand Coverage**: Add tests for any new features
4. **CI Integration**: Add test workflow to .github/workflows/
5. **Performance Tests**: Add benchmarks for critical operations

## Documentation

- Test Plan: `tests/TEST_PLAN.md`
- Manual Testing: `tests/MANUAL_TESTING.md`
- This Summary: `tests/TEST_SUMMARY.md`

## Support

For questions about the test suite:
- Check inline docstrings in test files
- Refer to TEST_PLAN.md for detailed test descriptions
- See MANUAL_TESTING.md for workflow testing guidance
