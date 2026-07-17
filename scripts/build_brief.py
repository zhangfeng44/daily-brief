#!/usr/bin/env python3
"""Build a concise, source-linked daily brief from public RSS feeds and price APIs."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "brief.json"
USER_AGENT = "daily-brief/1.0 (+https://github.com/zhangfeng44/daily-brief)"
BEIJING = timezone(timedelta(hours=8))

TOPICS = [
    {
        "id": "china-policy",
        "query": "中国经济 政策 消费 金融 数据",
        "source": "中国经济",
        "priority_publishers": ["gov.cn", "国家统计局", "中国政府网", "中国人民银行", "国家发展改革委", "新华社", "Reuters", "财新"],
        "publishers": ["gov.cn", "国家统计局", "中国政府网", "中国人民银行", "国家发展改革委", "新华社", "Reuters", "财新", "第一财经", "证券时报", "上海证券报", "经济观察报", "界面新闻", "澎湃新闻", "Bloomberg", "Financial Times"],
        "keywords": ["中国", "经济", "政策", "消费", "统计", "国民", "金融", "财政", "货币", "投资", "就业", "地产", "制造业", "人民币", "pmi"],
        "required_keywords": ["经济", "政策", "消费", "统计", "国民", "金融", "财政", "货币", "投资", "就业", "地产", "制造业", "人民币", "pmi"],
        "minimum_keyword_hits": 1,
        "section": "lead",
        "minutes": 2,
        "tags": [["中国经济", "china"], ["政策", "market"], ["中影响", "risk"]],
        "why": "政策标题只能说明方向。更有用的是继续确认资金规模、落地细则和随后的消费、就业或投资数据。",
        "impact": "中国增长预期、内需相关行业和人民币风险偏好可能首先反应；持续性仍取决于执行与数据验证。",
        "uncertain": "单一表态不能直接代表政策效果，需等待正式文件、部门执行口径和后续数据。",
    },
    {
        "id": "us-macro",
        "query": "美国 通胀 就业 美联储 利率",
        "source": "美国宏观",
        "priority_publishers": ["Federal Reserve", "Bureau of Labor Statistics", "BLS", "BEA", "Reuters", "Associated Press", "AP"],
        "publishers": ["Federal Reserve", "Bureau of Labor Statistics", "BLS", "BEA", "Reuters", "Associated Press", "AP", "Bloomberg", "Financial Times", "Wall Street Journal", "CNBC", "MarketWatch", "Yahoo Finance", "BBC News", "The New York Times"],
        "keywords": ["美国", "美联储", "通胀", "就业", "cpi", "inflation", "federal reserve", "fed", "jobs", "gdp", "利率", "降息", "加息", "收益率", "国债", "鲍威尔", "powell", "fomc", "零售销售"],
        "required_keywords": ["美联储", "通胀", "就业", "cpi", "inflation", "federal reserve", "fed", "jobs", "gdp", "利率", "降息", "加息", "收益率", "国债", "鲍威尔", "powell", "fomc", "零售销售"],
        "minimum_keyword_hits": 1,
        "section": "lead",
        "minutes": 3,
        "tags": [["美联储", "us"], ["美股", "market"], ["BTC", "crypto"]],
        "why": "通胀、就业和美联储表态共同决定利率预期，而利率预期是美股估值、美元和 BTC 风险偏好的共同变量。",
        "impact": "若数据显著高于预期，收益率和美元通常更易走强；反之可能支持风险资产。实际反应取决于市场此前定价。",
        "uncertain": "单一数据经常被修正，且美联储会综合多项指标判断，不能把标题等同于政策结论。",
    },
    {
        "id": "trade-chain",
        "query": "中美贸易 关税 供应链 出口",
        "source": "全球贸易",
        "priority_publishers": ["Reuters", "Nikkei Asia", "商务部", "MOFCOM", "Associated Press", "AP"],
        "publishers": ["Reuters", "Nikkei Asia", "商务部", "MOFCOM", "Associated Press", "AP", "Bloomberg", "Financial Times", "Wall Street Journal", "South China Morning Post", "BBC News", "CNBC", "财新"],
        "keywords": ["中美", "美国", "中国", "贸易", "关税", "供应链", "出口", "进口", "wto", "tariff", "trade", "export", "import", "制裁", "芯片", "航运"],
        "required_keywords": ["中美", "美国", "中国", "贸易", "关税", "wto", "tariff", "trade", "制裁"],
        "minimum_keyword_hits": 1,
        "section": "lead",
        "minutes": 3,
        "tags": [["中国", "china"], ["美国", "us"], ["政策风险", "risk"]],
        "why": "贸易政策从新闻标题走向盈利影响，需要拆分生效日期、豁免范围、库存周期和企业的成本传导能力。",
        "impact": "出口链、进口依赖度较高的企业以及部分制造和消费行业的预期可能变化；指数层面的影响取决于权重行业暴露。",
        "uncertain": "最终文本、谈判进展与企业应对节奏可能改变初始判断，需以原始公告为准。",
    },
    {
        "id": "us-markets",
        "query": "美股 财报 科技股 标普 纳斯达克",
        "source": "美国市场",
        "priority_publishers": ["Reuters", "SEC", "Associated Press", "AP"],
        "publishers": ["Reuters", "SEC", "Associated Press", "AP", "Bloomberg", "Financial Times", "Wall Street Journal", "CNBC", "MarketWatch", "Yahoo Finance", "Barron's"],
        "keywords": ["美股", "美国", "标普", "纳斯达克", "华尔街", "财报", "科技股", "股市", "earnings", "stocks", "wall street", "s&p", "nasdaq", "道琼斯", "英伟达", "苹果", "微软", "指数"],
        "required_keywords": ["美股", "标普", "纳斯达克", "华尔街", "财报", "科技股", "earnings", "stocks", "wall street", "s&p", "nasdaq", "道琼斯", "英伟达", "苹果", "微软", "指数"],
        "minimum_keyword_hits": 1,
        "section": "update",
        "minutes": 1,
        "tags": [["美股", "us"], ["企业盈利", "market"]],
        "why": "市场交易的是未来预期，指引、利润率和资本开支往往比单季结果更能改变估值。",
        "impact": "大型科技公司的业绩与资本开支会对指数、供应链和成长风格估值产生较大影响。",
        "uncertain": "股价反应同时受估值和投资者仓位影响，业绩超预期也不必然意味着上涨。",
    },
    {
        "id": "bitcoin",
        "query": "比特币 BTC ETF 加密市场",
        "source": "加密资产",
        "priority_publishers": ["Reuters", "SEC", "CoinDesk"],
        "publishers": ["Reuters", "SEC", "CoinDesk", "Bloomberg", "Financial Times", "CNBC", "The Block", "Blockworks", "Decrypt", "Cointelegraph"],
        "keywords": ["比特币", "btc", "bitcoin", "加密", "etf"],
        "required_keywords": ["比特币", "btc", "bitcoin", "加密", "etf"],
        "minimum_keyword_hits": 1,
        "section": "update",
        "minutes": 1,
        "tags": [["BTC", "crypto"], ["资金流", "market"]],
        "why": "BTC 同时受链上和 ETF 资金、美元流动性、实际利率与风险情绪影响，单一指标的解释力有限。",
        "impact": "持续配置型资金流入可能改善边际买盘预期；利率上行或风险资产走弱也可能抵消这种支持。",
        "uncertain": "短期波动常由多因素共同驱动，单日流入流出不能独立预测价格趋势。",
    },
]

MARKETS = [
    ("沪深 300", "000300.SS"),
    ("标普 500", "^GSPC"),
    ("美元/人民币", "CNY=X"),
    ("BTC", "BTC-USD"),
]


def request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()


def google_news_item(
    query: str,
    priority_publishers: list[str],
    publishers: list[str],
    keywords: list[str],
    required_keywords: list[str],
    minimum_keyword_hits: int,
) -> dict | None:
    params = urllib.parse.urlencode({
        "q": query + " when:3d",
        "hl": "zh-CN",
        "gl": "CN",
        "ceid": "CN:zh-Hans",
    })
    try:
        root = ET.fromstring(request("https://news.google.com/rss/search?" + params))
        selected_candidates = []
        fallback_candidates = []
        for item in root.findall("./channel/item"):
            title = strip_html(item.findtext("title", ""))
            link = item.findtext("link", "")
            source = item.find("source")
            source_name = source.text if source is not None else "Google 新闻"
            source_text = source_name.lower()
            if not any(keyword.lower() in title.lower() for keyword in keywords):
                continue
            keyword_hits = sum(keyword.lower() in title.lower() for keyword in required_keywords)
            if keyword_hits < minimum_keyword_hits:
                continue
            priority_source = any(publisher.lower() in source_text for publisher in priority_publishers)
            selected_source = priority_source or any(publisher.lower() in source_text for publisher in publishers)
            # A source outside the selected list is only used as a clearly marked
            # fallback when its headline has a stronger-than-minimum topic match.
            if not selected_source and keyword_hits < 2:
                continue
            candidate = {
                "title": title,
                "url": link,
                "publisher": source_name,
                "published": item.findtext("pubDate", ""),
                "source_level": "优先来源" if priority_source else ("扩展来源" if selected_source else "聚合线索，需核对"),
                "score": keyword_hits * 10 + (3 if priority_source else (2 if selected_source else 0)),
            }
            if selected_source:
                selected_candidates.append(candidate)
            else:
                fallback_candidates.append(candidate)
        # Relevance still orders candidates within a tier, but a selected source
        # should not be displaced by an unknown outlet merely because its title
        # repeats more matching keywords.
        candidates = selected_candidates or fallback_candidates
        return max(candidates, key=lambda item: item["score"]) if candidates else None
    except Exception as error:
        print(f"Feed unavailable for {query}: {error}")
        return None


def quote(symbol: str) -> dict | None:
    params = urllib.parse.urlencode({"range": "5d", "interval": "1d"})
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?" + params
    try:
        result = json.loads(request(url))["chart"]["result"][0]
        closes = [value for value in result["indicators"]["quote"][0]["close"] if value is not None]
        if len(closes) < 2:
            return None
        current, previous = closes[-1], closes[-2]
        return {"current": current, "change": (current / previous - 1) * 100}
    except Exception as error:
        print(f"Quote unavailable for {symbol}: {error}")
        return None


def format_market(label: str, value: float) -> str:
    if label == "BTC":
        return "$" + (f"{value / 1000:.1f}k" if value >= 1000 else f"{value:,.0f}")
    if label == "美元/人民币":
        return f"{value:.4f}"
    return f"{value:,.2f}"


def story_from_topic(topic: dict, now: datetime) -> dict:
    item = google_news_item(
        topic["query"],
        topic["priority_publishers"],
        topic["publishers"],
        topic["keywords"],
        topic["required_keywords"],
        topic["minimum_keyword_hits"],
    )
    title = item["title"] if item else "今日暂未取得主题相关的公开线索"
    publisher = item["publisher"] if item else "待核查"
    source_level = item["source_level"] if item else "暂无"
    url = item["url"] if item else ""
    summary = ("来源等级：" + source_level + "。这是自动筛出的短线索；打开原文核对背景、数据口径与完整表述。") if item else (
        "自动采集未找到同时满足主题相关性和最低来源要求的条目，下一轮更新会重新检索。"
    )
    published = item.get("published", "") if item else ""
    time_label = "更新"
    if published:
        try:
            time_label = parsedate_to_datetime(published).astimezone(BEIJING).strftime("%H:%M")
        except (TypeError, ValueError):
            pass
    return {
        "id": topic["id"],
        "section": topic["section"],
        "source": topic["source"] + " · " + publisher + ((" · " + source_level) if item else ""),
        "title": title,
        "summary": summary,
        "time": time_label,
        "minutes": topic["minutes"],
        "tags": topic["tags"],
        "fact": ("来源 " + publisher + " 的公开标题指出：" + title + "。来源等级为" + source_level + "；此处保留的是短线索，完整事实与措辞请以原文为准。") if item else (
            "今日尚无可展示的主题线索。市场数据仍可作为背景参考，但不应被当作该主题的新闻结论。"
        ),
        "why": topic["why"],
        "impact": topic["impact"],
        "uncertain": topic["uncertain"],
        "url": url,
        "sources": ("原始来源：" + publisher + "（" + source_level + "）") if item else "等待下一轮公开来源更新",
    }


def build() -> dict:
    now = datetime.now(BEIJING)
    stories = [story_from_topic(topic, now) for topic in TOPICS]
    market_data = []
    for label, symbol in MARKETS:
        result = quote(symbol)
        if result:
            market_data.append({
                "label": label,
                "value": format_market(label, result["current"]),
                "change": round(result["change"], 2),
            })
        else:
            market_data.append({"label": label, "value": "--", "change": 0})

    by_id = {story["id"]: story for story in stories}
    topics = [
        {
            "title": "中国内需与政策传导",
            "status": "每日更新",
            "update": by_id["china-policy"]["title"],
            "next": "正式文件、资金安排，以及消费和就业的后续数据。",
            "story_id": "china-policy",
        },
        {
            "title": "美联储与风险资产",
            "status": "每日更新",
            "update": by_id["us-macro"]["title"],
            "next": "通胀、就业、收益率及美联储沟通是否形成同一方向。",
            "story_id": "us-macro",
        },
        {
            "title": "BTC 与流动性",
            "status": "每日更新",
            "update": by_id["bitcoin"]["title"],
            "next": "ETF 资金、美元与实际利率、风险资产波动。",
            "story_id": "bitcoin",
        },
    ]

    return {
        "edition_title": now.strftime("%-m 月 %-d 日，") + "星期" + "一二三四五六日"[now.weekday()],
        "updated_label": now.strftime("%Y-%m-%d %H:%M 北京时间"),
        "estimated_minutes": 8,
        "market_label": "收盘或最近可得报价 · 非实时",
        "theme": "先分清事实、阅读框架和市场反应。对政策与宏观数据，优先等待执行细则和后续数据，不追逐单日情绪。",
        "stories": stories,
        "markets": market_data,
        "calendar": [
            {"time": "每日", "event": "中国政策与经济数据", "note": "优先核对官方发布与统计口径", "grade": "重点"},
            {"time": "美盘前", "event": "美国宏观与公司公告", "note": "关注预期偏离和利率反应", "grade": "重点"},
            {"time": "全天", "event": "BTC 与市场流动性", "note": "将资金流与美元、利率一起看", "grade": "跟进"},
        ],
        "topics": topics,
        "sources": ["中国政府网", "国家统计局", "美联储", "BLS", "SEC", "Reuters", "AP", "Bloomberg", "Financial Times", "财新", "Nikkei Asia", "Google 新闻索引"],
    }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", OUTPUT)
