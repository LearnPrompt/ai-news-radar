"""Factory for creating storage backends.

This module provides a factory function to create storage backends based on
configuration (environment variables), with fallback to file storage if the
configured backend fails to initialize.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from . import StorageBackend, ConnectionError, InitializationError
from .file_storage import FileStorage
from .db_storage import DatabaseStorage, DB_TYPE_SQLITE, DB_TYPE_MYSQL, DB_TYPE_POSTGRESQL

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Environment variable names
ENV_DB_TYPE = "DB_TYPE"
ENV_DB_FILE = "DB_FILE"
ENV_DB_HOST = "DB_HOST"
ENV_DB_PORT = "DB_PORT"
ENV_DB_NAME = "DB_NAME"
ENV_DB_USER = "DB_USER"
ENV_DB_PASSWORD = "DB_PASSWORD"

# Default values
DEFAULT_DB_TYPE = "sqlite"
DEFAULT_DATA_DIR = "data"

# Valid database types
VALID_DB_TYPES = [DB_TYPE_SQLITE, DB_TYPE_MYSQL, DB_TYPE_POSTGRESQL, "file"]


def get_db_type() -> str:
    """Get the configured database type from environment variables.

    Returns:
        Database type: "sqlite", "mysql", "postgresql", or "file"

    Defaults to "sqlite" if not configured.
    """
    db_type = os.getenv(ENV_DB_TYPE, DEFAULT_DB_TYPE).lower().strip()

    if db_type not in VALID_DB_TYPES:
        logger.warning(
            f"Invalid DB_TYPE '{db_type}'. Valid options: {VALID_DB_TYPES}. "
            f"Using default '{DEFAULT_DB_TYPE}'."
        )
        return DEFAULT_DB_TYPE

    return db_type


def get_db_file() -> str:
    """Get the SQLite database file path from environment.

    Returns:
        Path to SQLite database file
    """
    return os.getenv(ENV_DB_FILE, DEFAULT_DATA_DIR + "/ai_news_radar.db")


def get_data_dir() -> Path:
    """Get the data directory for file storage.

    Returns:
        Path to data directory
    """
    data_dir = os.getenv("DATA_DIR", DEFAULT_DATA_DIR)
    from pathlib import Path
    return Path(data_dir).expanduser()


def create_storage(
    db_type: str | None = None,
    db_file: str | None = None,
    enable_fallback: bool = True,
    data_dir: str | None = None,
) -> StorageBackend:
    """Create a storage backend based on configuration.

    Args:
        db_type: Type of database to use. If None, reads from DB_TYPE env var.
        db_file: Path to SQLite database file. If None, reads from DB_FILE env var.
        enable_fallback: If True, fallback to file storage if primary backend fails.
        data_dir: Data directory for file storage fallback.

    Returns:
        Configured storage backend instance

    Environment Variables:
        DB_TYPE: Database type ("sqlite", "mysql", "postgresql", "file")
        DB_FILE: Path to SQLite database file (for sqlite type)
        DB_HOST: Database host (for mysql/postgresql)
        DB_PORT: Database port (for mysql/postgresql)
        DB_NAME: Database name (for mysql/postgresql)
        DB_USER: Database user (for mysql/postgresql)
        DB_PASSWORD: Database password (for mysql/postgresql)
        DATA_DIR: Data directory for file storage fallback

    Raises:
        InitializationError: If storage initialization fails and fallback is disabled
    """
    db_type = db_type or get_db_type()
    logger.info(f"Creating storage backend of type: {db_type}")

    # File storage (explicit)
    if db_type == "file":
        logger.info("Using file storage backend")
        file_storage = FileStorage(data_dir=data_dir or get_data_dir())
        file_storage.initialize()
        return file_storage

    # Database storage
    try:
        if db_type == DB_TYPE_SQLITE:
            db_file = db_file or get_db_file()
            storage = DatabaseStorage(db_type=DB_TYPE_SQLITE, db_file=db_file)
        else:
            storage = DatabaseStorage(db_type=db_type)

        storage.initialize()

        # Verify connection is healthy
        if not storage.is_healthy():
            raise ConnectionError(f"Database connection not healthy for {db_type}")

        logger.info(f"Successfully initialized {db_type} storage backend")
        return storage

    except (ConnectionError, InitializationError) as e:
        logger.error(f"Failed to initialize {db_type} storage backend: {e}")

        if enable_fallback:
            logger.warning("Falling back to file storage")
            file_storage = FileStorage(data_dir=data_dir or get_data_dir())
            try:
                file_storage.initialize()
                logger.info("Successfully initialized file storage as fallback")
                return file_storage
            except Exception as fallback_error:
                logger.error(f"File storage fallback also failed: {fallback_error}")
                raise InitializationError(
                    f"Both {db_type} and file storage failed to initialize"
                ) from fallback_error
        else:
            raise InitializationError(
                f"Failed to initialize {db_type} storage and fallback is disabled"
            ) from e


def get_storage_info(storage: StorageBackend) -> dict[str, str]:
    """Get information about a storage backend.

    Args:
        storage: Storage backend instance

    Returns:
        Dictionary with storage information
    """
    info = {
        "backend_type": type(storage).__name__,
    }

    if hasattr(storage, "get_stats"):
        info.update(storage.get_stats())

    if hasattr(storage, "is_healthy"):
        info["healthy"] = str(storage.is_healthy())

    if hasattr(storage, "db_type"):
        info["db_type"] = storage.db_type

    if hasattr(storage, "data_dir"):
        info["data_dir"] = str(storage.data_dir)

    return info


def create_storage_with_retry(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs,
) -> StorageBackend:
    """Create a storage backend with retry logic.

    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds
        **kwargs: Additional arguments passed to create_storage

    Returns:
        Configured storage backend instance

    Raises:
        InitializationError: If all retry attempts fail
    """
    import time

    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return create_storage(**kwargs)
        except (ConnectionError, InitializationError) as e:
            last_exception = e
            logger.warning(
                f"Storage creation attempt {attempt}/{max_retries} failed: {e}"
            )

            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("All storage creation attempts failed")

    raise InitializationError(
        f"Failed to create storage after {max_retries} attempts"
    ) from last_exception


__all__ = [
    "create_storage",
    "create_storage_with_retry",
    "get_storage_info",
    "get_db_type",
    "get_db_file",
    "get_data_dir",
    "ENV_DB_TYPE",
    "ENV_DB_FILE",
    "ENV_DB_HOST",
    "ENV_DB_PORT",
    "ENV_DB_NAME",
    "ENV_DB_USER",
    "ENV_DB_PASSWORD",
    "DEFAULT_DB_TYPE",
    "VALID_DB_TYPES",
]
