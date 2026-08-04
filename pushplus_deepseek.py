#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pushplus_deepseek.py — 港股数据 + DeepSeek 分析 → 多通道推送
                          （PushPlus / 企业微信 / Server酱 / 控制台）

功能模块
========
1. 港股行情模块：三个免费无需 Key 的数据源（Yahoo财经 / 东方财富 / 腾讯财经）
2. 交叉核验模块：同一标的从三源取价，比对偏差，给出可信度结论；异常源自动剔除
3. 分析框架模块：DeepSeek 按 10 套模板生成内容，多空判断一律带概率
4. 推送模块：多通道真实推送 / dry-run 预览 / Secrets 检查

用法
====
    python pushplus_deepseek.py --template fusion --topic "金风科技" --hk-code 02208
    python pushplus_deepseek.py --template scan --dry-run
    python pushplus_deepseek.py --selftest            # 离线自检（解析器+核验+模板）
    python pushplus_deepseek.py --check-only          # 只检查 Secrets
    python pushplus_deepseek.py                       # 默认: analysis + pushplus + deepseek（详细内容）

Secrets（keyless 数据源无需配置）：
    PUSHPLUS_TOKEN / WECOM_KEY / SERVERCHAN_SENDKEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
环境变量（可选）：TOPIC / CONTEXT / HK_CODE / RISK(low|mid|high)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from statistics import median

# ================================================================ 常量

PUSHPLUS_URL = "http://www.pushplus.plus/send"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
WECOM_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

YAHOO_CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
                   "{code}.HK?interval=1d&range=5d")
EASTMONEY_URL = ("https://push2.eastmoney.com/api/qt/stock/get"
                 "?secid=116.{code}&fields=f43,f44,f45,f46,f57,f58,f60,f170,f47")
TENCENT_URL = "https://qt.gtimg.cn/q=hk{code}"
EM_HK_PRICE_SCALE = 1000          # 东财港股价格为实际价格×1000
HK_TZ = timezone(timedelta(hours=8), "HKT")

DEFAULT_TOPIC = "金风科技(Goldwind) 每日简报"
CST = timezone(timedelta(hours=8), "CST")

VERSION = "2.8-2026-08-04"  # 脚本版本指纹：每次交付递增，日志首行可见

CHANNELS = ["pushplus", "wecom", "serverchan", "console", "all"]
ALL_CHANNELS = ["pushplus", "wecom", "serverchan"]
PROVIDERS = ["deepseek", "rule", "openai"]
RISKS = ["low", "mid", "high"]
RISK_ZH = {"low": "低", "mid": "中", "high": "高"}

TEMPLATES = ["brief", "analysis", "scan", "picker", "fusion",
             "plan", "earnings", "portfolio", "review", "regime",
             "sentiment", "feedscan"]
TEMPLATE_TITLES = {
    "brief": "简报", "analysis": "多空因子分析", "scan": "市场情报扫描",
    "picker": "选股器·未来30日", "fusion": "技术面×基本面融合",
    "plan": "交易计划·进出场风控", "earnings": "财报前瞻",
    "portfolio": "组合配置优化", "review": "交易复盘改进", "regime": "市场形态识别",
    "sentiment": "量价舆情动量·48h", "feedscan": "全市场快讯情绪扫描",
}
# 会员版 PushPlus 单条可达 10 万字，内容按「详细版」生成：token 预算大幅上调，
# 提示词不再要求压缩字数（详见各模板 prompt）。
TEMPLATE_MAX_TOKENS = {
    "brief": 2500, "analysis": 4000, "scan": 5000, "picker": 6000,
    "fusion": 4500, "plan": 5500, "earnings": 4500, "portfolio": 5500,
    "review": 4500, "regime": 4000, "sentiment": 6000, "feedscan": 6500,
}

FACTORS = [
    "基本面（业绩/订单/毛利率）",
    "行业与政策面（风电装机/招标/电价政策）",
    "技术面（趋势/量价/关键价位）",
    "资金面（主力/北向/两融动向）",
    "消息面与情绪面（公告/舆情/行业事件）",
    "估值面（PE/PB 与历史分位）",
]

# ================================================================ 基础工具


def log(msg: str = "") -> None:
    print(msg, flush=True)


class PushError(RuntimeError):
    """可预期失败（缺 Secret、API 返回错误等）。"""


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def http_request(url: str, data: bytes | None = None, content_type: str = "",
                 headers: dict | None = None, timeout: int = 30,
                 encoding: str = "utf-8") -> tuple[int, str]:
    """GET/POST 统一入口，返回 (HTTP 状态码, 响应文本)。网络层异常转 PushError。"""
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if content_type:
        req.add_header("Content-Type", content_type)
    req.add_header("User-Agent", "Mozilla/5.0 (pushplus-deepseek/2.0)")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode(encoding, "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(encoding, "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise PushError(f"网络请求失败 {url.split('?')[0]}: {reason}") from e


def http_post_json(url: str, payload: dict, headers: dict | None = None,
                   timeout: int = 30) -> tuple[int, str]:
    return http_request(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "application/json", headers, timeout)


def http_post_form(url: str, fields: dict, timeout: int = 30) -> tuple[int, str]:
    return http_request(url, urllib.parse.urlencode(fields).encode("utf-8"),
                        "application/x-www-form-urlencoded", None, timeout)


# ================================================================ 模块①：港股行情（三源接入）

@dataclass
class Quote:
    source: str
    ok: bool = False
    name: str = ""
    price: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    time_str: str = ""
    error: str = ""


def normalize_hk_code(raw: str) -> str:
    """接受 2208 / 02208 / 2208.HK / hk02208 等写法，统一为 5 位数字字符串。"""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        raise PushError(f"无法识别的港股代码: {raw!r}")
    code = digits[-5:].zfill(5)
    if code == "00000":
        raise PushError(f"非法港股代码: {raw!r}")
    return code


def _sane(price: float | None) -> bool:
    return price is not None and 0 < price < 100000


def _fill_change(q: Quote) -> None:
    if q.change_pct is None and _sane(q.price) and _sane(q.prev_close) and q.prev_close:
        q.change_pct = round((q.price - q.prev_close) / q.prev_close * 100, 2)


def parse_yahoo(text: str) -> Quote:
    data = json.loads(text)
    meta = data["chart"]["result"][0]["meta"]
    q = Quote(source="Yahoo财经", ok=True,
              name=meta.get("longName") or meta.get("shortName")
                   or meta.get("symbol", ""),
              price=meta.get("regularMarketPrice"),
              prev_close=(meta.get("previousClose")
                          or meta.get("chartPreviousClose")))
    ts = meta.get("regularMarketTime")
    if ts:
        q.time_str = datetime.fromtimestamp(ts, HK_TZ).strftime("%Y-%m-%d %H:%M")
    _fill_change(q)
    if not _sane(q.price):
        raise ValueError("价格异常或缺失")
    return q


def parse_eastmoney(text: str) -> Quote:
    data = json.loads(text).get("data") or {}
    raw_price, raw_prev = data.get("f43"), data.get("f60")
    q = Quote(source="东方财富", ok=True, name=data.get("f58", ""))
    if raw_price is not None:
        q.price = round(raw_price / EM_HK_PRICE_SCALE, 3)
    if raw_prev is not None:
        q.prev_close = round(raw_prev / EM_HK_PRICE_SCALE, 3)
    if data.get("f170") is not None:
        q.change_pct = round(data["f170"] / 100, 2)
    _fill_change(q)
    if not _sane(q.price):
        raise ValueError("价格异常或缺失")
    return q


def parse_tencent(text: str) -> Quote:
    # 形如: v_hk02208="100~金风科技~02208~16.800~16.610~16.850~...";
    if '="' not in text or not text.strip().endswith(";"):
        raise ValueError("返回格式不符合预期")
    body = text.split('="', 1)[1].rstrip('";\n ')
    parts = body.split("~")
    if len(parts) < 5:
        raise ValueError("字段数量不足")
    q = Quote(source="腾讯财经", ok=True, name=parts[1],
              price=float(parts[3]), prev_close=float(parts[4]))
    _fill_change(q)
    if not _sane(q.price):
        raise ValueError("价格异常或缺失")
    return q


SOURCES = [  # (源名, URL 构造器, 解析器, 解码)
    ("Yahoo财经", lambda c: YAHOO_CHART_URL.format(code=str(int(c))), parse_yahoo, "utf-8"),
    ("东方财富", lambda c: EASTMONEY_URL.format(code=c), parse_eastmoney, "utf-8"),
    ("腾讯财经", lambda c: TENCENT_URL.format(code=c), parse_tencent, "gbk"),
]


def fetch_all(code: str, timeout: int = 15) -> list[Quote]:
    """从三个免费源取价。任何单源失败只记录、不抛出，绝不拖垮主流程。"""
    quotes: list[Quote] = []
    for name, url_fn, parser, encoding in SOURCES:
        try:
            status, body = http_request(url_fn(code), timeout=timeout,
                                        encoding=encoding)
            if status != 200:
                raise PushError(f"HTTP {status}: {body[:120]}")
            quotes.append(parser(body))
        except Exception as e:  # noqa: BLE001 —— 逐源隔离
            quotes.append(Quote(source=name, ok=False, error=str(e)[:150]))
    return quotes


# ================================================================ 模块①·交叉核验

MAX_DEV_OK = 0.5      # ≤0.5% 视为一致
MAX_DEV_EXCLUDE = 2.0  # >2% 视为异常并剔除出共识


@dataclass
class Verification:
    consensus: float | None = None
    max_dev_pct: float | None = None
    n_ok: int = 0
    n_excluded: int = 0
    verdict: str = ""
    rows: list[dict] = field(default_factory=list)


def _short_err(err: str) -> str:
    """失败原因压缩成短文案（去掉 URL 等噪音），便于微信表格阅读。"""
    if "网络请求失败" in err:
        host = err.split("//", 1)[1].split("/")[0] if "//" in err else ""
        low = err.lower()
        if "timed out" in low or "timeout" in low:
            cat = "超时"
        elif "ssl" in low or "eof" in low or "reset" in low:
            cat = "网络不可达"
        elif "name" in low or "resolve" in low:
            cat = "域名解析失败"
        else:
            cat = "连接失败"
        return f"{cat}（{host}）"
    return err[:40]


def verify_quotes(quotes: list[Quote]) -> Verification:
    v = Verification()
    ok = [q for q in quotes if q.ok and _sane(q.price)]
    v.n_ok = len(ok)
    for q in quotes:
        if not q.ok:
            v.rows.append({"source": q.source, "price": None, "dev": None,
                           "status": f"❌ 获取失败（{_short_err(q.error)}）"})
    if not ok:
        v.verdict = "❌ 三个数据源全部失败，本次内容降级为纯模型推断"
        return v
    prices = [q.price for q in ok]
    mid = median(prices)
    for q in ok:
        dev = abs(q.price - mid) / mid * 100
        status = "✅ 一致" if dev <= MAX_DEV_OK else (
            "⚠️ 偏差偏大" if dev <= MAX_DEV_EXCLUDE else "❌ 异常剔除")
        v.rows.append({"source": f"{q.source}（{q.name or '?'}）",
                       "price": q.price, "dev": round(dev, 2), "status": status,
                       "change": q.change_pct, "time": q.time_str})
    included = [r for r in v.rows if r["price"] is not None
                and not r["status"].startswith("❌")]
    v.n_excluded = v.n_ok - len(included)
    if len(included) >= 2:
        v.consensus = round(median([r["price"] for r in included]), 3)
        v.max_dev_pct = max(r["dev"] for r in included)
    elif len(included) == 1:
        v.consensus = included[0]["price"]
        v.max_dev_pct = None
    dev2 = v.max_dev_pct if v.max_dev_pct is not None else 99.0
    if v.n_ok >= 3 and v.n_excluded == 0 and dev2 <= MAX_DEV_OK:
        v.verdict = f"✅ 三源一致，数据可信（最大偏差 {v.max_dev_pct:.2f}%）"
    elif len(included) >= 2 and dev2 <= MAX_DEV_EXCLUDE:
        v.verdict = (f"✅ {len(included)} 源基本一致（最大偏差 {v.max_dev_pct:.2f}%"
                     + (f"，已剔除 {v.n_excluded} 个异常源）" if v.n_excluded else "）"))
    elif len(included) == 1:
        v.verdict = "⚠️ 仅单源数据，未经交叉核验，仅供参考"
    else:
        v.verdict = "❌ 数据源之间分歧过大，本次数值不可信"
    return v


def market_block_md(code: str, quotes: list[Quote], v: Verification) -> str:
    lines = ["---", f"📊 **数据核验（HK{code}）**",
             "", "| 数据源 | 最新价 | 涨跌 | 偏差 | 状态 |", "|---|---|---|---|---|"]
    for r in v.rows:
        price = f"{r['price']:.3f}" if r["price"] is not None else "—"
        chg = (f"{r['change']:+.2f}%" if r.get("change") is not None
               and r["price"] is not None else "—")
        dev = f"{r['dev']:.2f}%" if r.get("dev") is not None else "—"
        lines.append(f"| {r['source']} | {price} | {chg} | {dev} | {r['status']} |")
    lines += ["", f"> 共识价：**{v.consensus if v.consensus else '—'}**　{v.verdict}",
              "> 数据源：Yahoo财经 / 东方财富 / 腾讯财经（均免费免Key）"]
    return "\n".join(lines)


def market_context_line(code: str, quotes: list[Quote], v: Verification) -> str:
    ok_names = [f"{q.name}" for q in quotes if q.ok and q.name][:1]
    chg = next((q.change_pct for q in quotes if q.ok
                and q.change_pct is not None), None)
    chg_txt = f"{chg:+.2f}%" if chg is not None else "未知"
    grade = "已交叉核验" if v.n_ok >= 2 and not v.n_excluded else "部分核验"
    return (f"HK{code} {ok_names[0] if ok_names else ''} "
            f"最新价 {v.consensus or '—'}（{chg_txt}），"
            f"{grade}，可信度说明见文末数据核验表")


# ================================================================ 模块②：舆情采集与情绪动量（48h）

GOOGLE_NEWS_RSS = ("https://news.google.com/rss/search?"
                   "q={q}&hl=zh-HK&gl=HK&ceid=HK:zh-Hant")
REDDIT_SEARCH = ("https://www.reddit.com/search.json"
                 "?q={q}&sort=new&t=week&limit=25")
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
YOUTUBE_HANDLE_PAGE = "https://www.youtube.com/@{handle}"
FUTU_PAGE = "https://www.futunn.com/stock/{code}-HK"
STOCKTWITS_STREAM = "https://api.stocktwits.com/api/2/streams/symbol/{t}.json"
REDDIT_UA = {"User-Agent": "hk-sentiment-research/2.0 (educational)"}

# 轻量情绪词典（先本地打标，AI 再综合——rule 模式下也能出完整报告）
POS_WORDS = ["利好", "上涨", "大涨", "增长", "中标", "突破", "创新高", "创纪录",
             "回购", "预增", "超预期", "盈利", "签约", "订单", "扩产", "获批",
             "分红", "surge", "rally", "beat", "upgrade", "record", "profit",
             "bullish", "soar", "win", "growth", "boost"]
NEG_WORDS = ["利空", "下跌", "大跌", "亏损", "减持", "违约", "下调", "预警",
             "预亏", "低于预期", "处罚", "诉讼", "削减", "延期", "停产",
             "plunge", "miss", "downgrade", "loss", "lawsuit", "cut", "bearish",
             "slump", "drop", "warning", "fraud"]

UTC = timezone.utc


def _count_word(low: str, w: str) -> int:
    """英文词按词边界匹配（防止 win 命中 Goldwind 之类误判），中文按子串。"""
    if w.isascii():
        return len(re.findall(r"\b" + re.escape(w.lower()) + r"\b", low))
    return low.count(w)


def score_text(text: str) -> tuple[float, str, float]:
    """词典法情绪打分。返回 (score∈[-1,1], 标签, 置信度∈[0,1])。"""
    low = text.lower()
    pos = sum(_count_word(low, w) for w in POS_WORDS)
    neg = sum(_count_word(low, w) for w in NEG_WORDS)
    total = pos + neg
    score = 0.0 if total == 0 else max(-1.0, min(1.0, (pos - neg) / total))
    label = "利好" if score > 0.12 else ("利空" if score < -0.12 else "中性")
    return round(score, 2), label, round(min(1.0, total / 4), 2)


@dataclass
class SentItem:
    source: str
    title: str
    url: str = ""
    age_h: float | None = None   # 距抓取时刻的小时数
    score: float = 0.0
    label: str = "中性"
    conf: float = 0.0


def _mk_item(source: str, title: str, url: str, ts: datetime | None,
             now: datetime) -> SentItem:
    title = re.sub(r"\s+", " ", title).strip()
    score, label, conf = score_text(title)
    age = round((now - ts).total_seconds() / 3600, 1) if ts else None
    return SentItem(source=source, title=title, url=url,
                    age_h=age, score=score, label=label, conf=conf)


def _in_window(ts: datetime | None, hours: int, now: datetime) -> bool:
    return ts is not None and (now - ts).total_seconds() <= hours * 3600


# ---------- 源1：Google 新闻（官方 RSS）----------

GOOGLE_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>金风科技中标 500MW 海上风电项目 订单超预期 - 香港经济日报</title>
<link>https://example.com/a</link><pubDate>Mon, 04 Aug 2026 08:00:00 GMT</pubDate>
<source>香港经济日报</source></item>
<item><title>Goldwind shares plunge 3% on profit warning fears - Reuters</title>
<link>https://example.com/b</link><pubDate>Sun, 03 Aug 2026 20:00:00 GMT</pubDate>
<source>Reuters</source></item>
<item><title>风电板块周度回顾 - 财华社</title><link>https://example.com/c</link>
<pubDate>Fri, 01 Aug 2026 08:00:00 GMT</pubDate><source>财华社</source></item>
</channel></rss>"""


def parse_google_rss(text: str, hours: int, limit: int,
                     now: datetime) -> list[SentItem]:
    root = ET.fromstring(text)
    items = []
    for it in root.iter("item"):
        title = it.findtext("title", "")
        if " - " in title:  # Google 格式: "标题 - 来源"
            title, src = title.rsplit(" - ", 1)
        else:
            src = it.findtext("source", "")
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate", ""))
        except (TypeError, ValueError):
            ts = None
        if not _in_window(ts, hours, now):
            continue  # 48h 窗口过滤
        itm = _mk_item(f"Google·{src or '新闻'}", title,
                       it.findtext("link", ""), ts, now)
        items.append(itm)
        if len(items) >= limit:
            break
    return items


def fetch_google_news(query: str, hours: int, limit: int,
                      timeout: int) -> tuple[list[SentItem], str]:
    q = urllib.parse.quote_plus(f"{query} when:2d")
    status, body = http_request(GOOGLE_NEWS_RSS.format(q=q), timeout=timeout)
    if status != 200:
        raise PushError(f"HTTP {status}")
    items = parse_google_rss(body, hours, limit,
                             datetime.now(UTC))
    if not items:
        raise PushError(f"{hours}h 内无相关新闻")
    return items, ""


# ---------- 源2：Reddit（公开 JSON）----------

REDDIT_SAMPLE = json.dumps({"data": {"children": [
    {"data": {"title": "Goldwind wins record offshore order, bullish",
              "permalink": "/r/stocks/abc", "created_utc": 1754300000,
              "score": 42, "num_comments": 13, "subreddit": "stocks"}},
    {"data": {"title": "Wind sector slump: downgrade hits Goldwind",
              "permalink": "/r/investing/def", "created_utc": 1754200000,
              "score": 5, "num_comments": 2, "subreddit": "investing"}},
    {"data": {"title": "Old news beyond window", "permalink": "/r/x",
              "created_utc": 1754000000, "score": 1, "num_comments": 0,
              "subreddit": "stocks"}}]}})


def parse_reddit(text: str, hours: int, limit: int,
                 now: datetime) -> list[SentItem]:
    children = json.loads(text)["data"]["children"]
    items = []
    for c in children:
        d = c["data"]
        ts = datetime.fromtimestamp(d.get("created_utc", 0), UTC)
        if not _in_window(ts, hours, now):
            continue
        extra = f"（r/{d.get('subreddit','?')} ▲{d.get('score',0)} 💬{d.get('num_comments',0)}）"
        itm = _mk_item("Reddit", d.get("title", "") + extra,
                       "https://www.reddit.com" + d.get("permalink", ""), ts, now)
        items.append(itm)
        if len(items) >= limit:
            break
    return items


def fetch_reddit(query: str, hours: int, limit: int,
                 timeout: int) -> tuple[list[SentItem], str]:
    q = urllib.parse.quote_plus(query)
    status, body = http_request(REDDIT_SEARCH.format(q=q), headers=REDDIT_UA,
                                timeout=timeout)
    if status != 200:
        raise PushError(f"HTTP {status}")
    items = parse_reddit(body, hours, limit, datetime.now(UTC))
    if not items:
        raise PushError(f"{hours}h 内无相关帖子")
    return items, ""


# ---------- 源3：moomoo/富途（无公开接口 → 尝试 + 降级 Stocktwits）----------

def fetch_moomoo(code: str, hours: int, limit: int, timeout: int,
                 stocktwits_ticker: str = "XJNGF",
                 now: datetime | None = None) -> tuple[list[SentItem], str]:
    now = now or datetime.now(UTC)
    # 尝试富途页面内嵌评论（JS 渲染，多数情况下抓不到 → 走降级）
    try:
        status, body = http_request(FUTU_PAGE.format(code=code), timeout=timeout)
        if status == 200:
            snippets = re.findall(r'"content"\s*:\s*"([^"]{10,200})"', body)
            words = re.compile(r"[一-鿿]")
            junk = re.compile(r"http|function|var |null|\\\\u|\{|\}")
            snippets = [s for s in snippets
                        if words.search(s) and not junk.search(s)]
            items = [_mk_item("moomoo·富途", s, "", None, now)
                     for s in snippets[:limit]]
            if items:
                return items, "moomoo 页面直接解析（无时间戳，未按48h过滤）"
    except PushError:
        pass
    # 降级：Stocktwits 公开情绪流（同維社交评论数据）
    try:
        status, body = http_request(
            STOCKTWITS_STREAM.format(t=urllib.parse.quote(stocktwits_ticker)),
            timeout=timeout)
        if status == 200:
            msgs = json.loads(body).get("messages", [])[:limit]
            items = []
            for m in msgs:
                try:
                    ts = datetime.fromisoformat(
                        m["created_at"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    ts = None
                if ts and not _in_window(ts, max(hours, 24 * 7), now):
                    continue
                itm = _mk_item("moomoo替代·Stocktwits",
                               re.sub(r"<[^>]+>", "", m.get("body", "")),
                               "", ts, now)
                if m.get("entities", {}).get("sentiment", {}).get("basic"):
                    st = m["entities"]["sentiment"]["basic"]
                    itm.label = {"Bullish": "利好", "Bearish": "利空"}.get(
                        st, itm.label)
                items.append(itm)
            if items:
                return items, "moomoo 无公开接口，已降级 Stocktwits 社交情绪流"
    except (PushError, json.JSONDecodeError, KeyError):
        pass
    raise PushError("moomoo 无公开评论接口且降级源不可用——本项跳过")


# ---------- 源4：YouTube @investtalk（Handle 解析 + 官方 RSS）----------

YOUTUBE_ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
<entry><yt:videoId>abc123</yt:videoId>
<title>Market rally: why tech could surge this week</title>
<published>2026-08-04T06:00:00+00:00</published></entry>
<entry><yt:videoId>def456</yt:videoId>
<title>Investors brace for loss: bearish signals in energy</title>
<published>2026-08-03T07:00:00+00:00</published></entry>
<entry><yt:videoId>old789</yt:videoId><title>Old episode</title>
<published>2026-07-30T07:00:00+00:00</published></entry>
</feed>"""


def parse_youtube_atom(text: str, hours: int, limit: int,
                       now: datetime) -> list[SentItem]:
    ns = {"a": "http://www.w3.org/2005/Atom",
          "yt": "http://www.youtube.com/xml/schemas/2015"}
    items = []
    for e in ET.fromstring(text).findall("a:entry", ns):
        try:
            ts = datetime.fromisoformat(e.findtext("a:published", "", ns))
        except ValueError:
            ts = None
        if not _in_window(ts, hours, now):
            continue
        vid = e.findtext("yt:videoId", "", ns)
        itm = _mk_item("YouTube·investtalk", e.findtext("a:title", "", ns),
                       f"https://youtu.be/{vid}" if vid else "", ts, now)
        items.append(itm)
        if len(items) >= limit:
            break
    return items


def fetch_youtube(handle: str, hours: int, limit: int,
                  timeout: int) -> tuple[list[SentItem], str]:
    handle = (handle or "investtalk").lstrip("@")
    status, body = http_request(YOUTUBE_HANDLE_PAGE.format(handle=handle),
                                timeout=timeout)
    if status != 200:
        raise PushError(f"频道页 HTTP {status}")
    m = (re.search(r'"channelId"\s*:\s*"(UC[\w-]{22})"', body)
         or re.search(r'itemprop="channelId"\s+content="(UC[\w-]{22})"', body))
    if not m:
        raise PushError(f"未能解析 @{handle} 的 channelId")
    status, feed = http_request(YOUTUBE_FEED.format(cid=m.group(1)),
                                timeout=timeout)
    if status != 200:
        raise PushError(f"频道 RSS HTTP {status}")
    items = parse_youtube_atom(feed, hours, limit, datetime.now(UTC))
    if not items:
        raise PushError(f"@{handle} 在 {hours}h 内无新视频")
    return items, ""


# ================================================================ 模块②b：全市场快讯 12 源（通用采集框架）
#
# 设计：各家快讯 API 返回结构差异大且无官方文档，这里用「通用 JSON 探测 +
# 键名试探 + 时间格式自适应」做防御式解析。任何单源失败只记入缺口，不中断。

TITLE_KEYS = ["title", "content", "digest", "summary", "brief", "name",
              "description", "news_title", "sub_title", "text"]
TIME_KEYS = ["ctime", "created_at", "display_time", "show_time", "time",
             "pubDate", "publish_time", "update_time", "timestamp",
             "created", "date", "release_time"]
LIST_KEYS = ["data", "list", "items", "result", "newest", "news", "lives",
             "telegraphs", "articles", "messages", "rows", "records"]


def _json_find_list(obj, depth: int = 0):
    """在任意 JSON 里找第一个「dict 列表」（含常见包裹键递归下探）。"""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict) and depth < 4:
        for k in LIST_KEYS:
            v = obj.get(k)
            got = _json_find_list(v, depth + 1)
            if got is not None:
                return got
        for v in obj.values():
            if isinstance(v, (dict, list)):
                got = _json_find_list(v, depth + 1)
                if got is not None:
                    return got
    return None


def _parse_any_time(v) -> datetime | None:
    """兼容：epoch 秒/毫秒、'YYYY-MM-DD HH:MM:SS'、ISO、RFC822。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if v > 1e12:
            v = v / 1000
        if v > 1e8:
            return datetime.fromtimestamp(v, UTC)
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.isdigit():
        return _parse_any_time(int(s))
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=CST)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None


def extract_items_generic(payload, source: str, limit: int, hours: int,
                          now: datetime) -> list[SentItem]:
    """通用提取：定位列表 → 每条试探标题/时间键 → 情绪打标 → 48h 过滤。"""
    rows = _json_find_list(payload) or []
    items = []
    for row in rows:
        title, ts = "", None
        for k in TITLE_KEYS:
            v = row.get(k)
            if isinstance(v, str) and len(v.strip()) >= 4:
                title = v.strip()
                break
        if not title and isinstance(row.get("data"), dict):  # jin10 双层 data
            for k in TITLE_KEYS:
                v = row["data"].get(k)
                if isinstance(v, str) and len(v.strip()) >= 4:
                    title = v.strip()
                    break
        if not title:
            continue
        for scope in (row, row.get("data") if isinstance(row.get("data"), dict) else {}):
            for k in TIME_KEYS:
                if k in scope:
                    ts = _parse_any_time(scope[k])
                if ts:
                    break
            if ts:
                break
        if ts and not _in_window(ts, hours, now):
            continue
        # 快讯流本身即最新：无可靠时间戳的条目保留但标记
        itm = _mk_item(source, re.sub(r"<[^>]+>", "", title), "", ts, now)
        items.append(itm)
        if len(items) >= limit:
            break
    return items


@dataclass
class FeedSpec:
    name: str
    urls: list[str]                # 依次尝试
    kind: str = "json"             # json | js | html
    headers: dict = field(default_factory=dict)
    note: str = ""


FEED_HEADERS = {"Referer": "https://wallstreetcn.com/", "Accept": "application/json"}
FEED_SPECS: list[FeedSpec] = [
    FeedSpec("MKTNews 快讯", [
        "https://api.mktnews.net/api/flash?limit=10",
        "https://mktnews.net/api/flash?limit=10",
    ]),
    FeedSpec("华尔街见闻 快讯", [
        "https://api-ddc-wscn.awtmt.com/market/lives?channel=global-channel&limit=10",
        "https://api-ddc-wscn.awtmt.com/apiv1/content/lives?channel=global-channel&limit=10",
    ], headers=FEED_HEADERS),
    FeedSpec("华尔街见闻 最新", [
        "https://api-ddc-wscn.awtmt.com/apiv1/content/articles?limit=10&plat=pc",
    ], headers=FEED_HEADERS),
    FeedSpec("华尔街见闻 最热", [
        "https://api-ddc-wscn.awtmt.com/apiv1/content/articles/hot?limit=10&plat=pc",
        "https://api-ddc-wscn.awtmt.com/apiv1/content/articles?limit=10&sort=hot&plat=pc",
    ], headers=FEED_HEADERS),
    FeedSpec("财联社 电报", [
        "https://www.cls.cn/nodeapi/telegraphList?app=CailianpressWeb&os=web&sv=8.4.6&rn=10",
    ], headers={"Referer": "https://www.cls.cn/telegraph"}),
    FeedSpec("财联社 深度", [
        "https://www.cls.cn/api/depth/home/assembled/1000?app=CailianpressWeb&os=web&sv=8.4.6&rn=10",
        "https://www.cls.cn/v1/depth/home/articles?app=CailianpressWeb&os=web&sv=8.4.6&rn=10",
    ], headers={"Referer": "https://www.cls.cn/depth"}),
    FeedSpec("财联社 热门", [
        "https://www.cls.cn/v1/articles/hot?app=CailianpressWeb&os=web&sv=8.4.6&rn=10",
        "https://www.cls.cn/api/articles/hot?app=CailianpressWeb&os=web&sv=8.4.6&rn=10",
    ], headers={"Referer": "https://www.cls.cn/hot"}),
    FeedSpec("雪球 热门股票", [], kind="xueqiu"),  # 专用流程（Cookie 预热）
    FeedSpec("格隆汇 事件", [
        "https://www.gelonghui.com/api/fastnews/v2/getFastNewsList?limit=10",
        "https://www.gelonghui.com/api/article/v2/getArticleList?type=fastnews&page=1&limit=10",
    ], headers={"Referer": "https://www.gelonghui.com/live"}),
    FeedSpec("法布财经 快讯", [], note="公开端点未确认，需提供快讯页地址后接入"),
    FeedSpec("法布财经 头条", [], note="公开端点未确认，需提供头条页地址后接入"),
    FeedSpec("金十数据", [
        "https://www.jin10.com/flash_newest.js",
    ], kind="js", headers={"Referer": "https://www.jin10.com/", "x-app-id": "rU6QIu7JHe2gOUTe"}),
]


def fetch_feed_json(spec: FeedSpec, hours: int, timeout: int,
                    now: datetime) -> list[SentItem]:
    last_err = "无可用端点"
    for url in spec.urls:
        try:
            status, body = http_request(url, headers=spec.headers or None,
                                        timeout=timeout)
            if status != 200:
                last_err = f"HTTP {status}"
                continue
            if spec.kind == "js":  # 金十 flash_newest.js：剥 JS 壳
                m = re.search(r"[{\[]", body)
                body = body[m.start():] if m else body
                body = body.rstrip(";\n ")
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                last_err = "非 JSON 返回（可能需要登录/被反爬）"
                continue
            items = extract_items_generic(payload, spec.name, 10, hours, now)
            if items:
                return items
            last_err = "解析成功但 48h 内无条目（结构可能已变）"
        except PushError as e:
            last_err = str(e)[:80]
    raise PushError(last_err)


XUEQIU_HOT_URL = ("https://stock.xueqiu.com/v5/stock/hot_stock/list.json"
                  "?size=10&_type=10&type=10")


def parse_xueqiu_hot(text: str, now: datetime) -> list[SentItem]:
    """雪球热度榜：涨跌幅直接映射情绪分，关注度增量作置信参考。"""
    rows = _json_find_list(json.loads(text)) or []
    items = []
    for row in rows:
        name, code = row.get("name", ""), row.get("code", "")
        if not name:
            continue
        pct = row.get("percent")
        inc = row.get("increment") or row.get("follow_increment")
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            pct = None
        score = max(-1.0, min(1.0, (pct or 0) / 5))
        label = "利好" if score > 0.12 else ("利空" if score < -0.12 else "中性")
        title = f"{name} {code} 涨跌{pct:+.2f}%" if pct is not None \
            else f"{name} {code}"
        if inc:
            title += f"，关注增量 {inc}"
        items.append(SentItem(source="雪球 热门股票", title=title,
                              age_h=0.0, score=round(score, 2), label=label,
                              conf=0.7))
        if len(items) >= 10:
            break
    return items


def fetch_xueqiu(timeout: int, now: datetime) -> list[SentItem]:
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (pushplus-deepseek/2.0)")]
    try:
        opener.open("https://xueqiu.com/hq", timeout=timeout).read()  # Cookie 预热
        resp = opener.open(XUEQIU_HOT_URL, timeout=timeout)
        body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise PushError(f"HTTP {e.code}（雪球反爬升级）") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise PushError(f"网络失败 {getattr(e, 'reason', e)}") from e
    items = parse_xueqiu_hot(body, now)
    if not items:
        raise PushError("接口结构已变，未解析到榜单")
    return items


@dataclass
class FeedPack:
    hours: int
    items: dict[str, list[SentItem]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    agg: dict = field(default_factory=dict)


def collect_feeds(hours: int, timeout: int) -> FeedPack:
    now = datetime.now(UTC)
    pack = FeedPack(hours=hours)
    for spec in FEED_SPECS:
        if spec.kind == "xueqiu":
            try:
                pack.items[spec.name] = fetch_xueqiu(min(timeout, 12), now)
            except Exception as e:  # noqa: BLE001
                pack.errors.append(f"{spec.name}：{str(e)[:100]}")
            continue
        if not spec.urls:
            pack.errors.append(f"{spec.name}：{spec.note or '无端点'}")
            continue
        try:
            pack.items[spec.name] = fetch_feed_json(
                spec, hours, min(timeout, 12), now)
        except Exception as e:  # noqa: BLE001 —— 逐源隔离
            pack.errors.append(f"{spec.name}：{str(e)[:100]}")
    all_items = [i for v in pack.items.values() for i in v]
    n_ok = len(pack.items)
    mean = round(sum(i.score for i in all_items) / len(all_items), 2) \
        if all_items else 0.0
    pos = sum(1 for i in all_items if i.label == "利好")
    neg = sum(1 for i in all_items if i.label == "利空")
    anchor = 50 + 45 * max(-1.0, min(1.0, mean * 3))
    pack.agg = {"n": len(all_items), "pos": pos, "neg": neg,
                "neu": len(all_items) - pos - neg, "mean": mean,
                "n_sources": n_ok, "综合多头概率锚点": round(anchor)}
    return pack


def feed_context(topic: str, pack: FeedPack) -> str:
    ctx = [f"【{pack.hours}h 全市场快讯数据：{pack.agg['n_sources']}/12 源可用，"
           f"共 {pack.agg['n']} 条，已本地打标】关注标的：{topic}"]
    for spec in FEED_SPECS:
        items = pack.items.get(spec.name)
        if not items:
            continue
        agg = _src_agg(items)
        ctx.append(f"▼ {spec.name}（{agg['n']}条：利好{agg['pos']}/"
                   f"利空{agg['neg']}/中性{agg['neu']}，动量{agg['mean']:+.2f}）")
        ctx += [_item_line(i, k + 1) for k, i in enumerate(items[:10])]
    if pack.errors:
        ctx.append("▼ 数据缺口：" + "；".join(pack.errors))
    ctx.append(f"▼ 本地聚合：总样本 {pack.agg['n']}，利好/利空/中性="
               f"{pack.agg['pos']}/{pack.agg['neg']}/{pack.agg['neu']}，"
               f"情绪均值 {pack.agg['mean']:+.2f}，"
               f"综合多头概率锚点 ≈ {pack.agg['综合多头概率锚点']}%")
    return "\n".join(ctx)


def render_feed_rule(topic: str, pack: FeedPack) -> str:
    lines = [f"**{topic} · 全市场快讯情绪扫描**（rule 本地计算，未经 AI 综合）",
             "", "| 来源 | 样本 | 利好/利空/中性 | 情绪分 | 代表快讯 |",
             "|---|---|---|---|---|"]
    for spec in FEED_SPECS:
        items = pack.items.get(spec.name)
        if not items:
            err = next((e.split("：", 1)[1] for e in pack.errors
                        if e.startswith(spec.name)), "失败")
            lines.append(f"| {spec.name} | — | — | — | ⚠️ {err[:16]} |")
            continue
        agg = _src_agg(items)
        rep = items[0].title[:16]
        lines.append(f"| {spec.name} | {agg['n']} | {agg['pos']}/{agg['neg']}"
                     f"/{agg['neu']} | {agg['mean']:+.2f} | {rep}… |")
    a = pack.agg
    anchor = a.get("综合多头概率锚点", 50)
    stance = "偏多" if anchor >= 55 else ("偏空" if anchor <= 45 else "中性")
    lines += ["",
              f"- **全市场情绪温度**：均值 {a['mean']:+.2f}"
              f"（{a['pos']}利好/{a['neg']}利空/{a['neu']}中性，"
              f"共 {a['n']} 条 / {a['n_sources']}/12 源）",
              f"- **综合判断**：{stance}，综合多头概率 ≈ **{anchor}%**",
              "", "> ai_provider 选 deepseek 可生成跨源主线归纳与板块映射。",
              "> ⚠️ 非投资建议，仅供参考。"]
    return "\n".join(lines)


def render_feed_appendix(pack: FeedPack) -> str:
    lines = ["---", f"📰 **快讯原始明细（{pack.agg['n']} 条，每源≤10）**"]
    for spec in FEED_SPECS:
        items = pack.items.get(spec.name)
        if not items:
            continue
        lines.append(f"\n**{spec.name}（{len(items)}/10）**")
        lines += [_item_line(i, k + 1) for k, i in enumerate(items[:10])]
    if pack.errors:
        lines.append("\n**数据缺口**")
        lines += [f"- ⚠️ {e}" for e in pack.errors]
    return "\n".join(lines)


# ---------- 量价情绪动量：Yahoo 小时线（近48h 涨跌 + 量比）----------

def compute_price_momentum(closes: list[float], vols: list[float],
                           tss: list[int], hours: int,
                           now: datetime) -> dict:
    cutoff = now.timestamp() - hours * 3600
    pts = [(t, c, v) for t, c, v in zip(tss, closes, vols)
           if c is not None and t >= cutoff]
    prev_vols = [v for t, c, v in zip(tss, closes, vols)
                 if t < cutoff and v]
    if len(pts) < 2:
        return {"ok": False, "score": 0.0, "label": "数据不足", "detail": ""}
    ret = (pts[-1][1] - pts[0][1]) / pts[0][1] * 100
    vols_48 = [v for _, _, v in pts if v]
    avg_recent = sum(vols_48) / len(vols_48) if vols_48 else 0.0
    avg_prev = sum(prev_vols) / len(prev_vols) if prev_vols else avg_recent
    vol_ratio = avg_recent / avg_prev if avg_prev else 1.0
    score = max(-1.0, min(1.0, ret / 4)) * 0.6 \
        + max(-0.8, min(0.8, vol_ratio - 1)) * 0.5
    score = round(max(-1.0, min(1.0, score)), 2)
    label = "偏多" if score > 0.12 else ("偏空" if score < -0.12 else "中性")
    detail = f"近{hours}h {ret:+.2f}%，量比 {vol_ratio:.2f}，样本 {len(pts)} 根K线"
    return {"ok": True, "score": score, "label": label,
            "detail": detail, "ret": round(ret, 2),
            "vol_ratio": round(vol_ratio, 2)}


def fetch_price_momentum(code: str, hours: int, timeout: int) -> dict:
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{int(code)}.HK?interval=1h&range=5d")
    status, body = http_request(url, timeout=timeout)
    if status != 200:
        raise PushError(f"小时线 HTTP {status}")
    res = json.loads(body)["chart"]["result"][0]
    quote = res["indicators"]["quote"][0]
    return compute_price_momentum(quote.get("close", []),
                                  quote.get("volume", []),
                                  res.get("timestamp", []), hours,
                                  datetime.now(UTC))


# ---------- 汇总：多源采集 + 动量聚合 ----------

@dataclass
class SentPack:
    hours: int
    items: dict[str, list[SentItem]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    momentum: dict = field(default_factory=dict)
    agg: dict = field(default_factory=dict)


def _src_agg(items: list[SentItem]) -> dict:
    if not items:
        return {"n": 0}
    pos = sum(1 for i in items if i.label == "利好")
    neg = sum(1 for i in items if i.label == "利空")
    mean = round(sum(i.score for i in items) / len(items), 2)
    recent = [i.score for i in items if i.age_h is not None and i.age_h <= 24]
    older = [i.score for i in items if i.age_h is not None and i.age_h > 24]
    trend = "→"
    if recent and older:
        d = sum(recent) / len(recent) - sum(older) / len(older)
        trend = "↑" if d > 0.1 else ("↓" if d < -0.1 else "→")
    return {"n": len(items), "pos": pos, "neg": neg,
            "neu": len(items) - pos - neg, "mean": mean, "24h趋势": trend}


def _clean_query_topic(topic: str) -> str:
    """检索用主题清洗：去括号注释、去模板名等杂质，避免污染外部查询。"""
    t = re.sub(r"[（(].*$", "", topic).strip()
    t = re.sub(r"(每日简报|简报)$", "", t).strip(" 　·-")
    return t or "金风科技"


def collect_sentiment(topic: str, code: str | None, hours: int,
                      timeout: int, yt_handle: str = "") -> SentPack:
    """采集 4 源 + 量价动量。任何单源失败只记录、不中断。"""
    pack = SentPack(hours=hours)
    q_topic = _clean_query_topic(topic)
    jobs = [
        ("Google新闻", lambda: fetch_google_news(q_topic, hours, 10, timeout)),
        ("Reddit", lambda: fetch_reddit(
            f"{q_topic} OR {int(code)}.HK" if code else q_topic,
            hours, 10, timeout)),
        ("moomoo", lambda: fetch_moomoo(code or "02208", hours, 10, timeout)),
        ("YouTube·investtalk", lambda: fetch_youtube(
            yt_handle or (env("YT_CHANNEL") or "investtalk"), hours, 10, timeout)),
    ]
    for name, fn in jobs:
        if name in ("moomoo",) and not code:
            pack.errors.append("moomoo：未提供 hk_code，跳过")
            continue
        try:
            items, note = fn()
            pack.items[name] = items
            if note:
                pack.errors.append(f"{name}：{note}")
        except Exception as e:  # noqa: BLE001 —— 逐源隔离
            pack.errors.append(f"{name}：{str(e)[:120]}")
    if code:
        try:
            pack.momentum = fetch_price_momentum(code, hours, timeout)
        except Exception as e:  # noqa: BLE001
            pack.momentum = {"ok": False, "score": 0.0,
                             "label": "获取失败", "detail": str(e)[:100]}
    a = {"news": _src_agg(pack.items.get("Google新闻", [])),
         "social": _src_agg([i for k in ("Reddit", "moomoo", "YouTube·investtalk")
                             for i in pack.items.get(k, [])])}
    news_score = a["news"].get("mean", 0.0) if a["news"].get("n") else 0.0
    social_score = a["social"].get("mean", 0.0) if a["social"].get("n") else 0.0
    mom_score = pack.momentum.get("score", 0.0)
    anchor = 50 + 45 * (0.40 * mom_score + 0.35 * news_score + 0.25 * social_score)
    a["综合多头概率锚点"] = max(5, min(95, round(anchor)))
    pack.agg = a
    return pack


def _item_line(i: SentItem, idx: int) -> str:
    age = f"{i.age_h:.0f}h前" if i.age_h is not None else "时间未知"
    t = i.title if len(i.title) <= 60 else i.title[:57] + "…"
    return f"{idx}. [{i.label} {i.score:+.2f}] {t} — {i.source} · {age}"


def render_sentiment_appendix(pack: SentPack) -> str:
    n = sum(len(v) for v in pack.items.values())
    lines = ["---", f"📡 **48h 多源舆情原始数据（共 {n} 条，本地打标）**"]
    for name in ("Google新闻", "Reddit", "moomoo", "YouTube·investtalk"):
        items = pack.items.get(name)
        if not items:
            continue
        lines.append(f"\n**{name}（{len(items)}/10）**")
        lines += [_item_line(i, k + 1) for k, i in enumerate(items)]
    m = pack.momentum
    if m:
        lines.append("\n**量价情绪动量**")
        lines.append(f"- {m.get('detail') or m.get('label')} → "
                     f"{m.get('label')}（动量分 {m.get('score', 0):+.2f}）")
    if pack.errors:
        lines.append("\n**数据缺口**")
        lines += [f"- ⚠️ {e}" for e in pack.errors]
    return "\n".join(lines)


def sentiment_context(pack: SentPack) -> str:
    ctx = [f"【{pack.hours}h 多源舆情数据（本地预打标：标签/分值/时效）】"]
    for name, items in pack.items.items():
        ctx.append(f"▼ {name}")
        ctx += [_item_line(i, k + 1) for k, i in enumerate(items)]
    m = pack.momentum
    if m.get("ok"):
        ctx.append(f"▼ 量价动量：{m['detail']} → {m['label']}（{m['score']:+.2f}）")
    if pack.errors:
        ctx.append("▼ 数据缺口：" + "；".join(pack.errors))
    a = pack.agg
    ctx.append(
        "▼ 本地预聚合："
        f"新闻动量 {a.get('news', {}).get('mean', 0):+.2f}，"
        f"社媒动量 {a.get('social', {}).get('mean', 0):+.2f}，"
        f"量价动量 {m.get('score', 0):+.2f}，"
        f"综合多头概率锚点 ≈ {a.get('综合多头概率锚点', '—')}%")
    return "\n".join(ctx)


def render_sentiment_rule(topic: str, code: str | None, pack: SentPack) -> str:
    a, m = pack.agg, pack.momentum
    news, soc = a.get("news", {}), a.get("social", {})
    anchor = a.get("综合多头概率锚点", 50)
    stance = "偏多" if anchor >= 55 else ("偏空" if anchor <= 45 else "中性")
    rows = [
        "| 象限 | 样本 | 利好/利空/中性 | 动量分 | 24h趋势 |",
        "|---|---|---|---|---|",
        f"| 新闻动量 | {news.get('n', 0)} | {news.get('pos', 0)}/{news.get('neg', 0)}"
        f"/{news.get('neu', 0)} | {news.get('mean', 0):+.2f} | {news.get('24h趋势', '—')} |",
        f"| 舆情动量 | {soc.get('n', 0)} | {soc.get('pos', 0)}/{soc.get('neg', 0)}"
        f"/{soc.get('neu', 0)} | {soc.get('mean', 0):+.2f} | {soc.get('24h趋势', '—')} |",
        f"| 量价动量 | 小时K线 | — | {m.get('score', 0):+.2f} | — |",
    ]
    return "\n".join([
        f"**{topic} · 48h 量价舆情动量**（rule 本地计算，未经 AI 综合）",
        "", *rows, "",
        f"- **综合判断**：{stance}，综合多头概率 ≈ **{anchor}%**"
        "（权重：量价40% / 新闻35% / 舆情25%）",
        f"- **来源**：HK{code or '—'}；Google新闻 / Reddit / moomoo / "
        "YouTube@investtalk（48h 窗口）",
        "", "> ai_provider 选 deepseek 可在此数据基础上生成完整综合报告。",
        "> ⚠️ 非投资建议，仅供参考。"])


# ================================================================ 模块③：分析框架（11 套模板）

RULES_TAIL = "末尾固定一行「⚠️ 非投资建议，仅供参考」。"


def _ctx_line(context: str) -> str:
    if context:
        return f"参考数据/背景（优先采用，数值以此为准）：\n{context}\n\n"
    return ("注意：无实时数据接入，请基于既有知识推断，"
            "凡涉及具体点位/数值的地方标注 *（推断）。\n\n")


def build_messages(template: str, topic: str, context: str,
                   risk: str = "mid") -> list[dict]:
    """按模板构造 AI 对话。多空判断一律带概率（50%=中性）。"""
    ctx = _ctx_line(context)
    if template == "sentiment":
        user = (
            f"基于以下 48 小时内、已完成本地预打标的多源数据，"
            f"为「{topic}」输出一份量价与舆情动量报告。\n\n{context}\n\n"
            "严格按此格式输出：\n\n"
            f"## 48h 情绪动量报告\n\n"
            "| 象限 | 样本 | 利好/利空/中性 | 动量分 | 24h趋势 | 多头概率 |\n"
            "|---|---|---|---|---|---|\n"
            "| 新闻动量 |  |  |  |  |  |\n"
            "| 舆情动量 |  |  |  |  |  |\n"
            "| 量价动量 |  | — |  | — |  |\n\n"
            "- **新闻要点**：3 条最有信息量的（引用编号）\n"
            "- **舆情要点**：3 条（注明来自 Reddit/moomoo/YouTube）\n"
            "- **催化 vs 风险**：各 2 条\n"
            "- **综合判断**：明确偏多/偏空 + 综合多头概率%"
            "（可参考本地锚点，偏离须给理由）\n"
            "- **失效条件**：1~2 条\n\n"
            "打分区间 [-1,1]；样本不足的象限必须明说而非编造。"
            "输出详细内容：新闻/舆情要点逐条展开 2~3 句（引用编号+逻辑），"
            "催化与风险各给完整论证，不要压缩篇幅。" + RULES_TAIL)
    elif template == "feedscan":
        user = (
            f"基于以下 48h 内全市场快讯数据（已本地预打标，含各源情绪指标），"
            f"输出一份全市场情绪扫描报告，并评估对关注标的「{topic}」的传导。\n\n"
            f"{context}\n\n严格按此格式输出：\n\n"
            "## 全市场快讯情绪扫描\n\n"
            "| 来源 | 样本 | 利好/利空/中性 | 情绪分 | 多头概率 |\n"
            "|---|---|---|---|---|\n（逐源罗列，不可用源注明）\n\n"
            "- **全市场情绪温度**：偏暖/偏冷一句话 + 综合多头概率%"
            "（可参考本地锚点，偏离须给理由）\n"
            "- **三大主线**：跨源归纳，每条标注支撑来源与成立概率%\n"
            "- **板块映射**：利多板块/利空板块各 2~3 个\n"
            f"- **对「{topic}」所在产业链的传导**：1~2 句 + 方向概率%\n"
            "- **噪音提示**：2 条看似重要但可忽略的快讯\n\n"
            "打分区间 [-1,1]；样本不足的源必须明说而非编造。"
            "输出详细内容：三大主线逐条展开 2~3 句（支撑来源+逻辑），"
            "板块映射与传导给完整论证，不要压缩篇幅。" + RULES_TAIL)
    elif template == "scan":
        user = (
            "扫一遍今天全球市场，总结推动股价的 5 大力量。"
            "重点关注宏观事件、板块轮动、情绪变化，区分重点与噪音。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 力量 | 方向 | 对港股影响概率 | 逻辑（≤30字） | 相关板块 |\n"
            "|---|---|---|---|---|\n（恰好 5 行）\n\n"
            "- **重点**：2 条今日真正值得跟踪的\n- **噪音**：2 条看似热闹但可忽略的\n"
            "- **今日结论**：1~2 句，给出港股整体偏多/偏空概率\n\n"
            "概率取整数%。输出详细内容：每条力量与结论展开 2~3 句"
            "（数据/事件/逻辑），不要压缩篇幅。" + RULES_TAIL)
    elif template == "picker":
        user = (
            "根据当下市场环境，挑出未来 30 天高概率的股票 3~5 只"
            "（范围：港股/A股，风电及新能源链优先）。每只说清楚为什么看好、"
            "关键风险、什么情况下要止损。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 股票 | 方向 | 30日上涨概率 | 看好逻辑（≤30字） | 关键风险 | 止损触发 |\n"
            "|---|---|---|---|---|---|\n（3~5 行）\n\n"
            "- **首选**：1 句话点名胜率最高的一只\n"
            "- **弃权说明**：若环境不适合开新仓，明说并给理由\n\n"
            "概率取整数%。输出详细内容：每只股票展开完整逻辑链"
            "（催化剂/估值/技术位/仓位建议），不要压缩篇幅。" + RULES_TAIL)
    elif template == "fusion":
        user = (
            f"分析「{topic}」，结合 K 线结构、财报和最新新闻，给出明确的看多还是看空。\n\n"
            + ctx +
            "严格按此格式输出：\n\n"
            "| 维度 | 判断 | 多头概率 | 要点（≤30字） |\n|---|---|---|---|\n"
            "| K线结构 |  |  |  |\n| 基本面/财报 |  |  |  |\n"
            "| 最新消息 |  |  |  |\n| 资金与情绪 |  |  |  |\n\n"
            "- **结论**：明确写「看多」或「看空」+ 信心概率%\n"
            "- **关键点位**：支撑 S1/S2、压力 R1/R2（有行情数据时按真实价格算，"
            "否则标注推断）\n- **适合风格**：短线/波段/长线三选一 + 一句理由\n\n"
            "输出详细内容：每个维度展开 2~3 句论证（含数据与逻辑），"
            "关键点位给出计算过程，不要压缩篇幅。" + RULES_TAIL)
    elif template == "plan":
        user = (
            f"给「{topic}」做个完整交易计划：理想进场区间、止损怎么设、"
            "多个止盈位、头寸怎么配置才低风险。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "- **方向**：做多/观望/做空 + 信心概率%\n"
            "- **理想进场区间**：价格带 + 理由 1 句\n"
            "- **止损位**：价格 + 距进场幅度% + 触发即无条件执行\n\n"
            "| 止盈位 | 目标价 | 到达概率 | 到达后动作 |\n|---|---|---|---|\n"
            "| T1 |  |  | 减仓 1/3 |\n| T2 |  |  | 再减 1/3 |\n"
            "| T3 |  |  | 清仓或移动止盈 |\n\n"
            "- **头寸配置**：占总资金%（低风险原则，单票≤15%）\n"
            "- **盈亏比**：估算并给出值\n- **计划失效条件**：2 条\n\n"
            "输出详细内容：进场/止损/止盈每档给出完整计算过程与理由，"
            "头寸配置与失效条件展开说明，不要压缩篇幅。" + RULES_TAIL)
    elif template == "earnings":
        user = (
            f"分析「{topic}」的即将发布财报：用历史财报反应、指引趋势、"
            "板块表现、市场情绪，推测财报后股价最可能怎么走。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "- **历史财报反应**：近几次财报后平均涨跌% 与规律 1 句\n"
            "- **指引趋势**：管理层口径变化 1 句\n- **板块与情绪**：1 句\n\n"
            "| 财报后情形 | 概率 | 触发条件 |\n|---|---|---|\n"
            "| 大涨(>5%) |  |  |\n| 小涨(0~5%) |  |  |\n"
            "| 小跌(0~-5%) |  |  |\n| 大跌(<-5%) |  |  |\n"
            "（概率合计=100%）\n\n"
            "- **最可能路径**：1~2 句\n- **关键观察点**：2 条（订单/毛利率/指引）\n\n"
            "输出详细内容：历史财报反应逐次展开，概率表每档给出触发条件"
            "与判断依据，不要压缩篇幅。" + RULES_TAIL)
    elif template == "portfolio":
        user = (
            f"根据我的风险偏好【{RISK_ZH[risk]}】，设计一个分散的股票组合"
            "（港股/A股，风电新能源为重点再加其他板块）。各板块怎么配、"
            "为什么要这些头寸、多久调整一次。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 板块 | 配置比例 | 代表标的 | 配置理由（≤30字） |\n|---|---|---|---|\n"
            "（4~6 行，比例合计 100%，含现金档）\n\n"
            "- **头寸原则**：单票上限%、单板块上限%\n"
            "- **再平衡**：频率（如每季度）+ 2 条触发式调整条件\n"
            "- **预期特征**：该风险档位的预期波动 1 句\n\n"
            "输出详细内容：每个板块/头寸原则展开论证，再平衡条件逐条说明，"
            "不要压缩篇幅。" + RULES_TAIL)
    elif template == "review":
        if context:
            user = (
                f"复盘我这笔交易：\n{context}\n\n"
                "找出我的错误、优点、心理偏差，以及下次怎样做才能长期稳定盈利。\n\n"
                "严格按此格式输出：\n\n"
                "- **错误 TOP3**：各 1 句，按损失贡献排序\n"
                "- **优点 TOP2**：各 1 句，需保持\n"
                "- **心理偏差**：点名具体偏差（FOMO/锚定/损失厌恶/过度自信等）"
                "+ 在本单中的表现\n"
                "- **下次改进（if-then 规则）**：3 条，形如"
                "「若…则…」，可直接执行\n"
                "- **长期胜率杠杆**：1 条最值得固化的习惯\n\n"
                "输出详细内容：错误/优点/偏差逐条展开 2~3 句"
                "（含数据与具体表现），改进规则给出完整操作步骤，不要压缩篇幅。"
                + RULES_TAIL)
        else:
            user = (
                "用户未提供具体交易细节。输出一份《交易复盘框架》：\n"
                "1) 需要记录哪些字段（进出场价/仓位/理由/情绪）；"
                "2) 错误分类清单（择时/仓位/纪律/信息）；"
                "3) 心理偏差自查表（各给一句自查问题）；"
                "4) 说明把交易细节粘贴到 context 输入后，可获得逐条复盘。\n\n"
                "输出详细内容：每个字段/清单/自查表给出使用说明与示例，"
                "不要压缩篇幅。" + RULES_TAIL)
    elif template == "regime":
        user = (
            "判断当前市场是趋势、震荡、风险偏好高还是低。"
            "在这个环境下交易策略应该怎么调整，交易员常掉的坑是什么。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 属性 | 判定 | 概率 | 依据（≤30字） |\n|---|---|---|---|\n"
            "| 趋势市 | 是/否 |  |  |\n| 震荡市 | 是/否 |  |  |\n"
            "| 风险偏好高 | 是/否 |  |  |\n| 高波动 | 是/否 |  |  |\n\n"
            "- **环境一句话**：当前最贴切的 regime 标签\n"
            "- **策略调整**：仓位/持仓周期/止损宽度/可用品类 各 1 条\n"
            "- **常见坑**：该环境下交易员最常犯的 2~3 个错误\n\n"
            "输出详细内容：每项判定给足依据，策略调整逐条展开"
            "（含仓位/周期/止损数值），不要压缩篇幅。" + RULES_TAIL)
    elif template == "analysis":
        factors_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(FACTORS))
        user = (
            f"请对「{topic}」按以下 6 个因子逐一做多空分析。{ctx}"
            "每个因子给出【方向】和【多头概率】：多头概率 = 该因子当前指向"
            "上涨/利多的把握，50% 中性，>50% 偏多，<50% 偏空。\n\n"
            f"因子列表（必须全部覆盖，顺序不可变）：\n{factors_text}\n\n"
            "严格按以下 Markdown 格式输出，不要增删表格行：\n\n"
            "| 因子 | 方向 | 多头概率 | 依据（≤30字） |\n|---|---|---|---|\n"
            "| （逐因子填写） |\n\n"
            "- **综合判断**：方向+综合多头概率（如「震荡偏多，约 58%」）\n"
            "- **关键风险**：1~2 条\n- **数据局限**：一句话\n\n"
            "概率取整数%。输出详细内容：每个因子依据展开 2~3 句"
            "（含数据与逻辑），综合判断给出完整推理链，不要压缩篇幅。"
            + RULES_TAIL)
    else:  # brief（详细版简报）
        user = (f"请围绕「{topic}」生成一份今日详细简报：3~5 个要点，"
                "每个要点展开 2~4 句（含数据与逻辑），结尾一句小结。"
                "输出详细内容，不要压缩篇幅。\n\n" + ctx)
    system = ("你是一位严谨的跨市场分析师，深耕港股/A股风电与新能源链。"
              "输出必须是简体中文 Markdown，不要寒暄，不要使用代码块，"
              "所有概率用整数百分比表示。")
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def validate_analysis(content: str) -> bool:
    """analysis 模板专属校验：应含表头且 ≥6 行带百分号的因子行。"""
    if "| 因子" not in content:
        return False
    rows = [ln for ln in content.splitlines()
            if ln.strip().startswith("|") and "%" in ln]
    return len(rows) >= len(FACTORS)


# ================================================================ 内容生成（rule / AI 统一入口）

def gen_by_rule(topic: str, template: str) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    if template == "analysis":
        rows = "\n".join(
            f"| {f} | 中性 | 50% | 示例占位，待 AI 填充 |" for f in FACTORS)
        return "\n".join([
            f"**{topic} · 多空因子分析框架**（rule 演示模板，概率均为占位示例）",
            "", "| 因子 | 方向 | 多头概率 | 依据 |", "|---|---|---|---|", rows,
            "", "- **综合判断**：示例——ai_provider 选 deepseek 后由 AI 填充真实概率",
            "- **关键风险**：示例", "- **数据局限**：rule 模式不含真实分析", "",
            f"> 运行时间：{now}（北京时间）。⚠️ 非投资建议，仅供参考。"])
    return "\n".join([
        f"**{topic} · {TEMPLATE_TITLES.get(template, '简报')}**（rule 演示模板）", "",
        f"- 模板：{template}（正式内容需 ai_provider=deepseek）",
        f"- 运行时间：{now}（北京时间）",
        "- 工作流：Manual Run - Goldwind PushPlus+DeepSeek", "",
        "> 在 Actions 运行页选择 ai_provider=deepseek 即可获得完整 AI 分析。",
        "> ⚠️ 非投资建议，仅供参考。"])


def chat_completion(url: str, api_key: str, model: str, messages: list[dict],
                    max_tokens: int, timeout: int) -> str:
    payload = {"model": model, "messages": messages,
               "temperature": 0.7, "max_tokens": max_tokens}
    status, body = http_post_json(url, payload,
                                  {"Authorization": f"Bearer {api_key}"}, timeout)
    if status != 200:
        raise PushError(f"AI 接口返回 HTTP {status}：{body[:400]}")
    try:
        return json.loads(body)["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise PushError(f"AI 接口返回格式异常：{body[:400]}") from e


# ================================================================ Secrets 检查

def required_secrets(channel: str, provider: str) -> list[str]:
    req: list[str] = []
    if channel in ("pushplus", "all"):
        req.append("PUSHPLUS_TOKEN")
    if channel in ("wecom", "all"):
        req.append("WECOM_KEY")
    if channel in ("serverchan", "all"):
        req.append("SERVERCHAN_SENDKEY")
    if provider == "deepseek":
        req.append("DEEPSEEK_API_KEY")
    elif provider == "openai":
        req.append("OPENAI_API_KEY")
    return req


def print_secret_report(channel: str, provider: str) -> bool:
    names = required_secrets(channel, provider)
    log("🔎 Secrets 配置检查（只显示是否配置，绝不打印内容）：")
    if not names:
        log("  （所选 通道+AI 组合无需任何 Secret）")
        return True
    missing = []
    for name in names:
        if env(name):
            log(f"  ✅ {name} 已配置")
        else:
            log(f"  ❌ {name} 缺失")
            missing.append(name)
    if missing:
        log("\n❌ 请前往 仓库 Settings → Secrets and variables → Actions 补齐后重试。")
        return False
    log("  → 全部所需 Secrets 已就绪 ✅")
    return True


# ================================================================ 模块④b：HTML 主题渲染
#
# PushPlus template=html 时走该渲染器。微信/PushPlus 详情页对 <style> 标签
# 支持不稳定，全部使用内联样式。klein 主题：浅灰底 + 克莱因蓝(#002FA7) +
# 字号较默认默认(≈16px)降两号 ≈ 13px。

KLEIN = {
    # ── 底色深浅：改这一行 ──────────────────────────
    "bg": "#F3F4F6",        # 卡片底色（浅灰）
    "hbg": "#E6ECF8",       # 表头底色
    # ── 字号档位：改这几行 ──────────────────────────
    "size": "13px",         # 正文（较微信默认≈16px 降两号）
    "size_title": "15px",   # 卡片大标题
    "size_h1": "16px",      # 「#」一级标题
    "size_h2": "15px",      # 「##」二级标题
    "size_h3": "13.5px",    # 「###」及以下标题
    # ── 表格/文字配色：改这几行 ──────────────────────
    "fg": "#002FA7",        # 主文字：克莱因蓝
    "muted": "#5C7BC4",     # 次级文字（引用/备注）
    "border": "#C9D4EA",    # 表格边框
    "line": "1.65",         # 行距
}


def _inline_md(s: str) -> str:
    s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               rf'<a href="\2" style="color:{KLEIN["fg"]};">\1</a>', s)
    return s


def _render_table(rows: list[str]) -> str:
    def cells(r: str) -> list[str]:
        return [c.strip() for c in r.strip().strip("|").split("|")]
    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if len(rows) > 2 else []
    th = "".join(f'<th style="border:1px solid {KLEIN["border"]};padding:4px 6px;'
                 f'background:{KLEIN["hbg"]};color:{KLEIN["fg"]};font-weight:bold;'
                 f'text-align:left;">{_inline_md(c)}</th>' for c in head)
    trs = []
    for r in body:
        tds = "".join(f'<td style="border:1px solid {KLEIN["border"]};'
                      f'padding:4px 6px;color:{KLEIN["fg"]};">'
                      f'{_inline_md(c)}</td>' for c in r)
        trs.append(f"<tr>{tds}</tr>")
    return (f'<table style="border-collapse:collapse;width:100%;'
            f'font-size:{KLEIN["size"]};margin:6px 0;">'
            f"<thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>")


def md_to_html(md: str) -> str:
    """轻量 Markdown→HTML（仅覆盖本工具自产结构，全部内联样式）。"""
    html: list[str] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("|"):  # 表格块
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            if len(tbl) >= 2:
                html.append(_render_table(tbl))
            continue
        if re.match(r"^-{3,}$", s):  # 分隔线
            html.append(f'<hr style="border:none;border-top:1px solid '
                        f'{KLEIN["border"]};margin:10px 0;">')
            i += 1
            continue
        if s.startswith("#"):  # 标题
            h = len(s) - len(s.lstrip("#"))
            txt = s.lstrip("#").strip()
            fs = {"1": KLEIN["size_h1"], "2": KLEIN["size_h2"]}.get(
                str(h), KLEIN["size_h3"])
            html.append(f'<div style="font-size:{fs};font-weight:bold;'
                        f'color:{KLEIN["fg"]};margin:8px 0 4px;">'
                        f"{_inline_md(txt)}</div>")
            i += 1
            continue
        if s.startswith(">"):  # 引用块
            qs = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                qs.append(lines[i].strip().lstrip(">").strip())
                i += 1
            html.append(f'<div style="color:{KLEIN["muted"]};font-size:'
                        f'{KLEIN["size"]};border-left:3px solid '
                        f'{KLEIN["border"]};padding-left:8px;margin:4px 0;">'
                        + "<br>".join(_inline_md(q) for q in qs) + "</div>")
            continue
        if re.match(r"^[-*]\s+", s):  # 无序列表
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            lis = "".join(f'<li style="margin:2px 0;">{_inline_md(x)}</li>'
                          for x in items)
            html.append(f'<ul style="margin:4px 0;padding-left:18px;'
                        f'color:{KLEIN["fg"]};">{lis}</ul>')
            continue
        if re.match(r"^\d+\.\s+", s):  # 有序列表
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            lis = "".join(f'<li style="margin:2px 0;">{_inline_md(x)}</li>'
                          for x in items)
            html.append(f'<ol style="margin:4px 0;padding-left:18px;'
                        f'color:{KLEIN["fg"]};">{lis}</ol>')
            continue
        # 普通段落：聚合连续普通行
        para = [s]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("|", "#", ">", "-", "*"))
                    or re.match(r"^\d+\.\s+", nxt) or re.match(r"^-{3,}$", nxt)):
                break
            para.append(nxt)
            i += 1
        html.append(f'<div style="margin:4px 0;color:{KLEIN["fg"]};">'
                    + "<br>".join(_inline_md(p) for p in para) + "</div>")
    return "".join(html)


def themed_html(title: str, content_md: str) -> str:
    body = md_to_html(content_md)
    return (
        f'<div style="background:{KLEIN["bg"]};padding:16px 14px;'
        f'border-radius:10px;font-size:{KLEIN["size"]};'
        f'line-height:{KLEIN["line"]};color:{KLEIN["fg"]};'
        f'font-family:-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,'
        f'sans-serif;">'
        f'<div style="font-size:{KLEIN["size_title"]};font-weight:bold;'
        f'color:{KLEIN["fg"]};margin-bottom:8px;">{title}</div>'
        f"{body}</div>")


# ================================================================ 模块⑤：推送通道

# pushplus 会员单条上限已提升至 10 万字（非会员 2 万字，不再按旧限额压缩）
CHANNEL_LIMITS = {"pushplus": 100000, "serverchan": 20000,
                  "wecom": 3600, "console": 0}  # 0 = 不限


def fit_for_channel(channel: str, content: str) -> tuple[str, str]:
    """按通道长度预算截断。返回 (内容, 截断说明或空串)。

    企业微信单条 markdown ≤4096 字节，超限整包必失败；
    截断时优先保住正文（AI 报告），从尾部明细往前收。
    """
    limit = CHANNEL_LIMITS.get(channel, 0)
    if not limit or len(content) <= limit:
        return content, ""
    budget = limit - 80
    cut = content.rfind("\n", 0, budget)
    if cut < budget * 0.5:  # 没有合适换行点才硬切
        cut = budget
    trimmed = (content[:cut].rstrip()
               + f"\n\n> ⚠️ 内容超出 {channel} 单条上限，尾部明细已省略"
                 "（完整内容见 GitHub Actions 运行日志）")
    return trimmed, f"已按 {limit} 字截断"


def push_pushplus(title: str, content: str, timeout: int,
                  theme: str = "default") -> str:
    token = env("PUSHPLUS_TOKEN")
    if not token:
        raise PushError("缺少 Secret：PUSHPLUS_TOKEN")
    title = title[:100]  # PushPlus 标题上限
    content, note = fit_for_channel("pushplus", content)
    fields = {"token": token, "title": title}
    if theme == "klein":  # 浅灰底 + 克莱因蓝 + 小两号（template=html）
        fields.update({"content": themed_html(title, content),
                       "template": "html"})
    else:
        fields.update({"content": content, "template": "markdown"})
    status, body = http_post_form(PUSHPLUS_URL, fields, timeout)
    code = None
    try:
        code = json.loads(body).get("code")
    except json.JSONDecodeError:
        pass
    if status == 200 and code == 200:
        return "发送成功" + (f"（{note}）" if note else "")
    raise PushError(f"PushPlus 返回异常（HTTP {status}）：{body[:400]}")


def push_wecom(title: str, content: str, timeout: int) -> str:
    key = env("WECOM_KEY")
    if not key:
        raise PushError("缺少 Secret：WECOM_KEY")
    content, note = fit_for_channel("wecom", content)
    payload = {"msgtype": "markdown",
               "markdown": {"content": f"**{title}**\n\n{content}"}}
    status, body = http_post_json(f"{WECOM_URL}?key={key}", payload, timeout=timeout)
    try:
        errcode = json.loads(body).get("errcode")
    except json.JSONDecodeError:
        errcode = None
    if status == 200 and errcode == 0:
        return "发送成功" + (f"（{note}）" if note else "")
    raise PushError(f"企业微信机器人返回异常（HTTP {status}）：{body[:400]}")


def push_serverchan(title: str, content: str, timeout: int) -> str:
    sendkey = env("SERVERCHAN_SENDKEY")
    if not sendkey:
        raise PushError("缺少 Secret：SERVERCHAN_SENDKEY")
    content, note = fit_for_channel("serverchan", content)
    status, body = http_post_form(SERVERCHAN_URL.format(sendkey=sendkey),
                                  {"title": title, "desp": content}, timeout)
    try:
        code = json.loads(body).get("code")
    except json.JSONDecodeError:
        code = None
    if status == 200 and code == 0:
        return "发送成功" + (f"（{note}）" if note else "")
    raise PushError(f"Server酱返回异常（HTTP {status}）：{body[:400]}")


def push_console(title: str, content: str, timeout: int) -> str:  # noqa: ARG001
    log("----- console 通道输出 begin -----")
    log(f"# {title}\n\n{content}")
    log("----- console 通道输出 end -----")
    return "已打印到日志"


PUSH_FUNCS = {
    "pushplus": push_pushplus, "wecom": push_wecom,
    "serverchan": push_serverchan, "console": push_console,
}


# ================================================================ 离线自检

YAHOO_SAMPLE = json.dumps({"chart": {"result": [{"meta": {
    "symbol": "2208.HK", "longName": "Xinjiang Goldwind Science & Technology",
    "regularMarketPrice": 16.80, "previousClose": 16.61,
    "regularMarketDayHigh": 16.92, "regularMarketDayLow": 16.55,
    "regularMarketVolume": 19923879, "regularMarketTime": 1754280000}}],
    "error": None}})

EASTMONEY_SAMPLE = json.dumps({"rc": 0, "data": {
    "f43": 16800, "f44": 16920, "f45": 16550, "f46": 16850,
    "f57": "02208", "f58": "金风科技", "f60": 16610,
    "f170": 114, "f47": 19923879}})

TENCENT_SAMPLE = ('v_hk02208="100~金风科技~02208~16.800~16.610~16.850~16.900'
                  '~16.550~16.800~19923879~335544320~3.51~2.18~16.920~16.550'
                  '~2026/08/04 16:08:07~0.190~1.140~3.52~2.05~38.69~184.94'
                  '~190.02~18.440~14.080~1.230~16.800~3.30~0.00~0.00~0~0~0~0~0";')


def selftest() -> int:
    """离线自检：三源解析器 + 交叉核验逻辑 + 全部模板构造。"""
    fails = 0

    def check(name: str, cond: bool):
        nonlocal fails
        log(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails += 1

    log("① 三源解析器")
    qa, qb, qc = (parse_yahoo(YAHOO_SAMPLE), parse_eastmoney(EASTMONEY_SAMPLE),
                  parse_tencent(TENCENT_SAMPLE))
    check("Yahoo 解析 16.80", qa.ok and abs(qa.price - 16.80) < 1e-9)
    check("东财 解析 ÷1000=16.80", qb.ok and abs(qb.price - 16.80) < 1e-9
          and qb.name == "金风科技")
    check("东财 涨跌幅 1.14%", abs((qb.change_pct or 0) - 1.14) < 1e-9)
    check("腾讯 解析 16.80", qc.ok and abs(qc.price - 16.80) < 1e-9)

    log("② 交叉核验")
    v = verify_quotes([qa, qb, qc])
    check("三源一致→可信", "三源一致" in v.verdict and v.n_excluded == 0)
    bad = Quote(source="东方财富", ok=True, name="金风科技", price=18.50,
                prev_close=16.61, change_pct=11.4)
    v2 = verify_quotes([qa, bad, qc])
    check("异常源被剔除", v2.n_excluded == 1 and "剔除" in v2.verdict)
    v3 = verify_quotes([qa, Quote(source="B", ok=False, error="HTTP 500"),
                        Quote(source="C", ok=False, error="timeout")])
    check("仅单源→未核验", "单源" in v3.verdict)
    v4 = verify_quotes([Quote(source="A", ok=False, error="x"),
                        Quote(source="B", ok=False, error="y"),
                        Quote(source="C", ok=False, error="z")])
    check("全失败→降级提示", "全部失败" in v4.verdict)
    md = market_block_md("02208", [qa, qb, qc], v)
    check("核验表含三源名", all(s in md for s in ("Yahoo", "东方财富", "腾讯")))

    log("③ 港股代码规整")
    check("normalize 2208→02208", normalize_hk_code("2208") == "02208")
    check("normalize 2208.HK→02208", normalize_hk_code("2208.HK") == "02208")

    log("③b 情绪模块（48h 窗口）")
    NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    s, l_, _ = score_text("金风科技中标海上风电订单，业绩大增")
    check("词典:利好", l_ == "利好" and s > 0)
    s, l_, _ = score_text("公司亏损并遭大股东减持")
    check("词典:利空", l_ == "利空" and s < 0)
    s, l_, _ = score_text("举行年度股东大会")
    check("词典:中性", l_ == "中性" and s == 0)
    s, l_, _ = score_text("Goldwind")
    check("词典:词边界防误判(Goldwind≠win)", l_ == "中性" and s == 0)
    g = parse_google_rss(GOOGLE_SAMPLE, 48, 10, NOW)
    check("Google:48h过滤剩2条", len(g) == 2)
    check("Google:利好识别", g[0].label == "利好")
    check("Google:利空识别(英文)", g[1].label == "利空")
    g3 = parse_google_rss(GOOGLE_SAMPLE, 8, 10, NOW)
    check("Google:8h窗口更严", len(g3) == 1)
    NOW_R = datetime.fromtimestamp(1754300000 + 3600, timezone.utc)
    r = parse_reddit(REDDIT_SAMPLE, 48, 10, NOW_R)
    check("Reddit:48h过滤剩2条", len(r) == 2)
    check("Reddit:子版与热度后缀", "r/stocks" in r[0].title)
    y = parse_youtube_atom(YOUTUBE_ATOM_SAMPLE, 48, 10, NOW)
    check("YouTube:48h过滤剩2条", len(y) == 2 and "youtu.be/abc123" in y[0].url)
    t0 = NOW.timestamp()
    tss = [int(t0 - 3600 * (120 - k)) for k in range(120)]
    closes = [15.5] * 71 + [16.0 + 0.01 * k for k in range(49)]  # 48h内缓涨
    vols = [1000] * 71 + [1500] * 49                              # 近48h放量
    mom = compute_price_momentum(closes, vols, tss, 48, NOW)
    check("量价:放量上涨→偏多", mom["ok"] and mom["label"] == "偏多"
          and mom["score"] > 0.3)
    mom2 = compute_price_momentum([16.5] * 71 + [16.0 - 0.02 * k for k in range(49)],
                                  vols, tss, 48, NOW)
    check("量价:缩量下跌→偏空", mom2["ok"] and mom2["label"] == "偏空")

    log("③c 快讯通用解析框架")
    ts_8am = datetime(2026, 8, 4, 8, tzinfo=timezone.utc).timestamp()
    schema_a = {"data": {"list": [
        {"title": "央行超预期降准释放流动性", "ctime": ts_8am},
        {"title": "某大宗商品库存平稳", "ctime": ts_8am - 60 * 60 * 100},
    ]}}
    ia = extract_items_generic(schema_a, "测试源A", 10, 48, NOW)
    check("通用:schema A 提取+48h过滤", len(ia) == 1 and ia[0].label == "利好")
    schema_b = {"errno": 0, "data": [
        {"content": "制造业 PMI 低于预期引发下跌担忧", "display_time": ts_8am * 1000},
        {"brief": "新能源招标再创纪录", "pubDate": "Mon, 04 Aug 2026 09:00:00 GMT"},
    ]}
    ib = extract_items_generic(schema_b, "测试源B", 10, 48, NOW)
    check("通用:schema B 毫秒时间+多键名", len(ib) == 2 and ib[0].label == "利空"
          and ib[1].label == "利好")
    schema_c = {"items": [{"title": "美联储维持利率不变",
                           "display_time": "2026-08-04 07:30:00"}]}
    ic = extract_items_generic(schema_c, "测试源C", 10, 48, NOW)
    check("通用:字符串时间解析", len(ic) == 1 and ic[0].age_h is not None)
    xq_sample = json.dumps({"data": {"items": [
        {"name": "金风科技", "code": "HK02208", "percent": 3.2,
         "current": 16.8, "increment": 8888},
        {"name": "某地产股", "code": "SH600000", "percent": -4.1},
    ]}})
    xq = parse_xueqiu_hot(xq_sample, NOW)
    check("雪球:涨跌幅→情绪", len(xq) == 2 and xq[0].label == "利好"
          and xq[1].label == "利空" and "关注增量" in xq[0].title)
    jin10_sample = ('var flash_newest = {"status":200,"data":['
                    '{"id":"1","time":"2026-08-04 09:00:00","type":0,'
                    '"data":{"content":"黄金突破历史新高","pic":""}}]};')
    m = re.search(r"[{\[]", jin10_sample)
    jj = json.loads(jin10_sample[m.start():].rstrip(";\n "))
    ij = extract_items_generic(jj, "金十数据", 10, 48, NOW)
    check("金十:JS壳+双层data", len(ij) == 1 and ij[0].label == "利好")
    fp = FeedPack(hours=48)
    fp.items["金十数据"] = ij
    fp.errors.append("法布财经 快讯：公开端点未确认，需提供快讯页地址后接入")
    fp.agg = {"n": 1, "pos": 1, "neg": 0, "neu": 0, "mean": 1.0,
              "n_sources": 1, "综合多头概率锚点": 50 + 45 * min(1.0, 1.0 * 3)}
    md_rule = render_feed_rule("金风科技", fp)
    check("feedscan:rule渲染含缺口行", "⚠️" in md_rule and "情绪温度" in md_rule)
    check("feedscan:附录含来源明细", "金十数据（1/10）" in render_feed_appendix(fp))

    log("③d 审计修复回归")
    check("查询词清洗:默认主题", _clean_query_topic(
        "金风科技(Goldwind) 每日简报") == "金风科技")
    check("查询词清洗:普通主题不动", _clean_query_topic("比亚迪") == "比亚迪")
    check("查询词清洗:空值兜底", _clean_query_topic("(空)") == "金风科技")

    log("③e 通道长度保护（防内容被截/整包拒发）")
    short_c, note = fit_for_channel("wecom", "短内容")
    check("限内原样", short_c == "短内容" and note == "")
    long_c = "报告头部\n" + "明细行\n" * 1500
    trim_c, note = fit_for_channel("wecom", long_c)
    check("超限截断+注释", len(trim_c) <= 3600 and "已省略" in trim_c
          and note.startswith("已按"))
    check("截断保住正文头部", trim_c.startswith("报告头部"))
    unlim_c, _ = fit_for_channel("pushplus", "x" * 5000)
    check("pushplus 5000字不限", len(unlim_c) == 5000)
    member_c, _ = fit_for_channel("pushplus", "x" * 50000)
    check("pushplus 会员5万字不限", len(member_c) == 50000)
    over_c, note = fit_for_channel("pushplus", "x" * 100500)
    check("pushplus 超10万才截断", len(over_c) <= 100000 and "已省略" in over_c
          and note.startswith("已按"))

    log("③f klein 主题渲染")
    h = md_to_html("## 标题\n\n| 因子 | 概率 |\n|---|---|\n| 基本面 | 65% |\n\n"
                   "- **要点**一\n> 备注：推断\n\n---\n\n1. 有序项")
    check("表格→table+表头底色", "<table" in h and KLEIN["hbg"] in h
          and "<th" in h and "<td" in h)
    check("加粗保留", "<strong>要点</strong>" in h)
    check("列表/引用/分隔线/有序表", "<ul" in h and KLEIN["muted"] in h
          and "border-left" in h and "<hr" in h and "<ol" in h)
    check("HTML 转义", "&lt;" in md_to_html("a<b>c"))
    full = themed_html("测试标题", "正文**加粗**")
    check("klein 三要素", KLEIN["bg"] in full and KLEIN["fg"] in full
          and "13px" in full)

    log("③g 主题集中化（一行改动全局生效）")
    bak = dict(KLEIN)
    try:
        KLEIN.update({"bg": "#111111", "fg": "#222222", "border": "#333333",
                      "hbg": "#444444", "size": "15px", "size_title": "17px",
                      "size_h1": "18px"})
        v = themed_html("T", "# H1\n\n| a | b |\n|---|---|\n| 1 | 2 |")
        check("改 bg 全局生效", "#111111" in v)
        check("改 fg 全局生效", "#222222" in v)
        check("改表格色生效", "#333333" in v and "#444444" in v)
        check("改字号档位生效", "18px" in v and "17px" in v
              and "font-size:15px" in v and "font-size:16px" not in v)
        src = open(__file__, encoding="utf-8").read()
        theme_zone = src.split("模块④b")[1].split("模块⑤")[0]
        theme_zone = re.sub(r"KLEIN = \{.*?\n\}", "", theme_zone, flags=re.S)
        # 注释行不参与扫描（文档里允许出现色值说明）
        theme_zone = "\n".join(l for l in theme_zone.splitlines()
                               if not l.lstrip().startswith("#"))
        hexes = set(re.findall(r"#[0-9A-Fa-f]{6}", theme_zone))
        check("主题区无绕过常量的硬编码色", hexes == set())
    finally:
        KLEIN.clear()
        KLEIN.update(bak)

    log("④ 全部模板可构造")
    for t in TEMPLATES:
        try:
            msgs = build_messages(t, "金风科技", "示例背景", "mid")
            check(f"模板 {t}", bool(msgs[1]["content"]))
        except Exception as e:  # noqa: BLE001
            check(f"模板 {t} 构造异常: {e}", False)
    check("analysis 校验器", validate_analysis(gen_by_rule("t", "analysis")))

    log(f"\n{'✅ 自检全部通过' if fails == 0 else f'❌ {fails} 项失败'}")
    return 1 if fails else 0


# ================================================================ 主流程

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="港股数据+ DeepSeek 分析 → 多通道推送",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="只生成不推送")
    p.add_argument("--check-only", action="store_true", help="只检查 Secrets")
    p.add_argument("--selftest", action="store_true", help="离线自检后退出")
    p.add_argument("--channel", default="pushplus", choices=CHANNELS)
    p.add_argument("--ai-provider", default="deepseek", choices=PROVIDERS,
                   dest="ai_provider")
    p.add_argument("--template", default="analysis", choices=TEMPLATES,
                   help="分析框架：默认 analysis（详细内容），"
                        + "/".join(TEMPLATES))
    p.add_argument("--topic", default="", help="分析标的/主题（或环境变量 TOPIC）")
    p.add_argument("--context", default="",
                   help="背景信息/复盘细节（或环境变量 CONTEXT）")
    p.add_argument("--hk-code", default="", dest="hk_code",
                   help="港股代码（如 02208），接入三源核验行情（或环境变量 HK_CODE）")
    p.add_argument("--risk", default="mid", choices=RISKS,
                   help="portfolio 模板的风险偏好档位")
    p.add_argument("--theme", default="", choices=["", "default", "klein"],
                   help="pushplus 通道主题：klein=浅灰底+克莱因蓝+小两号"
                        "（或环境变量 THEME）")
    p.add_argument("--hours", type=int, default=48,
                   help="sentiment 模板的数据窗口小时数（默认 48）")
    p.add_argument("--yt-channel", default="", dest="yt_channel",
                   help="YouTube 频道 handle（默认 @investtalk，或环境变量 YT_CHANNEL）")
    p.add_argument("--timeout", type=int, default=30)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()

    channel, provider, template = args.channel, args.ai_provider, args.template
    topic = args.topic or env("TOPIC") or DEFAULT_TOPIC
    user_context = args.context or env("CONTEXT")
    hk_code_raw = args.hk_code or env("HK_CODE")
    risk = args.risk or env("RISK") or "mid"
    theme = args.theme or env("THEME") or "default"
    targets = ALL_CHANNELS if channel == "all" else [channel]

    log("=" * 60)
    log(f"Manual Run - Goldwind PushPlus+DeepSeek  v{VERSION}")
    log(f"  模板: {template}({TEMPLATE_TITLES[template]})  通道: {channel}"
        f"  AI: {provider}  dry_run: {args.dry_run}  主题: {theme}")
    log(f"  主题: {topic}"
        + (f"  港股: {hk_code_raw}" if hk_code_raw else "")
        + (f"  风险档: {RISK_ZH[risk]}" if template == "portfolio" else ""))
    log("=" * 60)

    if args.check_only:
        return 0 if print_secret_report(channel, provider) else 1

    # ---------- 模块②：sentiment 模板先采集 4 源舆情 + 量价动量 ----------
    sent_pack, appendix_md, code4sent = None, "", None
    if template == "sentiment":
        code4sent = normalize_hk_code(hk_code_raw) if hk_code_raw else None
        log(f"\n📡 正在采集 {args.hours}h 窗口的多源舆情"
            f"（Google新闻/Reddit/moomoo/YouTube·investtalk）…")
        sent_pack = collect_sentiment(topic, code4sent, args.hours,
                                      min(args.timeout, 15), args.yt_channel)
        for name, items in sent_pack.items.items():
            agg = _src_agg(items)
            log(f"  ✅ {name}: {agg['n']} 条"
                f"（利好{agg['pos']}/利空{agg['neg']}/中性{agg['neu']}"
                f"，动量 {agg['mean']:+.2f}）")
        if sent_pack.momentum:
            log(f"  {'✅' if sent_pack.momentum.get('ok') else '❌'} 量价动量: "
                f"{sent_pack.momentum.get('detail') or sent_pack.momentum.get('label')}")
        for e in sent_pack.errors:
            log(f"  ⚠️  {e}")
        log(f"  → 综合多头概率锚点 ≈ "
            f"{sent_pack.agg.get('综合多头概率锚点', '—')}%")
        appendix_md = render_sentiment_appendix(sent_pack)
        user_context = sentiment_context(sent_pack)

    # ---------- 模块②b：feedscan 模板采集 12 源全市场快讯 ----------
    feed_pack = None
    if template == "feedscan":
        log(f"\n📡 正在采集 12 源全市场快讯（{args.hours}h 窗口）…")
        feed_pack = collect_feeds(args.hours, min(args.timeout, 12))
        for spec in FEED_SPECS:
            items = feed_pack.items.get(spec.name)
            if items:
                agg = _src_agg(items)
                log(f"  ✅ {spec.name}: {agg['n']} 条"
                    f"（利好{agg['pos']}/利空{agg['neg']}/中性{agg['neu']}"
                    f"，情绪 {agg['mean']:+.2f}）")
            else:
                err = next((e for e in feed_pack.errors
                            if e.startswith(spec.name)), "失败")
                log(f"  ⚠️  {err}")
        log(f"  → 全市场 {feed_pack.agg['n']} 条，情绪均值 "
            f"{feed_pack.agg['mean']:+.2f}，多头概率锚点 ≈ "
            f"{feed_pack.agg['综合多头概率锚点']}%")
        appendix_md = render_feed_appendix(feed_pack)
        user_context = feed_context(topic, feed_pack)

    # ---------- 模块①：三源取价 + 交叉核验（可选）----------
    data_md, context = "", user_context
    if hk_code_raw:
        code = normalize_hk_code(hk_code_raw)
        log(f"\n📥 正在从 3 个免费源获取 HK{code} 行情…")
        quotes = fetch_all(code, timeout=min(args.timeout, 15))
        ver = verify_quotes(quotes)
        for q in quotes:
            if q.ok:
                log(f"  ✅ {q.source}: {q.price:.3f}"
                    + (f"（{q.change_pct:+.2f}%）" if q.change_pct is not None else ""))
            else:
                log(f"  ❌ {q.source}: {q.error}")
        log(f"  → 核验结论：{ver.verdict}")
        data_md = market_block_md(code, quotes, ver)
        line = market_context_line(code, quotes, ver)
        context = (f"{line}\n\n{user_context}" if user_context else line)

    # ---------- 模块③：内容生成 ----------
    try:
        if provider == "rule":
            if template == "sentiment" and sent_pack is not None:
                content = render_sentiment_rule(topic, code4sent, sent_pack)
            elif template == "feedscan" and feed_pack is not None:
                content = render_feed_rule(topic, feed_pack)
            else:
                content = gen_by_rule(topic, template)
        else:
            key_env = ("DEEPSEEK_API_KEY" if provider == "deepseek"
                       else "OPENAI_API_KEY")
            key = env(key_env)
            if not key:
                raise PushError(f"缺少 Secret：{key_env}（ai_provider={provider} 必需）")
            messages = build_messages(template, topic, context, risk)
            if provider == "deepseek":
                content = chat_completion(DEEPSEEK_URL, key, "deepseek-chat",
                                          messages, TEMPLATE_MAX_TOKENS[template],
                                          args.timeout)
            else:
                base = env("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
                content = chat_completion(
                    f"{base.rstrip('/')}/chat/completions", key, "gpt-4o-mini",
                    messages, TEMPLATE_MAX_TOKENS[template], args.timeout)
    except PushError as e:
        if args.dry_run and "缺少 Secret" in str(e):
            log(f"⚠️  {e}")
            log("⚠️  dry-run 模式：降级使用 rule 模板继续演示管线")
            content = gen_by_rule(topic, template)
        else:
            log(f"❌ 内容生成失败：{e}")
            return 1

    if template == "analysis" and provider != "rule" \
            and not validate_analysis(content):
        content += "\n\n> ⚠️ 本次模型输出未通过框架格式校验，以上为原始返回，仅供参考。"
    if data_md:
        content += "\n\n" + data_md
    if appendix_md:
        content += "\n\n" + appendix_md

    now = datetime.now(CST).strftime("%m-%d %H:%M")
    title = f"{topic}·{TEMPLATE_TITLES[template]}（{now}）"
    log("\n📝 生成的内容：")
    log("-" * 60)
    log(f"# {title}\n\n{content}")
    log("-" * 60)

    # ---------- dry-run ----------
    if args.dry_run:
        log("\n🧪 dry-run：跳过真实推送。各通道 Secret 就绪情况：")
        for ch in targets:
            missing = [n for n in required_secrets(ch, "rule") if not env(n)]
            log(f"  {'⚠️ ' if missing else '✅'} {ch}: "
                + (f"缺少 {', '.join(missing)}" if missing else "就绪"))
        log("\n✅ dry-run 完成。去掉 --dry-run 即为真实推送。")
        return 0

    # ---------- 模块⑤：真实推送 ----------
    if theme != "default" and any(ch != "pushplus" for ch in targets):
        log("ℹ️  主题样式仅作用于 pushplus 通道（企微/Server酱不支持换肤）")
    results: dict[str, str] = {}
    failures = 0
    for ch in targets:
        log(f"\n📤 正在通过 {ch} 推送…")
        try:
            if ch == "pushplus":
                results[ch] = push_pushplus(title, content, args.timeout,
                                            theme=theme)
            else:
                results[ch] = PUSH_FUNCS[ch](title, content, args.timeout)
            log(f"  ✅ {ch}: {results[ch]}")
        except PushError as e:
            results[ch] = f"失败：{e}"
            failures += 1
            log(f"  ❌ {ch}: {e}")

    log("\n===== 推送结果汇总 =====")
    for ch, r in results.items():
        log(f"  {'❌' if r.startswith('失败') else '✅'} {ch}: {r}")
    if failures:
        log(f"\n❌ 共 {failures}/{len(targets)} 个通道失败（详见上方日志）")
        return 1
    log("\n✅ 全部通道推送成功，请到微信查收。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
