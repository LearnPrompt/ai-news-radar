#!/usr/bin/env python3
"""
HR × AI 资讯台 - 抓取与处理脚本
基于原项目思路，但独立运行，只处理 HR 相关资讯
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import feedparser

# 读取配置文件
CONFIG_PATH = Path("config/hr_sources.json")
OUTPUT_DIR = Path("data")
OUTPUT_PATH = OUTPUT_DIR / "hr-radar.json"

# HR 关键词库（按栏目分类）
HR_KEYWORDS = {
    "policy": [
        "劳动合同", "劳动关系", "劳动争议", "社保", "公积金", "最低工资",
        "工时", "加班", "休假", "招聘", "就业", "人才引进", "职业技能",
        "培训补贴", "裁员", "竞业限制", "劳务派遣", "灵活用工", "外包",
        "个人信息", "员工数据", "员工监控", "算法", "生成式AI", "自动化决策",
        "劳动", "劳动法", "合规", "用工", "工资", "薪酬", "福利",
        "social security", "labor law", "employment", "compliance",
        "workforce", "payroll", "benefits"
    ],
    "ai_recruiting": [
        "AI招聘", "智能招聘", "AI面试", "简历筛选", "人才画像",
        "招聘自动化", "ATS", "候选人", "AI recruiting", "AI hiring",
        "resume screening", "talent acquisition", "interview"
    ],
    "org_talent": [
        "组织", "人才", "绩效", "人才盘点", "组织设计", "HRBP",
        "员工体验", "People Analytics", "组织发展", "OD", "Talent",
        "organization", "performance", "talent management"
    ],
    "learning": [
        "AI培训", "学习发展", "技能转型", "企业培训", "岗位技能",
        "人才培养", "L&D", "learning", "upskilling", "training"
    ],
    "hr_product": [
        "HR SaaS", "飞书", "钉钉", "北森", "Moka", "Workday",
        "SAP", "人力资源系统", "数字化", "HR tech", "HRIS",
        "SaaS", "software", "platform"
    ],
    "cases": [
        "案例", "报告", "趋势", "研究", "调研", "白皮书",
        "report", "trend", "study", "research", "case study"
    ]
}

# AI 相关关键词（用于交叉判断）
AI_KEYWORDS = [
    "AI", "人工智能", "大模型", "LLM", "生成式", "GenAI", "Agent",
    "智能体", "算法", "自动化", "机器学习", "深度学习", "数字化",
    "artificial intelligence", "machine learning", "automation",
    "generative AI", "large language model"
]

# 噪音排除（看到这些词的内容不要）
NOISE_KEYWORDS = [
    "娱乐", "明星", "八卦", "体育", "彩票", "旅游", "美食",
    "游戏", "影视", "股票", "炒股", "crypto", "bitcoin"
]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_rss(source: dict) -> list[dict]:
    """抓取 RSS 来源"""
    url = source.get("url", "")
    if not url:
        return []
    
    items = []
    try:
        parsed = feedparser.parse(url)
        for entry in parsed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            
            if not title or not link:
                continue
            
            # 解析时间
            parsed_time = None
            if published:
                try:
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        parsed_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        parsed_time = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            
            if not parsed_time:
                parsed_time = datetime.now(timezone.utc)
            
            items.append({
                "title": title,
                "url": link,
                "published_at": parsed_time.isoformat(),
                "source_id": source.get("id", "unknown"),
                "source_name": source.get("name", "Unknown"),
                "source_region": source.get("region", "未知"),
                "source_level": source.get("level", "一般")
            })
    except Exception as e:
        print(f"抓取失败 {source.get('name')}: {e}")
    
    return items


def classify_item(title: str) -> str | None:
    """基于标题关键词分类到 6 个栏目之一"""
    t = title.lower()
    
    # 1. 政策与劳动合规（最高优先级）
    if any(kw.lower() in t for kw in HR_KEYWORDS["policy"]):
        return "政策与劳动合规"
    
    # 2. AI 招聘
    if any(kw.lower() in t for kw in HR_KEYWORDS["ai_recruiting"]):
        return "AI 招聘与招聘工具"
    
    # 3. 组织与人才
    if any(kw.lower() in t for kw in HR_KEYWORDS["org_talent"]):
        return "组织与人才管理"
    
    # 4. 学习发展
    if any(kw.lower() in t for kw in HR_KEYWORDS["learning"]):
        return "学习发展与技能转型"
    
    # 5. HR 产品
    if any(kw.lower() in t for kw in HR_KEYWORDS["hr_product"]):
        return "HR 产品与数字化"
    
    # 6. 案例报告
    if any(kw.lower() in t for kw in HR_KEYWORDS["cases"]):
        return "案例、报告与趋势"
    
    return None


def is_hr_relevant(title: str) -> bool:
    """判断是否 HR 相关"""
    t = title.lower()
    
    # 排除噪音
    for noise in NOISE_KEYWORDS:
        if noise.lower() in t:
            return False
    
    # 只要有 HR 或 AI 相关关键词，就保留
    all_hr = []
    for kw_list in HR_KEYWORDS.values():
        all_hr.extend(kw_list)
    
    has_hr = any(kw.lower() in t for kw in all_hr)
    has_ai = any(kw.lower() in t for kw in AI_KEYWORDS)
    
    return has_hr or has_ai


def is_ai_hr_crossover(title: str) -> bool:
    """判断是否 AI × HR 交叉内容"""
    t = title.lower()
    all_hr = []
    for kw_list in HR_KEYWORDS.values():
        all_hr.extend(kw_list)
    has_hr = any(kw.lower() in t for kw in all_hr)
    has_ai = any(kw.lower() in t for kw in AI_KEYWORDS)
    return has_hr and has_ai


def dedupe_items(items: list[dict]) -> list[dict]:
    """基于 URL 和标题去重"""
    seen_urls = set()
    seen_titles = set()
    result = []
    
    for item in items:
        url = item.get("url", "")
        title = item.get("title", "")
        
        if url in seen_urls:
            continue
        seen_urls.add(url)
        
        title_norm = title.strip().lower()
        if title_norm in seen_titles:
            continue
        seen_titles.add(title_norm)
        
        result.append(item)
    
    return result


def main():
    print("=" * 40)
    print("HR × AI 资讯台 - 更新脚本")
    print("=" * 40)
    
    config = load_config()
    categories = config.get("categories", [])
    
    # 读取配置中的 sources，如果为空则使用内置测试源
    sources = config.get("sources", [])
    if not sources:
        print("配置中 sources 为空，使用内置测试源...")
        sources = [
            {
                "id": "hr_dive",
                "name": "HR Dive",
                "type": "rss",
                "url": "https://www.hrdive.com/feeds/news/",
                "region": "全球",
                "level": "行业媒体",
                "default_category": "HR 产品与数字化",
                "enabled": True
            },
            {
                "id": "people_mgmt",
                "name": "People Management",
                "type": "rss",
                "url": "https://www.peoplemanagement.co.uk/rss",
                "region": "全球",
                "level": "行业媒体",
                "default_category": "组织与人才管理",
                "enabled": True
            },
            {
                "id": "hbr_manage",
                "name": "HBR Managing People",
                "type": "rss",
                "url": "https://hbr.org/rss/topic/managing-people",
                "region": "全球",
                "level": "权威媒体",
                "default_category": "案例、报告与趋势",
                "enabled": True
            }
        ]
    
    all_items = []
    for source in sources:
        if not source.get("enabled", True):
            continue
        print(f"正在抓取: {source['name']} ...")
        items = fetch_rss(source)
        print(f"  获取 {len(items)} 条")
        all_items.extend(items)
    
    print(f"\n总计抓取: {len(all_items)} 条原始资讯")
    
    # 筛选与分类
    processed = []
    for item in all_items:
        title = item.get("title", "")
        if not is_hr_relevant(title):
            continue
        
        category = classify_item(title)
        if not category:
            category = item.get("default_category", "案例、报告与趋势")
        
        item["is_ai_hr"] = is_ai_hr_crossover(title)
        item["category"] = category
        
        # 生成唯一 ID
        uid = hashlib.md5(f"{item['url']}{item['title']}".encode()).hexdigest()[:12]
        item["id"] = uid
        
        processed.append(item)
    
    print(f"HR 相关筛选后: {len(processed)} 条")
    
    # 去重
    processed = dedupe_items(processed)
    print(f"去重后: {len(processed)} 条")
    
    # 按时间倒序
    processed.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    
    # 取每日上限
    limit = config.get("daily_pick_limit", 12)
    final_items = processed[:limit]
    
    # 按栏目分组
    categorized = {cat: [] for cat in categories}
    for item in final_items:
        cat = item.get("category", "案例、报告与趋势")
        if cat in categorized:
            categorized[cat].append(item)
    
    # 生成输出
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    output = {
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "name": config.get("name", "HR × AI 资讯台"),
        "total_count": len(final_items),
        "categories": categories,
        "items_by_category": categorized,
        "all_items": final_items
    }
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n已生成: {OUTPUT_PATH}")
    print(f"   共 {len(final_items)} 条精选资讯")

if __name__ == "__main__":
    main()