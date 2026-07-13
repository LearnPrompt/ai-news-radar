import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.update_news import (
    BUILTIN_SOURCE_TASKS,
    RETIRED_SOURCE_IDS,
    add_bilingual_fields,
    add_creator_ranking_fields,
    add_source_tier_fields,
    build_agentmail_digest_payload,
    build_creator_hot_items,
    build_latest_payloads,
    dedupe_items_by_title_url,
    fetch_agentmail_digest,
    fetch_aihot,
    fetch_ai_hubtoday,
    fetch_hacker_news_algolia,
    fetch_socialdata_list_tweets,
    fetch_tikhub_search,
    hn_algolia_keyword_score,
    is_ai_related_record,
    is_hubtoday_generic_anchor_title,
    is_hubtoday_placeholder_title,
    load_archive,
    maybe_fetch_agentmail_digest,
    maybe_fetch_socialdata_updates,
    socialdata_status_base,
    maybe_fetch_tikhub_updates,
    maybe_fetch_x_api_updates,
    maybe_fix_mojibake,
    normalize_source_for_display,
    parse_ai_breakfast_items,
    parse_aihot_api_items,
    parse_aihot_feed_items,
    parse_curated_ai_media_feed_items,
    parse_date_any,
    parse_feed_entries_via_xml,
    parse_hn_algolia_hits,
    parse_tikhub_douyin_items,
    parse_tikhub_xiaohongshu_items,
    parse_anthropic_news_items,
    parse_follow_builders_items,
    parse_openai_codex_changelog_items,
    redact_public_text,
    repair_zh_title_translation,
    source_tier_for_site,
    source_tier_sort_key,
    sync_paid_source_status_timestamps,
    tikhub_status_base,
    update_paid_source_state,
)


class TopicFilterTests(unittest.TestCase):
    def test_paid_source_status_uses_the_persisted_run_timestamps(self):
        now = __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00")
        state = {"sources": {}}
        status = {"attempted": True, "ok": True, "item_count": 7}

        update_paid_source_state(state, "socialdata", status, now)
        sync_paid_source_status_timestamps(status, state, "socialdata")

        self.assertEqual(status["last_run_at"], "2026-05-03T01:00:00Z")
        self.assertEqual(status["last_success_at"], "2026-05-03T01:00:00Z")

    def test_paid_source_default_intervals_are_per_source(self):
        now = __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00")
        with patch.dict("os.environ", {}, clear=True):
            socialdata_status = socialdata_status_base(now, None)
            tikhub_status = tikhub_status_base(now, None)

        self.assertEqual(socialdata_status["run_interval_hours"], 12)
        self.assertEqual(tikhub_status["run_interval_hours"], 24)

    def test_accepts_ai_keyword(self):
        rec = {
            "site_id": "techurls",
            "site_name": "TechURLs",
            "source": "Hacker News",
            "title": "OpenAI releases new GPT model",
            "url": "https://example.com/ai",
        }
        self.assertTrue(is_ai_related_record(rec))

    def test_accepts_copilot_keyword(self):
        rec = {
            "site_id": "official_ai",
            "site_name": "Official AI Updates",
            "source": "GitHub Changelog",
            "title": "GitHub Copilot adds a new coding agent",
            "url": "https://example.com/copilot",
        }
        self.assertTrue(is_ai_related_record(rec))

    def test_accepts_robotics_keyword(self):
        rec = {
            "site_id": "newsnow",
            "site_name": "NewsNow",
            "source": "technology",
            "title": "Embodied robotics gets new funding",
            "url": "https://example.com/robotics",
        }
        self.assertTrue(is_ai_related_record(rec))

    def test_accepts_follow_builders_curated_feed(self):
        rec = {
            "site_id": "followbuilders",
            "site_name": "Follow Builders",
            "source": "Follow Builders · X · Andrej Karpathy",
            "title": "A terse but useful Codex builder note",
            "url": "https://x.com/karpathy/status/1",
        }
        self.assertTrue(is_ai_related_record(rec))

    def test_rejects_noise_topic(self):
        rec = {
            "site_id": "newsnow",
            "site_name": "NewsNow",
            "source": "微博热搜",
            "title": "明星八卦今日热搜",
            "url": "https://example.com/noise",
        }
        self.assertFalse(is_ai_related_record(rec))

    def test_rejects_commerce_noise(self):
        rec = {
            "site_id": "newsnow",
            "site_name": "NewsNow",
            "source": "淘宝 ‧ 天猫 · 热销总榜",
            "title": "白象拌面任选加码 券后¥29.96",
            "url": "https://example.com/shop",
        }
        self.assertFalse(is_ai_related_record(rec))

    def test_zeli_only_24h_hot(self):
        keep = {
            "site_id": "zeli",
            "site_name": "Zeli",
            "source": "Hacker News · 24h最热",
            "title": "AI Agent for code search",
            "url": "https://example.com/a",
        }
        drop = {
            "site_id": "zeli",
            "site_name": "Zeli",
            "source": "HN New",
            "title": "AI Agent for code search",
            "url": "https://example.com/b",
        }
        self.assertTrue(is_ai_related_record(keep))
        self.assertFalse(is_ai_related_record(drop))

    def test_zeli_24h_hot_still_requires_an_ai_signal(self):
        rec = {
            "site_id": "zeli",
            "site_name": "Zeli",
            "source": "Hacker News · 24h最热",
            "title": "An Infuriating Goodbye to Photoshop",
            "url": "https://example.com/photoshop",
        }
        self.assertFalse(is_ai_related_record(rec))

    def test_retired_sources_are_neither_fetched_nor_reloaded_from_archive(self):
        active_source_ids = {site_id for site_id, _site_name, _fetcher in BUILTIN_SOURCE_TASKS}
        self.assertTrue(RETIRED_SOURCE_IDS.isdisjoint(active_source_ids))

        with TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "archive.json"
            archive_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {"id": "old-top", "site_id": "tophub"},
                            {"id": "old-buzz", "site_id": "buzzing"},
                            {"id": "old-iris", "site_id": "iris"},
                            {"id": "keep", "site_id": "techurls"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(set(load_archive(archive_path)), {"keep"})

    def test_hn_algolia_keyword_score_requires_multiple_signals(self):
        self.assertGreaterEqual(hn_algolia_keyword_score("OpenAI releases Codex agent tools"), 0.38)
        self.assertLess(hn_algolia_keyword_score("OpenAI announces a policy update"), 0.38)

    def test_parse_hn_algolia_hits_filters_and_dedupes_discussion_items(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)
        payloads = [
            (
                "OpenAI",
                {
                    "hits": [
                        {
                            "objectID": "1",
                            "title": "OpenAI releases Codex agent tools",
                            "url": "https://example.com/codex",
                            "created_at": "2026-06-23T10:00:00Z",
                            "num_comments": 5,
                            "points": 11,
                        },
                        {
                            "objectID": "2",
                            "title": "OpenAI announces a policy update",
                            "url": "https://example.com/policy",
                            "created_at": "2026-06-23T09:00:00Z",
                            "num_comments": 20,
                            "points": 50,
                        },
                        {
                            "objectID": "3",
                            "title": "MCP server benchmark for coding agents",
                            "created_at_i": 1782210600,
                            "num_comments": 1,
                            "points": 8,
                        },
                    ]
                },
            ),
            (
                "Codex",
                {
                    "hits": [
                        {
                            "objectID": "1",
                            "title": "OpenAI releases Codex agent tools",
                            "url": "https://duplicate.example.com/codex",
                            "created_at": "2026-06-23T10:00:00Z",
                            "num_comments": 99,
                            "points": 99,
                        },
                        {
                            "objectID": "4",
                            "title": "MCP server benchmark for coding agents",
                            "created_at_i": 1782210600,
                            "num_comments": 2,
                            "points": 10,
                        },
                    ]
                },
            ),
        ]

        items = parse_hn_algolia_hits(payloads, now)

        self.assertEqual([item.meta["hn_id"] for item in items], ["1", "4"])
        self.assertEqual(items[0].site_id, "hackernews")
        self.assertEqual(items[0].site_name, "Hacker News")
        self.assertEqual(items[0].source, "HN Algolia · AI 24h")
        self.assertEqual(items[0].meta["hn_url"], "https://news.ycombinator.com/item?id=1")
        self.assertEqual(items[1].url, "https://news.ycombinator.com/item?id=4")

    def test_fetch_hn_algolia_uses_public_search_by_date_api(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "hits": [
                        {
                            "objectID": "1",
                            "title": "OpenAI releases Codex agent tools",
                            "url": "https://example.com/codex",
                            "created_at": "2026-06-23T10:00:00Z",
                            "num_comments": 5,
                            "points": 11,
                        }
                    ]
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        with patch("scripts.update_news.HN_ALGOLIA_QUERIES", ("OpenAI",)), patch("scripts.update_news.time.sleep"):
            items = fetch_hacker_news_algolia(session, now)

        self.assertEqual(len(items), 1)
        self.assertEqual(session.calls[0][0], "https://hn.algolia.com/api/v1/search_by_date")
        self.assertEqual(session.calls[0][1]["params"]["query"], "OpenAI")
        self.assertEqual(session.calls[0][1]["params"]["tags"], "story")
        self.assertEqual(session.calls[0][1]["params"]["numericFilters"], "created_at_i>1782129600")

    def test_buzzing_source_fallback_to_host(self):
        source = normalize_source_for_display("buzzing", "Buzzing", "https://news.ycombinator.com/item?id=1")
        self.assertEqual(source, "news.ycombinator.com")

    def test_fix_mojibake(self):
        raw = "è°å¨ç¼åä»£ç "
        self.assertEqual(maybe_fix_mojibake(raw), "谁在编写代码")

    def test_parse_feed_entries_via_xml(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<rss><channel>
<item><title>A</title><link>https://x/a</link><pubDate>2026-02-20</pubDate></item>
</channel></rss>"""
        items = parse_feed_entries_via_xml(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")

    def test_parse_atom_feed_entries_via_xml(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>A</title><link href="https://x/a" /><updated>2026-02-20</updated></entry>
</feed>"""
        items = parse_feed_entries_via_xml(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "A")
        self.assertEqual(items[0]["link"], "https://x/a")

    def test_parse_anthropic_news_items(self):
        html = """
        <a href="/news/claude-opus-4-7">
          <time>Apr 16, 2026</time>
          <h2>Introducing Claude Opus 4.7</h2>
        </a>
        <a href="/news">News</a>
        """
        items = parse_anthropic_news_items(html, now=None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "Anthropic News")
        self.assertEqual(items[0].title, "Introducing Claude Opus 4.7")
        self.assertEqual(items[0].url, "https://www.anthropic.com/news/claude-opus-4-7")

    def test_parse_openai_codex_changelog_items(self):
        html = """
        <div id="codex-changelog-content">
          <li id="codex-2026-05-01">
            <time>2026-05-01</time>
            <h3><span>Codex app adds workspace companions</span></h3>
          </li>
        </div>
        """
        items = parse_openai_codex_changelog_items(html, now=None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source, "OpenAI Codex Changelog")
        self.assertEqual(items[0].title, "Codex app adds workspace companions")
        self.assertEqual(items[0].url, "https://developers.openai.com/codex/changelog#codex-2026-05-01")

    def test_parse_ai_breakfast_items(self):
        markdown = """
        [May 1, 2026 • 4 min read ### **Anthropic update lands** AI Breakfast](https://aibreakfast.beehiiv.com/p/anthropic-update-lands)
        [Apr 29, 2026 • 5 min read ### **OpenAI ships a model update** AI Breakfast](https://aibreakfast.beehiiv.com/p/openai-ships-model-update)
        """
        items = parse_ai_breakfast_items(markdown, now=None)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].source, "AI Breakfast")
        self.assertEqual(items[0].title, "Anthropic update lands")
        self.assertEqual(items[0].url, "https://aibreakfast.beehiiv.com/p/anthropic-update-lands")

    def test_parse_aihot_feed_items(self):
        xml = """<?xml version='1.0' encoding='UTF-8'?>
<rss><channel><title>AI HOT — 精选</title>
<item>
<title>OpenAI ships a new Codex feature</title>
<link>https://example.com/codex</link>
<pubDate>Mon, 11 May 2026 02:05:04 GMT</pubDate>
<author>noreply@aihot.virxact.com (X：Builder)</author>
</item>
</channel></rss>""".encode("utf-8")
        items = parse_aihot_feed_items(xml, now=None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "aihot")
        self.assertEqual(items[0].site_name, "AI HOT")
        self.assertEqual(items[0].title, "OpenAI ships a new Codex feature")
        self.assertEqual(items[0].url, "https://example.com/codex")

    def test_parse_aihot_api_items_keeps_only_score_60_plus(self):
        payload = {
            "items": [
                {
                    "id": "high",
                    "title": "高分条目",
                    "title_en": "High score item",
                    "url": "https://example.com/high",
                    "source": "OpenAI Blog",
                    "publishedAt": "2026-06-16T19:35:22.252Z",
                    "summary": "Worth reading",
                    "category": "ai-models",
                    "score": 60,
                    "selected": True,
                },
                {
                    "id": "low",
                    "title": "Low score item",
                    "url": "https://example.com/low",
                    "source": "Blog",
                    "publishedAt": "2026-06-16T18:00:00.000Z",
                    "score": 59,
                    "selected": True,
                },
                {
                    "id": "missing",
                    "title": "Missing score item",
                    "url": "https://example.com/missing",
                    "source": "Blog",
                    "publishedAt": "2026-06-16T18:00:00.000Z",
                    "score": None,
                    "selected": True,
                },
            ]
        }

        items = parse_aihot_api_items(payload, now=datetime(2026, 6, 16, tzinfo=timezone.utc))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "高分条目")
        self.assertEqual(items[0].source, "OpenAI Blog")
        self.assertEqual(items[0].meta["aihot_score"], 60)
        self.assertEqual(items[0].meta["aihot_category"], "ai-models")
        self.assertEqual(items[0].meta["provided_title_zh"], "高分条目")
        self.assertEqual(items[0].meta["provided_title_en"], "High score item")

    def test_bilingual_fields_preserve_source_provided_title_pair_and_summary(self):
        class NoNetworkSession:
            def get(self, *args, **kwargs):
                raise AssertionError("source-provided bilingual titles must not be translated again")

        item = {
            "title": "Codex 加入 ChatGPT 桌面应用",
            "provided_title_zh": "Codex 加入 ChatGPT 桌面应用",
            "provided_title_en": "Codex joins the ChatGPT desktop app",
            "summary": "中文编辑摘要",
            "url": "https://example.com/codex",
        }
        ai_items, _, _ = add_bilingual_fields([item], [item], NoNetworkSession(), {}, 80)
        self.assertEqual(ai_items[0]["title_zh"], "Codex 加入 ChatGPT 桌面应用")
        self.assertEqual(ai_items[0]["title_en"], "Codex joins the ChatGPT desktop app")
        self.assertEqual(ai_items[0]["title_original"], "Codex joins the ChatGPT desktop app")
        self.assertEqual(ai_items[0]["summary"], "中文编辑摘要")
        self.assertNotIn("provided_title_en", ai_items[0])

        pseudo_english = {
            "title": "如何在低配置电脑运行 GLM-5.2",
            "provided_title_zh": "如何在低配置电脑运行 GLM-5.2",
            "provided_title_en": "Show HN：如何在我的低配置电脑上运行 GLM-5.2",
            "url": "https://example.com/glm",
        }
        pseudo_items, _, _ = add_bilingual_fields([pseudo_english], [pseudo_english], NoNetworkSession(), {}, 80)
        self.assertIsNone(pseudo_items[0]["title_en"])
        self.assertEqual(pseudo_items[0]["title_zh"], "如何在低配置电脑运行 GLM-5.2")

    def test_repairs_recurring_ai_title_translation_errors(self):
        self.assertEqual(
            repair_zh_title_translation("Codex CLI 0.144.0", "法典 CLI 0.144.0"),
            "Codex CLI 0.144.0",
        )
        self.assertEqual(
            repair_zh_title_translation("GPT-5.5 Bio Bug Bounty", "GPT-5.5 生物错误赏金"),
            "GPT-5.5 生物安全漏洞悬赏",
        )

    def test_fetch_aihot_uses_public_items_api_with_score_filter(self):
        page_1 = {
            "items": [
                {
                    "id": "page1",
                    "title": "Page one strong item",
                    "url": "https://example.com/page-1",
                    "source": "AI HOT Source",
                    "publishedAt": "2026-06-16T19:35:22.252Z",
                    "score": 88,
                    "selected": True,
                },
                {
                    "id": "page1-low",
                    "title": "Page one low item",
                    "url": "https://example.com/page-1-low",
                    "source": "AI HOT Source",
                    "publishedAt": "2026-06-16T19:35:22.252Z",
                    "score": 40,
                    "selected": True,
                },
            ],
            "hasNext": True,
            "nextCursor": "cursor-2",
        }
        page_2 = {
            "items": [
                {
                    "id": "page2",
                    "title": "Page two boundary item",
                    "url": "https://example.com/page-2",
                    "source": "AI HOT Source",
                    "publishedAt": "2026-06-16T19:36:22.252Z",
                    "score": 60,
                    "selected": True,
                }
            ],
            "hasNext": False,
            "nextCursor": None,
        }

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse(page_1 if len(self.calls) == 1 else page_2)

        session = FakeSession()
        items = fetch_aihot(session, now=datetime(2026, 6, 16, tzinfo=timezone.utc))
        self.assertEqual([item.title for item in items], ["Page one strong item", "Page two boundary item"])
        self.assertEqual(session.calls[0][0], "https://aihot.virxact.com/api/public/items")
        self.assertEqual(session.calls[0][1]["params"], {"mode": "selected", "take": 100})
        self.assertEqual(session.calls[1][1]["params"], {"mode": "selected", "take": 100, "cursor": "cursor-2"})
        self.assertIn("aihot-skill/0.2.0", session.calls[0][1]["headers"]["User-Agent"])

    def test_parse_curated_media_feed_applies_strict_title_filter_and_cap(self):
        xml = """<?xml version='1.0' encoding='UTF-8'?>
<rss><channel><title>The Verge</title>
<item>
<title>OpenAI launches a new ChatGPT product</title>
<link>https://www.theverge.com/ai-product</link>
<pubDate>Mon, 15 Jun 2026 02:05:04 GMT</pubDate>
</item>
<item>
<title>A phone accessory launches this week</title>
<link>https://www.theverge.com/phone</link>
<pubDate>Mon, 15 Jun 2026 03:05:04 GMT</pubDate>
</item>
</channel></rss>""".encode("utf-8")
        feed = {
            "title": "The Verge",
            "xml_url": "https://www.theverge.com/rss/index.xml",
            "include_keywords": "openai,chatgpt,artificial intelligence",
            "strict_title_filter": True,
            "max_entries": 1,
        }
        items = parse_curated_ai_media_feed_items(xml, feed, now=parse_date_any("2026-06-16T00:00:00Z", None))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "curated_media")
        self.assertEqual(items[0].source, "The Verge")
        self.assertIn("OpenAI", items[0].title)

    def test_parse_follow_builders_items(self):
        feeds = {
            "x": {
                "x": [
                    {
                        "name": "Andrej Karpathy",
                        "handle": "karpathy",
                        "tweets": [
                            {
                                "text": "LLM notes from the field",
                                "createdAt": "2026-05-02T06:21:22.000Z",
                                "url": "https://x.com/karpathy/status/1",
                            }
                        ],
                    }
                ]
            },
            "blogs": {
                "generatedAt": "2026-05-02T07:41:11.599Z",
                "blogs": [
                    {
                        "name": "Anthropic Engineering",
                        "title": "A Claude Code postmortem",
                        "url": "https://www.anthropic.com/engineering/postmortem",
                        "publishedAt": None,
                    }
                ],
            },
            "podcasts": {
                "podcasts": [
                    {
                        "name": "No Priors",
                        "title": "Inference cloud interview",
                        "url": "https://www.youtube.com/watch?v=abc",
                        "publishedAt": "2026-05-01T19:34:00.000Z",
                    }
                ]
            },
        }
        items = parse_follow_builders_items(feeds, now=None)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].site_id, "followbuilders")
        self.assertEqual(items[0].source, "Follow Builders · X · Andrej Karpathy")
        self.assertEqual(items[1].source, "Follow Builders · Blog · Anthropic Engineering")
        self.assertEqual(items[2].source, "Follow Builders · Podcast · No Priors")

    def test_hubtoday_placeholder_title(self):
        self.assertTrue(is_hubtoday_placeholder_title("详情见官方介绍(AI资讯)"))
        self.assertTrue(is_hubtoday_placeholder_title("查看详情"))
        self.assertFalse(is_hubtoday_placeholder_title("OpenAI 发布 GPT-5o"))
        self.assertTrue(is_hubtoday_generic_anchor_title("论文已公开(AI资讯)"))
        self.assertFalse(is_hubtoday_generic_anchor_title("Anthropic禁止第三方调用订阅。"))

    def test_dedupe_items_by_title_url_latest(self):
        items = [
            {
                "id": "1",
                "title": "Same",
                "title_original": "Same",
                "url": "https://example.com/a",
                "published_at": "2026-02-20T00:00:00Z",
            },
            {
                "id": "2",
                "title": "Same",
                "title_original": "Same",
                "url": "https://example.com/a",
                "published_at": "2026-02-20T01:00:00Z",
            },
        ]
        out = dedupe_items_by_title_url(items, random_pick=False)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "2")

    def test_rejects_broad_agent_noise_without_ai_context(self):
        rec = {
            "site_id": "buzzing",
            "site_name": "Buzzing",
            "source": "github.com",
            "title": "New travel agent marketplace launches in Europe",
            "url": "https://example.com/travel-agent",
        }
        self.assertFalse(is_ai_related_record(rec))

    def test_accepts_chinese_model_news_after_noise_tightening(self):
        rec = {
            "site_id": "newsnow",
            "site_name": "NewsNow",
            "source": "机器之心",
            "title": "新一代推理模型刷新多模态数学基准",
            "url": "https://example.com/reasoning-model",
        }
        self.assertTrue(is_ai_related_record(rec))

    def test_redacts_email_like_public_text(self):
        self.assertEqual(redact_public_text("Contact editor@example.com for access"), "Contact [redacted-email] for access")

    def test_build_latest_payloads_keeps_initial_payload_slim(self):
        latest_payload = {
            "generated_at": "2026-05-03T00:00:00Z",
            "window_hours": 24,
            "total_items": 1,
            "total_items_raw": 3,
            "total_items_all_mode": 2,
            "items_ai": [{"title": "AI post", "url": "https://example.com/a"}],
            "creator_items_ai": [{"title": "Hot creator post", "url": "https://example.com/hot"}],
            "items_all": [{"title": "All post", "url": "https://example.com/b"}],
            "items_all_raw": [{"title": "Raw post", "url": "https://example.com/c"}],
        }
        slim, all_payload = build_latest_payloads(latest_payload)
        self.assertIn("items_ai", slim)
        self.assertIn("creator_items_ai", slim)
        self.assertNotIn("items_all", slim)
        self.assertNotIn("items_all_raw", slim)
        self.assertEqual(slim["all_mode_data_url"], "data/latest-24h-all.json")
        self.assertEqual(slim["stories_data_url"], "data/stories-merged.json")
        self.assertEqual(all_payload["items_all"][0]["title"], "All post")
        self.assertEqual(all_payload["items_all_raw"][0]["title"], "Raw post")

    def test_agentmail_digest_strips_body_addresses_and_secrets(self):
        payload = build_agentmail_digest_payload(
            [
                {
                    "message_id": "msg_private_1",
                    "timestamp": "2026-05-03T00:00:00Z",
                    "from": "Private Sender <newsletter@example.com>",
                    "to": ["reader@personal.example"],
                    "subject": "OpenAI update for reader@personal.example",
                    "preview": "New model notes. token=supersecret123 and contact reader@personal.example",
                    "text": "FULL PRIVATE BODY SHOULD NOT SHIP",
                    "html": "<p>FULL PRIVATE HTML SHOULD NOT SHIP</p>",
                    "extracted_text": "EXTRACTED BODY SHOULD NOT SHIP",
                    "labels": ["newsletter", "private-client"],
                    "attachments": [{"filename": "deck.pdf"}],
                }
            ],
            generated_at="2026-05-03T01:00:00Z",
            window_hours=24,
        )
        item = payload["items"][0]
        dumped = str(payload)
        self.assertEqual(payload["privacy"], "metadata_only_no_body")
        self.assertEqual(item["sender_domain"], "example.com")
        self.assertIn("[redacted-email]", item["subject"])
        self.assertIn("[redacted-secret]", item["preview"])
        self.assertTrue(item["has_attachments"])
        self.assertNotIn("newsletter@example.com", dumped)
        self.assertNotIn("reader@personal.example", dumped)
        self.assertNotIn("FULL PRIVATE BODY", dumped)
        self.assertNotIn("EXTRACTED BODY", dumped)
        self.assertNotIn("private-client", dumped)

    def test_agentmail_digest_can_filter_single_sender_domain(self):
        payload = build_agentmail_digest_payload(
            [
                {
                    "message_id": "msg_alpha",
                    "timestamp": "2026-05-03T00:00:00Z",
                    "from": "AlphaSignal <daily@mail.alphasignal.ai>",
                    "subject": "AI research digest",
                    "preview": "New papers and repos",
                },
                {
                    "message_id": "msg_other",
                    "timestamp": "2026-05-03T00:00:00Z",
                    "from": "Other Newsletter <news@example.com>",
                    "subject": "Should not be included",
                    "preview": "Noise",
                },
            ],
            generated_at="2026-05-03T01:00:00Z",
            window_hours=24,
            allowed_sender_domains=["alphasignal.ai"],
        )
        self.assertEqual(payload["allowed_sender_domains"], ["alphasignal.ai"])
        self.assertEqual(payload["total_messages"], 1)
        self.assertEqual(payload["items"][0]["sender_domain"], "mail.alphasignal.ai")
        self.assertIn("AI research digest", payload["items"][0]["subject"])

    def test_fetch_agentmail_digest_uses_list_messages_endpoint_only(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "messages": [
                        {
                            "message_id": "msg_2",
                            "timestamp": "2026-05-03T00:00:00Z",
                            "from": "AI Newsletter <news@example.com>",
                            "subject": "Claude ships a new feature",
                            "preview": "Short public-ish preview",
                        }
                    ]
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        payload = fetch_agentmail_digest(
            session,
            api_key="test-key",
            inbox_id="inbox_123",
            generated_at="2026-05-03T01:00:00Z",
            after="2026-05-02T01:00:00Z",
            limit=10,
            base_url="https://api.agentmail.to",
        )
        self.assertEqual(len(session.calls), 1)
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.agentmail.to/v0/inboxes/inbox_123/messages")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["params"]["after"], "2026-05-02T01:00:00Z")
        self.assertNotIn("raw", url)
        self.assertEqual(payload["items"][0]["sender_domain"], "example.com")

    def test_agentmail_default_off_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("AgentMail should stay offline unless explicitly enabled")

        session = NoNetworkSession()
        with patch.dict("os.environ", {}, clear=True):
            payload, status = maybe_fetch_agentmail_digest(
                session,
                generated_at="2026-05-03T01:00:00Z",
                after="2026-05-02T01:00:00Z",
                window_hours=24,
            )
        self.assertIsNone(payload)
        self.assertFalse(status["enabled"])
        self.assertIsNone(status["ok"])
        self.assertEqual(session.calls, 0)

    def test_agentmail_enabled_without_credentials_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("AgentMail should not fetch without full credentials")

        session = NoNetworkSession()
        with patch.dict("os.environ", {"EMAIL_DIGEST_ENABLED": "1"}, clear=True):
            payload, status = maybe_fetch_agentmail_digest(
                session,
                generated_at="2026-05-03T01:00:00Z",
                after="2026-05-02T01:00:00Z",
                window_hours=24,
            )
        self.assertIsNone(payload)
        self.assertTrue(status["enabled"])
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"], "missing_agentmail_credentials")
        self.assertEqual(session.calls, 0)

    def test_x_api_default_off_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("X API should stay offline unless explicitly enabled")

        session = NoNetworkSession()
        with patch.dict("os.environ", {}, clear=True):
            items, status = maybe_fetch_x_api_updates(session, __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"))
        self.assertEqual(items, [])
        self.assertFalse(status["enabled"])
        self.assertEqual(session.calls, 0)

    def test_x_api_default_on_when_token_present(self):
        # Bearer token present, X_API_ENABLED unset -> treated as enabled (token
        # is the switch); outside the daily window it schedules without calling.
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("should wait for the daily window, not call now")

        session = NoNetworkSession()
        env = {"X_BEARER_TOKEN": "test", "X_API_RUN_UTC_HOUR": "0"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_x_api_updates(session, __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"))
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(session.calls, 0)

    def test_x_api_enabled_outside_daily_window_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("X API should wait for its daily run window")

        session = NoNetworkSession()
        env = {"X_API_ENABLED": "1", "X_BEARER_TOKEN": "test", "X_API_RUN_UTC_HOUR": "0"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_x_api_updates(session, __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"))
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(status["skip_reason"], "outside_x_api_daily_window")
        self.assertEqual(session.calls, 0)

    def test_x_api_force_run_maps_recent_search_posts(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "data": [
                        {
                            "id": "12345",
                            "author_id": "u1",
                            "text": "OpenAI ships a useful AI agent update",
                            "created_at": "2026-05-03T00:00:00Z",
                            "lang": "en",
                            "public_metrics": {"like_count": 10},
                        }
                    ],
                    "includes": {"users": [{"id": "u1", "username": "builder"}]},
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        env = {"X_API_ENABLED": "1", "X_BEARER_TOKEN": "test", "X_API_FORCE_RUN": "1", "X_API_MAX_RESULTS": "10"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_x_api_updates(session, __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"))
        self.assertTrue(status["ok"])
        self.assertEqual(status["item_count"], 1)
        self.assertEqual(status["estimated_cost_usd"], 0.005)
        self.assertEqual(items[0].site_id, "xapi")
        self.assertEqual(items[0].source, "@builder")
        self.assertEqual(items[0].url, "https://x.com/builder/status/12345")
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.x.com/2/tweets/search/recent")
        self.assertEqual(kwargs["params"]["max_results"], 10)

    def test_source_tiers_separate_discussion_signals_from_core_sources(self):
        self.assertEqual(source_tier_for_site("official_ai")["source_tier"], "official")
        self.assertEqual(source_tier_for_site("aihot")["source_tier"], "ai_vertical")
        self.assertEqual(source_tier_for_site("curated_media")["source_tier"], "ai_media")
        self.assertEqual(source_tier_for_site("followbuilders")["source_tier"], "builders")
        self.assertEqual(source_tier_for_site("opmlrss:abc123")["source_tier"], "user_opml")
        self.assertEqual(source_tier_for_site("socialdata_x")["source_tier"], "advanced")
        self.assertEqual(source_tier_for_site("tikhub_xiaohongshu")["source_tier"], "self_media")
        self.assertEqual(source_tier_for_site("zeli")["source_tier"], "discussion")
        self.assertEqual(source_tier_for_site("newsnow")["source_tier_label"], "热议参考")

    def test_source_tier_fields_and_sort_put_discussion_after_core_sources(self):
        official = add_source_tier_fields(
            {
                "site_id": "official_ai",
                "site_name": "Official AI Updates",
                "source": "OpenAI News",
                "title": "OpenAI ships a model",
                "url": "https://example.com/openai",
                "published_at": "2026-05-03T00:00:00Z",
            }
        )
        discussion = add_source_tier_fields(
            {
                "site_id": "zeli",
                "site_name": "Zeli",
                "source": "Hacker News · 24h最热",
                "title": "AI tool discussion",
                "url": "https://example.com/hn",
                "published_at": "2026-05-03T01:00:00Z",
            }
        )
        self.assertEqual(official["source_tier_label"], "官方一手源")
        self.assertEqual(discussion["source_tier_label"], "热议参考")
        self.assertLess(source_tier_sort_key(official), source_tier_sort_key(discussion))

    def test_dedupe_prefers_core_source_over_newer_discussion_duplicate(self):
        official = add_source_tier_fields(
            {
                "id": "official",
                "site_id": "official_ai",
                "site_name": "Official AI Updates",
                "source": "OpenAI News",
                "title": "OpenAI ships a model",
                "url": "https://example.com/same",
                "published_at": "2026-05-03T00:00:00Z",
            }
        )
        discussion = add_source_tier_fields(
            {
                "id": "discussion",
                "site_id": "zeli",
                "site_name": "Zeli",
                "source": "Hacker News · 24h最热",
                "title": "OpenAI ships a model",
                "url": "https://example.com/same",
                "published_at": "2026-05-03T01:00:00Z",
            }
        )
        deduped = dedupe_items_by_title_url([discussion, official], random_pick=False)
        self.assertEqual(deduped[0]["id"], "official")

    def test_fetch_ai_hubtoday_parses_rss_feed(self):
        # ai.hubtoday.app moved to hex2077.dev; we now read its RSS feed.
        rss = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel><title>hex2077</title>'
            '<item><title>AI 资讯日报 2026/6/20 多家发布</title>'
            '<link>https://hex2077.dev/docs/2026-06/2026-06-20/</link>'
            '<pubDate>Sat, 20 Jun 2026 00:00:00 GMT</pubDate></item>'
            '<item><title>AI 深度信号周报 W24</title>'
            '<link>https://hex2077.dev/blog/weekly/2026-w24/</link>'
            '<pubDate>Fri, 19 Jun 2026 10:00:00 GMT</pubDate></item>'
            '</channel></rss>'
        ).encode("utf-8")

        class FakeResponse:
            content = rss

            def raise_for_status(self):
                return None

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                return FakeResponse()

        session = FakeSession()
        items = fetch_ai_hubtoday(
            session,
            __import__("datetime").datetime.fromisoformat("2026-06-20T12:00:00+00:00"),
        )
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i.site_id == "aihubtoday" for i in items))
        self.assertEqual(items[0].url, "https://hex2077.dev/docs/2026-06/2026-06-20/")
        self.assertIsNotNone(items[0].published_at)
        self.assertEqual(session.calls[0], "https://hex2077.dev/rss-zh-CN.xml")

    def test_socialdata_default_off_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("SocialData should stay offline unless explicitly enabled")

        session = NoNetworkSession()
        with patch.dict("os.environ", {}, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        self.assertFalse(status["enabled"])
        self.assertEqual(session.calls, 0)

    def test_socialdata_enabled_without_key_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("SocialData should not run without an API key")

        session = NoNetworkSession()
        env = {"SOCIALDATA_ENABLED": "1", "SOCIALDATA_FORCE_RUN": "1"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        # Key-first policy: no key -> not enabled, regardless of ENABLED=1.
        self.assertFalse(status["enabled"])
        self.assertTrue(status["enable_toggle"])
        self.assertFalse(status["api_key_present"])
        self.assertEqual(status["disabled_reason"], "no_api_key")
        self.assertEqual(session.calls, 0)

    def test_socialdata_default_on_when_key_present(self):
        # API key present, ENABLED unset -> treated as enabled (key is the switch).
        # 01:00 is outside the initial run window, so it schedules but does not call.
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("should wait for the run window, not call now")

        session = NoNetworkSession()
        env = {"SOCIALDATA_API_KEY": "test"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(session.calls, 0)

    def test_socialdata_enabled_zero_is_kill_switch(self):
        # Explicit ENABLED=0 hard-stops the source even with a key and FORCE_RUN.
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("ENABLED=0 must hard-stop SocialData")

        session = NoNetworkSession()
        env = {"SOCIALDATA_API_KEY": "test", "SOCIALDATA_ENABLED": "0", "SOCIALDATA_FORCE_RUN": "1"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["enable_toggle"])
        self.assertEqual(status["disabled_reason"], "disabled_by_toggle")
        self.assertEqual(session.calls, 0)

    def test_socialdata_interval_state_skips_without_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("SocialData should not run before the paid-source interval")

        session = NoNetworkSession()
        state = {"sources": {"socialdata": {"last_run_at": "2026-05-03T00:00:00Z"}}}
        env = {
            "SOCIALDATA_ENABLED": "1",
            "SOCIALDATA_API_KEY": "test",
            "SOCIALDATA_RUN_INTERVAL_HOURS": "24",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T12:00:00+00:00"),
                state,
            )
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(status["skip_reason"], "before_socialdata_run_interval")
        self.assertEqual(status["run_interval_hours"], 24)
        self.assertEqual(session.calls, 0)

    def test_socialdata_force_run_maps_search_tweets(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "tweets": [
                        {
                            "id_str": "1734810168053956719",
                            "full_text": "OpenAI ships a useful AI agent update",
                            "tweet_created_at": "2026-05-03T00:00:00.000000Z",
                            "lang": "en",
                            "favorite_count": 42,
                            "user": {"screen_name": "builder"},
                        },
                        {
                            "id_str": "1734810168053956720",
                            "full_text": "Extra item beyond the cap",
                            "tweet_created_at": "2026-05-03T00:01:00.000000Z",
                            "user": {"screen_name": "builder"},
                        },
                    ]
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        env = {
            "SOCIALDATA_ENABLED": "1",
            "SOCIALDATA_API_KEY": "test",
            "SOCIALDATA_FORCE_RUN": "1",
            "SOCIALDATA_MAX_RESULTS": "1",
            "SOCIALDATA_LIST_ENABLED": "0",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertTrue(status["ok"])
        self.assertEqual(status["item_count"], 1)
        # Cost now tracks raw tweet READS (2), not mapped items (1).
        self.assertEqual(status["estimated_cost_usd"], 0.0004)
        self.assertEqual(status["raw_reads"], 2)
        self.assertEqual(status["diagnostics"]["raw_tweet_count"], 2)
        self.assertEqual(status["diagnostics"]["mapped_tweet_count"], 1)
        self.assertEqual(items[0].site_id, "socialdata_x")
        self.assertEqual(items[0].source, "@builder")
        self.assertEqual(items[0].url, "https://x.com/builder/status/1734810168053956719")
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.socialdata.tools/twitter/search")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test")
        self.assertEqual(kwargs["params"]["type"], "Top")

    def test_socialdata_drops_tweets_older_than_recency_window(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "tweets": [
                        {"id_str": "fresh", "full_text": "最新 AI 进展",
                         "tweet_created_at": "2026-05-03T00:00:00.000000Z",
                         "user": {"screen_name": "builder"}},
                        {"id_str": "stale", "full_text": "两周前的 AI 旧闻",
                         "tweet_created_at": "2026-04-20T00:00:00.000000Z",
                         "user": {"screen_name": "builder"}},
                    ]
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        env = {
            "SOCIALDATA_ENABLED": "1",
            "SOCIALDATA_API_KEY": "test",
            "SOCIALDATA_FORCE_RUN": "1",
            "SOCIALDATA_MAX_RESULTS": "10",
            "SOCIALDATA_LIST_ENABLED": "0",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual([item.meta["post_id"] for item in items], ["fresh"])
        self.assertEqual(status["item_count"], 1)
        self.assertEqual(status["recency_days"], 4)
        self.assertEqual(status["skipped_stale_count"], 1)
        # Cost still counts the stale tweet — we paid to READ it before dropping it.
        self.assertEqual(status["raw_reads"], 2)

    def test_socialdata_status_cost_ceiling_includes_list(self):
        env = {"SOCIALDATA_API_KEY": "test"}  # list on by default
        with patch.dict("os.environ", env, clear=True):
            status = socialdata_status_base(
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00")
            )
        # search cap (20) + list cap (50) both counted in the per-run ceiling.
        self.assertEqual(status["search_result_cap"], 20)
        self.assertEqual(status["list_result_cap"], 50)
        self.assertEqual(status["combined_result_cap"], 70)
        self.assertEqual(status["estimated_max_cost_usd_per_run"], round(70 * 0.0002, 4))

    def test_socialdata_paginates_until_result_cap(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                if "cursor" not in kwargs["params"]:
                    return FakeResponse(
                        {
                            "next_cursor": "CURSOR_2",
                            "tweets": [
                                {
                                    "id_str": "1",
                                    "full_text": "AI search result one",
                                    "tweet_created_at": "2026-05-03T00:00:00.000000Z",
                                    "user": {"screen_name": "builder"},
                                },
                                {
                                    "id_str": "2",
                                    "full_text": "AI search result two",
                                    "tweet_created_at": "2026-05-03T00:01:00.000000Z",
                                    "user": {"screen_name": "builder"},
                                },
                            ],
                        }
                    )
                return FakeResponse(
                    {
                        "next_cursor": None,
                        "tweets": [
                            {
                                "id_str": "3",
                                "full_text": "AI search result three",
                                "tweet_created_at": "2026-05-03T00:02:00.000000Z",
                                "user": {"screen_name": "builder"},
                            },
                            {
                                "id_str": "4",
                                "full_text": "Beyond configured cap",
                                "tweet_created_at": "2026-05-03T00:03:00.000000Z",
                                "user": {"screen_name": "builder"},
                            },
                        ],
                    }
                )

        session = FakeSession()
        env = {
            "SOCIALDATA_ENABLED": "1",
            "SOCIALDATA_API_KEY": "test",
            "SOCIALDATA_FORCE_RUN": "1",
            "SOCIALDATA_MAX_RESULTS": "3",
            "SOCIALDATA_DAILY_TWEET_LIMIT": "3",
            "SOCIALDATA_LIST_ENABLED": "0",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )

        self.assertEqual([item.url for item in items], [
            "https://x.com/builder/status/1",
            "https://x.com/builder/status/2",
            "https://x.com/builder/status/3",
        ])
        self.assertEqual(status["item_count"], 3)
        self.assertEqual(status["diagnostics"]["page_count"], 2)
        self.assertEqual(status["diagnostics"]["cursor_request_count"], 1)
        self.assertTrue(status["diagnostics"]["reached_result_cap"])
        self.assertEqual(session.calls[1][1]["params"]["cursor"], "CURSOR_2")

    def test_socialdata_empty_response_records_diagnostics(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"next_cursor": None, "tweets": []}

        class FakeSession:
            def get(self, *args, **kwargs):
                return FakeResponse()

        env = {
            "SOCIALDATA_ENABLED": "1",
            "SOCIALDATA_API_KEY": "test",
            "SOCIALDATA_FORCE_RUN": "1",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_socialdata_updates(
                FakeSession(),
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )

        self.assertEqual(items, [])
        self.assertTrue(status["ok"])
        self.assertEqual(status["item_count"], 0)
        self.assertEqual(status["diagnostics"]["response_top_level_keys"], ["next_cursor", "tweets"])
        self.assertEqual(status["diagnostics"]["empty_reason"], "no_tweets_returned_by_socialdata")

    def test_socialdata_list_filters_noise_and_excludes_owner(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "next_cursor": None,
                    "tweets": [
                        {
                            "id_str": "10",
                            "type": "tweet",
                            "full_text": "First-party AI insight from a member",
                            "tweet_created_at": "2026-05-03T00:00:00.000000Z",
                            "lang": "en",
                            "user": {"screen_name": "karminski3"},
                        },
                        {
                            "id_str": "11",
                            "type": "quote",
                            "full_text": "成员对大模型的中文评论",
                            "tweet_created_at": "2026-05-03T00:01:00.000000Z",
                            "lang": "zh",
                            "user": {"screen_name": "dotey"},
                        },
                        {
                            "id_str": "12",
                            "type": "retweet",
                            "full_text": "RT @someone: not authored by the member",
                            "tweet_created_at": "2026-05-03T00:02:00.000000Z",
                            "user": {"screen_name": "dotey"},
                        },
                        {
                            "id_str": "13",
                            "type": "reply",
                            "full_text": "@x conversational reply noise",
                            "tweet_created_at": "2026-05-03T00:03:00.000000Z",
                            "user": {"screen_name": "vista8"},
                        },
                        {
                            "id_str": "14",
                            "type": "tweet",
                            "full_text": "owner self-promo to drop",
                            "tweet_created_at": "2026-05-03T00:04:00.000000Z",
                            "user": {"screen_name": "aiwarts"},
                        },
                        {
                            "id_str": "15",
                            "type": "tweet",
                            "full_text": "egg-avatar bot spam",
                            "tweet_created_at": "2026-05-03T00:05:00.000000Z",
                            "user": {"screen_name": "spammer", "default_profile_image": True},
                        },
                    ],
                }

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return FakeResponse()

        session = FakeSession()
        items, diagnostics = fetch_socialdata_list_tweets(
            session,
            api_key="test",
            list_id="1695376776867062037",
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            max_results=50,
            exclude_handles={"aiwarts"},
        )

        self.assertEqual([item.source for item in items], ["@karminski3", "@dotey"])
        self.assertTrue(all(item.site_id == "socialdata_x" for item in items))
        self.assertTrue(all(item.meta["via"] == "list" for item in items))
        self.assertEqual(items[0].url, "https://x.com/karminski3/status/10")
        self.assertEqual(diagnostics["mapped_tweet_count"], 2)
        self.assertEqual(diagnostics["skipped"]["retweet_or_reply"], 2)
        self.assertEqual(diagnostics["skipped"]["excluded_author"], 1)
        self.assertEqual(diagnostics["skipped"]["bot_like"], 1)
        url, kwargs = session.calls[0]
        self.assertEqual(
            url, "https://api.socialdata.tools/twitter/list/1695376776867062037/tweets"
        )
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test")

    def test_tikhub_default_off_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should stay offline unless explicitly enabled")

            def post(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should stay offline unless explicitly enabled")

        session = NoNetworkSession()
        with patch.dict("os.environ", {}, clear=True):
            items, status = maybe_fetch_tikhub_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        self.assertFalse(status["enabled"])
        self.assertEqual(session.calls, 0)

    def test_tikhub_enabled_without_key_does_not_request_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should not run without an API key")

            def post(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should not run without an API key")

        session = NoNetworkSession()
        env = {"TIKHUB_ENABLED": "1", "TIKHUB_FORCE_RUN": "1"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_tikhub_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        # Key-first policy: no key -> not enabled, regardless of ENABLED=1.
        self.assertFalse(status["enabled"])
        self.assertTrue(status["enable_toggle"])
        self.assertFalse(status["api_key_present"])
        self.assertEqual(status["disabled_reason"], "no_api_key")
        self.assertEqual(session.calls, 0)

    def test_tikhub_default_on_when_key_present(self):
        # API key present, ENABLED unset -> treated as enabled; outside the run
        # window it schedules without calling the network.
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("should wait for the run window, not call now")

            def post(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("should wait for the run window, not call now")

        session = NoNetworkSession()
        env = {"TIKHUB_API_KEY": "test"}
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_tikhub_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            )
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(session.calls, 0)

    def test_tikhub_interval_state_skips_without_network(self):
        class NoNetworkSession:
            def __init__(self):
                self.calls = 0

            def get(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should not run before the paid-source interval")

            def post(self, *args, **kwargs):
                self.calls += 1
                raise AssertionError("TikHub should not run before the paid-source interval")

        session = NoNetworkSession()
        state = {"sources": {"tikhub": {"last_run_at": "2026-05-03T00:00:00Z"}}}
        env = {
            "TIKHUB_ENABLED": "1",
            "TIKHUB_API_KEY": "test",
            "TIKHUB_RUN_INTERVAL_HOURS": "24",
        }
        with patch.dict("os.environ", env, clear=True):
            items, status = maybe_fetch_tikhub_updates(
                session,
                __import__("datetime").datetime.fromisoformat("2026-05-03T12:00:00+00:00"),
                state,
            )
        self.assertEqual(items, [])
        self.assertTrue(status["enabled"])
        self.assertTrue(status["skipped"])
        self.assertEqual(status["skip_reason"], "before_tikhub_run_interval")
        self.assertEqual(status["run_interval_hours"], 24)
        self.assertEqual(session.calls, 0)

    def test_parse_tikhub_douyin_items(self):
        payload = {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "712345",
                        "desc": "OpenAI 发布新的 AI Agent 工作流",
                        "create_time": 1770000000,
                        "author": {"nickname": "AI观察"},
                        "statistics": {"digg_count": 42},
                    }
                }
            ]
        }
        items = parse_tikhub_douyin_items(
            payload,
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            keyword="AI",
            limit=5,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "tikhub_douyin")
        self.assertEqual(items[0].source, "AI观察")
        self.assertEqual(items[0].url, "https://www.douyin.com/video/712345")
        self.assertEqual(items[0].meta["keyword"], "AI")

    def test_parse_tikhub_douyin_uses_meaningful_fallback_title_and_camel_case_time(self):
        now = __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00")
        created_at = int((now - __import__("datetime").timedelta(days=2)).timestamp())
        payload = {
            "data": [
                {
                    "aweme_info": {
                        "aweme_id": "fallback-title",
                        "desc": "@AI大道创作的原声",
                        "caption": "用 AI 做了一个自动化工作流",
                        "createTime": created_at,
                        "author": {"nickname": "AI创作者"},
                    }
                },
                {
                    "aweme_info": {
                        "aweme_id": "audio-only",
                        "desc": "@AI大道创作的原声",
                        "create_time": created_at,
                        "author": {"nickname": "应被跳过"},
                    }
                },
            ]
        }

        items = parse_tikhub_douyin_items(payload, now=now, keyword="AI", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "用 AI 做了一个自动化工作流")
        self.assertEqual(items[0].published_at, __import__("datetime").datetime.fromtimestamp(created_at, tz=timezone.utc))

    def test_fetch_tikhub_search_drops_posts_older_than_recency_window(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-05-03T01:00:00+00:00")
        recent_ts = int((now - _dt.timedelta(days=2)).timestamp())
        stale_ts = int((now - _dt.timedelta(days=10)).timestamp())
        payload = {
            "data": [
                {"aweme_info": {"aweme_id": "fresh1", "desc": "最新 AI Agent 发布解读",
                                "create_time": recent_ts, "author": {"nickname": "AI观察"},
                                "statistics": {"digg_count": 42}}},
                {"aweme_info": {"aweme_id": "stale1", "desc": "十天前的 AI 大模型视频",
                                "create_time": stale_ts, "author": {"nickname": "AI观察"},
                                "statistics": {"digg_count": 10}}},
            ]
        }

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        class FakeSession:
            def __init__(self):
                self.calls = 0

            def post(self, url, **kwargs):
                self.calls += 1
                return FakeResponse()

        session = FakeSession()
        items, diagnostics = fetch_tikhub_search(
            session, api_key="test", query="AI", now=now, max_results=10, platforms=["douyin"]
        )
        self.assertEqual(len(items), 1)
        self.assertIn("fresh1", items[0].url)
        self.assertEqual(diagnostics["recency_days"], 7)
        self.assertEqual(diagnostics["skipped_stale_count"], 1)

    def test_parse_tikhub_xiaohongshu_items(self):
        payload = {
            "data": {
                "items": [
                    {
                        "id": "69f53e8000000000180190e6",
                        "note_card": {
                            "display_title": "Claude Code 实测：AI 编程代理",
                            "user": {"nickname": "工具研究员"},
                            "interact_info": {
                                "liked_count": "99",
                                "comments_count": "7",
                                "collected_count": "31",
                                "shared_count": "12",
                            },
                        },
                    }
                ]
            }
        }
        items = parse_tikhub_xiaohongshu_items(
            payload,
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            keyword="AI工具",
            limit=5,
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "tikhub_xiaohongshu")
        self.assertEqual(items[0].source, "工具研究员")
        self.assertEqual(items[0].url, "https://www.xiaohongshu.com/explore/69f53e8000000000180190e6")
        self.assertEqual(items[0].meta["post_id"], "69f53e8000000000180190e6")
        self.assertEqual(
            items[0].meta["creator_metrics"],
            {"likes": 99, "comments": 7, "collects": 31, "shares": 12},
        )
        self.assertEqual(
            items[0].published_at,
            __import__("datetime").datetime.fromtimestamp(int("69f53e80", 16), tz=timezone.utc),
        )

    def test_parse_tikhub_xiaohongshu_accepts_camel_case_publish_time(self):
        now = __import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00")
        created_at = int((now - __import__("datetime").timedelta(days=2)).timestamp())
        payload = {
            "data": {
                "items": [
                    {
                        "id": "xhs-camel-time",
                        "note_card": {
                            "display_title": "AI 编程工作流实测",
                            "createTime": created_at,
                            "user": {"nickname": "时间字段测试"},
                        },
                    }
                ]
            }
        }

        items = parse_tikhub_xiaohongshu_items(payload, now=now, keyword="AI", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, __import__("datetime").datetime.fromtimestamp(created_at, tz=timezone.utc))

    def test_parse_tikhub_xiaohongshu_ignores_zero_api_time_and_uses_note_id(self):
        now = __import__("datetime").datetime.fromisoformat("2026-06-22T01:30:00+00:00")
        note_id = "6a388dd1000000001503c7b5"
        payload = {
            "data": {
                "items": [
                    {
                        "id": note_id,
                        "desc": "今日 AI 大事件",
                        "last_update_time": 0,
                        "user": {"nickname": "AI观察"},
                    }
                ]
            }
        }

        items = parse_tikhub_xiaohongshu_items(payload, now=now, keyword="AI", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0].published_at,
            __import__("datetime").datetime.fromtimestamp(int(note_id[:8], 16), tz=timezone.utc),
        )

    def test_creator_hot_ranking_keeps_heat_primary_and_adds_24h_bonus(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-22T01:30:00+00:00")
        hot_week_item = add_creator_ranking_fields(
            {
                "site_id": "tikhub_xiaohongshu",
                "published_at": (now - _dt.timedelta(days=3)).isoformat(),
                "creator_metrics": {"likes": 2800, "comments": 70, "collects": 3600, "shares": 1400},
            },
            now,
        )
        fresh_low_item = add_creator_ranking_fields(
            {
                "site_id": "tikhub_xiaohongshu",
                "published_at": (now - _dt.timedelta(hours=1)).isoformat(),
                "creator_metrics": {"likes": 2, "comments": 0, "collects": 0, "shares": 0},
            },
            now,
        )

        self.assertEqual(hot_week_item["creator_freshness_bonus"], 0)
        self.assertEqual(fresh_low_item["creator_freshness_bonus"], 15)
        self.assertGreater(hot_week_item["creator_hot_score"], fresh_low_item["creator_hot_score"])

    def test_build_creator_hot_items_uses_seven_day_window_and_hot_score_order(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-22T01:30:00+00:00")

        def record(item_id, age, likes):
            return {
                "id": item_id,
                "site_id": "tikhub_xiaohongshu",
                "site_name": "TikHub Xiaohongshu",
                "source": "AI作者",
                "title": f"OpenAI 热门内容 {item_id}",
                "url": f"https://example.com/{item_id}",
                "published_at": (now - age).isoformat(),
                "first_seen_at": now.isoformat(),
                "last_seen_at": now.isoformat(),
                "creator_metrics": {"likes": likes, "comments": 0, "collects": 0, "shares": 0},
            }

        archive = {
            "week-hot": record("week-hot", _dt.timedelta(days=3), 2000),
            "fresh-low": record("fresh-low", _dt.timedelta(hours=1), 2),
            "stale": record("stale", _dt.timedelta(days=8), 99999),
        }

        items = build_creator_hot_items(archive, now, ai_only=True)

        self.assertEqual([item["id"] for item in items], ["week-hot", "fresh-low"])
        self.assertGreater(items[0]["creator_hot_score"], items[1]["creator_hot_score"])

    def test_parse_tikhub_xiaohongshu_accepts_millisecond_api_time(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-22T01:30:00+00:00")
        published = now - _dt.timedelta(hours=2)
        payload = {
            "data": {
                "items": [
                    {
                        "id": "67934b0c00000000180190e6",
                        "desc": "毫秒时间的 AI 笔记",
                        "create_time": int(published.timestamp() * 1000),
                        "user": {"nickname": "毫秒时间作者"},
                    }
                ]
            }
        }

        items = parse_tikhub_xiaohongshu_items(payload, now=now, keyword="AI", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, published)

    def test_parse_tikhub_xiaohongshu_rejects_future_api_time_and_uses_note_id(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-22T01:30:00+00:00")
        note_time = now - _dt.timedelta(hours=1)
        note_id = f"{int(note_time.timestamp()):x}00000000180190e6"
        payload = {
            "data": {
                "items": [
                    {
                        "id": note_id,
                        "desc": "未来 API 时间应回退 note_id",
                        "create_time": int((now + _dt.timedelta(minutes=1)).timestamp()),
                        "user": {"nickname": "未来时间作者"},
                    }
                ]
            }
        }

        items = parse_tikhub_xiaohongshu_items(payload, now=now, keyword="AI", limit=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, note_time)

    def test_fetch_tikhub_xiaohongshu_enforces_exact_seven_day_boundary(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-22T01:30:00+00:00")
        cutoff = now - _dt.timedelta(days=7)
        boundary_note_id = f"{int(cutoff.timestamp()):x}00000000180190e6"
        stale_note_id = f"{int((cutoff - _dt.timedelta(seconds=1)).timestamp()):x}00000000180190e6"

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def get(self, url, **kwargs):
                if "/web_v3/fetch_search_notes" in url:
                    return FakeResponse({"data": {"items": []}})
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {"id": stale_note_id, "desc": "超过七天一秒", "user": {"nickname": "旧帖"}},
                                {"id": "not-a-timestamp", "desc": "无法确认时间", "user": {"nickname": "未知时间"}},
                                {"id": boundary_note_id, "desc": "恰好七天", "user": {"nickname": "边界帖"}},
                            ]
                        }
                    }
                )

        items, diagnostics = fetch_tikhub_search(
            FakeSession(),
            api_key="test",
            query="AI",
            now=now,
            max_results=10,
            platforms=["xiaohongshu"],
        )

        self.assertEqual([item.meta["post_id"] for item in items], [boundary_note_id])
        self.assertEqual(items[0].published_at, cutoff)
        self.assertEqual(diagnostics["skipped_stale_count"], 1)
        self.assertEqual(diagnostics["skipped_missing_published_at_count"], 1)

    def test_fetch_tikhub_xiaohongshu_drops_old_note_id_when_api_time_missing(self):
        import datetime as _dt

        now = _dt.datetime.fromisoformat("2026-06-21T16:00:00+00:00")
        recent_ts = int((now - _dt.timedelta(days=1)).timestamp())
        recent_note_id = f"{recent_ts:x}00000000180190e6"
        old_note_id = "67934b0c00000000180190e6"
        future_ts = int((now + _dt.timedelta(seconds=1)).timestamp())
        future_note_id = f"{future_ts:x}00000000180190e6"

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def get(self, url, **kwargs):
                if "/web_v3/fetch_search_notes" in url:
                    return FakeResponse({"data": {"items": []}})
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "id": old_note_id,
                                    "note_card": {
                                        "display_title": "一月旧 AI 大模型合集",
                                        "user": {"nickname": "旧帖作者"},
                                    },
                                },
                                {
                                    "id": future_note_id,
                                    "note_card": {
                                        "display_title": "未来时间的 AI 笔记",
                                        "user": {"nickname": "异常时间作者"},
                                    },
                                },
                                {
                                    "id": recent_note_id,
                                    "note_card": {
                                        "display_title": "今天的 AI Agent 笔记",
                                        "user": {"nickname": "小红书AI"},
                                    },
                                },
                            ]
                        }
                    }
                )

        items, diagnostics = fetch_tikhub_search(
            FakeSession(),
            api_key="test",
            query="AI",
            now=now,
            max_results=1,
            platforms=["xiaohongshu"],
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].meta["post_id"], recent_note_id)
        self.assertEqual(items[0].published_at, _dt.datetime.fromtimestamp(recent_ts, tz=timezone.utc))
        self.assertEqual(diagnostics["skipped_stale_count"], 1)
        self.assertEqual(diagnostics["skipped_missing_published_at_count"], 1)

    def test_fetch_tikhub_search_calls_both_platforms(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def post(self, url, **kwargs):
                self.calls.append(("POST", url, kwargs))
                return FakeResponse(
                    {
                        "data": [
                            {
                                "aweme_info": {
                                    "aweme_id": "douyin1",
                                    "desc": "OpenAI Agent 发布",
                                    "author": {"nickname": "抖音AI"},
                                }
                            }
                        ]
                    }
                )

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                if "/web_v3/fetch_search_notes" in url:
                    return FakeResponse(
                        {
                            "data": {
                                "items": [
                                    {
                                        "id": "69f53e8100000000180190e6",
                                        "note_card": {
                                            "display_title": "Web 端 AI 工具更新",
                                            "user": {"nickname": "小红书Web"},
                                        },
                                    }
                                ]
                            }
                        }
                    )
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "id": "69f53e8000000000180190e6",
                                    "note_card": {
                                        "display_title": "大模型工具更新",
                                        "user": {"nickname": "小红书AI"},
                                    },
                                }
                            ]
                        }
                    }
                )

        session = FakeSession()
        items, diagnostics = fetch_tikhub_search(
            session,
            api_key="test",
            query="AI",
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            max_results=4,
            platforms=["douyin", "xiaohongshu"],
        )
        self.assertEqual([item.site_id for item in items], ["tikhub_douyin", "tikhub_xiaohongshu", "tikhub_xiaohongshu"])
        self.assertEqual([item.meta["search_surface"] for item in items], [
            "douyin_general_v2",
            "xiaohongshu_app_v2",
            "xiaohongshu_web_v3",
        ])
        self.assertEqual([call[0] for call in session.calls], ["POST", "GET", "GET"])
        self.assertEqual(session.calls[0][2]["json"]["sort_type"], "1")
        self.assertEqual(session.calls[0][2]["json"]["publish_time"], "7")
        self.assertIn("/api/v1/xiaohongshu/app_v2/search_notes", session.calls[1][1])
        self.assertEqual(session.calls[1][2]["params"]["sort_type"], "popularity_descending")
        self.assertEqual(session.calls[1][2]["params"]["time_filter"], "一周内")
        self.assertIn("/api/v1/xiaohongshu/web_v3/fetch_search_notes", session.calls[2][1])
        self.assertEqual(session.calls[2][2]["params"]["sort"], "popularity_descending")
        self.assertEqual(diagnostics["mapped_item_count"], 3)

    def test_fetch_tikhub_search_falls_back_to_xiaohongshu_web_v3(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                if "/app_v2/search_notes" in url:
                    return FakeResponse({"data": {"items": []}})
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "id": "69f53e8200000000180190e6",
                                    "note_card": {
                                        "display_title": "AI 工作流笔记",
                                        "user": {"nickname": "Web V3 用户"},
                                    },
                                }
                            ]
                        }
                    }
                )

        session = FakeSession()
        items, diagnostics = fetch_tikhub_search(
            session,
            api_key="test",
            query="AI",
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            max_results=1,
            platforms=["xiaohongshu"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].site_id, "tikhub_xiaohongshu")
        self.assertEqual([call[1] for call in session.calls], [
            "https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes",
            "https://api.tikhub.io/api/v1/xiaohongshu/web_v3/fetch_search_notes",
        ])
        self.assertEqual(diagnostics["requests"][0]["fallback_reason"], "no_items_mapped_try_web_v3")

    def test_fetch_tikhub_search_dedupes_xiaohongshu_app_and_web_results(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(("GET", url, kwargs))
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "id": "69f53e8300000000180190e6",
                                    "note_card": {
                                        "display_title": "同一条 AI 笔记",
                                        "user": {"nickname": "同一作者"},
                                    },
                                }
                            ]
                        }
                    }
                )

        session = FakeSession()
        items, diagnostics = fetch_tikhub_search(
            session,
            api_key="test",
            query="AI",
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            max_results=4,
            platforms=["xiaohongshu"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual([call[1] for call in session.calls], [
            "https://api.tikhub.io/api/v1/xiaohongshu/app_v2/search_notes",
            "https://api.tikhub.io/api/v1/xiaohongshu/web_v3/fetch_search_notes",
        ])
        self.assertEqual(diagnostics["requests"][0]["appended_item_count"], 1)
        self.assertEqual(diagnostics["requests"][1]["mapped_item_count"], 1)
        self.assertEqual(diagnostics["requests"][1]["appended_item_count"], 0)

    def test_fetch_tikhub_search_keeps_app_results_when_web_surface_fails(self):
        class FakeResponse:
            def __init__(self, payload=None, status_code=200):
                self.payload = payload or {}
                self.status_code = status_code

            def raise_for_status(self):
                if self.status_code >= 400:
                    import requests

                    raise requests.HTTPError(f"{self.status_code} error", response=self)
                return None

            def json(self):
                return self.payload

        class FakeSession:
            def get(self, url, **kwargs):
                if "/web_v3/fetch_search_notes" in url:
                    return FakeResponse(status_code=400)
                return FakeResponse(
                    {
                        "data": {
                            "items": [
                                {
                                    "id": "69f53e8400000000180190e6",
                                    "note_card": {
                                        "display_title": "App 端 AI 笔记",
                                        "user": {"nickname": "App 用户"},
                                    },
                                }
                            ]
                        }
                    }
                )

        items, diagnostics = fetch_tikhub_search(
            FakeSession(),
            api_key="test",
            query="AI",
            now=__import__("datetime").datetime.fromisoformat("2026-05-03T01:00:00+00:00"),
            max_results=4,
            platforms=["xiaohongshu"],
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].meta["search_surface"], "xiaohongshu_app_v2")
        self.assertEqual(diagnostics["successful_request_count"], 1)
        self.assertEqual(diagnostics["request_error_count"], 1)
        self.assertEqual(diagnostics["requests"][1]["surface"], "xiaohongshu_web_v3")
        self.assertEqual(diagnostics["requests"][1]["status_code"], 400)


if __name__ == "__main__":
    unittest.main()
