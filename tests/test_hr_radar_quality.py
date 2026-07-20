import unittest
from datetime import datetime, timezone

from scripts.probe_hr_radar_quality import (
    CandidateItem,
    classify_item,
    evaluate_item,
    matches_term,
    parse_html_content,
)


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def make_item(title: str, authority: str = "industry_media") -> CandidateItem:
    return CandidateItem(
        source_id="test",
        source_name="Test",
        source_url="https://example.com/feed",
        source_type="rss",
        authority=authority,
        region="测试",
        title=title,
        url="https://example.com/item",
        published_at=NOW,
    )


class HrRadarRelevanceTests(unittest.TestCase):
    def test_pure_ai_news_is_rejected(self):
        result = evaluate_item(make_item("OpenAI releases a new video model"))
        self.assertFalse(result["kept"])
        self.assertEqual(result["reason"], "missing_hr_signal")

    def test_training_and_model_substrings_do_not_create_hr_signal(self):
        result = evaluate_item(make_item("A practical guide to training image models"))
        self.assertFalse(result["kept"])
        self.assertFalse(matches_term("training", "ai"))

    def test_ai_recruiting_crossover_is_retained_and_classified(self):
        item = make_item("AI招聘系统升级：简历筛选增加人工复核")
        result = evaluate_item(item)
        self.assertTrue(result["kept"])
        self.assertEqual(result["category"], "AI 招聘与招聘工具")

    def test_official_policy_listing_does_not_require_title_keyword(self):
        item = make_item("北京市调整工伤保险费率政策", authority="official_policy")
        result = evaluate_item(item)
        self.assertTrue(result["kept"])
        self.assertEqual(result["reason"], "official_policy_listing")
        self.assertEqual(result["category"], "政策与劳动合规")

    def test_official_hr_news_rejects_generic_employment_activity(self):
        item = make_item("江西南昌：50余场夏季夜市招聘会来了", authority="official_hr_news")
        result = evaluate_item(item)
        self.assertFalse(result["kept"])
        self.assertEqual(result["reason"], "missing_policy_or_ai_signal")

    def test_official_hr_news_keeps_policy_or_ai_signal(self):
        policy = evaluate_item(make_item("推动养老保险制度优化的规划解读", authority="official_hr_news"))
        crossover = evaluate_item(make_item("人工智能+就业服务探索", authority="official_hr_news"))
        self.assertTrue(policy["kept"])
        self.assertTrue(crossover["kept"])

    def test_generic_candidate_word_does_not_create_hr_signal(self):
        result = evaluate_item(make_item("AI predicts the election candidate most likely to win"))
        self.assertFalse(result["kept"])

    def test_marketing_risk_is_visible_but_not_silently_dropped(self):
        result = evaluate_item(make_item("AI招聘系统选型指南：2026年厂商TOP榜"))
        self.assertTrue(result["kept"])
        self.assertTrue(result["marketing_risk"])
        self.assertIn("厂商", result["marketing_signals"])

    def test_vendor_source_is_always_marked_as_marketing_risk(self):
        result = evaluate_item(make_item("AI招聘如何改变简历筛选", authority="vendor"))
        self.assertTrue(result["kept"])
        self.assertTrue(result["marketing_risk"])
        self.assertIn("vendor_source", result["marketing_signals"])

    def test_product_category_is_below_ai_recruiting_priority(self):
        self.assertEqual(
            classify_item("Moka AI招聘系统升级", "vendor"),
            "AI 招聘与招聘工具",
        )

    def test_chinese_hr_system_is_an_hr_signal(self):
        result = evaluate_item(make_item("人资系统中可用 AI 的地方比想象中更多", authority="vendor"))
        self.assertTrue(result["kept"])
        self.assertEqual(result["category"], "HR 产品与数字化")


class HrRadarParserTests(unittest.TestCase):
    def test_html_parser_reports_missing_timestamp_without_using_now(self):
        source = {
            "id": "example",
            "name": "Example",
            "type": "html",
            "url": "https://example.com/list/",
            "region": "全国",
            "authority": "official_policy",
            "item_selector": "li",
            "title_selector": "a[href]",
            "date_selector": "time",
        }
        html = """
        <ul>
          <li><a href="/dated">就业政策更新</a><time>2026-07-19</time></li>
          <li><a href="/missing">劳动关系政策</a></li>
        </ul>
        """
        items, seen, missing = parse_html_content(source, html)
        self.assertEqual(seen, 2)
        self.assertEqual(missing, 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.com/dated")
        self.assertEqual(items[0].timestamp_quality, "explicit")


if __name__ == "__main__":
    unittest.main()
