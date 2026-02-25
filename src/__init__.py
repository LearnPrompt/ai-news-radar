"""AI News Radar source package.

This package contains the storage abstraction layer and other core modules.
"""

from .storage import (
    NewsItem,
    StatusRecord,
    SnapshotMetadata,
    StorageBackend,
    StorageError,
    ConnectionError,
    InitializationError,
    QueryError,
)

from .storage.factory import (
    create_storage,
    create_storage_with_retry,
    get_storage_info,
    get_db_type,
    get_db_file,
    get_data_dir,
)

from .storage.file_storage import FileStorage
from .storage.db_storage import DatabaseStorage

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
