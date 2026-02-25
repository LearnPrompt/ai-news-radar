#!/usr/bin/env python3
"""Configuration manager for AI news radar.

Handles loading, validating, and managing source configurations from YAML files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class SourceFilterConfig:
    """Filter configuration for a source."""
    min_score: int = 0
    min_stars: int = 0
    min_votes: int = 0
    min_reactions: int = 0
    max_items: int = 100
    categories: list[str] = field(default_factory=list)
    subreddits: list[str] = field(default_factory=list)
    publications: list[str] = field(default_factory=list)
    tag: str = ""
    allow_keywords: list[str] = field(default_factory=list)
    block_keywords: list[str] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Authentication configuration for a source."""
    required: bool = False
    type: str = ""  # oauth, api_key, basic
    env_vars: list[str] = field(default_factory=list)
    api_key: str = ""
    client_id: str = ""
    client_secret: str = ""
    token: str = ""

    def get_credentials(self) -> dict[str, str]:
        """Get credentials from environment or config."""
        creds = {}
        for var in self.env_vars:
            value = os.environ.get(var) or ""
            if value:
                creds[var.lower()] = value
        if self.api_key:
            creds["api_key"] = self.api_key
        if self.client_id:
            creds["client_id"] = self.client_id
        if self.client_secret:
            creds["client_secret"] = self.client_secret
        if self.token:
            creds["token"] = self.token
        return creds


@dataclass
class SourceConfigItem:
    """Configuration for a single source."""
    id: str
    name: str
    enabled: bool = True
    priority: int = 10
    type: str = "web"  # web, api, rss, custom
    url: str = ""
    category: str = "general"
    description: str = ""
    tags: list[str] = field(default_factory=list)
    auth: AuthConfig = field(default_factory=AuthConfig)
    filters: SourceFilterConfig = field(default_factory=SourceFilterConfig)


@dataclass
class GlobalSettings:
    """Global application settings."""
    update_interval: int = 30
    window_hours: int = 24
    archive_days: int = 45
    translate_max_new: int = 80
    max_items_per_source: int = 100
    parallel_fetches: int = 10
    fetch_timeout: int = 30
    ai_keywords: list[str] = field(default_factory=list)
    tech_keywords: list[str] = field(default_factory=list)
    block_keywords: list[str] = field(default_factory=list)
    commerce_keywords: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    """Complete application configuration."""
    sources: list[SourceConfigItem] = field(default_factory=list)
    settings: GlobalSettings = field(default_factory=GlobalSettings)

    def get_enabled_sources(self) -> list[SourceConfigItem]:
        """Get all enabled sources sorted by priority."""
        return sorted(
            [s for s in self.sources if s.enabled],
            key=lambda x: x.priority,
            reverse=True
        )

    def get_source_by_id(self, source_id: str) -> SourceConfigItem | None:
        """Get a source by ID."""
        for s in self.sources:
            if s.id == source_id:
                return s
        return None

    def get_sources_by_category(self, category: str) -> list[SourceConfigItem]:
        """Get all enabled sources in a category."""
        return [
            s for s in self.sources
            if s.enabled and s.category == category
        ]

    def get_sources_by_tag(self, tag: str) -> list[SourceConfigItem]:
        """Get all enabled sources with a specific tag."""
        return [
            s for s in self.sources
            if s.enabled and tag in s.tags
        ]


class ConfigManager:
    """Manages loading and saving configuration files."""

    def __init__(self, config_dir: Path | str | None = None):
        """Initialize config manager.

        Args:
            config_dir: Directory containing config files. Defaults to ./config/
        """
        if config_dir is None:
            self.config_dir = Path(__file__).parent.parent / "config"
        else:
            self.config_dir = Path(config_dir)

        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.sources_file = self.config_dir / "sources.yaml"
        self.local_file = self.config_dir / "local.yaml"  # For overrides
        self.env_file = self.config_dir / ".env"  # For environment variables

    def load_yaml(self, path: Path) -> dict[str, Any] | None:
        """Load a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Parsed YAML data or None if file doesn't exist
        """
        if not path.exists():
            return None

        if yaml is None:
            raise ImportError("PyYAML is required for YAML config files")

        try:
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    def parse_auth_config(self, auth_data: dict[str, Any]) -> AuthConfig:
        """Parse auth config from dict."""
        return AuthConfig(
            required=auth_data.get("required", False),
            type=auth_data.get("type", ""),
            env_vars=auth_data.get("env_vars", []),
            api_key=auth_data.get("api_key", ""),
            client_id=auth_data.get("client_id", ""),
            client_secret=auth_data.get("client_secret", ""),
            token=auth_data.get("token", ""),
        )

    def parse_filter_config(self, filter_data: dict[str, Any]) -> SourceFilterConfig:
        """Parse filter config from dict."""
        return SourceFilterConfig(
            min_score=filter_data.get("min_score", 0),
            min_stars=filter_data.get("min_stars", 0),
            min_votes=filter_data.get("min_votes", 0),
            min_reactions=filter_data.get("min_reactions", 0),
            max_items=filter_data.get("max_items", 100),
            categories=filter_data.get("categories", []),
            subreddits=filter_data.get("subreddits", []),
            publications=filter_data.get("publications", []),
            tag=filter_data.get("tag", ""),
            allow_keywords=filter_data.get("allow_keywords", []),
            block_keywords=filter_data.get("block_keywords", []),
        )

    def parse_source_config(self, source_data: dict[str, Any]) -> SourceConfigItem:
        """Parse source config from dict."""
        return SourceConfigItem(
            id=source_data["id"],
            name=source_data["name"],
            enabled=source_data.get("enabled", True),
            priority=source_data.get("priority", 10),
            type=source_data.get("type", "web"),
            url=source_data.get("url", ""),
            category=source_data.get("category", "general"),
            description=source_data.get("description", ""),
            tags=source_data.get("tags", []),
            auth=self.parse_auth_config(source_data.get("auth", {})),
            filters=self.parse_filter_config(source_data.get("filters", {})),
        )

    def parse_global_settings(self, settings_data: dict[str, Any]) -> GlobalSettings:
        """Parse global settings from dict."""
        return GlobalSettings(
            update_interval=settings_data.get("update_interval", 30),
            window_hours=settings_data.get("window_hours", 24),
            archive_days=settings_data.get("archive_days", 45),
            translate_max_new=settings_data.get("translate_max_new", 80),
            max_items_per_source=settings_data.get("max_items_per_source", 100),
            parallel_fetches=settings_data.get("parallel_fetches", 10),
            fetch_timeout=settings_data.get("fetch_timeout", 30),
            ai_keywords=settings_data.get("ai_keywords", []),
            tech_keywords=settings_data.get("tech_keywords", []),
            block_keywords=settings_data.get("block_keywords", []),
            commerce_keywords=settings_data.get("commerce_keywords", []),
        )

    def load_config(self) -> AppConfig:
        """Load complete configuration.

        Loads from sources.yaml, with optional overrides from local.yaml.

        Returns:
            Complete AppConfig
        """
        # Load base config
        base_data = self.load_yaml(self.sources_file) or {}
        sources_data = base_data.get("sources", [])
        settings_data = base_data.get("settings", {})

        # Load local overrides
        local_data = self.load_yaml(self.local_file) or {}
        local_sources = {s["id"]: s for s in local_data.get("sources", [])}
        local_settings = local_data.get("settings", {})

        # Merge settings (local overrides base)
        merged_settings = {**settings_data, **local_settings}

        # Parse sources (local overrides base)
        sources = []
        for source_data in sources_data:
            source_id = source_data["id"]
            if source_id in local_sources:
                # Merge with local override
                merged_source = {**source_data, **local_sources[source_id]}
                # Handle nested merges
                if "auth" in local_sources[source_id]:
                    merged_source["auth"] = {**source_data.get("auth", {}),
                                             **local_sources[source_id]["auth"]}
                if "filters" in local_sources[source_id]:
                    merged_source["filters"] = {**source_data.get("filters", {}),
                                                **local_sources[source_id]["filters"]}
                sources.append(self.parse_source_config(merged_source))
            else:
                sources.append(self.parse_source_config(source_data))

        return AppConfig(
            sources=sources,
            settings=self.parse_global_settings(merged_settings)
        )

    def save_config(self, config: AppConfig, path: Path | None = None) -> None:
        """Save configuration to YAML file.

        Args:
            config: AppConfig to save
            path: Path to save to. Defaults to local.yaml (for local overrides)
        """
        if yaml is None:
            raise ImportError("PyYAML is required to save config files")

        if path is None:
            path = self.local_file

        data = {
            "sources": [
                {
                    "id": s.id,
                    "name": s.name,
                    "enabled": s.enabled,
                    "priority": s.priority,
                    "type": s.type,
                    "url": s.url,
                    "category": s.category,
                    "description": s.description,
                    "tags": s.tags,
                }
                for s in config.sources
            ],
            "settings": {
                "window_hours": config.settings.window_hours,
                "archive_days": config.settings.archive_days,
                "translate_max_new": config.settings.translate_max_new,
            },
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

    def load_env_file(self) -> None:
        """Load environment variables from .env file."""
        if not self.env_file.exists():
            return

        try:
            with open(self.env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()
        except Exception:
            pass

    def create_example_local_config(self) -> None:
        """Create an example local.yaml file with common overrides."""
        example = """# Local configuration overrides
# Copy this to local.yaml and customize as needed

sources:
  # Example: Disable a source
  - id: tophub
    enabled: false

  # Example: Enable auth-required sources with credentials
  # - id: reddit_ai
  #   enabled: true
  #   auth:
  #     client_id: "your_client_id"
  #     client_secret: "your_client_secret"

  # - id: product_hunt
  #   enabled: true
  #   auth:
  #     api_key: "your_api_key"

  # - id: github_trending
  #   enabled: true
  #   auth:
  #     token: "your_github_token"

settings:
  # Example: Change time window
  window_hours: 48

  # Example: More translations
  translate_max_new: 150
"""
        example_file = self.config_dir / "local.example.yaml"
        if not example_file.exists():
            example_file.write_text(example, encoding="utf-8")


def load_config(config_dir: str | Path | None = None) -> AppConfig:
    """Convenience function to load configuration.

    Args:
        config_dir: Directory containing config files

    Returns:
        Loaded AppConfig
    """
    manager = ConfigManager(config_dir)
    manager.load_env_file()
    return manager.load_config()


if __name__ == "__main__":
    # Test config loading
    manager = ConfigManager()

    print("Loading configuration...")
    config = manager.load_config()

    print(f"\nFound {len(config.sources)} sources:")
    enabled = [s for s in config.sources if s.enabled]
    print(f"  Enabled: {len(enabled)}")
    disabled = [s for s in config.sources if not s.enabled]
    print(f"  Disabled: {len(disabled)}")

    print(f"\nEnabled sources by category:")
    by_category: dict[str, list[SourceConfigItem]] = {}
    for s in enabled:
        by_category.setdefault(s.category, []).append(s)

    for cat, sources in sorted(by_category.items()):
        print(f"  {cat}: {len(sources)}")
        for s in sources:
            auth_note = " [auth]" if s.auth.required else ""
            print(f"    - {s.name}{auth_note}")

    print(f"\nGlobal settings:")
    print(f"  Update interval: {config.settings.update_interval} min")
    print(f"  Time window: {config.settings.window_hours} h")
    print(f"  Archive retention: {config.settings.archive_days} days")

    # Create example local config
    manager.create_example_local_config()
    print(f"\nCreated example config at: {manager.config_dir / 'local.example.yaml'}")
