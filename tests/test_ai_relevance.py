import unittest

from scripts.ai_relevance import add_ai_relevance_fields, is_ai_related_record, score_ai_relevance


class AiRelevanceScoringTests(unittest.TestCase):
    def test_scores_strong_ai_signal_with_reason(self):
        rec = {
            "site_id": "techurls",
            "site_name": "TechURLs",
            "source": "Hacker News",
            "title": "OpenAI releases new GPT model",
            "url": "https://example.com/ai",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["label"], "model_release")
        self.assertIn("openai", result["signals"])
        self.assertIn("matched_ai_signal", result["reason"])

    def test_rejects_broad_model_without_tech_context(self):
        rec = {
            "site_id": "buzzing",
            "site_name": "Buzzing",
            "source": "general",
            "title": "这个商业模型终于跑通了",
            "url": "https://example.com/model",
        }
        result = score_ai_relevance(rec)
        self.assertFalse(result["is_ai_related"])
        self.assertLess(result["score"], 0.65)
        self.assertEqual(result["reason"], "missing_meaningful_ai_signal")

    def test_accepts_broad_ai_plus_tech_context(self):
        rec = {
            "site_id": "techurls",
            "site_name": "TechURLs",
            "source": "GitHub",
            "title": "开源推理框架支持更多GPU后端",
            "url": "https://example.com/inference-gpu",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["reason"], "matched_broad_ai_plus_tech_signal")
        self.assertIn("gpu", result["signals"])

    def test_accepts_agent_context_as_developer_tool(self):
        rec = {
            "site_id": "opmlrss",
            "site_name": "OPML RSS",
            "source": "BestBlogs.dev",
            "title": "分层记忆：Agent 中的上下文管理",
            "url": "https://example.com/agent-context",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["label"], "agent_workflow")

    def test_zeli_hotlist_uses_the_normal_ai_signal_gate(self):
        rec = {
            "site_id": "zeli",
            "site_name": "Zeli",
            "source": "Hacker News · 24h最热",
            "title": "Grok CLI uploaded the whole home directory to GCS",
            "url": "https://example.com/grok-cli",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertEqual(result["reason"], "matched_ai_signal")

        unrelated = dict(rec, title="An Infuriating Goodbye to Photoshop")
        unrelated_result = score_ai_relevance(unrelated)
        self.assertFalse(unrelated_result["is_ai_related"])
        self.assertEqual(unrelated_result["reason"], "missing_meaningful_ai_signal")

    def test_ascii_ai_keywords_do_not_match_inside_unrelated_words(self):
        precursor = {
            "site_id": "newsnow",
            "site_name": "NewsNow",
            "source": "Hacker News",
            "title": "Precursor",
            "url": "https://news.ycombinator.com/item?id=1",
        }
        self.assertFalse(score_ai_relevance(precursor)["is_ai_related"])

        cursor = dict(precursor, title="Cursor ships a new coding agent")
        self.assertTrue(score_ai_relevance(cursor)["is_ai_related"])

    def test_ai_domain_alone_is_not_a_relevance_signal(self):
        rec = {
            "site_id": "zeli",
            "site_name": "Zeli",
            "source": "Hacker News · 24h最热",
            "title": "Against Usefulness",
            "url": "https://example.ai/against-usefulness",
        }
        self.assertFalse(score_ai_relevance(rec)["is_ai_related"])

    def test_trusted_ai_source_defaults_to_keep(self):
        rec = {
            "site_id": "aihot",
            "site_name": "AI HOT",
            "source": "AI HOT",
            "title": "今日值得关注的产品更新",
            "url": "https://aihot.virxact.com/post/1",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertGreaterEqual(result["score"], 0.65)
        self.assertEqual(result["reason"], "trusted_ai_source_default_keep")

    def test_rejects_explicit_adult_promotion_even_with_ai_keyword(self):
        rec = {
            "site_id": "socialdata_x",
            "site_name": "SocialData X",
            "source": "@spam_account",
            "title": "AI virtual girlfriends with uncensored pictures and explicit promotion",
            "url": "https://x.com/spam_account/status/1",
        }
        result = score_ai_relevance(rec)
        self.assertFalse(result["is_ai_related"])
        self.assertEqual(result["reason"], "unsafe_promotional_content")

    def test_keeps_neutral_safety_news_with_single_adult_term(self):
        rec = {
            "site_id": "techurls",
            "site_name": "TechURLs",
            "source": "AI policy",
            "title": "OpenAI publishes a safety policy for detecting AI-generated pornography",
            "url": "https://example.com/ai-safety-policy",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])

    def test_curated_media_keeps_trusted_ai_feed(self):
        rec = {
            "site_id": "curated_media",
            "site_name": "Curated Media",
            "source": "TechCrunch AI",
            "title": "Startup raises funding for enterprise workflow automation",
            "url": "https://techcrunch.com/example",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertEqual(result["reason"], "curated_media_source_filter")
        self.assertEqual(result["label"], "industry_business")

    def test_curated_general_feed_requires_title_signal(self):
        rec = {
            "site_id": "curated_media",
            "site_name": "Curated Media",
            "source": "The Verge",
            "title": "A new phone accessory launches this week",
            "url": "https://www.theverge.com/example",
        }
        result = score_ai_relevance(rec)
        self.assertFalse(result["is_ai_related"])
        self.assertEqual(result["reason"], "curated_media_requires_ai_title_or_trusted_ai_feed")

    def test_curated_research_feed_is_research_labeled_and_capped(self):
        rec = {
            "site_id": "curated_media",
            "site_name": "Curated Media",
            "source": "MarkTechPost Research",
            "title": "A new benchmark evaluates multimodal LLM reasoning",
            "url": "https://www.marktechpost.com/example",
        }
        result = score_ai_relevance(rec)
        self.assertTrue(result["is_ai_related"])
        self.assertEqual(result["label"], "research_paper")
        self.assertLessEqual(result["score"], 0.76)

    def test_adds_public_debug_fields(self):
        rec = {
            "site_id": "official_ai",
            "site_name": "Official AI Updates",
            "source": "GitHub Changelog",
            "title": "GitHub Copilot adds a coding agent",
            "url": "https://example.com/copilot-agent",
        }
        out = add_ai_relevance_fields(rec)
        self.assertTrue(out["ai_is_related"])
        self.assertIn("ai_score", out)
        self.assertIn("ai_label", out)
        self.assertIn("ai_relevance_reason", out)
        self.assertIn("ai_signals", out)
        self.assertTrue(is_ai_related_record(rec))


if __name__ == "__main__":
    unittest.main()
