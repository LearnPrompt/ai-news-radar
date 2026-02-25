#!/usr/bin/env python3
"""New information sources for AI news radar.

This module contains implementations for high-value AI/tech information sources.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from update_news import RawItem, normalize_url, parse_date_any
from update_news import maybe_fix_mojibake, parse_unix_timestamp, parse_iso

UTC = timezone.utc
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


# ============================================================================
# Hacker News (Official API)
# ============================================================================

def fetch_hacker_news_official(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch top stories from Hacker News official API.

    This uses the official HN API which requires no authentication.
    """
    site_id = "hacker_news"
    site_name = "Hacker News"

    out: list[RawItem] = []

    try:
        # Get top story IDs
        r = session.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15)
        r.raise_for_status()
        story_ids = r.json()

        # Fetch top 30 stories
        for story_id in story_ids[:30]:
            try:
                item_r = session.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    timeout=10
                )
                item_r.raise_for_status()
                item = item_r.json()

                if not item or item.get("type") != "story":
                    continue

                title = str(item.get("title", "")).strip()
                url = str(item.get("url", "")).strip()
                if not url:
                    url = f"https://news.ycombinator.com/item?id={story_id}"

                if not title or not url:
                    continue

                # Score filter for quality
                score = item.get("score", 0)
                if score < 10:
                    continue

                # Fetch comments count for ranking
                comments = item.get("descendants", 0)

                published = parse_unix_timestamp(item.get("time")) or now

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=f"Top Stories (score:{score})",
                        title=title,
                        url=url,
                        published_at=published,
                        meta={
                            "hn_id": story_id,
                            "score": score,
                            "comments": comments,
                            "author": item.get("by"),
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Arxiv AI/ML Papers
# ============================================================================

def fetch_arxiv_ai(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch latest AI/ML papers from Arxiv.

    Uses the Arxiv API to fetch papers from AI/ML related categories.
    """
    site_id = "arxiv_ai"
    site_name = "Arxiv AI/ML"

    # AI/ML related Arxiv categories
    categories = [
        "cs.AI",  # Artificial Intelligence
        "cs.CL",  # Computation and Language
        "cs.CV",  # Computer Vision
        "cs.LG",  # Machine Learning
        "cs.NE",  # Neural and Evolutionary Computing
        "stat.ML",  # Statistics - Machine Learning
    ]

    out: list[RawItem] = []

    try:
        # Build query for recent papers (last 2 days)
        query_parts = [f"cat:{cat}" for cat in categories]
        query = " OR ".join(query_parts)

        # Use date filter via Arxiv API
        date_filter = f"submittedDate:[{now - timedelta(days=2):YmdH} TO {now:YmdH}]"
        search_query = f"({query}) AND {date_filter}"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": 50,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        r = session.get(
            "http://export.arxiv.org/api/query",
            params=params,
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
        )
        r.raise_for_status()

        # Parse Arxiv Atom feed
        soup = BeautifulSoup(r.text, "xml")

        for entry in soup.find_all("entry", limit=50):
            try:
                title = entry.find("title").text.strip()
                # Clean title from multiple newlines
                title = re.sub(r"\s+", " ", title)

                arxiv_id = entry.find("id").text.strip()
                # Extract arxiv ID like 2402.12345
                arxiv_id_match = re.search(r"(\d+\.\d+)", arxiv_id)
                if arxiv_id_match:
                    arxiv_id = f"arxiv:{arxiv_id_match.group(1)}"
                    url = f"https://arxiv.org/abs/{arxiv_id_match.group(1)}"
                else:
                    continue

                # Get authors
                authors = entry.find_all("author")
                author_list = [a.find("name").text for a in authors[:5]]
                authors_str = ", ".join(author_list)
                if len(authors) > 5:
                    authors_str += " et al."

                # Get published date
                published = entry.find("published").text.strip()
                published_dt = parse_iso(published)

                # Get primary category
                primary_cat = entry.find("arxiv:primary_category")
                category = primary_cat.get("term") if primary_cat else "cs.AI"

                # Get summary
                summary = entry.find("summary")
                summary_text = summary.text.strip() if summary else ""
                summary_text = re.sub(r"\s+", " ", summary_text)[:300]

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=category,
                        title=f"[{arxiv_id}] {title}",
                        url=url,
                        published_at=published_dt,
                        meta={
                            "authors": authors_str,
                            "summary": summary_text,
                            "arxiv_id": arxiv_id,
                            "category": category,
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Papers With Code
# ============================================================================

def fetch_papers_with_code(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch latest ML papers with code from Papers With Code."""
    site_id = "papers_with_code"
    site_name = "Papers With Code"

    out: list[RawItem] = []

    try:
        # Papers With Code doesn't have a public API, so we scrape trending
        r = session.get(
            "https://paperswithcode.com/trending",
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select(".paper-card", limit=20):
            try:
                link = item.select_one("a.paper-title")
                if not link:
                    continue

                title = link.get_text(" ", strip=True)
                href = link.get("href", "").strip()
                url = urljoin("https://paperswithcode.com/", href) if href else ""

                if not title or not url:
                    continue

                # Extract stars
                stars = item.select_one(".stars-count")
                stars_text = stars.get_text(strip=True) if stars else ""

                # Extract frameworks
                frameworks = item.select(".framework-tag")
                framework_list = [f.get_text(strip=True) for f in frameworks]

                # Extract tasks
                tasks = item.select(".task-tag")
                task_list = [t.get_text(strip=True) for t in tasks]

                source = f"Trending [{stars_text}]"
                if task_list:
                    source += f" | {', '.join(task_list[:2])}"

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=source,
                        title=title,
                        url=url,
                        published_at=now,  # Trending doesn't show publish date
                        meta={
                            "stars": stars_text,
                            "frameworks": framework_list,
                            "tasks": task_list,
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Lobsters
# ============================================================================

def fetch_lobsters(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch stories from Lobsters tech community via RSS."""
    site_id = "lobsters"
    site_name = "Lobsters"

    out: list[RawItem] = []

    try:
        r = session.get(
            "https://lobste.rs/rss",
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "xml")

        for item in soup.find_all("item", limit=25):
            try:
                title = item.find("title").text.strip()
                link = item.find("link").text.strip()

                if not title or not link:
                    continue

                # Get comments URL
                comments = item.find("comments")
                comments_url = comments.text.strip() if comments else link

                # Get tags
                tags = item.find("category")
                tags_text = tags.text.strip() if tags else ""

                # Get published date
                pub_date = item.find("pubDate")
                published = parse_date_any(pub_date.text.strip() if pub_date else "", now)

                # Clean title to remove domain suffix
                title = re.sub(r"\s*\(\w+\.\w+\)$", "", title)

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=tags_text or "Lobsters",
                        title=title,
                        url=comments_url if "lobste.rs" in comments_url else link,
                        published_at=published,
                        meta={
                            "link": link,
                            "comments": comments_url,
                            "tags": tags_text,
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Dev.to AI Articles
# ============================================================================

def fetch_dev_to_ai(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch AI tagged articles from Dev.to."""
    site_id = "dev_ai"
    site_name = "Dev.to (AI)"

    out: list[RawItem] = []

    try:
        # Dev.to public API
        r = session.get(
            "https://dev.to/api/articles",
            params={
                "tag": "artificialintelligence",
                "top": 7,  # Top of last 7 days
                "per_page": 30,
            },
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
        )
        r.raise_for_status()

        articles = r.json()

        for article in articles:
            try:
                title = str(article.get("title", "")).strip()
                url = str(article.get("url", "")).strip()
                if not title or not url:
                    continue

                # Get metadata
                author = article.get("user", {}).get("name", "")
                tags = article.get("tag_list", [])
                positive_reactions = article.get("positive_reactions_count", 0)
                comments = article.get("comments_count", 0)

                # Filter for quality
                if positive_reactions < 5:
                    continue

                published = parse_date_any(article.get("published_at"), now)

                source = f"{author}"
                if tags:
                    source += f" | {', '.join(tags[:3])}"

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=source,
                        title=title,
                        url=url,
                        published_at=published,
                        meta={
                            "author": author,
                            "tags": tags,
                            "reactions": positive_reactions,
                            "comments": comments,
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Medium AI Publications RSS
# ============================================================================

def fetch_medium_ai(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch AI publications from Medium via RSS.

    Focuses on AI/ML related publications.
    """
    site_id = "medium_ai"
    site_name = "Medium (AI)"

    # AI/ML related Medium publications
    rss_feeds = [
        ("Towards Data Science", "https://towardsdatascience.com/feed"),
        ("The Startup", "https://medium.com/feed/the-startup"),
        ("AI Advances", "https://medium.com/feed/@openai"),
        ("Google AI Blog", "https://ai.googleblog.com/feeds/posts/default"),  # Actually on Blogger
    ]

    out: list[RawItem] = []

    for pub_name, feed_url in rss_feeds:
        try:
            r = session.get(feed_url, timeout=30, headers={"User-Agent": BROWSER_UA})
            r.raise_for_status()

            soup = BeautifulSoup(r.content, "xml")

            for item in soup.find_all("item", limit=10):
                try:
                    title = item.find("title").text.strip()
                    link = item.find("link").text.strip()

                    if not title or not link:
                        continue

                    # Skip Medium upgrade prompts
                    if "medium.com/membership" in link or "medium.com/p/" not in link:
                        continue

                    pub_date = item.find("pubDate")
                    published = parse_date_any(pub_date.text.strip() if pub_date else "", now)

                    # Get author
                    author = item.find("dc:creator")
                    author_name = author.text.strip() if author else ""

                    # Get categories/tags
                    categories = item.find_all("category")
                    tags = [c.text.strip() for c in categories if c.text.strip()]

                    source = pub_name
                    if author_name:
                        source += f" | {author_name}"

                    out.append(
                        RawItem(
                            site_id=site_id,
                            site_name=site_name,
                            source=source,
                            title=title,
                            url=link,
                            published_at=published,
                            meta={
                                "author": author_name,
                                "tags": tags,
                                "publication": pub_name,
                            },
                        )
                    )
                except Exception:
                    continue

        except Exception:
            continue

    return out


# ============================================================================
# Indie Hackers
# ============================================================================

def fetch_indiehackers(session: requests.Session, now: datetime) -> list[RawItem]:
    """Fetch AI startup and indie hacker stories from Indie Hackers."""
    site_id = "indiehackers"
    site_name = "Indie Hackers"

    out: list[RawItem] = []

    try:
        # Indie Hackers doesn't have public API, scrape via RSS
        r = session.get(
            "https://www.indiehackers.com/feed",
            timeout=30,
            headers={"User-Agent": BROWSER_UA},
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "xml")

        for item in soup.find_all("item", limit=20):
            try:
                title = item.find("title").text.strip()
                link = item.find("link").text.strip()

                if not title or not link:
                    continue

                # Get published date
                pub_date = item.find("pubDate")
                published = parse_date_any(pub_date.text.strip() if pub_date else "", now)

                # Get description and check for AI relevance
                description = item.find("description")
                desc_text = description.text if description else ""
                desc_text = re.sub(r"<[^>]+>", "", desc_text).strip()

                # Get categories
                categories = item.find_all("category")
                tags = [c.text.strip() for c in categories if c.text.strip()]

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=f"Indie Hackers",
                        title=title,
                        url=link,
                        published_at=published,
                        meta={
                            "tags": tags,
                            "description": desc_text[:200],
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Reddit (optional, requires API credentials)
# ============================================================================

def fetch_reddit_ai(session: requests.Session, now: datetime, client_id: str = "", client_secret: str = "") -> list[RawItem]:
    """Fetch posts from AI/ML subreddits.

    Note: Requires Reddit API credentials.
    Set client_id and client_secret from Reddit app settings.
    """
    site_id = "reddit_ai"
    site_name = "Reddit (AI)"

    out: list[RawItem] = []

    if not client_id or not client_secret:
        return out

    try:
        # Get access token
        auth = requests.auth.HTTPBasicAuth(client_id, client_secret)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": BROWSER_UA}

        token_r = session.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers=headers,
            timeout=15,
        )
        token_r.raise_for_status()
        token_data = token_r.json()
        access_token = token_data.get("access_token")

        if not access_token:
            return out

        # Fetch from AI/ML subreddits
        subreddits = ["artificial", "MachineLearning", "LocalLLaMA", "ChatGPT"]

        headers["Authorization"] = f"bearer {access_token}"

        for subreddit in subreddits:
            try:
                params = {"limit": 20, "sort": "hot"}
                r = session.get(
                    f"https://oauth.reddit.com/r/{subreddit}/hot",
                    params=params,
                    headers=headers,
                    timeout=20,
                )
                r.raise_for_status()
                data = r.json()

                for post in data.get("data", {}).get("children", []):
                    try:
                        post_data = post.get("data", {})
                        title = str(post_data.get("title", "")).strip()

                        # Use self text URL if no external link
                        url = post_data.get("url")
                        if not url or url.startswith(f"https://www.reddit.com/r/{subreddit}/"):
                            post_id = post_data.get("id", "")
                            url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/"

                        if not title or not url:
                            continue

                        # Filter for quality (upvotes)
                        score = post_data.get("score", 0)
                        if score < 10:
                            continue

                        # Filter for AI relevance based on title
                        ai_keywords = ["ai", "gpt", "llm", "model", "agent", "prompt", "diffusion"]
                        if not any(kw in title.lower() for kw in ai_keywords):
                            continue

                        published = parse_unix_timestamp(post_data.get("created_utc")) or now

                        out.append(
                            RawItem(
                                site_id=site_id,
                                site_name=site_name,
                                source=f"r/{subreddit} ({score}↑)",
                                title=title,
                                url=url,
                                published_at=published,
                                meta={
                                    "subreddit": subreddit,
                                    "score": score,
                                    "comments": post_data.get("num_comments", 0),
                                    "author": post_data.get("author"),
                                },
                            )
                        )
                    except Exception:
                        continue

            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Product Hunt (optional, requires API key)
# ============================================================================

def fetch_product_hunt(session: requests.Session, now: datetime, api_key: str = "") -> list[RawItem]:
    """Fetch daily AI tool launches from Product Hunt.

    Note: Requires Product Hunt API key.
    """
    site_id = "product_hunt"
    site_name = "Product Hunt"

    out: list[RawItem] = []

    if not api_key:
        return out

    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": BROWSER_UA,
        }

        # Get today's posts
        r = session.get(
            "https://api.producthunt.com/v2/api/graphql",
            headers=headers,
            json={
                "query": """
                    query {
                        posts(order: VOTING, first: 20) {
                            nodes {
                                id
                                name
                                description
                                tagline
                                url
                                votesCount
                                website
                                topics(first: 5) {
                                    nodes {
                                        name
                                    }
                                }
                            }
                        }
                    }
                """
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        posts = data.get("data", {}).get("posts", {}).get("nodes", [])

        for post in posts:
            try:
                name = str(post.get("name", "")).strip()
                tagline = str(post.get("tagline", "")).strip()
                url = str(post.get("url") or post.get("website", "")).strip()

                if not name or not url:
                    continue

                # Filter for AI relevance
                topics = [t.get("name", "") for t in post.get("topics", {}).get("nodes", [])]
                topics_lower = [t.lower() for t in topics]

                ai_keywords = ["ai", "artificial intelligence", "machine learning", "llm", "gpt"]
                if not any(kw in tagline.lower() or any(kw in t for t in topics_lower)
                          for kw in ai_keywords):
                    continue

                # Filter for quality
                votes = post.get("votesCount", 0)
                if votes < 5:
                    continue

                title = f"{name}: {tagline}"

                out.append(
                    RawItem(
                        site_id=site_id,
                        site_name=site_name,
                        source=f"Product Hunt ({votes}👍) | {', '.join(topics[:2])}",
                        title=title,
                        url=url,
                        published_at=now,
                        meta={
                            "name": name,
                            "tagline": tagline,
                            "votes": votes,
                            "topics": topics,
                        },
                    )
                )
            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# GitHub Trending (optional, requires token)
# ============================================================================

def fetch_github_trending(session: requests.Session, now: datetime, token: str = "") -> list[RawItem]:
    """Fetch trending repositories from GitHub.

    Note: Works better with GitHub token for higher rate limits.
    """
    site_id = "github_trending"
    site_name = "GitHub Trending"

    out: list[RawItem] = []

    try:
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "application/vnd.github.v3+json",
        }

        if token:
            headers["Authorization"] = f"token {token}"

        # Search for AI/ML repositories, sorted by stars
        query = """
            query($q: String!) {
                search(query: $q, type: REPOSITORY, first: 20, sort: stars-desc) {
                    nodes {
                        ... on Repository {
                            id
                            name
                            description
                            url
                            stargazerCount
                            forkCount
                            primaryLanguage {
                                name
                            }
                            createdAt
                            updatedAt
                            repositoryTopics(first: 10) {
                                nodes {
                                    topic {
                                        name
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """

        # AI/ML search terms
        search_queries = [
            "language:python stars:>100 pushed:>2024-01-01 artificial-intelligence",
            "language:python stars:>100 pushed:>2024-01-01 machine-learning",
            "language:python stars:>100 pushed:>2024-01-01 llm OR gpt OR transformer",
        ]

        for search_q in search_queries:
            try:
                r = session.post(
                    "https://api.github.com/graphql",
                    headers=headers,
                    json={"query": query, "variables": {"q": search_q}},
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()

                repos = data.get("data", {}).get("search", {}).get("nodes", [])

                for repo in repos:
                    try:
                        name = str(repo.get("name", "")).strip()
                        description = str(repo.get("description", "")).strip()
                        url = str(repo.get("url", "")).strip()

                        if not name or not url:
                            continue

                        # Filter for AI relevance
                        desc_lower = description.lower()
                        topics = [t.get("topic", {}).get("name", "")
                                for t in repo.get("repositoryTopics", {}).get("nodes", [])]
                        topics_lower = [t.lower() for t in topics]

                        ai_keywords = ["ai", "artificial intelligence", "machine learning",
                                      "deep learning", "neural", "llm", "gpt", "transformer",
                                      "diffusion", "stable diffusion", "embedding"]
                        if not any(kw in desc_lower or any(kw in t for t in topics_lower)
                                  for kw in ai_keywords):
                            continue

                        stars = repo.get("stargazerCount", 0)
                        if stars < 500:
                            continue

                        language = repo.get("primaryLanguage", {}).get("name", "")

                        title = description or name
                        if description:
                            title = f"{name}: {description}"

                        out.append(
                            RawItem(
                                site_id=site_id,
                                site_name=site_name,
                                source=f"{language} | ⭐{stars}",
                                title=title,
                                url=url,
                                published_at=parse_iso(repo.get("updatedAt")) or now,
                                meta={
                                    "name": name,
                                    "stars": stars,
                                    "forks": repo.get("forkCount", 0),
                                    "language": language,
                                    "topics": topics,
                                },
                            )
                        )
                    except Exception:
                        continue

            except Exception:
                continue

    except Exception:
        pass

    return out


# ============================================================================
# Helper function to get all new source fetchers
# ============================================================================

NEW_SOURCE_FUNCTIONS = {
    "hacker_news": fetch_hacker_news_official,
    "arxiv_ai": fetch_arxiv_ai,
    "papers_with_code": fetch_papers_with_code,
    "lobsters": fetch_lobsters,
    "dev_ai": fetch_dev_to_ai,
    "medium_ai": fetch_medium_ai,
    "indiehackers": fetch_indiehackers,
}


# Sources requiring authentication
AUTH_SOURCE_FUNCTIONS = {
    "reddit_ai": lambda s, n: fetch_reddit_ai(
        s, n,
        client_id="",  # Set from env
        client_secret="",  # Set from env
    ),
    "product_hunt": lambda s, n: fetch_product_hunt(
        s, n,
        api_key="",  # Set from env
    ),
    "github_trending": lambda s, n: fetch_github_trending(
        s, n,
        token="",  # Set from env
    ),
}


if __name__ == "__main__":
    # Test all new sources
    import requests

    session = requests.Session()
    now = datetime.now(UTC)

    print("Testing new sources...")
    print()

    for site_id, fetch_fn in NEW_SOURCE_FUNCTIONS.items():
        print(f"Fetching from {site_id}...")
        try:
            items = fetch_fn(session, now)
            print(f"  Got {len(items)} items")
            for item in items[:3]:
                print(f"    - {item.title[:60]}...")
        except Exception as e:
            print(f"  Error: {e}")
        print()
