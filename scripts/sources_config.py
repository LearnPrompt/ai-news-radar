#!/usr/bin/env python3
"""Configurable source management for AI news radar.

This module provides a plugin-based architecture for adding new information sources.
Each source is defined as a SourceConfig with its own fetch function.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    import requests

    from update_news import RawItem


class SourceStatus(str, Enum):
    """Status of a source fetch operation."""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"
    SKIPPED = "skipped"


@dataclass
class SourceConfig:
    """Configuration for a single information source."""
    # Identity
    site_id: str
    site_name: str

    # Source type
    type: str = "web"  # web, api, rss, custom

    # Description
    description: str = ""
    url: str = ""
    icon: str = ""

    # Authorization
    requires_auth: bool = False
    auth_type: str = ""  # api_key, oauth, basic, etc.
    auth_env_var: str = ""  # Environment variable name for credentials

    # Rate limiting
    rate_limit_per_hour: int = 0  # 0 means no limit
    rate_limit_per_day: int = 0

    # Reliability
    reliability_score: float = 1.0  # 0.0 to 1.0
    timeout_seconds: int = 30
    retry_count: int = 3

    # Filtering
    enabled: bool = True
    filter_keywords: list[str] = field(default_factory=list)
    block_keywords: list[str] = field(default_factory=list)

    # Metadata
    tags: list[str] = field(default_factory=list)
    category: str = "general"  # ai, tech, news, research, etc.


class SourceFetcher(ABC):
    """Abstract base class for source fetchers."""

    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    def fetch(self, session: "requests.Session", now: "datetime") -> list["RawItem"]:
        """Fetch items from the source.

        Args:
            session: HTTP session for making requests
            now: Current datetime for reference

        Returns:
            List of RawItem objects

        Raises:
            Exception: If fetching fails catastrophically
        """
        pass

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Get current status of this source."""
        pass


# Registry for source fetchers
_SOURCE_REGISTRY: dict[str, tuple[SourceConfig, type[SourceFetcher]]] = {}


def register_source(config: SourceConfig, fetcher_class: type[SourceFetcher]) -> None:
    """Register a source configuration and fetcher class.

    Args:
        config: Source configuration
        fetcher_class: Class that implements SourceFetcher
    """
    _SOURCE_REGISTRY[config.site_id] = (config, fetcher_class)


def get_source_configs() -> list[SourceConfig]:
    """Get all registered source configurations.

    Returns:
        List of all registered SourceConfig objects
    """
    return [config for config, _ in _SOURCE_REGISTRY.values()]


def get_source_config(site_id: str) -> SourceConfig | None:
    """Get a specific source configuration.

    Args:
        site_id: The site identifier

    Returns:
        SourceConfig if found, None otherwise
    """
    config, _ = _SOURCE_REGISTRY.get(site_id, (None, None))
    return config


def get_source_fetcher(site_id: str) -> SourceFetcher | None:
    """Create a fetcher instance for a specific source.

    Args:
        site_id: The site identifier

    Returns:
        SourceFetcher instance if found, None otherwise
    """
    config, fetcher_class = _SOURCE_REGISTRY.get(site_id, (None, None))
    if config and fetcher_class:
        return fetcher_class(config)
    return None


def get_enabled_source_configs() -> list[SourceConfig]:
    """Get all enabled source configurations.

    Returns:
        List of enabled SourceConfig objects
    """
    return [config for config, _ in _SOURCE_REGISTRY.values() if config.enabled]


def get_source_configs_by_category(category: str) -> list[SourceConfig]:
    """Get all source configurations for a specific category.

    Args:
        category: Category to filter by

    Returns:
        List of SourceConfig objects in the category
    """
    return [
        config for config, _ in _SOURCE_REGISTRY.values()
        if config.category == category and config.enabled
    ]


def get_source_configs_by_tag(tag: str) -> list[SourceConfig]:
    """Get all source configurations with a specific tag.

    Args:
        tag: Tag to filter by

    Returns:
        List of SourceConfig objects with the tag
    """
    return [
        config for config, _ in _SOURCE_REGISTRY.values()
        if tag in config.tags and config.enabled
    ]


def list_all_sources() -> list[dict[str, Any]]:
    """Get a summary of all registered sources.

    Returns:
        List of source summary dictionaries
    """
    return [
        {
            "site_id": config.site_id,
            "site_name": config.site_name,
            "type": config.type,
            "enabled": config.enabled,
            "category": config.category,
            "tags": config.tags,
            "requires_auth": config.requires_auth,
            "reliability": config.reliability_score,
            "description": config.description,
            "url": config.url,
        }
        for config, _ in _SOURCE_REGISTRY.values()
    ]


# Default source configurations
DEFAULT_SOURCES: list[dict[str, Any]] = [
    {
        "site_id": "techurls",
        "site_name": "TechURLs",
        "type": "web",
        "description": "Technology news aggregation site",
        "url": "https://techurls.com/",
        "category": "tech",
        "tags": ["aggregator", "tech"],
        "enabled": True,
        "reliability": 0.9,
    },
    {
        "site_id": "buzzing",
        "site_name": "Buzzing",
        "type": "api",
        "description": "News aggregation platform",
        "url": "https://www.buzzing.cc/feed.json",
        "category": "general",
        "tags": ["aggregator", "news"],
        "enabled": True,
        "reliability": 0.95,
    },
    {
        "site_id": "iris",
        "site_name": "Info Flow",
        "type": "rss",
        "description": "Multiple RSS feeds aggregator",
        "url": "https://iris.findtruman.io/web/info_flow",
        "category": "general",
        "tags": ["aggregator", "rss"],
        "enabled": True,
        "reliability": 0.85,
    },
    {
        "site_id": "bestblogs",
        "site_name": "BestBlogs",
        "type": "api",
        "description": "Weekly newsletter compilation",
        "url": "https://www.bestblogs.dev/en/newsletter",
        "category": "tech",
        "tags": ["newsletter", "weekly"],
        "enabled": True,
        "reliability": 0.9,
    },
    {
        "site_id": "tophub",
        "site_name": "TopHub",
        "type": "web",
        "description": "Hot topics platform with AI/tech filtering",
        "url": "https://tophub.today/",
        "category": "general",
        "tags": ["aggregator", "hot"],
        "enabled": True,
        "reliability": 0.85,
    },
    {
        "site_id": "zeli",
        "site_name": "Zeli",
        "type": "api",
        "description": "Hacker News 24h hot posts",
        "url": "https://zeli.app/",
        "category": "tech",
        "tags": ["hackernews", "daily"],
        "enabled": True,
        "reliability": 0.95,
    },
    {
        "site_id": "aihubtoday",
        "site_name": "AI HubToday",
        "type": "web",
        "description": "Daily AI digest",
        "url": "https://ai.hubtoday.app/",
        "category": "ai",
        "tags": ["ai", "daily"],
        "enabled": True,
        "reliability": 0.9,
    },
    {
        "site_id": "aibase",
        "site_name": "AIbase",
        "type": "web",
        "description": "AI news in Chinese",
        "url": "https://www.aibase.com/zh/news",
        "category": "ai",
        "tags": ["ai", "chinese"],
        "enabled": True,
        "reliability": 0.85,
    },
    {
        "site_id": "aihot",
        "site_name": "AI今日热榜",
        "type": "web",
        "description": "AI hot ranking in Chinese",
        "url": "https://aihot.today/",
        "category": "ai",
        "tags": ["ai", "chinese", "hot"],
        "enabled": True,
        "reliability": 0.9,
    },
    {
        "site_id": "newsnow",
        "site_name": "NewsNow",
        "type": "api",
        "description": "Multi-source news feed",
        "url": "https://newsnow.busiyi.world/",
        "category": "general",
        "tags": ["aggregator", "news"],
        "enabled": True,
        "reliability": 0.85,
    },
]


# New high-value sources to add
NEW_SOURCES: list[dict[str, Any]] = [
    {
        "site_id": "reddit_ai",
        "site_name": "Reddit (AI Subreddits)",
        "type": "api",
        "description": "AI/ML subreddits: r/artificial, r/MachineLearning, r/LocalLLaMA",
        "url": "https://www.reddit.com/r/artificial/",
        "category": "ai",
        "tags": ["ai", "community", "discussion"],
        "enabled": False,  # Requires Reddit app credentials
        "requires_auth": True,
        "auth_type": "api_key",
        "auth_env_var": "REDDIT_CLIENT_ID",
        "reliability": 0.95,
        "rate_limit_per_hour": 60,
    },
    {
        "site_id": "product_hunt",
        "site_name": "Product Hunt",
        "type": "api",
        "description": "Daily product launches, especially AI tools",
        "url": "https://www.producthunt.com/",
        "category": "ai",
        "tags": ["ai", "tools", "launches"],
        "enabled": False,  # Requires API key
        "requires_auth": True,
        "auth_type": "api_key",
        "auth_env_var": "PRODUCT_HUNT_API_KEY",
        "reliability": 0.95,
        "rate_limit_per_hour": 30,
    },
    {
        "site_id": "github_trending",
        "site_name": "GitHub Trending",
        "type": "api",
        "description": "Trending repositories, filtered for AI/ML",
        "url": "https://github.com/trending",
        "category": "tech",
        "tags": ["code", "ai", "open-source"],
        "enabled": False,  # Requires GitHub token
        "requires_auth": True,
        "auth_type": "api_key",
        "auth_env_var": "GITHUB_TOKEN",
        "reliability": 0.98,
        "rate_limit_per_hour": 60,
    },
    {
        "site_id": "hacker_news",
        "site_name": "Hacker News (Official)",
        "type": "api",
        "description": "Official Hacker News API for top stories",
        "url": "https://news.ycombinator.com/",
        "category": "tech",
        "tags": ["hackernews", "tech", "discussion"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.98,
    },
    {
        "site_id": "arxiv_ai",
        "site_name": "Arxiv AI/ML Papers",
        "type": "api",
        "description": "Latest AI/ML research papers from Arxiv",
        "url": "https://arxiv.org/",
        "category": "research",
        "tags": ["research", "papers", "ai"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.99,
    },
    {
        "site_id": "papers_with_code",
        "site_name": "Papers With Code",
        "type": "api",
        "description": "ML papers with implementation code",
        "url": "https://paperswithcode.com/",
        "category": "research",
        "tags": ["research", "code", "ai"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.95,
    },
    {
        "site_id": "lobsters",
        "site_name": "Lobsters",
        "type": "rss",
        "description": "Tech-focused link aggregation community",
        "url": "https://lobste.rs/",
        "category": "tech",
        "tags": ["tech", "discussion"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.9,
    },
    {
        "site_id": "medium_ai",
        "site_name": "Medium (AI Publications)",
        "type": "rss",
        "description": "AI/ML publications on Medium",
        "url": "https://medium.com/",
        "category": "ai",
        "tags": ["ai", "articles", "blog"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.85,
    },
    {
        "site_id": "dev_ai",
        "site_name": "Dev.to (AI Tag)",
        "type": "api",
        "description": "AI tagged articles on Dev.to",
        "url": "https://dev.to/t/artificialintelligence",
        "category": "ai",
        "tags": ["ai", "articles", "developer"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.85,
        "rate_limit_per_hour": 100,
    },
    {
        "site_id": "indiehackers",
        "site_name": "Indie Hackers",
        "type": "rss",
        "description": "AI startups and indie hacker stories",
        "url": "https://www.indiehackers.com/",
        "category": "ai",
        "tags": ["ai", "startup", "business"],
        "enabled": True,  # No auth required
        "requires_auth": False,
        "reliability": 0.85,
    },
]


def init_default_sources() -> None:
    """Initialize default sources configuration."""
    from update_news import fetch_techurls, fetch_buzzing, fetch_iris, fetch_bestblogs
    from update_news import fetch_tophub, fetch_zeli, fetch_ai_hubtoday, fetch_aibase
    from update_news import fetch_aihot, fetch_newsnow

    # Create wrapper fetcher classes for existing functions
    class TechURLsFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_techurls(session, now)
        def get_status(self):
            return {"status": "active"}

    class BuzzingFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_buzzing(session, now)
        def get_status(self):
            return {"status": "active"}

    class IrisFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_iris(session, now)
        def get_status(self):
            return {"status": "active"}

    class BestBlogsFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_bestblogs(session, now)
        def get_status(self):
            return {"status": "active"}

    class TopHubFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_tophub(session, now)
        def get_status(self):
            return {"status": "active"}

    class ZeliFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_zeli(session, now)
        def get_status(self):
            return {"status": "active"}

    class AIHubTodayFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_ai_hubtoday(session, now)
        def get_status(self):
            return {"status": "active"}

    class AIbaseFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_aibase(session, now)
        def get_status(self):
            return {"status": "active"}

    class AIhotFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_aihot(session, now)
        def get_status(self):
            return {"status": "active"}

    class NewsNowFetcher(SourceFetcher):
        def fetch(self, session, now):
            return fetch_newsnow(session, now)
        def get_status(self):
            return {"status": "active"}

    # Register all default sources
    fetchers = {
        "techurls": TechURLsFetcher,
        "buzzing": BuzzingFetcher,
        "iris": IrisFetcher,
        "bestblogs": BestBlogsFetcher,
        "tophub": TopHubFetcher,
        "zeli": ZeliFetcher,
        "aihubtoday": AIHubTodayFetcher,
        "aibase": AIbaseFetcher,
        "aihot": AIhotFetcher,
        "newsnow": NewsNowFetcher,
    }

    for source_def in DEFAULT_SOURCES:
        config = SourceConfig(**source_def)
        fetcher_class = fetchers.get(source_def["site_id"])
        if fetcher_class:
            register_source(config, fetcher_class)


# Initialize when module is imported
try:
    init_default_sources()
except ImportError:
    # Delayed initialization for circular imports
    pass


if __name__ == "__main__":
    # Print all available sources
    sources = list_all_sources()
    print(f"Registered {len(sources)} sources:")
    for s in sources:
        status = "enabled" if s["enabled"] else "disabled"
        auth = " [auth]" if s["requires_auth"] else ""
        print(f"  - {s['site_name']}: {s['category']} | {status}{auth}")
        if s["description"]:
            print(f"      {s['description']}")

    print(f"\nNew sources available:")
    for s in NEW_SOURCES:
        status = "enabled" if s["enabled"] else "disabled"
        auth = " [auth]" if s["requires_auth"] else ""
        print(f"  - {s['site_name']}: {s['category']} | {status}{auth}")
        print(f"      {s['description']}")
