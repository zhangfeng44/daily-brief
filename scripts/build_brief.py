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
GOOGLE_NEWS_URL = re.compile(r"^https://news\.google\.com/rss/articles/([^?]+)")
DOMESTIC_MEDIA_MARKERS = [
    "东方财富", "汇通网", "fx678", "新浪", "网易", "腾讯", "搜狐", "凤凰", "财联社",
    "第一财经", "证券时报", "上海证券报", "经济观察报", "界面", "澎湃", "富途", "moomoo",
    "华尔街见闻", "观察", "股票",
]
CHINESE_OFFICIAL_MARKERS = ["国家统计局", "中国政府网", "中国人民银行", "国家发展改革委", "商务部"]
OVERSEAS_CHINESE_MARKERS = ["路透", "彭博", "金融时报", "日经", "华尔街日报", "美联社", "英国广播公司", "经济学人"]

TOPICS = [
    {
        "id": "china-policy",
        "query": "China economy policy consumption stimulus",
        "fallback_query": "中国经济 政策 消费 金融 数据",
        "source": "中国经济",
        "priority_publishers": ["Reuters", "Bloomberg", "Financial Times", "Nikkei Asia", "Wall Street Journal", "Associated Press", "AP", "BBC News", "The Economist"],
        "publishers": ["Reuters", "Bloomberg", "Financial Times", "Nikkei Asia", "Wall Street Journal", "Associated Press", "AP", "BBC News", "The Economist", "South China Morning Post", "CNBC", "gov.cn", "国家统计局", "中国政府网", "中国人民银行", "国家发展改革委"],
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
        "query": "Federal Reserve inflation jobs interest rates",
        "fallback_query": "美国 通胀 就业 美联储 利率",
        "source": "美国宏观",
        "priority_publishers": ["Federal Reserve", "Bureau of Labor Statistics", "BLS", "BEA", "Reuters", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP"],
        "publishers": ["Federal Reserve", "Bureau of Labor Statistics", "BLS", "BEA", "Reuters", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP", "CNBC", "MarketWatch", "Yahoo Finance", "BBC News", "The New York Times", "Trading Economics", "FXStreet"],
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
        "query": "US China trade tariffs supply chain",
        "fallback_query": "中美贸易 关税 供应链 出口",
        "source": "全球贸易",
        "priority_publishers": ["Reuters", "Nikkei Asia", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP"],
        "publishers": ["Reuters", "Nikkei Asia", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP", "South China Morning Post", "BBC News", "CNBC", "The Economist", "商务部", "MOFCOM"],
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
        "id": "china-risk",
        "query": "China economy risks property debt deflation jobs yuan",
        "fallback_query": "中国 宏观 风险 房地产 地方债 通缩 就业 人民币 资本流动",
        "source": "中国宏观风险",
        "priority_publishers": ["Reuters", "Bloomberg", "Financial Times", "Nikkei Asia", "Wall Street Journal", "Associated Press", "AP", "BBC News", "The Economist"],
        "publishers": ["Reuters", "Bloomberg", "Financial Times", "Nikkei Asia", "Wall Street Journal", "Associated Press", "AP", "BBC News", "The Economist", "South China Morning Post", "CNBC"],
        "keywords": ["中国", "经济", "风险", "房地产", "地方债", "债务", "通缩", "就业", "青年失业", "人民币", "资本", "china", "property", "debt", "deflation", "jobs", "yuan", "capital outflow"],
        "required_keywords": ["风险", "房地产", "地方债", "债务", "通缩", "就业", "青年失业", "人民币", "资本", "property", "debt", "deflation", "jobs", "yuan", "capital outflow"],
        "minimum_keyword_hits": 1,
        "allow_unlisted_source": True,
        "section": "update",
        "minutes": 2,
        "tags": [["中国经济", "china"], ["宏观风险", "risk"], ["人民币", "market"]],
        "why": "中国宏观风险往往不是由一个总量数据触发，而是地产、地方财政、价格、就业和资本流动之间的相互强化。应判断新闻反映的是个案、政策信号还是更广的趋势。",
        "impact": "风险若持续扩散，通常会先影响人民币预期、内需与银行相关资产的风险偏好，也可能通过全球需求和供应链传导到海外市场。",
        "uncertain": "要继续核对地产销售和价格、地方融资与财政安排、核心价格、就业数据及人民币汇率；政策工具的规模和落地速度同样关键。",
    },
    {
        "id": "us-markets",
        "query": "US stock market earnings technology shares",
        "fallback_query": "美股 财报 科技股 标普 纳斯达克",
        "source": "美国市场",
        "priority_publishers": ["Reuters", "SEC", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP"],
        "publishers": ["Reuters", "SEC", "Bloomberg", "Financial Times", "Wall Street Journal", "Associated Press", "AP", "CNBC", "MarketWatch", "Yahoo Finance", "Barron's", "Investing.com"],
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
        "query": "Bitcoin BTC ETF crypto market",
        "fallback_query": "比特币 BTC ETF 加密市场",
        "source": "加密资产",
        "priority_publishers": ["Reuters", "SEC", "CoinDesk", "Bloomberg", "Financial Times", "CNBC"],
        "publishers": ["Reuters", "SEC", "CoinDesk", "Bloomberg", "Financial Times", "CNBC", "The Block", "Blockworks", "Decrypt", "Cointelegraph", "DL News"],
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


def post(url: str, data: bytes) -> bytes:
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read()


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()


def clean_headline(title: str, publisher: str) -> str:
    suffix = " - " + publisher
    return title[:-len(suffix)].strip() if title.lower().endswith(suffix.lower()) else title.strip()


def translate_to_chinese(value: str) -> str:
    if not value or re.search(r"[\u4e00-\u9fff]", value):
        return value
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "zh-CN",
        "dt": "t",
        "q": value,
    })
    try:
        payload = json.loads(request("https://translate.googleapis.com/translate_a/single?" + params))
        translated = "".join(part[0] for part in payload[0] if part and part[0]).strip()
        return translated or value
    except Exception as error:
        print(f"Translation unavailable: {error}")
        return value


def decode_google_news_url(url: str) -> str:
    """Resolve a Google News RSS wrapper to the publisher page when available."""
    match = GOOGLE_NEWS_URL.match(url)
    if not match:
        return url
    article_id = match.group(1)
    try:
        article_page = request("https://news.google.com/articles/" + article_id).decode("utf-8", "ignore")
        signature = re.search(r'data-n-a-sg="([^"]+)"', article_page)
        timestamp = re.search(r'data-n-a-ts="([^"]+)"', article_page)
        if not signature or not timestamp:
            return url
        request_body = [
            [
                "Fbv4je",
                json.dumps([
                    "garturlreq",
                    [
                        [
                            "en-US", "US", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"],
                            None, None, 1, 1, "US:en", None, 1, None, None, None,
                            None, None, 0, 1,
                        ],
                        "en-US", "US", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
                    ],
                    article_id,
                    timestamp.group(1),
                    signature.group(1),
                ], separators=(",", ":")),
            ]
        ]
        body = urllib.parse.urlencode({"f.req": json.dumps([request_body], separators=(",", ":"))}).encode()
        response = post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            body,
        ).decode("utf-8", "ignore")
        payload = json.loads(response.split("\n\n", 1)[1])
        decoded = json.loads(payload[0][2])
        return decoded[1] if isinstance(decoded, list) and len(decoded) > 1 else url
    except Exception as error:
        print(f"Article URL unavailable: {error}")
        return url


def page_summary(url: str) -> str:
    """Read only a publisher's public metadata description, not the article body."""
    if not url or "news.google.com" in urllib.parse.urlparse(url).netloc:
        return ""
    try:
        page = request(url).decode("utf-8", "ignore")
        matches = re.findall(
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)["\']',
            page,
            flags=re.IGNORECASE,
        )
        if not matches:
            matches = re.findall(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description)["\']',
                page,
                flags=re.IGNORECASE,
            )
        summary = strip_html(matches[0]) if matches else ""
        return summary[:360].rsplit(" ", 1)[0] if len(summary) > 360 else summary
    except Exception as error:
        print(f"Article summary unavailable: {error}")
        return ""


def is_domestic_media_source(source_name: str) -> bool:
    source_text = source_name.lower()
    if any(marker in source_text for marker in DOMESTIC_MEDIA_MARKERS):
        return True
    if not re.search(r"[\u4e00-\u9fff]", source_name):
        return False
    if any(marker in source_name for marker in CHINESE_OFFICIAL_MARKERS + OVERSEAS_CHINESE_MARKERS):
        return False
    return True


def publisher_matches(source_text: str, publisher: str) -> bool:
    publisher_text = publisher.lower()
    if len(publisher_text) <= 3 and publisher_text.isalpha():
        return re.search(r"(?<![a-z])" + re.escape(publisher_text) + r"(?![a-z])", source_text) is not None
    return publisher_text in source_text


def google_news_item(
    query: str,
    fallback_query: str,
    priority_publishers: list[str],
    publishers: list[str],
    keywords: list[str],
    required_keywords: list[str],
    minimum_keyword_hits: int,
    allow_unlisted_source: bool = False,
) -> dict | None:
    try:
        priority_candidates = []
        selected_candidates = []
        fallback_candidates = []
        feeds = [
            (query, "en-US", "US", "US:en"),
            (fallback_query, "zh-CN", "CN", "CN:zh-Hans"),
        ]
        for search_query, language, region, edition in feeds:
            params = urllib.parse.urlencode({
                "q": search_query + " when:3d",
                "hl": language,
                "gl": region,
                "ceid": edition,
            })
            root = ET.fromstring(request("https://news.google.com/rss/search?" + params))
            for item in root.findall("./channel/item"):
                title = strip_html(item.findtext("title", ""))
                link = item.findtext("link", "")
                source = item.find("source")
                source_name = source.text if source is not None else "Google 新闻"
                source_text = source_name.lower()
                if is_domestic_media_source(source_name):
                    continue
                if not any(keyword.lower() in title.lower() for keyword in keywords):
                    continue
                keyword_hits = sum(keyword.lower() in title.lower() for keyword in required_keywords)
                if keyword_hits < minimum_keyword_hits:
                    continue
                priority_source = any(publisher_matches(source_text, publisher) for publisher in priority_publishers)
                selected_source = priority_source or any(publisher_matches(source_text, publisher) for publisher in publishers)
                # A source outside the selected list is only used as a clearly marked
                # fallback when its headline has a stronger-than-minimum topic match.
                if not selected_source and (not allow_unlisted_source or keyword_hits < minimum_keyword_hits):
                    continue
                candidate = {
                    "title": title,
                    "url": link,
                    "publisher": source_name,
                    "published": item.findtext("pubDate", ""),
                    "source_level": "优先来源" if priority_source else ("扩展来源" if selected_source else "聚合线索，需核对"),
                    "score": keyword_hits * 10 + (3 if priority_source else (2 if selected_source else 0)),
                }
                if priority_source:
                    priority_candidates.append(candidate)
                elif selected_source:
                    selected_candidates.append(candidate)
                else:
                    fallback_candidates.append(candidate)
        # Source tier comes before relevance: the page should use an overseas
        # primary report when one is available, then a named extension, then a
        # clearly marked aggregated lead.
        candidates = priority_candidates or selected_candidates or fallback_candidates
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


def market_context(markets: list[dict]) -> str:
    changes = {market["label"]: market["change"] for market in markets}
    parts = []
    for label in ("标普 500", "BTC", "美元/人民币"):
        if label in changes:
            change = changes[label]
            direction = "上涨" if change > 0 else ("下跌" if change < 0 else "持平")
            parts.append(label + direction + f"{abs(change):.2f}%")
    return "；".join(parts)


def insight_for(topic: dict, headline: str, markets: list[dict]) -> dict:
    snapshot = market_context(markets)
    topic_id = topic["id"]
    if topic_id == "china-policy":
        return {
            "summary": "一句话：这是一项中国经济运行或政策线索。比“总体向好”的表述更重要的是消费、制造业投资、地产和就业分项是否同步改善。",
            "why": "这类综合表述主要影响市场对增长下限和政策加码必要性的判断。对投资者而言，关键是把总量信号拆成内需、地产、出口和价格四条线来看。",
            "impact": "若消费和制造业投资分项继续改善，内需与顺周期板块的预期更容易得到支持；若改善主要依赖单一分项，市场反应通常不会持续。",
            "uncertain": "下一步看消费、固定资产投资、地产销售与就业的分项数据，以及是否出现更具体的财政或货币政策安排。",
        }
    if topic_id == "us-macro":
        return {
            "summary": "一句话：联储系统对通胀、就业和货币政策作出沟通。它会影响利率预期，但单位官员讲话不等同于 FOMC 的正式决定。",
            "why": "市场真正交易的是“通胀回落是否足以允许更宽松的利率路径”。讲话若强调通胀风险，通常会让降息预期更谨慎；若强调就业转弱，方向可能相反。",
            "impact": "对美股和 BTC，最直接的传导是美债收益率与美元。当前页面市场快照为：" + snapshot + "；应把该变动与利率、美元是否同向一起看。",
            "uncertain": "下一步看 CPI、PCE、非农就业、失业率，以及下一次 FOMC 声明和点阵图，而不是只根据一次讲话下注。",
        }
    if topic_id == "trade-chain":
        return {
            "summary": "一句话：标题反映企业正通过产地、物流或供应链布局来应对美国关税。关税的影响正在从政策层面传导到具体采购与制造决策。",
            "why": "这类案例的价值在于观察企业是否真的迁移订单和产能，而不只是宣布计划。若更多企业采取相似做法，关税成本会改变区域贸易流和部分行业的利润率。",
            "impact": "汽车零部件、电子、航运和北美制造链更值得跟踪。对中国相关资产，重点不是单一公司，而是转口、海外产能和订单转移是否形成趋势。",
            "uncertain": "下一步看关税生效范围、原产地规则、豁免条款，以及企业是否披露资本开支、库存或交付地的实质调整。",
        }
    if topic_id == "china-risk":
        return {
            "summary": "一句话：这是一条中国宏观风险线索。判断重点不在于标题是否悲观，而在于地产、地方财政、价格、就业或资本流动中是否有更多指标朝同一方向变化。",
            "why": "这些风险会相互传导：地产走弱影响地方收入和居民预期，价格偏弱影响企业利润，就业压力又会压低消费。单一指标转弱不必然构成系统性风险，但多项指标共振值得提高关注。",
            "impact": "对人民币和中国资产，风险信号若持续，通常会提高防御性需求并压低内需预期；对海外资产，重点看它是否影响全球需求、原材料和供应链订单。",
            "uncertain": "下一步看地产销售与价格、地方融资和财政支持、核心通胀、就业及人民币汇率；也要看政策是否给出规模、时点和执行主体明确的安排。",
        }
    if topic_id == "us-markets":
        return {
            "summary": "一句话：指数层面出现分化时，往往意味着盈利或宏观数据的利好不足以覆盖权重行业的压力。",
            "why": "如果芯片或大型科技股走弱，即便整体盈利不错，指数也可能承压，因为这些公司对标普和纳指的权重很高。要区分“市场整体变差”和“少数权重股拖累”。",
            "impact": "观察半导体、云计算资本开支和大盘成长股的相对表现。当前页面市场快照为：" + snapshot + "；若收益率同步上行，高估值板块通常更脆弱。",
            "uncertain": "下一步看公司业绩指引、利润率和资本开支，而不是只看单季是否超预期；同时留意市场下跌是否扩散到非科技板块。",
        }
    return {
        "summary": "一句话：ETF 资金变化与加密资产内部相对强弱同时出现，说明资金不仅在判断方向，也在选择配置对象。",
        "why": "ETF 净流入可以反映配置型需求，但不能单独解释价格。若以太坊跑赢比特币，可能代表资金在加密资产内部轮动，而不是整个风险偏好普遍升温。",
        "impact": "BTC 更需要与美元、实际利率和美股风险偏好一起看。当前页面市场快照为：" + snapshot + "；单日 ETF 流量应视为确认信号，而不是交易指令。",
        "uncertain": "下一步看 ETF 连续多日净流、主要发行方资金占比、BTC 与 ETH 的相对强弱，以及美债收益率和美元是否反向变化。",
    }


def story_from_topic(topic: dict, now: datetime, markets: list[dict]) -> dict:
    item = google_news_item(
        topic["query"],
        topic["fallback_query"],
        topic["priority_publishers"],
        topic["publishers"],
        topic["keywords"],
        topic["required_keywords"],
        topic["minimum_keyword_hits"],
        topic.get("allow_unlisted_source", False),
    )
    original_title = clean_headline(item["title"], item["publisher"]) if item else ""
    title = translate_to_chinese(original_title) if item else "今日暂未取得主题相关的公开线索"
    publisher = item["publisher"] if item else "待核查"
    source_level = item["source_level"] if item else "暂无"
    url = decode_google_news_url(item["url"]) if item else ""
    source_summary = page_summary(url) if item else ""
    summary_translation = translate_to_chinese(source_summary)
    insight = insight_for(topic, title, markets)
    summary = (summary_translation or insight["summary"]) if item else (
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
        "original_title": original_title,
        "summary": summary,
        "time": time_label,
        "minutes": topic["minutes"],
        "tags": topic["tags"],
        "fact": (("来源摘要：" + summary_translation + " ") if summary_translation else "") + "标题线索：" + title + "。完整事实、数字与条件请以原文为准。" if item else (
            "今日尚无可展示的主题线索。市场数据仍可作为背景参考，但不应被当作该主题的新闻结论。"
        ),
        "why": insight["why"],
        "impact": insight["impact"],
        "uncertain": insight["uncertain"],
        "url": url,
        "sources": ("原始来源：" + publisher + "（" + source_level + "）") if item else "等待下一轮公开来源更新",
    }


def build() -> dict:
    now = datetime.now(BEIJING)
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
    stories = [story_from_topic(topic, now, market_data) for topic in TOPICS]

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
            "title": "中国宏观风险",
            "status": "每日更新",
            "update": by_id["china-risk"]["title"],
            "next": "地产、地方财政、价格、就业与人民币是否出现共振。",
            "story_id": "china-risk",
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
        "estimated_minutes": 10,
        "market_label": "收盘或最近可得报价 · 非实时",
        "theme": "先分清事实、阅读框架和市场反应。政策利好与宏观风险可以并存；对中国经济尤其要观察地产、地方财政、价格、就业和人民币是否出现同向变化。",
        "stories": stories,
        "markets": market_data,
        "calendar": [
            {"time": "每日", "event": "中国政策与经济数据", "note": "优先核对官方发布与统计口径", "grade": "重点"},
            {"time": "美盘前", "event": "美国宏观与公司公告", "note": "关注预期偏离和利率反应", "grade": "重点"},
            {"time": "全天", "event": "BTC 与市场流动性", "note": "将资金流与美元、利率一起看", "grade": "跟进"},
        ],
        "topics": topics,
        "sources": ["Reuters", "Bloomberg", "Financial Times", "Nikkei Asia", "Wall Street Journal", "AP", "BBC News", "CoinDesk", "美联储", "BLS", "SEC", "中国官方原始发布（仅核对）"],
    }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote", OUTPUT)
