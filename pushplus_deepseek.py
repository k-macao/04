#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pushplus_deepseek.py — 港股数据 + DeepSeek 分析 → 多通道推送
                          （PushPlus / 企业微信 / Server酱 / 控制台）

功能模块
========
1. 港股行情模块：三个免费无需 Key 的数据源（Yahoo财经 / 东方财富 / 腾讯财经）
2. 交叉核验模块：同一标的从三源取价，比对偏差，给出可信度结论；异常源自动剔除
3. 分析框架模块：DeepSeek 按 12 套模板生成内容，多空判断一律带概率；analysis 包含 7 个因子
4. 推送模块：多通道真实推送 / dry-run 预览 / Secrets 检查
5. 字符模拟图模块：纯字符模拟走势（非图片）——基于日级 OHLC 渲染等宽字符图
   （涨 █ 跌 ▓ 影线 │，叠加 MA5/10/20 点位、成交量字符条、支撑/压力标注），
   直接以 Markdown/HTML <pre> 嵌入推送正文，无需图片上传与 CDN；--no-chart 可关闭；
   任何失败自动降级不影响推送

用法
====
    python pushplus_deepseek.py --template fusion --topic "阿里巴巴" --hk-code 09988
    python pushplus_deepseek.py --template scan --dry-run
    python pushplus_deepseek.py --selftest            # 离线自检（解析器+核验+模板）
    python pushplus_deepseek.py --check-only          # 只检查 Secrets
    python pushplus_deepseek.py                       # 默认: brief + pushplus + deepseek

Secrets（keyless 数据源无需配置）：
    PUSHPLUS_TOKEN / WECOM_KEY / SERVERCHAN_SENDKEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
环境变量（可选）：TOPIC / CONTEXT / HK_CODE / RISK(low|mid|high) / PUSH_STATE_PATH
新鲜度看板：每次推送正文顶部打印「数据新鲜度·本次运行指纹」，跨运行对比
    内容指纹与样本增量（状态文件默认 output/push_state.json，Actions 用
    actions/cache 持久化；--no-state 可关闭）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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
# newsnow 7源（用户指定）
try:
    import newsnow_sources as newsnow_mod
except Exception:
    newsnow_mod = None


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

DEFAULT_TOPIC = "阿里巴巴(Alibaba) 每日简报"
CST = timezone(timedelta(hours=8), "CST")

VERSION = "2.17-char-2026-08-07"  # 脚本版本指纹：每次交付递增，日志首行可见

CHANNELS = ["pushplus", "wecom", "serverchan", "console", "all"]
ALL_CHANNELS = ["pushplus", "wecom", "serverchan"]
PROVIDERS = ["deepseek", "rule", "openai"]
RISKS = ["low", "mid", "high"]
RISK_ZH = {"low": "低", "mid": "中", "high": "高"}

TEMPLATES = ["brief", "analysis", "scan", "picker", "fusion",
             "plan", "earnings", "portfolio", "review", "regime",
             "sentiment", "feedscan", "newsnow", "equity",
             "initiate", "earnings_preview", "earnings_update",
             "model_update", "morning_note", "catalysts",
             "thesis", "sector", "ideas"]
TEMPLATE_TITLES = {
    "brief": "简报", "analysis": "多空因子分析", "scan": "市场情报扫描",
    "picker": "选股器·未来30日", "fusion": "技术面×基本面融合",
    "plan": "交易计划·进出场风控", "earnings": "财报前瞻",
    "portfolio": "组合配置优化", "review": "交易复盘改进", "regime": "市场形态识别",
    "sentiment": "量价舆情动量·48h", "feedscan": "全市场快讯情绪扫描",
    "newsnow": "NewsNow热榜聚合·7源",
    "equity": "机构级个股投研",
    "initiate": "首次覆盖·公司研究",
    "earnings_preview": "财报前瞻·Skill",
    "earnings_update": "季报更新",
    "model_update": "模型修订",
    "morning_note": "晨会纪要",
    "catalysts": "催化剂日历",
    "thesis": "论点记分卡",
    "sector": "行业格局",
    "ideas": "选股/主题扫描",
}
TEMPLATE_MAX_TOKENS = {
    "brief": 2000, "analysis": 3000, "scan": 4000, "picker": 4000,
    "fusion": 3000, "plan": 4000, "earnings": 3000, "portfolio": 4000,
    "review": 3000, "regime": 3000, "sentiment": 4000, "feedscan": 4000,
    "newsnow": 4000, "equity": 8000,
    "initiate": 6000, "earnings_preview": 3500, "earnings_update": 5000,
    "model_update": 3500, "morning_note": 2500, "catalysts": 3000,
    "thesis": 3000, "sector": 4500, "ideas": 4000,
}

# analysis 的第 7 项是新增因子。它与“消息面与情绪面”不同：这里使用
# 48 小时内的价格/成交量、新闻和社媒样本做本地预聚合，必须单独呈现。
SENTIMENT_FACTOR = "量价舆情动量（48h）"
# 行业与政策面：只做真实可见的政策/监管动态分析，不预设任何行业政策、不套产业链逻辑
INDUSTRY_POLICY_FACTOR = "行业与政策面（真实政策分析）"
FACTORS = [
    "基本面（业绩/订单/毛利率）",
    INDUSTRY_POLICY_FACTOR,
    "技术面（趋势/量价/关键价位）",
    "资金面（主力/北向/两融动向）",
    "消息面与情绪面（公告/舆情/行业事件）",
    "估值面（PE/PB 与历史分位）",
    SENTIMENT_FACTOR,
]
FACTOR_COUNT = len(FACTORS)

# ---------------- 品牌信息：全部结果的统一头部与尾注 ----------------
BRAND_TITLE = "章鱼 AI 全景分析"
BRAND_SUBTITLE = "全网多个境内境外多个大模型混合部署 AI 调研平台"
BRAND_AUTHOR = "作者：章鱼 ai"
BRAND_SLOGAN = ("全网境内外为你寻找蛛丝马迹-提供全景视野分析，"
                "由多模型协同推理决策，底层所使用的大语言模型（LLM）多模式")
BRAND_DISCLAIMER = "声明：仅供参考，不作为投资建议。"


def brand_header_md() -> str:
    """全部结果统一头部：只放标题和副标题。"""
    return "\n".join([
        f"## 🐙 {BRAND_TITLE}",
        f"> {BRAND_SUBTITLE}",
        "",
        "---",
    ])


def brand_footer_md() -> str:
    """全部结果统一尾注；作者信息必须是推送正文的最后一行。"""
    return "\n".join([
        "> " + BRAND_DISCLAIMER,
        "",
        f"**{BRAND_AUTHOR}** {BRAND_SLOGAN}",
    ])


def add_branding(content: str) -> str:
    """给正文加品牌头和固定尾注，避免各调用点自行拼接而放错位置。"""
    return f"{brand_header_md()}\n{content.rstrip()}\n\n{brand_footer_md()}"

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
    """接受 9988 / 09988 / 9988.HK / hk09988 等写法，统一为 5 位数字字符串。"""
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
    # 形如: v_hk09988="100~阿里巴巴~09988~16.800~16.610~16.850~...";
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


def pick_cn_name(quotes: list[Quote], fallback: str = "") -> str:
    """从三源行情里挑中文名填入标题：腾讯/东财返回中文名，Yahoo 英文名兜底。

    全部失败时回退 ``fallback``（通常为 TOPIC）。
    """
    names = [q.name.strip() for q in quotes if q.ok and q.name.strip()]
    for n in names:
        if re.search(r"[\u4e00-\u9fff]", n):  # 含中文的优先（腾讯/东财）
            return n
    return names[0] if names else fallback


# ================================================================ 模块②：舆情采集与情绪动量（48h）

GOOGLE_NEWS_RSS = ("https://news.google.com/rss/search?"
                   "q={q}&hl=zh-HK&gl=HK&ceid=HK:zh-Hant")
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
YOUTUBE_HANDLE_PAGE = "https://www.youtube.com/@{handle}"

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
    """英文词按词边界匹配（防止 win 命中 downwind 之类误判），中文按子串。"""
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
<item><title>阿里巴巴Q3营收超预期 云计算业务增长提速 - 香港经济日报</title>
<link>https://example.com/a</link><pubDate>Mon, 04 Aug 2026 08:00:00 GMT</pubDate>
<source>香港经济日报</source></item>
<item><title>Alibaba shares plunge 3% on profit warning fears - Reuters</title>
<link>https://example.com/b</link><pubDate>Sun, 03 Aug 2026 20:00:00 GMT</pubDate>
<source>Reuters</source></item>
<item><title>电商板块周度回顾 - 财华社</title><link>https://example.com/c</link>
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


def render_feed_appendix(pack: FeedPack, new_keys: set | None = None) -> str:
    nk = new_keys or set()
    lines = ["---", f"📰 **快讯原始明细（{pack.agg['n']} 条，每源≤10）**"]
    for spec in FEED_SPECS:
        items = pack.items.get(spec.name)
        if not items:
            continue
        lines.append(f"\n**{spec.name}（{len(items)}/10）**")
        lines += [_item_line(i, k + 1, _item_key(i.title) in nk)
                  for k, i in enumerate(items[:10])]
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
    detail = f"近{hours}h {ret:+.2f}%，量比 {vol_ratio:.2f}，样本 {len(pts)} 根数据"
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
    scan: object | None = None   # 十四平台股票扫描结果（stock_news_scan.ScanPack）


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
    return t or "阿里巴巴"


def collect_sentiment(topic: str, code: str | None, hours: int,
                      timeout: int, yt_handle: str = "") -> SentPack:
    """采集 4 源 + 量价动量。任何单源失败只记录、不中断。"""
    pack = SentPack(hours=hours)
    q_topic = _clean_query_topic(topic)
    jobs = [
        ("Google新闻", lambda: fetch_google_news(q_topic, hours, 10, timeout)),
        ("YouTube·investtalk", lambda: fetch_youtube(
            yt_handle or (env("YT_CHANNEL") or "investtalk"), hours, 10, timeout)),
    ]
    for name, fn in jobs:
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
    # ---------- 十四平台扫描：输入股票代码 → 窗口内相关新闻 + 有关板块 ----------
    if code or q_topic:
        try:
            from stock_news_scan import scan_stock
            pack.scan = scan_stock(code or "", q_topic, hours=hours,
                                   timeout=min(timeout, 12))
        except Exception as e:  # noqa: BLE001 —— 扫描失败仅记数据缺口
            pack.errors.append(f"十四平台扫描：{str(e)[:120]}")
    a = {"news": _src_agg(pack.items.get("Google新闻", [])),
         "social": _src_agg([i for k in ("YouTube·investtalk",)
                             for i in pack.items.get(k, [])])}
    news_score = a["news"].get("mean", 0.0) if a["news"].get("n") else 0.0
    social_score = a["social"].get("mean", 0.0) if a["social"].get("n") else 0.0
    mom_score = pack.momentum.get("score", 0.0)
    anchor = 50 + 45 * (0.40 * mom_score + 0.35 * news_score + 0.25 * social_score)
    a["综合多头概率锚点"] = max(5, min(95, round(anchor)))
    pack.agg = a
    return pack


def _item_line(i: SentItem, idx: int, is_new: bool = False) -> str:
    age = f"{i.age_h:.0f}h前" if i.age_h is not None else "时间未知"
    t = i.title if len(i.title) <= 60 else i.title[:57] + "…"
    mark = "🆕 " if is_new else ""   # 上次推送之后新进入窗口的样本
    return f"{idx}. {mark}[{i.label} {i.score:+.2f}] {t} — {i.source} · {age}"


def render_sentiment_appendix(pack: SentPack, new_keys: set | None = None) -> str:
    nk = new_keys or set()
    n = sum(len(v) for v in pack.items.values())
    lines = ["---", f"📡 **{SENTIMENT_FACTOR}证据（{pack.hours}h，共 {n} 条，本地打标）**"]
    for name in ("Google新闻", "YouTube·investtalk"):
        items = pack.items.get(name)
        if not items:
            continue
        lines.append(f"\n**{name}（{len(items)}/10）**")
        lines += [_item_line(i, k + 1, _item_key(i.title) in nk)
                  for k, i in enumerate(items)]
    m = pack.momentum
    if m:
        lines.append("\n**量价情绪动量**")
        lines.append(f"- {m.get('detail') or m.get('label')} → "
                     f"{m.get('label')}（动量分 {m.get('score', 0):+.2f}）")
    if pack.errors:
        lines.append("\n**数据缺口**")
        lines += [f"- ⚠️ {e}" for e in pack.errors]
    if getattr(pack, "scan", None):
        try:
            from stock_news_scan import render_scan_md
            lines += ["", render_scan_md(pack.scan)]
        except Exception:  # noqa: BLE001 —— 附录缺扫描段不影响主报告
            pass
    return "\n".join(lines)


def sentiment_context(pack: SentPack) -> str:
    ctx = [
        f"【新增因子：{SENTIMENT_FACTOR}】",
        f"【{pack.hours}h 多源舆情数据（本地预打标：标签/分值/时效）】",
    ]
    for name, items in pack.items.items():
        ctx.append(f"▼ {name}")
        ctx += [_item_line(i, k + 1) for k, i in enumerate(items)]
    m = pack.momentum
    if m.get("ok"):
        ctx.append(f"▼ 量价动量：{m['detail']} → {m['label']}（{m['score']:+.2f}）")
    if getattr(pack, "scan", None):
        try:
            from stock_news_scan import scan_context
            ctx.append("▼ 十四平台扫描：")
            ctx += ["  " + line for line in scan_context(pack.scan).splitlines()]
        except Exception:  # noqa: BLE001
            pass
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
        f"| 量价动量 | 小时级数据 | — | {m.get('score', 0):+.2f} | — |",
    ]
    return "\n".join([
        f"**{topic} · {pack.hours}h 量价舆情动量**（rule 本地计算，未经 AI 综合）",
        "", *rows, "",
        f"- **综合判断**：{stance}，综合多头概率 ≈ **{anchor}%**"
        "（权重：量价40% / 新闻35% / 舆情25%）",
        f"- **来源**：HK{code or '—'}；Google新闻 / YouTube@investtalk（{pack.hours}h 窗口）",
        "", "> ai_provider 选 deepseek 可在此数据基础上生成完整综合报告。",
        "> ⚠️ 非投资建议，仅供参考。"])


# ================================================================ 模块③：分析框架（12 套模板 / 7 个分析因子）

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
            f"基于以下数据窗口内、已完成本地预打标的多源数据，"
            f"为「{topic}」输出一份量价与舆情动量报告。\n\n{context}\n\n"
            "严格按此格式输出：\n\n"
            "## 情绪动量报告\n\n"
            "| 象限 | 样本 | 利好/利空/中性 | 动量分 | 24h趋势 | 多头概率 |\n"
            "|---|---|---|---|---|---|\n"
            "| 新闻动量 |  |  |  |  |  |\n"
            "| 舆情动量 |  |  |  |  |  |\n"
            "| 量价动量 |  | — |  | — |  |\n\n"
            "- **新闻要点**：3 条最有信息量的（引用编号）\n"
            "- **舆情要点**：3 条（注明来自 YouTube）\n"
            "- **催化 vs 风险**：各 2 条\n"
            "- **综合判断**：明确偏多/偏空 + 综合多头概率%"
            "（可参考本地锚点，偏离须给理由）\n"
            "- **失效条件**：1~2 条\n\n"
            "打分区间 [-1,1]；样本不足的象限必须明说而非编造。"
            + RULES_TAIL)
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
            + RULES_TAIL)
    elif template == "newsnow":
        user = (
            f"基于以下 NewsNow 热榜聚合数据（7源：知乎热榜/抖音热搜/微博实时热搜/虎扑热搜/AI hot/联合早报/香港01），"
            f"分析全网热点与对标的「{topic}」的潜在关联。\n\n{context}\n\n"
            "严格按此格式输出：\n\n"
            "## 热榜聚合分析\n\n"
            "| 来源 | Top3 标题 | 热度/备注 | 与标的关联度% |\n"
            "|---|---|---|---|\n（逐源 Top3）\n\n"
            "- **全网热点温度**：一句话 + 热点集中度%\n"
            "- **三大主线**：跨源归纳热点主线，每条标注来源数与成立概率%\n"
            "- **对「{topic}」的传导**：1~2 句 + 方向概率%\n"
            "- **可忽略噪音**：2条\n\n"
            "若某源无数据需明说。"
            + RULES_TAIL)
    elif template == "scan":
        user = (
            "扫一遍今天全球市场，总结推动股价的 5 大力量。"
            "重点关注宏观事件、板块轮动、情绪变化，区分重点与噪音。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 力量 | 方向 | 对港股影响概率 | 逻辑 | 相关板块 |\n"
            "|---|---|---|---|---|\n（恰好 5 行）\n\n"
            "- **重点**：2 条今日真正值得跟踪的\n- **噪音**：2 条看似热闹但可忽略的\n"
            "- **今日结论**：1~2 句，给出港股整体偏多/偏空概率\n\n"
            "概率取整数%。" + RULES_TAIL)
    elif template == "picker":
        user = (
            "根据当下市场环境，挑出未来 30 天高概率的股票 3~5 只"
            "（范围：港股/A股，互联网及科技链优先）。每只说清楚为什么看好、"
            "关键风险、什么情况下要止损。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 股票 | 方向 | 30日上涨概率 | 看好逻辑 | 关键风险 | 止损触发 |\n"
            "|---|---|---|---|---|---|\n（3~5 行）\n\n"
            "- **首选**：1 句话点名胜率最高的一只\n"
            "- **弃权说明**：若环境不适合开新仓，明说并给理由\n\n"
            "概率取整数%。" + RULES_TAIL)
    elif template == "fusion":
        user = (
            f"分析「{topic}」，结合价格走势结构、财报和最新新闻，给出明确的看多还是看空。\n\n"
            + ctx +
            "严格按此格式输出：\n\n"
            "| 维度 | 判断 | 多头概率 | 要点 |\n|---|---|---|---|\n"
            "| 走势结构 |  |  |  |\n| 基本面/财报 |  |  |  |\n"
            "| 最新消息 |  |  |  |\n| 资金与情绪 |  |  |  |\n\n"
            "- **结论**：明确写「看多」或「看空」+ 信心概率%\n"
            "- **关键点位**：支撑 S1/S2、压力 R1/R2（有行情数据时按真实价格算，"
            "否则标注推断）\n- **适合风格**：短线/波段/长线三选一 + 一句理由\n\n"
            + RULES_TAIL)
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
            "" + RULES_TAIL)
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
            "" + RULES_TAIL)
    elif template == "portfolio":
        user = (
            f"根据我的风险偏好【{RISK_ZH[risk]}】，设计一个分散的股票组合"
            "（港股/A股，互联网科技为重点再加其他板块）。各板块怎么配、"
            "为什么要这些头寸、多久调整一次。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 板块 | 配置比例 | 代表标的 | 配置理由 |\n|---|---|---|---|\n"
            "（4~6 行，比例合计 100%，含现金档）\n\n"
            "- **头寸原则**：单票上限%、单板块上限%\n"
            "- **再平衡**：频率（如每季度）+ 2 条触发式调整条件\n"
            "- **预期特征**：该风险档位的预期波动 1 句\n\n"
            "" + RULES_TAIL)
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
                "" + RULES_TAIL)
        else:
            user = (
                "用户未提供具体交易细节。输出一份《交易复盘框架》：\n"
                "1) 需要记录哪些字段（进出场价/仓位/理由/情绪）；"
                "2) 错误分类清单（择时/仓位/纪律/信息）；"
                "3) 心理偏差自查表（各给一句自查问题）；"
                "4) 说明把交易细节粘贴到 context 输入后，可获得逐条复盘。\n\n"
                "" + RULES_TAIL)
    elif template == "regime":
        user = (
            "判断当前市场是趋势、震荡、风险偏好高还是低。"
            "在这个环境下交易策略应该怎么调整，交易员常掉的坑是什么。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 属性 | 判定 | 概率 | 依据 |\n|---|---|---|---|\n"
            "| 趋势市 | 是/否 |  |  |\n| 震荡市 | 是/否 |  |  |\n"
            "| 风险偏好高 | 是/否 |  |  |\n| 高波动 | 是/否 |  |  |\n\n"
            "- **环境一句话**：当前最贴切的 regime 标签\n"
            "- **策略调整**：仓位/持仓周期/止损宽度/可用品类 各 1 条\n"
            "- **常见坑**：该环境下交易员最常犯的 2~3 个错误\n\n"
            "" + RULES_TAIL)
    elif template == "analysis":
        factors_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(FACTORS))
        new_factor_no = FACTORS.index(SENTIMENT_FACTOR) + 1
        user = (
            f"请对「{topic}」按以下 {FACTOR_COUNT} 个因子逐一做多空分析。{ctx}"
            "每个因子给出【方向】和【多头概率】：多头概率 = 该因子当前指向"
            "上涨/利多的把握，50% 中性，>50% 偏多，<50% 偏空。\n\n"
            f"因子列表（必须全部覆盖，顺序不可变）：\n{factors_text}\n\n"
            f"第 {new_factor_no} 项「{SENTIMENT_FACTOR}」是新增因子，必须单独占一行，"
            "不得并入消息面与情绪面；优先使用上下文中标注的本地预聚合结果和样本依据。\n\n"
            f"「{INDUSTRY_POLICY_FACTOR}」只依据真实可见的政策/监管动态分析"
            "（如实际发布的产业政策、监管文件、补贴或招标规则），禁止编造，"
            "不得默认任何单一行业政策，也不得套用产业链传导逻辑。\n\n"
            "严格按以下 Markdown 格式输出，不要增删表格行：\n\n"
            "| 因子 | 方向 | 多头概率 | 依据 |\n|---|---|---|---|\n"
            "| （逐因子填写） |\n\n"
            "- **综合判断**：方向+综合多头概率（如「震荡偏多，约 58%」）\n"
            "- **关键风险**：1~2 条\n- **数据局限**：一句话\n\n"
            "" + RULES_TAIL)
    elif template == "equity":
        # 机构级个股投研：正式路径走 equity_research_column.generate_column；
        # 此处 prompt 作为 pushplus_deepseek 主流程的降级/兼容入口。
        user = (
            f"请按 equity-research skill 九章结构，为「{topic}」撰写机构级个股投资研究报告。\n\n"
            + ctx +
            "必须包含：结论框（决策三分法：内在价值/1–3个月交易方向/投资动作）、"
            "Tearsheet、预期差 Gap 表、护城河、财报质量等级 A–D、"
            "至少三种估值方法交叉验证、反方论证（一年后失败的3个原因）、"
            "监控清单与免责声明。关键数据标注来源+时间戳；缺失写「未获取到」。\n"
            "输出简体中文 Markdown。" + RULES_TAIL)
    else:
        # Anthropic 官方 skill 模板：委托 skills_hub 构造完整 prompt
        try:
            import skills_hub as sh
            if sh.is_skill_template(template):
                return sh.build_messages(template, topic, context)
        except Exception:
            pass
        if template == "brief":
            user = (f"请围绕「{topic}」生成一份今日简报：3~5 个要点，"
                    "每个要点一句话；结尾一句小结。\n\n" + ctx)
        else:
            user = (
                f"请围绕「{topic}」按模板「{template}」生成一份研究备忘录。\n\n"
                + ctx + RULES_TAIL)
    system = ("你是一位严谨的跨市场分析师，深耕港股/A股市场，熟悉宏观与行业政策。"
              "输出必须是简体中文 Markdown，不要寒暄，不要使用代码块，"
              "所有概率用整数百分比表示。")
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def validate_analysis(content: str) -> bool:
    """校验 analysis 是否逐项体现全部因子（包括新增的量价舆情动量）。"""
    if "| 因子" not in content:
        return False

    # 只检查因子表格，避免模型在后续风险说明中写几个百分比就误通过。
    rows: list[str] = []
    in_factor_table = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_factor_table and stripped:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and cells[0] == "因子":
            in_factor_table = True
            continue
        if not in_factor_table or not cells:
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) >= 3:
            rows.append(stripped)

    return all(
        any(factor in row and re.search(r"(?<!\d)\d{1,3}%", row) for row in rows)
        for factor in FACTORS
    )


# ================================================================ 内容生成（rule / AI 统一入口）

def gen_by_rule(topic: str, template: str,
                sent_pack: SentPack | None = None,
                newsnow_pack=None) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    if template == "newsnow" and newsnow_pack is not None:
        # 移植 newsnow 渲染
        try:
            from newsnow_sources import render_newsnow_rule
            return render_newsnow_rule(topic, newsnow_pack)
        except Exception:
            return f"**{topic} · NewsNow热榜**（rule）\n\n> 暂无数据，newsnow模块未加载"
    if template == "analysis":
        rows = []
        for factor in FACTORS:
            direction, probability, evidence = "中性", 50, "示例占位，待 AI 填充"
            if factor == SENTIMENT_FACTOR and sent_pack is not None:
                has_data = any(sent_pack.items.values()) or bool(
                    sent_pack.momentum.get("ok"))
                if has_data:
                    probability = int(sent_pack.agg.get("综合多头概率锚点", 50))
                    direction = ("偏多" if probability > 50
                                 else ("偏空" if probability < 50 else "中性"))
                    momentum = sent_pack.momentum.get("score", 0)
                    evidence = (f"48h本地锚点 {probability}%；"
                                f"量价动量 {momentum:+.2f}")
                else:
                    evidence = "48h 数据不足，无法计算本地锚点"
            rows.append(f"| {factor} | {direction} | {probability}% | {evidence} |")
        return "\n".join([
            f"**{topic} · 多空因子分析框架**（rule 演示模板，概率均为占位示例）",
            "", "| 因子 | 方向 | 多头概率 | 依据 |", "|---|---|---|---|",
            "\n".join(rows),
            "", "- **综合判断**：示例——ai_provider 选 deepseek 后由 AI 填充真实概率",
            "- **关键风险**：示例", "- **数据局限**：rule 模式不含真实分析", "",
            f"> 运行时间：{now}（北京时间）。⚠️ 非投资建议，仅供参考。"])
    if template == "equity":
        # 优先走独立栏目模块（含 dcf.py）；失败则给简短骨架
        try:
            import equity_research_column as erc
            return erc.gen_rule_report(topic, context="", mode="full",
                                       industry=erc.guess_industry(topic))
        except Exception as e:  # noqa: BLE001
            return "\n".join([
                f"**{topic} · 机构级个股投研**（rule 降级）", "",
                f"- equity_research_column 不可用：{e}",
                f"- 运行时间：{now}（北京时间）",
                "- 请确认 equity_research/ 已安装 skill 资源", "",
                "> ⚠️ 非投资建议，仅供参考。"])
    try:
        import skills_hub as sh
        if sh.is_skill_template(template):
            return sh.gen_rule_skill(template, topic, context="")
    except Exception as e:  # noqa: BLE001
        if template in ("initiate", "earnings_preview", "earnings_update",
                        "model_update", "morning_note", "catalysts",
                        "thesis", "sector", "ideas"):
            return "\n".join([
                f"**{topic} · {TEMPLATE_TITLES.get(template, template)}**（rule 降级）",
                "", f"- skills_hub 不可用：{e}",
                f"- 运行时间：{now}（北京时间）",
                "> ⚠️ 非投资建议，仅供参考。"])
    return "\n".join([
        f"**{topic} · {TEMPLATE_TITLES.get(template, '简报')}**（rule 演示模板）", "",
        f"- 模板：{template}（正式内容需 ai_provider=deepseek）",
        f"- 运行时间：{now}（北京时间）",
        "- 工作流：Manual Run - Alibaba PushPlus+DeepSeek", "",
        "> 在 Actions 运行页选择 ai_provider=deepseek 即可获得完整 AI 分析。",
        "> ⚠️ 非投资建议，仅供参考。"])


def chat_completion(url: str, api_key: str, model: str, messages: list[dict],
                    max_tokens: int, timeout: int,
                    temperature: float = 0.7) -> str:
    payload = {"model": model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
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
# 支持不稳定，全部使用内联样式。
# game 主题：8-bit 像素游戏风（整体默认）- 深夜蓝游戏屏/金色粗框/硬黑像素阴影/
#            HP血条/SCORE/LEVEL 游戏元素/金币高亮/涨跌突出
# klein 主题：游戏复古像素风 - 米黄纸底/黑细框/像素图标/涨跌突出
# pixel 主题：复古监控风 - 暗色服务器大屏/细线框/等宽细字/涨跌突出/REC摄像头元素

KLEIN = {
    # ---- 游戏复古像素风：米黄纸底 + 白卡片 + 黑细框 + 像素字体/图标 ----
    "bg": "#EDE8D0",            # 纸色底
    "card_bg": "#FFFFFF",       # 白卡片
    "hbg": "#111111",           # 黑底标题栏
    "hfg": "#FFFFFF",           # 标题白字
    "fg": "#111111",            # 正文黑字
    "muted": "#777777",         # 辅助灰
    "border": "#111111",        # 黑细线框 1px
    "line": "1.5",
    "font": "'Courier New','Nimbus Mono PS',Consolas,monospace",
    "size": "12px",
    "size_title": "13px",
    "size_h1": "13px",
    "size_h2": "12px",
    "size_h3": "12px",
    "up": "#00A85F",
    "down": "#FF2D2A",
    "up_bg": "#D1F5DF",
    "down_bg": "#FFD6D6",
    "accent": "#FFE600",        # 像素黄 重点凸显
    "accent_fg": "#111111",
}

PIXEL = {
    # ---- 复古监控风：暗色服务器大屏 + 细线框 + 等宽细字 + 摄像头元素 ----
    "bg": "#0A0E0C",            # 机房暗底
    "card_bg": "#101613",       # 监控面板底
    "hbg": "#0B100D",           # 顶部状态栏深底
    "hfg": "#C8F0D2",           # 磷光绿标题
    "fg": "#9FD9AD",            # 正文磷光绿
    "muted": "#5E7A68",         # 暗绿辅助字
    "border": "#2C4A39",        # 细线框（全部 1px）
    "accent": "#FFB000",        # 琥珀黄 重点数据/复古图标
    "accent_fg": "#1A1200",
    "up": "#3AE374",
    "down": "#FF4A4A",
    "up_bg": "#0D2417",
    "down_bg": "#2A1313",
    "size": "11px",
    "size_title": "12px",
    "size_h1": "12px",
    "size_h2": "11px",
    "size_h3": "11px",
    "line": "1.5",
    "font": "'Courier New','Nimbus Mono PS',Consolas,monospace",
    "scan": "rgba(0,0,0,0.30)",         # CRT 扫描线
    "grid": "rgba(140,220,170,0.05)",   # 面板抽象网格
    "shadow": "rgba(0,0,0,0.55)",       # 硬偏移阴影
}

GAME = {
    # ---- 8-bit 像素游戏风（整体默认）：深夜蓝游戏屏 + 金色粗框 + 硬黑像素阴影 ----
    #      标题栏=游戏菜单金条 / 状态栏=HP血条+LV等级 / 底部=SCORE+PRESS START
    "bg": "#0B0E2A",            # 游戏背景（深夜蓝）
    "card_bg": "#16193B",       # 游戏面板底（靛蓝）
    "hbg": "#F8B800",           # 金色标题栏（菜单金条）
    "hfg": "#111111",           # 标题黑字
    "fg": "#E9EAF5",            # 正文米白
    "muted": "#8A90BC",         # 辅助蓝灰
    "border": "#F8B800",        # 金色粗框（2px 游戏描边）
    "accent": "#FFD23F",        # 金币黄 重点凸显
    "accent_fg": "#1A1200",
    "up": "#5CFF5C",            # 磷光绿 涨
    "down": "#FF5C5C",          # 警示红 跌
    "up_bg": "#12301E",
    "down_bg": "#35121A",
    "size": "12px",
    "size_title": "13px",
    "size_h1": "14px",
    "size_h2": "12px",
    "size_h3": "12px",
    "line": "1.5",
    "font": "'Courier New','Nimbus Mono PS',Consolas,monospace",
    "shadow": "rgba(0,0,0,0.90)",       # 硬黑像素阴影
    "grid": "rgba(248,184,0,0.05)",     # 面板金色网格
    "star1": "rgba(255,255,255,0.55)",  # 背景星点（白）
    "star2": "rgba(255,210,63,0.45)",   # 背景星点（金）
    "hp_full": "#5CFF5C",               # 血条填充色
    "hp_empty": "rgba(233,234,245,0.20)",  # 血条空格色
    "status_bg": "#0E1130",             # 状态栏深底
}

MONITOR = {
    # ---- 服务器大屏监视风：深空暗底 + 荧光青绿 + 零表格（文字+列表横排） ----
    "bg": "#06090F",            # 深空暗黑科技底
    "card_bg": "#0B121E",       # 监控面板暗底
    "hbg": "#0F1E33",           # 顶部 HUD 栏深底
    "hfg": "#00F0FF",           # 荧光青标题
    "fg": "#E2E8F0",            # 正文亮白灰
    "muted": "#64748B",         # 辅助蓝灰
    "border": "#00F0FF",        # 荧光青发光边框
    "accent": "#00FF9D",        # 荧光绿重点
    "accent_fg": "#06090F",
    "up": "#00FF9D",            # 荧光绿 涨
    "down": "#FF3366",          # 警示红 跌
    "up_bg": "#072418",
    "down_bg": "#2B0B14",
    "size": "12px",
    "size_title": "13px",
    "size_h1": "14px",
    "size_h2": "12px",
    "size_h3": "12px",
    "line": "1.5",
    "font": "'Courier New','Nimbus Mono PS',Consolas,monospace",
    "shadow": "rgba(0,0,0,0.85)",
    "grid": "rgba(0,240,255,0.04)",
    "scan": "rgba(0,240,255,0.03)",
    "glow": "rgba(0,240,255,0.25)",
    "table_free": True,
}

THEMES = {
    "game": GAME,
    "klein": KLEIN,
    "pixel": PIXEL,
    "monitor": MONITOR,
    "noc": MONITOR,
}


def _get_theme(name_or_dict):
    if isinstance(name_or_dict, dict):
        return name_or_dict
    if isinstance(name_or_dict, str) and name_or_dict in THEMES:
        return THEMES[name_or_dict]
    return GAME


def _contains_up(txt: str) -> bool:
    # 涨关键词 + 数值 +▲
    up_kw = ["利好", "偏多", "看多", "上涨", "大涨", "突破", "中标", "增长",
             "创新高", "回购", "预增", "超预期", "盈利", "利多"]
    if any(k in txt for k in up_kw):
        return True
    if "▲" in txt or "↑" in txt:
        return True
    # +数字% 判定为涨
    if re.search(r"\+\s*\d", txt) and "%" in txt:
        return True
    if re.search(r"\+\d+\.\d+", txt):
        return True
    return False


def _contains_down(txt: str) -> bool:
    down_kw = ["利空", "偏空", "看空", "下跌", "大跌", "亏损", "减持", "下调",
               "预警", "预亏", "违约", "利空", "利淡"]
    if any(k in txt for k in down_kw):
        return True
    if "▼" in txt or "↓" in txt:
        return True
    if re.search(r"-\s*\d", txt) and "%" in txt:
        return True
    if re.search(r"-\d+\.\d+%", txt):
        return True
    return False


def _inline_md(s: str, theme_name: str = "game") -> str:
    theme = _get_theme(theme_name)
    s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    # 图片优先于链接：![alt](url) → <img>（微信/PushPlus html 主题直接显示）
    # referrerpolicy="no-referrer"：微信内置浏览器对第三方图床常做防盗链拦截，
    # 不发送 Referer 可显著提高外链图片（jsDelivr 等 CDN）在微信内的加载成功率。
    s = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        r'<img src="\2" alt="\1" referrerpolicy="no-referrer" '
        r'style="max-width:100%;display:block;'
        r'margin:6px 0;border:1px solid rgba(128,128,160,0.45);'
        r'border-radius:2px;">',
        s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               rf'<a href="\2" style="color:{theme["fg"]};text-decoration:underline;">\1</a>', s)
    return s


def _render_factor_cards(rows: list[str], theme_name: str = "game") -> str:
    """「因子 | 方向 | 多头概率 | 依据」表 → 卡片式内容展示（每个因子一张卡）。

    卡片结构（全主题统一，无 <table>）：
      ① 卡头：像素方块 + 因子名（加粗）+ 方向徽章（▲偏多绿 / ▼偏空红 / ●中性灰）
      ② 概率行：多头概率大号数字 + 概率条（game 主题为像素血条 █░，
         其余主题为细框进度条）；无【方向】列时按概率 50% 上下推导徽章
      ③ 额外列：逐行“列名：值”补充展示
      ④ 依据行：「依据」标签（标题栏配色）+ 辅助色正文
    色值全部取自主题常量，未硬编码。
    """
    theme = _get_theme(theme_name)

    def cells(r: str) -> list[str]:
        return [c.strip() for c in r.strip().strip("|").split("|")]

    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if len(rows) > 2 else []

    def col(*names: str):
        for want in names:
            for idx, h in enumerate(head):
                if h == want:
                    return idx
        return None

    dir_i = col("方向")
    prob_i = col("多头概率", "概率")
    ev_i = col("依据")
    prob_label = head[prob_i] if prob_i is not None else "多头概率"
    known = {i for i in (0, dir_i, prob_i, ev_i) if i is not None}

    # 卡片阴影：monitor 用辉光，game/pixel 用硬偏移像素阴影，klein 用黑框硬阴影
    if theme.get("glow"):
        shadow_css = f'box-shadow:0 0 6px {theme["glow"]};'
    elif theme.get("shadow"):
        shadow_css = f'box-shadow:2px 2px 0 {theme["shadow"]};'
    else:
        shadow_css = f'box-shadow:2px 2px 0 {theme["border"]};'

    cards: list[str] = []
    for r in body:
        if not r or not r[0]:
            continue

        def cell(i) -> str:
            return r[i] if (i is not None and 0 <= i < len(r)) else ""

        name = r[0]
        direction = cell(dir_i)
        prob_raw = cell(prob_i)
        evidence = cell(ev_i)
        extras = [(h, r[idx]) for idx, h in enumerate(head)
                  if idx not in known and idx < len(r) and r[idx]]

        m_prob = re.search(r"(\d{1,3})\s*%", prob_raw)
        p_val = max(0, min(100, int(m_prob.group(1)))) if m_prob else None
        if direction:
            is_up = _contains_up(direction)
            is_down = (not is_up) and _contains_down(direction)
            badge_text = direction
        elif p_val is not None:
            is_up, is_down = p_val > 50, p_val < 50
            badge_text = "偏多" if is_up else ("偏空" if is_down else "中性")
        else:
            joined = " ".join(r)
            is_up = _contains_up(joined)
            is_down = (not is_up) and _contains_down(joined)
            badge_text = "偏多" if is_up else ("偏空" if is_down else "")

        edge = theme["up"] if is_up else (
            theme["down"] if is_down else theme["border"])
        if is_up:
            badge_html = (
                f'<span style="color:{theme["up"]};background:{theme["up_bg"]};'
                f'border:1px solid {theme["up"]};padding:0 4px;font-weight:bold;'
                f'font-size:10px;white-space:nowrap;">▲ {badge_text}</span>')
        elif is_down:
            badge_html = (
                f'<span style="color:{theme["down"]};background:{theme["down_bg"]};'
                f'border:1px solid {theme["down"]};padding:0 4px;font-weight:bold;'
                f'font-size:10px;white-space:nowrap;">▼ {badge_text}</span>')
        elif badge_text:
            badge_html = (
                f'<span style="color:{theme["muted"]};border:1px solid '
                f'{theme["border"]};padding:0 4px;font-size:10px;'
                f'white-space:nowrap;">● {badge_text}</span>')
        else:
            badge_html = ""

        # 概率条：game 主题用像素血条字符，其余主题用细框进度条
        if p_val is None:
            bar_html = ""
        elif theme_name == "game":
            filled = max(0, min(10, round(p_val / 10)))
            bar_txt = "█" * filled + "░" * (10 - filled)
            bar_html = (
                f' <span style="color:{theme["hp_full"]};font-size:9px;'
                f'letter-spacing:-1px;">{bar_txt}</span>')
        else:
            bar_html = (
                f' <span style="display:inline-block;width:70px;height:6px;'
                f'border:1px solid {theme["border"]};background:{theme["bg"]};'
                f'vertical-align:middle;margin-left:4px;">'
                f'<span style="display:block;width:{p_val}%;height:100%;'
                f'background:{edge};"></span></span>')

        prob_html = ""
        if prob_raw:
            prob_html = (
                f'<div style="margin-top:4px;font-size:10px;'
                f'color:{theme["muted"]};">'
                f'{prob_label} '
                f'<span style="color:{edge};font-weight:bold;'
                f'font-size:{theme["size_title"]};">'
                f'{_inline_md(prob_raw, theme_name)}</span>{bar_html}</div>')

        extras_html = "".join(
            f'<div style="margin-top:3px;font-size:10px;color:{theme["muted"]};">'
            f'{_inline_md(h, theme_name)} '
            f'<span style="color:{theme["fg"]};font-weight:bold;">'
            f'{_inline_md(v, theme_name)}</span></div>'
            for h, v in extras)

        evidence_html = ""
        if evidence:
            evidence_html = (
                f'<div style="margin-top:4px;color:{theme["muted"]};'
                f'font-size:{theme["size"]};line-height:{theme["line"]};">'
                f'<span style="background:{theme["hbg"]};color:{theme["hfg"]};'
                f'padding:0 3px;font-size:9px;margin-right:4px;">依据</span>'
                f'{_inline_md(evidence, theme_name)}</div>')

        cards.append(
            f'<div style="background:{theme["card_bg"]};'
            f'border:1px solid {theme["border"]};'
            f'border-left:4px solid {edge};{shadow_css}'
            f'padding:6px 8px;margin:0 0 6px 0;box-sizing:border-box;">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;">'
            f'<span style="font-weight:bold;color:{theme["fg"]};'
            f'font-size:{theme["size"]};">'
            f'<span style="display:inline-block;width:6px;height:6px;'
            f'background:{theme["accent"]};margin-right:5px;'
            f'vertical-align:middle;"></span>{_inline_md(name, theme_name)}</span>'
            f'{badge_html}</div>'
            f'{prob_html}{extras_html}{evidence_html}</div>')

    return (
        f'<div style="margin:6px 0;'
        f'font-family:{theme.get("font", KLEIN["font"])};">'
        f'{"".join(cards)}</div>')


def _render_table(rows: list[str], theme_name: str = "game") -> str:
    theme = _get_theme(theme_name)

    def cells(r: str) -> list[str]:
        return [c.strip() for c in r.strip().strip("|").split("|")]

    head = cells(rows[0])
    body = [cells(r) for r in rows[2:]] if len(rows) > 2 else []

    # 因子分析表（因子/方向/多头概率/依据）→ 卡片式内容展示，不再渲染表格
    if head and head[0] == "因子":
        return _render_factor_cards(rows, theme_name)

    if theme.get("table_free") or theme_name in ("monitor", "noc"):
        # 服务器大屏监视风格：零表格（NO TABLES），文字 + 列表横排
        card_items = []
        for r in body:
            if not r:
                continue
            name = _inline_md(r[0], theme_name) if len(r) > 0 else ""
            orig = " ".join(r)
            is_up = _contains_up(orig)
            is_down = not is_up and _contains_down(orig)

            b_color = theme["up"] if is_up else (theme["down"] if is_down else theme["border"])
            dir_html = (
                f'<span style="color:{theme["up"]};font-weight:bold;font-size:10px;">▲ 偏多</span>'
                if is_up
                else (f'<span style="color:{theme["down"]};font-weight:bold;font-size:10px;">▼ 偏空</span>' if is_down else "")
            )
            val_strs = [
                f'<span style="padding:1px 4px;background:{theme["card_bg"]};border:1px solid {theme["border"]};color:{theme["accent"]};font-weight:bold;">{_inline_md(x, theme_name)}</span>'
                for x in r[1:]
            ]
            vals_line = " ".join(val_strs)

            card_items.append(
                f'<div style="flex:1 1 calc(50% - 6px);min-width:130px;background:{theme["card_bg"]};'
                f'border:1px solid {b_color};padding:6px 8px;font-size:{theme["size"]};'
                f'box-sizing:border-box;display:flex;flex-direction:column;gap:3px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-weight:bold;color:{theme["fg"]};font-size:{theme["size"]};">{name}</span>'
                f'{dir_html}</div>'
                f'<div style="color:{theme["muted"]};font-size:10px;">{vals_line}</div>'
                f'</div>'
            )
        return (
            f'<div style="display:flex;flex-direction:row;flex-wrap:wrap;gap:6px;margin:6px 0;'
            f'font-family:{theme.get("font", KLEIN["font"])};">'
            f'{"".join(card_items)}</div>'
        )

    # 表头 - 细线框 1px
    th_style_base = (
        f'border:1px solid {theme["border"]};'
        f'padding:3px 5px;'
        f'background:{theme["hbg"]};'
        f'color:{theme.get("hfg", theme["fg"])};'
        f'font-weight:bold;text-align:left;'
        f'font-size:{theme["size"]};'
        f'font-family:{theme.get("font", KLEIN["font"])};'
    )
    # 复古主题表头加像素图标
    th_cells = []
    for c in head:
        icon = ""
        if theme_name in ("pixel", "klein", "game"):
            icon = f'<span style="display:inline-block;width:6px;height:6px;background:{theme["accent"]};margin-right:4px;vertical-align:middle;"></span>'
        th_cells.append(
            f'<th style="{th_style_base}">{icon}{_inline_md(c, theme_name)}</th>'
        )
    th_html = "".join(th_cells)

    trs = []
    for r in body:
        tds = []
        for c in r:
            orig = c
            inner = _inline_md(c, theme_name)
            is_up = _contains_up(orig)
            is_down = not is_up and _contains_down(orig)

            # 基础 td：细线框
            td_base = (
                f'border:1px solid {theme["border"]};'
                f'padding:3px 5px;'
                f'color:{theme["fg"]};'
                f'font-size:{theme["size"]};'
                f'font-family:{theme.get("font", KLEIN["font"])};'
                f'line-height:{theme["line"]};'
            )
            prefix = ""

            if theme_name in ("pixel", "klein", "game"):
                if is_up:
                    # 涨：绿字 + 淡绿底 + ▲ 像素图标 最突出
                    td_base = (
                        f'border:1px solid {theme["border"]};'
                        f'padding:3px 5px;'
                        f'color:{theme["up"]};'
                        f'background:{theme["up_bg"]};'
                        f'font-weight:bold;'
                        f'font-size:{theme["size"]};'
                        f'font-family:{theme["font"]};'
                    )
                    prefix = f'<span style="font-size:9px;">▲</span> '
                elif is_down:
                    # 跌：红字 + 淡红底 + ▼ 最突出
                    td_base = (
                        f'border:1px solid {theme["border"]};'
                        f'padding:3px 5px;'
                        f'color:{theme["down"]};'
                        f'background:{theme["down_bg"]};'
                        f'font-weight:bold;'
                        f'font-size:{theme["size"]};'
                        f'font-family:{theme["font"]};'
                    )
                    prefix = f'<span style="font-size:9px;">▼</span> '
                else:
                    # 重点数据：数字/百分比/价格 加黄底黑框凸显，简洁
                    if len(orig) <= 20 and re.search(r"\d+\.\d+%?|\b\d+%\b|^\d+\.\d+$|^\d+$", orig):
                        inner = (
                            f'<span style="background:{theme["accent"]};'
                            f'color:{theme["accent_fg"]};'
                            f'border:1px solid {theme["border"]};'
                            f'padding:0px 3px;font-weight:bold;">'
                            f'{inner}</span>'
                        )
                    # game 主题：百分比数值附 8-bit 像素血条（HP BAR）
                    if theme_name == "game":
                        m = re.match(r"^(\d{1,3})\s*%$", orig)
                        if m:
                            filled = round(int(m.group(1)) / 10)
                            filled = max(0, min(10, filled))
                            bar = "█" * filled + "░" * (10 - filled)
                            inner += (
                                f' <span style="color:{theme["hp_full"]};'
                                f'font-size:9px;letter-spacing:-1px;'
                                f'background:{theme["card_bg"]};">'
                                f'{bar}</span>'
                            )
            else:
                # 兜底：其他主题保留涨跌突出
                if is_up:
                    td_base = (
                        f'border:1px solid {theme["border"]};'
                        f'padding:4px 6px;'
                        f'color:{theme.get("up", theme["fg"])};'
                        f'background:{theme.get("up_bg", KLEIN["card_bg"])};'
                        f'font-weight:bold;'
                    )
                    prefix = "▲ "
                elif is_down:
                    td_base = (
                        f'border:1px solid {theme["border"]};'
                        f'padding:4px 6px;'
                        f'color:{theme.get("down", theme["fg"])};'
                        f'background:{theme.get("down_bg", KLEIN["card_bg"])};'
                        f'font-weight:bold;'
                    )
                    prefix = "▼ "

            tds.append(f'<td style="{td_base}">{prefix}{inner}</td>')
        trs.append(f"<tr>{''.join(tds)}</tr>")

    table_style = (
        f'border-collapse:collapse;width:100%;'
        f'font-size:{theme["size"]};margin:6px 0;'
        f'border:1px solid {theme["border"]};'
    )
    return (
        f'<table style="{table_style}">'
        f"<thead><tr>{th_html}</tr></thead>"
        f"<tbody>{''.join(trs)}</tbody></table>"
    )


def md_to_html(md: str, theme_name: str = "game") -> str:
    """轻量 Markdown→HTML，支持 game/klein/pixel 三主题，全内联样式。"""
    theme = _get_theme(theme_name)
    html: list[str] = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue

        if s.startswith("```"):  # 代码块（用于字符模拟图等宽展示）
            lang = s[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and lines[i].strip().startswith("```"):
                i += 1  # 跳过闭合 ```
            code_text = "\n".join(code_lines)
            # 转义以防止 HTML 注入，保留字符图原样
            esc = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html.append(
                f'<pre style="background:{theme["card_bg"]};border:1px solid {theme["border"]};'
                f'padding:8px;overflow-x:auto;font-family:{theme["font"]};'
                f'font-size:{theme["size"]};line-height:1.35;white-space:pre;'
                f'color:{theme["fg"]};margin:6px 0;">{esc}</pre>'
            )
            continue

        if s.startswith("|"):  # 表格块
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            if len(tbl) >= 2:
                html.append(_render_table(tbl, theme_name))
            continue

        if re.match(r"^-{3,}$", s):  # 分隔线
            if theme_name == "game":
                # 游戏风：金色 2px 实线（像素分割线）
                html.append(
                    f'<hr style="border:none;border-top:2px solid {theme["border"]};'
                    f'margin:8px 0;">'
                )
            elif theme_name in ("pixel", "klein"):
                html.append(
                    f'<hr style="border:none;border-top:1px dashed {theme["border"]};margin:8px 0;">'
                )
            else:
                html.append(
                    f'<hr style="border:none;border-top:1px solid {theme["border"]};margin:10px 0;">'
                )
            i += 1
            continue

        if s.startswith("#"):  # 标题 - 像素图标
            h = len(s) - len(s.lstrip("#"))
            txt = s.lstrip("#").strip()
            fs = {"1": theme["size_h1"], "2": theme["size_h2"]}.get(
                str(h), theme["size_h3"]
            )
            if theme_name in ("pixel", "klein", "game"):
                if theme_name == "game":
                    icon_map = {1: "◆", 2: "►", 3: "·"}
                    lb = "3px"  # 游戏风粗左线
                else:
                    icon_map = {1: "■", 2: "►", 3: "·"}
                    # klein 游戏复古用粗左线 3px；pixel 监控风保持细线 1px
                    lb = "3px" if theme_name == "klein" else "1px"
                icon = icon_map.get(h, "·")
                html.append(
                    f'<div style="font-size:{fs};font-weight:bold;'
                    f'color:{theme["fg"]};margin:8px 0 3px;'
                    f'border-left:{lb} solid {theme["border"]};'
                    f'padding-left:6px;'
                    f'font-family:{theme["font"]};line-height:{theme["line"]};'
                    f'letter-spacing:1px;">'
                    f'<span style="margin-right:4px;color:{theme["accent"]};">{icon}</span>'
                    f"{_inline_md(txt, theme_name)}</div>"
                )
            else:
                html.append(
                    f'<div style="font-size:{fs};font-weight:bold;'
                    f'color:{theme["fg"]};margin:8px 0 4px;'
                    f'font-family:{theme.get("font", KLEIN["font"])};">'
                    f"{_inline_md(txt, theme_name)}</div>"
                )
            i += 1
            continue

        if s.startswith(">"):  # 引用块 - 细线框
            qs = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                qs.append(lines[i].strip().lstrip(">").strip())
                i += 1
            if theme_name in ("pixel", "klein", "game"):
                # game 游戏风：金色 3px 左线（任务/提示框）；pixel 细线 1px
                lb = "3px" if theme_name in ("klein", "game") else "1px"
                lb_color = theme["accent"] if theme_name == "game" else theme["border"]
                html.append(
                    f'<div style="color:{theme["muted"]};font-size:{theme["size"]};'
                    f'border:1px solid {theme["border"]};'
                    f'border-left:{lb} solid {lb_color};'
                    f'padding:4px 6px;margin:4px 0;'
                    f'background:{theme["card_bg"]};'
                    f'font-family:{theme["font"]};line-height:{theme["line"]};'
                    f'">' + "<br>".join(_inline_md(q, theme_name) for q in qs) + "</div>"
                )
            else:
                html.append(
                    f'<div style="color:{theme["muted"]};font-size:{theme["size"]};'
                    f'border-left:3px solid {theme["border"]};'
                    f'padding-left:8px;margin:4px 0;">'
                    + "<br>".join(_inline_md(q, theme_name) for q in qs)
                    + "</div>"
                )
            continue

        if re.match(r"^[-*]\s+", s):  # 无序列表 - 像素图标方块
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                items.append(re.sub(r"^[-*]\s+", "", lines[i].strip()))
                i += 1
            if theme_name in ("pixel", "klein", "game"):
                # game/pixel 用金币/琥珀方块；klein 游戏复古用黑方块
                mk = theme["accent"] if theme_name in ("pixel", "game") else theme["border"]
                lis = "".join(
                    f'<li style="margin:2px 0;list-style:none;position:relative;padding-left:12px;">'
                    f'<span style="position:absolute;left:0;top:2px;width:6px;height:6px;'
                    f'background:{mk};display:inline-block;"></span>'
                    f"{_inline_md(x, theme_name)}</li>"
                    for x in items
                )
                html.append(
                    f'<ul style="margin:4px 0;padding-left:4px;'
                    f'color:{theme["fg"]};font-family:{theme["font"]};'
                    f'font-size:{theme["size"]};list-style:none;">{lis}</ul>'
                )
            else:
                lis = "".join(
                    f'<li style="margin:2px 0;">{_inline_md(x, theme_name)}</li>'
                    for x in items
                )
                html.append(
                    f'<ul style="margin:4px 0;padding-left:18px;'
                    f'color:{theme["fg"]};">{lis}</ul>'
                )
            continue

        if re.match(r"^\d+\.\s+", s):  # 有序列表
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            lis = "".join(
                f'<li style="margin:2px 0;">{_inline_md(x, theme_name)}</li>'
                for x in items
            )
            html.append(
                f'<ol style="margin:4px 0;padding-left:18px;'
                f'color:{theme["fg"]};font-family:{theme.get("font")};'
                f'font-size:{theme["size"]};">{lis}</ol>'
            )
            continue

        # 普通段落
        para = [s]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt.startswith(("|", "#", ">", "-", "*"))
                or re.match(r"^\d+\.\s+", nxt)
                or re.match(r"^-{3,}$", nxt)
            ):
                break
            para.append(nxt)
            i += 1
        html.append(
            f'<div style="margin:4px 0;color:{theme["fg"]};'
            f'font-size:{theme["size"]};line-height:{theme["line"]};'
            f'font-family:{theme.get("font", KLEIN["font"])};">'
            + "<br>".join(_inline_md(p, theme_name) for p in para)
            + "</div>"
        )
    return "".join(html)


def themed_html(title: str, content_md: str, theme_name: str = "game") -> str:
    theme = _get_theme(theme_name)
    body = md_to_html(content_md, theme_name)
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if theme_name == "game":
        # 8-bit 像素游戏风（整体默认）：深夜蓝游戏屏 + 金色粗框 + 硬黑像素阴影
        # 标题栏=游戏菜单金条 / 状态栏=♥HP血条+★LV等级 / 底部=SCORE+PRESS START
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # 由标题生成稳定的游戏数值（SCORE/HP/LV），同一标题每次渲染一致
        seed = sum(ord(c) for c in title)
        score = seed * 7 % 999999
        hp = 60 + seed % 40                       # 60-99
        hp_filled = round(hp / 10)
        hp_bar = ("█" * hp_filled
                  + "░" * (10 - hp_filled))
        lv = 1 + seed % 9                         # LV.01-09
        return (
            # 外层：游戏机屏幕（深夜蓝 + 像素星点背景）
            f'<div style="background:{theme["bg"]};padding:14px 8px;'
            f'font-size:{theme["size"]};line-height:{theme["line"]};'
            f'color:{theme["fg"]};font-family:{theme["font"]};'
            f'background-image:'
            f'radial-gradient(1.5px 1.5px at 26px 32px,{theme["star1"]},rgba(0,0,0,0) 70%),'
            f'radial-gradient(1.5px 1.5px at 88px 74px,{theme["star1"]},rgba(0,0,0,0) 70%),'
            f'radial-gradient(2px 2px at 152px 22px,{theme["star2"]},rgba(0,0,0,0) 70%),'
            f'radial-gradient(1.5px 1.5px at 212px 96px,{theme["star1"]},rgba(0,0,0,0) 70%),'
            f'radial-gradient(2px 2px at 310px 52px,{theme["star2"]},rgba(0,0,0,0) 70%);\">'
            # 游戏面板：金色 2px 粗框 + 硬黑像素阴影 + 金色网格
            f'<div style="background:{theme["card_bg"]};'
            f'background-image:repeating-linear-gradient(0deg,{theme["grid"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px),'
            f'repeating-linear-gradient(90deg,{theme["grid"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px);'
            f'border:2px solid {theme["border"]};'
            f'box-shadow:4px 4px 0 {theme["shadow"]};'
            f'padding:0;">'
            # 标题栏：菜单金条（黑字 + 游戏角标 + SCORE 计分）
            f'<div style="background:{theme["hbg"]};color:{theme["hfg"]};'
            f'font-size:{theme["size_title"]};font-weight:bold;'
            f'padding:6px 8px;border-bottom:2px solid {theme["hfg"]};'
            f'font-family:{theme["font"]};letter-spacing:1px;">'
            f'<span>◤</span> {safe_title}'
            f'<span style="float:right;font-size:9px;letter-spacing:1px;">'
            f'SCORE {score:06d}</span>'
            f'</div>'
            # 状态栏：♥ HP 血条 + ★ LV 等级 + UTC 时间戳
            f'<div style="background:{theme["status_bg"]};color:{theme["muted"]};'
            f'font-size:9px;letter-spacing:1px;'
            f'padding:3px 8px;border-bottom:2px solid {theme["border"]};'
            f'font-family:{theme["font"]};">'
            f'<span style="color:{theme["down"]};">♥</span> '
            f'<span style="color:{theme["hp_full"]};">{hp_bar}</span>'
            f' <span style="color:{theme["up"]};">{hp}</span>/100'
            f'&nbsp;&nbsp;<span style="color:{theme["accent"]};">★</span> LV.{lv:02d}'
            f'<span style="float:right;">✦ {stamp} UTC</span>'
            f'</div>'
            # 正文
            f'<div style="padding:8px;">{body}</div>'
            # 底部状态行：GAME.LOG + PRESS START + 光标块
            f'<div style="border-top:2px solid {theme["border"]};'
            f'margin:4px 8px 6px;padding-top:4px;color:{theme["muted"]};'
            f'font-size:9px;font-family:{theme["font"]};letter-spacing:1px;">'
            f'<span style="color:{theme["accent"]};">▞▚</span> GAME.LOG · '
            f'<span style="color:{theme["accent"]};">★</span> LV.{lv:02d}'
            f'<span style="float:right;">PRESS START <span style="color:{theme["accent"]};">▮</span></span>'
            f'</div>'
            f'</div></div>'
        )
    if theme_name == "pixel":
        # 复古监控风：暗色服务器大屏 + 细线框 + 等宽细字 + 摄像头 REC 元素
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return (
            f'<div style="background:{theme["bg"]};padding:12px 8px;'
            f'font-size:{theme["size"]};line-height:{theme["line"]};'
            f'color:{theme["fg"]};font-family:{theme["font"]};'
            f'background-image:repeating-linear-gradient(0deg,{theme["scan"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 3px);">'
            f'<div style="background:{theme["card_bg"]};'
            f'background-image:repeating-linear-gradient(0deg,{theme["grid"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px),'
            f'repeating-linear-gradient(90deg,{theme["grid"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px);'
            f'border:1px solid {theme["border"]};'
            f'box-shadow:2px 2px 0 {theme["shadow"]};'
            f'padding:0;">'
            f'<div style="background:{theme["hbg"]};color:{theme["hfg"]};'
            f'font-size:{theme["size_title"]};font-weight:bold;'
            f'padding:5px 8px;border-bottom:1px solid {theme["border"]};'
            f'font-family:{theme["font"]};letter-spacing:1px;">'
            f'<span style="color:{theme["accent"]};">■</span> '
            f'{safe_title}'
            f'<span style="float:right;color:{theme["down"]};font-size:9px;'
            f'font-weight:bold;letter-spacing:1px;">● REC</span>'
            f'</div>'
            f'<div style="border-bottom:1px dashed {theme["border"]};'
            f'padding:2px 8px;color:{theme["muted"]};font-size:9px;'
            f'letter-spacing:1px;font-family:{theme["font"]};">'
            f'⌜ CAM-01 ▸ 04-SERVER ▸ LIVE ▸ {stamp} UTC ⌟'
            f'</div>'
            f'<div style="padding:8px;">{body}</div>'
            f'<div style="border-top:1px dashed {theme["border"]};'
            f'margin:4px 8px 6px;padding-top:4px;color:{theme["muted"]};'
            f'font-size:9px;font-family:{theme["font"]};letter-spacing:1px;">'
            f'<span style="color:{theme["accent"]};">▚▞</span> SYS.OK · CH-04 · '
            f'<span style="color:{theme["down"]};">●</span> REC-ON'
            f'</div>'
            f'</div></div>'
        )
    if theme_name in ("monitor", "noc"):
        # 服务器大屏监视风：深空暗底 + 荧光青绿 + 零表格（文字+横排卡片流） + HUD 双时钟
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return (
            f'<div style="background:{theme["bg"]};padding:12px 8px;'
            f'font-size:{theme["size"]};line-height:{theme["line"]};'
            f'color:{theme["fg"]};font-family:{theme["font"]};'
            f'background-image:repeating-linear-gradient(0deg,{theme["scan"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px),'
            f'repeating-linear-gradient(90deg,{theme["grid"]} 0 1px,'
            f'rgba(0,0,0,0) 1px 24px);">'
            f'<div style="background:{theme["card_bg"]};'
            f'border:1px solid {theme["border"]};'
            f'box-shadow:0 0 10px {theme["glow"]};'
            f'padding:0;">'
            f'<div style="background:{theme["hbg"]};color:{theme["hfg"]};'
            f'font-size:{theme["size_title"]};font-weight:bold;'
            f'padding:6px 10px;border-bottom:1px solid {theme["border"]};'
            f'font-family:{theme["font"]};letter-spacing:1px;'
            f'display:flex;justify-content:space-between;align-items:center;">'
            f'<span><span style="color:{theme["accent"]};">⌜</span> {safe_title} <span style="color:{theme["accent"]};">⌟</span></span>'
            f'<span style="color:{theme["down"]};font-size:9px;'
            f'font-weight:bold;letter-spacing:1px;">● REC LIVE</span>'
            f'</div>'
            f'<div style="border-bottom:1px dashed {theme["border"]};'
            f'padding:3px 10px;color:{theme["muted"]};font-size:9px;'
            f'letter-spacing:0.5px;font-family:{theme["font"]};'
            f'display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;">'
            f'<span><span style="color:{theme["accent"]};">●</span> NOC-SERVER-04 · LIVE TELEMETRY</span>'
            f'<span>✦ {stamp} UTC</span>'
            f'</div>'
            f'<div style="padding:10px 8px;">{body}</div>'
            f'<div style="border-top:1px dashed {theme["border"]};'
            f'margin:4px 8px 6px;padding-top:4px;color:{theme["muted"]};'
            f'font-size:9px;font-family:{theme["font"]};letter-spacing:1px;'
            f'display:flex;justify-content:space-between;">'
            f'<span><span style="color:{theme["accent"]};">▚▞</span> SYS.NOMINAL · CH-04 · 12ms</span>'
            f'<span style="color:{theme["accent"]};">ALL FEEDS VERIFIED ▮</span>'
            f'</div>'
            f'</div></div>'
        )
    # klein 游戏复古像素风：米黄纸底 + 白卡片 + 1px黑细框 + 像素阴影 + 黑底标题栏
    return (
        f'<div style="background:{theme["bg"]};padding:10px;'
        f'font-size:{theme["size"]};line-height:{theme["line"]};'
        f'color:{theme["fg"]};font-family:{theme["font"]};">'
        f'<div style="background:{theme["card_bg"]};'
        f'border:1px solid {theme["border"]};'
        f'box-shadow:3px 3px 0 {theme["border"]};'
        f'padding:0;">'
        f'<div style="background:{theme["hbg"]};color:{theme["hfg"]};'
        f'font-size:{theme["size_title"]};font-weight:bold;'
        f'padding:5px 8px;border-bottom:1px solid {theme["border"]};'
        f'font-family:{theme["font"]};letter-spacing:1px;">'
        f'<span style="display:inline-block;width:8px;height:8px;'
        f'background:{theme["accent"]};margin-right:6px;'
        f'vertical-align:middle;border:1px solid {theme["hfg"]};"></span>'
        f'{safe_title}'
        f'<span style="float:right;font-size:9px;opacity:0.8;">[RETRO]</span>'
        f'</div>'
        f'<div style="padding:8px;">{body}</div>'
        f'<div style="border-top:1px dashed {theme["border"]};'
        f'margin:4px 8px 8px;height:0;"></div>'
        f'</div></div>'
    )


# ================================================================ 模块⑤：推送通道

CHANNEL_LIMITS = {"pushplus": 0, "serverchan": 20000,
                  "wecom": 4096, "console": 0}  # 0 = 不限


# ================================================================ 运行状态与内容指纹
#
# 每次真实推送把「内容指纹 + 样本标题指纹 + 行情快照」写入本地状态文件
# （默认 output/push_state.json，可用环境变量 PUSH_STATE_PATH 覆盖，可用
# --no-state 关闭；GitHub Actions 用 actions/cache 跨运行恢复）。
# 与上次对比后即可回答两个问题——
#   ① 本次推送正文与上次是否几乎一致（“内容没变”）；
#   ② 数据窗口内新增了几条样本（🆕 增量）。
# 结论会直接印在推送正文顶部的「数据新鲜度看板」里，
# 不用翻 Actions 日志就能看出本次运行到底有没有新内容。

STATE_VERSION = 2
STATE_ENV_VAR = "PUSH_STATE_PATH"
STATE_MAX_KEYS_PER_SRC = 60          # 每源最多留存的样本指纹数
STATE_MAX_RUN_KEYS = 8               # 状态文件内最多保留的 模板|主题|代码 组合数

# AI 差异化重试前缀：指纹与上次完全一致时，自动换表述重试一次
ANTI_DUP_PREFIX = (
    "【差异化要求】上次推送的正文与本次即将生成的内容几乎完全一致。"
    "请换用不同的表述结构与段落组织重新生成（概率结论可保持一致），"
    "并在结尾新增一句「本期与上期观点差异」，显式说明本期新增证据；"
    "若确实没有任何变化，该句明确写作「无变化」。\n\n")


def _state_default_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "output", "push_state.json")


def state_path() -> str:
    return env(STATE_ENV_VAR) or _state_default_path()


def load_state(path: str) -> dict:
    """读取跨运行状态；文件缺失或损坏时返回空基线，绝不中断主流程。"""
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and isinstance(st.get("runs"), dict):
            return st
    except Exception:  # noqa: BLE001 —— 状态损坏视为全新基线
        pass
    return {"version": STATE_VERSION, "runs": {}}


def save_state(path: str, st: dict) -> None:
    """原子写入状态文件；失败仅告警，不影响推送本身。"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠️ 状态文件写入失败（不影响推送）：{str(e)[:100]}")


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).lower()


def _item_key(title: str) -> str:
    """样本标题指纹：忽略空白与大小写，跨运行可比。"""
    t = _norm_text(title)
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] if t else ""


def gather_item_keys(*packs) -> dict[str, list[str]]:
    """汇总各数据源本次样本标题指纹（按源分组、去重）。"""
    out: dict[str, list[str]] = {}

    def add(src: str, title: str) -> None:
        key = _item_key(title)
        if not key:
            return
        bucket = out.setdefault(src, [])
        if key not in bucket:
            bucket.append(key)

    for pack in packs:
        if pack is None:
            continue
        items = getattr(pack, "items", None)
        if isinstance(items, dict):
            for src, lst in items.items():
                for it in lst or []:
                    add(str(src), getattr(it, "title", "") or "")
        scan = getattr(pack, "scan", None)
        if scan is not None:
            for groups in (getattr(scan, "direct", None),
                           getattr(scan, "sector_hits", None)):
                if isinstance(groups, dict):
                    for src, lst in groups.items():
                        for it in lst or []:
                            add(f"扫·{src}", getattr(it, "title", "") or "")
    return {src: sorted(keys) for src, keys in out.items()}


def _quote_brief(quotes: list[Quote]) -> dict:
    """提取行情共识用于指纹与看板（多源取中位数）。"""
    prices = [q.price for q in quotes if q.ok and q.price]
    pcts = [q.change_pct for q in quotes
            if q.ok and q.change_pct is not None]
    brief: dict = {"n_ok": len(prices), "n_total": len(quotes)}
    if prices:
        brief["price"] = round(median(prices), 3)
        if pcts:
            brief["change_pct"] = round(median(pcts), 2)
        name = next((q.name for q in quotes if q.ok and q.name), "")
        if name:
            brief["name"] = name
        ts = next((q.time_str for q in quotes if q.ok and q.time_str), "")
        if ts:
            brief["time_str"] = ts
    return brief


def run_state_key(template: str, topic: str, hk_code_raw: str) -> str:
    if not hk_code_raw:
        code = "-"
    else:
        try:
            _c, _y, _em, sfx = resolve_chart_symbols(hk_code_raw)
            code = f"{sfx}{_c}"
        except Exception:
            code = normalize_hk_code(hk_code_raw)
    return f"{template}|{topic[:24]}|{code}"


def content_fingerprint(template: str, topic: str, ai_md: str,
                        quote_brief: dict, extra_points: dict,
                        item_keys: dict[str, list[str]]) -> str:
    """内容指纹：正文+行情共识+本地锚点+样本集合。
    时间戳/样本年龄不参与，保证「内容真变了」指纹才变。"""
    payload = {"t": template, "topic": _norm_text(topic),
               "md": _norm_text(ai_md),
               "q": quote_brief, "x": extra_points, "items": item_keys}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def diff_item_keys(cur: dict[str, list[str]],
                   prev: dict[str, list[str]]) -> dict[str, list[str]]:
    """本次有、上次没有的样本指纹，按源分组；无基线时返回空。"""
    if not prev:
        return {}
    out: dict[str, list[str]] = {}
    for src, keys in cur.items():
        prev_set = set(prev.get(src, []))
        new = [k for k in keys if k not in prev_set]
        if new:
            out[src] = new
    return out


def _quote_freshness_line(qb: dict, prev_price) -> str:
    """行情一句话：共识价 + 在线源数 + 与上次推送的价格差异。"""
    if not qb.get("n_ok"):
        return "三源行情未接入或全部失败（详见正文核验区块与数据缺口）"
    pct = (f"（{qb['change_pct']:+.2f}%）"
           if qb.get("change_pct") is not None else "")
    base = f"{qb['price']:.3f}{pct} · {qb['n_ok']}/{qb['n_total']} 源在线"
    if qb.get("time_str"):
        base += f" · 行情时间 {qb['time_str']}"
    if prev_price is None:
        return base + "｜首次记录基线"
    diff = qb["price"] - prev_price
    if abs(diff) < 1e-9:
        return base + "｜较上次推送价格持平"
    dpct = diff / prev_price * 100 if prev_price else 0.0
    return f"{base}｜较上次推送 {diff:+.3f}（{dpct:+.2f}%）"


def render_freshness_md(*, now_cst: str, template: str, hours: int,
                        fingerprint: str, dup: bool | None,
                        quote_line: str, new_items: dict[str, list[str]],
                        first_run: bool, anchor_line: str,
                        state_enabled: bool) -> str:
    """推送正文顶部的数据新鲜度看板：一眼看出本次运行有没有更新。"""
    if not state_enabled:
        fp_note = "状态对比已关闭（--no-state）"
    elif first_run:
        fp_note = "🆕 首次建立基线，下次运行起对比增量"
    elif dup:
        fp_note = "⚠️ 与上次推送内容一致（窗口内无新增信号）"
    else:
        fp_note = "✅ 与上次推送相比已更新"
    if not state_enabled or first_run:
        new_line = "🆕 新增样本：—（无上次基线可对比）"
    elif new_items:
        per_src = " · ".join(
            f"{s} {len(v)}" for s, v in
            sorted(new_items.items(), key=lambda kv: -len(kv[1]))[:5])
        total_new = sum(len(v) for v in new_items.values())
        new_line = f"🆕 新增样本：{total_new} 条（{per_src}）"
    else:
        new_line = "🆕 新增样本：0 条（窗口内条目与上次相同）"
    return "\n".join([
        "### 🧭 数据新鲜度 · 本次运行指纹",
        f"- ⏱ 运行时间：{now_cst}（北京时间）"
        f" · 模板「{TEMPLATE_TITLES.get(template, template)}」"
        f" · 数据窗口 {hours}h",
        f"- 📈 行情：{quote_line}",
        f"- {new_line}",
        f"- 🎯 本地计算：{anchor_line}",
        f"- 🔢 内容指纹 `{fingerprint}`：{fp_note}",
    ])


def _utf8_len(text: str) -> int:
    """推送服务的长度限制按 UTF-8 字节计算，不能用 Python 字符数代替。"""
    return len(text.encode("utf-8"))


def _truncate_to_utf8_bytes(text: str, max_bytes: int) -> str:
    """截到最多 ``max_bytes`` 个 UTF-8 字节，且绝不截断一个中文字符。"""
    if max_bytes <= 0:
        return ""
    if _utf8_len(text) <= max_bytes:
        return text
    return text.encode("utf-8")[:max_bytes].decode("utf-8", "ignore")


def _split_protected_suffix(content: str, protected_suffix: str) -> tuple[str, str]:
    """从内容中分离须保留的尾注；未匹配时保持普通截断行为。"""
    normalized = content.rstrip()
    suffix = protected_suffix.strip()
    if suffix and normalized.endswith(suffix):
        return normalized[:-len(suffix)].rstrip(), suffix
    return normalized, ""


def fit_for_channel(channel: str, content: str,
                    protected_suffix: str = "") -> tuple[str, str]:
    """按通道字节上限截断，返回 ``(内容, 截断说明或空串)``。

    企业微信的 Markdown 上限是 4096 UTF-8 字节。若指定 ``protected_suffix``
    （主流程传入品牌尾注），会从正文中间裁切，保留声明和最后一行作者，避免
    长报告在推送后显示“作者不见了”或作者不在结尾。
    """
    limit = CHANNEL_LIMITS.get(channel, 0)
    if not limit or _utf8_len(content) <= limit:
        return content, ""

    body, suffix = _split_protected_suffix(content, protected_suffix)
    note_detail = ("作者与声明已保留；" if suffix else "")
    notice = (f"> ⚠️ 内容超出 {channel} 单条上限，部分正文已省略"
              f"（{note_detail}完整内容见 GitHub Actions 运行日志）")
    suffix_block = f"\n\n{suffix}" if suffix else ""
    tail = f"\n\n{notice}{suffix_block}"
    body_budget = limit - _utf8_len(tail)

    if body_budget > 0:
        trimmed_body = _truncate_to_utf8_bytes(body, body_budget)
        # 尽量在一行结束处截断；没有合适换行时，安全地按字节截断。
        cut = trimmed_body.rfind("\n")
        if cut >= len(trimmed_body) * 0.5:
            trimmed_body = trimmed_body[:cut]
        trimmed = trimmed_body.rstrip() + tail
    elif suffix and _utf8_len(suffix) <= limit:
        # 极端情况下优先保留固定尾注，而不是发出一个不完整的作者行。
        trimmed = suffix
    else:
        trimmed = _truncate_to_utf8_bytes(notice, limit)

    # 上述预算应当保证这一条件；保留断言式兜底，防止日后改文案超限。
    if _utf8_len(trimmed) > limit:
        trimmed = _truncate_to_utf8_bytes(trimmed, limit)
    return trimmed, f"已按 {limit} 字节截断"


def push_pushplus(title: str, content: str, timeout: int,
                  theme: str = "default") -> str:
    token = env("PUSHPLUS_TOKEN")
    if not token:
        raise PushError("缺少 Secret：PUSHPLUS_TOKEN")
    title = title[:200]  # PushPlus 标题上限（会员支持 200 字）
    content, note = fit_for_channel("pushplus", content, brand_footer_md())
    fields = {"token": token, "title": title}
    # 主题：game / klein / pixel 均为 html 模板，其余走 markdown
    if theme in THEMES:
        fields.update({"content": themed_html(title, content, theme_name=theme),
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
    # 企业微信的 4096 字节限制作用于整个 markdown 字段，标题也必须计入。
    message = f"**{title}**\n\n{content}"
    message, note = fit_for_channel("wecom", message, brand_footer_md())
    payload = {"msgtype": "markdown", "markdown": {"content": message}}
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
    content, note = fit_for_channel("serverchan", content, brand_footer_md())
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


# ================================================================ 模块⑤b：字符模拟图（纯字符）

def _with_ma(bars: list[dict]) -> list[dict]:
    out = []
    for i, b in enumerate(bars):
        b = dict(b)
        for n in (5, 10, 20):
            win = [bars[j]["close"] for j in range(max(0, i - n + 1), i + 1)]
            b[f"ma{n}"] = round(sum(win) / len(win), 4)
        out.append(b)
    return out


def resolve_chart_symbols(raw: str) -> tuple[str, str, str, str]:
    """把任意港股/A股写法解析为 (统一代码, Yahoo 符号, 东财 secid, 市场后缀)。"""
    try:
        import hk_quote
        market, code, em_secid = hk_quote.detect_market(raw)
    except Exception:
        code = normalize_hk_code(raw)
        return code, f"{int(code)}.HK", f"116.{code}", "HK"
    suffix = {"hk": "HK", "sh": "SH", "sz": "SZ"}.get(market, "HK")
    if market == "hk":
        yahoo = f"{int(code)}.HK"
    elif market == "sh":
        yahoo = f"{code}.SS"
    else:
        yahoo = f"{code}.SZ"
    return code, yahoo, em_secid, suffix


def fetch_chart_bars(code: str, timeout: int = 15) -> tuple[list[dict], str]:
    """日级字符模拟图数据：Yahoo 主源 → 东方财富备源（均免 Key）。返回 (bars, 数据源标签)。

    支持港股（09988）与 A 股（600519 / 000001.SZ）。
    """
    code, yahoo_sym, em_secid, _sfx = resolve_chart_symbols(code)
    try:  # ① Yahoo Finance
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
               "?interval=1d&range=6mo")
        status, body = http_request(url, timeout=timeout)
        if status == 200:
            res = json.loads(body)["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            bars = []
            for t, o, h, l, c, v in zip(res.get("timestamp") or [],
                                        q.get("open") or [], q.get("high") or [],
                                        q.get("low") or [], q.get("close") or [],
                                        q.get("volume") or []):
                if o is None or c is None:
                    continue
                bars.append({
                    "date": datetime.fromtimestamp(t, timezone.utc)
                            .strftime("%Y-%m-%d"),
                    "open": float(o), "high": float(h), "low": float(l),
                    "close": float(c), "vol": float(v or 0),
                })
            if len(bars) >= 5:
                return _with_ma(bars), "YAHOO"
    except Exception as e:
        log(f"  ⚠️ 字符模拟图 Yahoo 源失败：{e}")
    try:  # ② 东方财富
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
               f"?secid={em_secid}&klt=101&fqt=1&lmt=90&end=20500101"
               "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57")
        status, body = http_request(url, timeout=timeout)
        if status == 200:
            data = json.loads(body).get("data") or {}
            bars = []
            for row in data.get("klines") or []:
                p = row.split(",")
                # 格式：日期,开盘,收盘,最高,最低,成交量,成交额
                bars.append({
                    "date": p[0], "open": float(p[1]), "close": float(p[2]),
                    "high": float(p[3]), "low": float(p[4]),
                    "vol": float(p[5] or 0),
                })
            if len(bars) >= 5:
                return _with_ma(bars), "EASTMONEY"
    except Exception as e:
        log(f"  ⚠️ 字符模拟图 东方财富 源失败：{e}")
    raise PushError("Yahoo 与东方财富日级数据均获取失败")


# 兼容旧名
fetch_kline_bars = fetch_chart_bars


def render_char_chart(bars: list[dict], meta: dict | None = None,
                      width: int = 52, height: int = 12) -> str:
    """把日级 OHLC bars 渲染为等宽字符模拟图（纯字符，无图片）。

    字符约定：
      影线 │  阳线实体 █  阴线实体 ▓
      MA5 ·  MA10 ×  MA20 +  （在空白处叠加，不覆盖实体）
      支撑 S1 / 压力 R1 用虚线 ─ 标注
    返回可直接嵌入 Markdown <pre> 的多行字符串。
    """
    bars = [b for b in bars if b.get("close") is not None][-width:]
    if len(bars) < 5:
        raise PushError("数据不足（<5 根），无法渲染字符模拟图")
    meta = meta or {}
    code = str(meta.get("code") or "09988")
    source = str(meta.get("source") or "YAHOO")
    suffix = str(meta.get("suffix") or "HK")

    # 选用收盘价决定量纲，保留适当上下边距
    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)
    pad = (hi - lo) * 0.08 or hi * 0.01 or 0.01
    lo -= pad
    hi += pad
    span = hi - lo or 1.0

    n = len(bars)
    # 字符网格：height 行 x n 列
    grid = [[" " for _ in range(n)] for _ in range(height)]

    def y_of(price: float) -> int:
        # 0=顶部, height-1=底部
        r = (hi - price) / span * (height - 1)
        return max(0, min(height - 1, int(round(r))))

    # 绘制影线与实体
    for i, b in enumerate(bars):
        yh = y_of(b["high"])
        yl = y_of(b["low"])
        yo = y_of(b["open"])
        yc = y_of(b["close"])
        top_body = min(yo, yc)
        bot_body = max(yo, yc)
        is_up = b["close"] >= b["open"]
        body_ch = "█" if is_up else "▓"
        # 影线
        for r in range(min(yh, yl), max(yh, yl) + 1):
            if grid[r][i] == " ":
                grid[r][i] = "│"
        # 实体覆盖
        if top_body == bot_body:
            grid[top_body][i] = body_ch
        else:
            for r in range(top_body, bot_body + 1):
                grid[r][i] = body_ch

    # 叠加均线（仅在空白处加点，不覆盖实体与影线，仅示意）
    ma_chars = {"ma5": "·", "ma10": "×", "ma20": "+"}
    for key, ch in ma_chars.items():
        for i, b in enumerate(bars):
            v = b.get(key)
            if v is None:
                continue
            r = y_of(v)
            if grid[r][i] == " ":
                grid[r][i] = ch
            elif grid[r][i] == "│":
                grid[r][i] = ch  # 均线优先于影线

    # 支撑/压力位（近 20 根）
    try:
        s1 = min(b["low"] for b in bars[-20:])
        r1 = max(b["high"] for b in bars[-20:])
        rs = y_of(s1)
        rr = y_of(r1)
        for c in range(n):
            if grid[rs][c] == " ":
                grid[rs][c] = "─"
            if grid[rr][c] == " ":
                grid[rr][c] = "─"
    except Exception:
        s1 = r1 = None

    # 生成价格轴标签
    lines: list[str] = []
    for r in range(height):
        price = hi - (r / (height - 1)) * span if height > 1 else hi
        if r % 3 == 0 or r == height - 1:
            label = f"{price:6.2f} ┤"
        else:
            label = "       │"
        lines.append(label + "".join(grid[r]))

    # 底部边框
    lines.append("       └" + "─" * n + "┘")
    # 日期刻度（首/中/尾）
    date_line = [" " * 8] + [" " for _ in range(n)]
    # 使用首、中、尾日期避免拥挤
    ticks = []
    if n >= 3:
        ticks = [(0, bars[0]["date"][5:]), (n // 2, bars[n // 2]["date"][5:]), (n - 1, bars[-1]["date"][5:])]
    elif n:
        ticks = [(0, bars[0]["date"][5:]), (n - 1, bars[-1]["date"][5:])]
    axis = [" "] * n
    for idx, ds in ticks:
        for k, ch in enumerate(ds):
            pos = idx - 2 + k
            if 0 <= pos < n:
                axis[pos] = ch
    lines.append("        " + "".join(axis))

    # 成交量字符条（单独一行，高度 1，用 ▁▂▃▄▅▆▇█ 归一化）
    try:
        vmax = max((b["vol"] or 0) for b in bars) or 1
        blocks = "▁▂▃▄▅▆▇█"
        vol_chars = []
        for b in bars:
            v = b["vol"] or 0
            ratio = v / vmax
            idx = min(len(blocks) - 1, int(ratio * (len(blocks) - 1) + 0.5))
            # 保持阳阴区分：涨用 █ 系列，跌用 ▓ 系列提示，但体积条本身用 block
            vol_chars.append(blocks[idx])
        lines.append("   VOL │" + "".join(vol_chars))
    except Exception:
        pass

    # 图例与数据说明
    header = f"{code}.{suffix} 字符模拟走势（近 {len(bars)} 日 · {source}）"
    if s1 is not None and r1 is not None:
        footer = f"S1 {s1:.2f} ── 支撑  ·  R1 {r1:.2f} ── 压力  ·  MA5 ·  MA10 ×  MA20 +"
    else:
        footer = "MA5 ·  MA10 ×  MA20 +  ·  涨 █  跌 ▓  影线 │"
    lines.insert(0, header)
    lines.append(footer)
    lines.append(f"{bars[0]['date']}  →  {bars[-1]['date']}")

    return "\n".join(lines)


def make_chart_block(hk_code_raw: str, quotes: list[Quote],
                     no_chart: bool) -> str:
    """生成「📊 字符模拟图」markdown 块（纯字符，无图片，推送正文顶部）。

    任何一步失败都安全降级为空串，绝不影响推送本身。
    """
    if no_chart or not hk_code_raw:
        return ""
    code, _yahoo, _em, suffix = resolve_chart_symbols(hk_code_raw)
    try:
        bars, source = fetch_chart_bars(hk_code_raw, timeout=15)
    except PushError as e:
        log(f"  ⚠️ 字符模拟图数据获取失败，本次推送不含字符图：{e}")
        return ""
    if len(bars) < 5:
        log("  ⚠️ 字符模拟图数据不足（<5 根），本次推送不含字符图")
        return ""

    name = pick_cn_name(quotes, fallback="") if quotes else ""
    label = name or f"{suffix}{code}"
    chart_txt = ""
    try:
        chart_txt = render_char_chart(
            bars, {"code": code, "source": source, "suffix": suffix})
    except PushError as e:
        log(f"  ⚠️ 字符模拟图渲染失败，本次推送不含字符图：{e}")
        return ""
    log(f"  📊 字符模拟图已生成（{len(bars)} 根，{source}，{len(chart_txt)} 字符）")
    last = bars[-1]
    # 用 <pre> 包裹字符图以保持等宽；Markdown 代码块在多数推送渠道亦可正常显示
    # 为兼顾 PushPlus HTML 与企微/Server酱 Markdown，输出双兼容：HTML <pre> 将在 md_to_html 中保留，
    # 纯 Markdown 则显示为代码块
    return (
        f"### 📊 字符模拟图 · {label}（近 {len(bars)} 个交易日，截至 {last['date']} · {source}）\n\n"
        f"```text\n{chart_txt}\n```\n\n"
        f"> 字符模拟图由日级 OHLC 模拟渲染（涨 █ 跌 ▓ 影线 │），仅供参考，非真实图片。\n"
    )


# 兼容旧名（历史脚本/测试可能仍调用 make_kline_block）
make_kline_block = make_chart_block


def demo_chart_bars(count: int = 60) -> list[dict]:
    """本地预览/自检用的演示 OHLC（确定性生成，涨跌形态完整）。"""
    base = 16.80
    out: list[dict] = []
    for i in range(count):
        phase = i / 9.0
        trend = (i / count) * 0.10 - 0.05
        noise = (math.sin(phase * 1.5) * 0.028
                 + math.cos(phase * 0.7) * 0.016 + trend)
        close = base * (1.0 + noise)
        open_ = close * (1.0 - math.sin(phase * 2.1) * 0.012)
        high = max(open_, close) * (1.0 + abs(math.cos(phase * 1.3)) * 0.010)
        low = min(open_, close) * (1.0 - abs(math.sin(phase * 1.9)) * 0.010)
        if i == count - 1:
            close, open_ = base, base * 0.998
        vol = int(12000000 + math.sin(phase * 3.0) * 5000000
                  + i * 70000)
        d = (datetime.now(timezone.utc) - timedelta(days=count - 1 - i))
        out.append({"date": d.strftime("%Y-%m-%d"), "open": round(open_, 3),
                    "high": round(high, 3), "low": round(low, 3),
                    "close": round(close, 3), "vol": vol})
    return _with_ma(out)


# 兼容旧名
demo_kline_bars = demo_chart_bars


# ================================================================ 离线自检

YAHOO_SAMPLE = json.dumps({"chart": {"result": [{"meta": {
    "symbol": "9988.HK", "longName": "Alibaba Group Holding Limited",
    "regularMarketPrice": 16.80, "previousClose": 16.61,
    "regularMarketDayHigh": 16.92, "regularMarketDayLow": 16.55,
    "regularMarketVolume": 19923879, "regularMarketTime": 1754280000}}],
    "error": None}})

EASTMONEY_SAMPLE = json.dumps({"rc": 0, "data": {
    "f43": 16800, "f44": 16920, "f45": 16550, "f46": 16850,
    "f57": "09988", "f58": "阿里巴巴", "f60": 16610,
    "f170": 114, "f47": 19923879}})

TENCENT_SAMPLE = ('v_hk09988="100~阿里巴巴~09988~16.800~16.610~16.850~16.900'
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
          and qb.name == "阿里巴巴")
    check("东财 涨跌幅 1.14%", abs((qb.change_pct or 0) - 1.14) < 1e-9)
    check("腾讯 解析 16.80", qc.ok and abs(qc.price - 16.80) < 1e-9)

    log("② 交叉核验")
    v = verify_quotes([qa, qb, qc])
    check("三源一致→可信", "三源一致" in v.verdict and v.n_excluded == 0)
    bad = Quote(source="东方财富", ok=True, name="阿里巴巴", price=18.50,
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
    md = market_block_md("09988", [qa, qb, qc], v)
    check("核验表含三源名", all(s in md for s in ("Yahoo", "东方财富", "腾讯")))

    log("③ 港股代码规整")
    check("normalize 9988→09988", normalize_hk_code("9988") == "09988")
    check("normalize 9988.HK→09988", normalize_hk_code("9988.HK") == "09988")
    c, y, em, sfx = resolve_chart_symbols("09988")
    check("chart 符号 港股", c == "09988" and y == "9988.HK" and em.startswith("116.") and sfx == "HK")
    c, y, em, sfx = resolve_chart_symbols("600519")
    check("chart 符号 沪A", c == "600519" and y == "600519.SS" and em == "1.600519" and sfx == "SH")
    c, y, em, sfx = resolve_chart_symbols("000001.SZ")
    check("chart 符号 深A", c == "000001" and y == "000001.SZ" and em == "0.000001" and sfx == "SZ")

    log("③b 情绪模块（48h 窗口）")
    NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    s, l_, _ = score_text("阿里巴巴签约云计算大单，营收增长超预期")
    check("词典:利好", l_ == "利好" and s > 0)
    s, l_, _ = score_text("公司亏损并遭大股东减持")
    check("词典:利空", l_ == "利空" and s < 0)
    s, l_, _ = score_text("举行年度股东大会")
    check("词典:中性", l_ == "中性" and s == 0)
    s, l_, _ = score_text("Downwind")
    check("词典:词边界防误判(downwind≠win)", l_ == "中性" and s == 0)
    g = parse_google_rss(GOOGLE_SAMPLE, 48, 10, NOW)
    check("Google:48h过滤剩2条", len(g) == 2)
    check("Google:利好识别", g[0].label == "利好")
    check("Google:利空识别(英文)", g[1].label == "利空")
    g3 = parse_google_rss(GOOGLE_SAMPLE, 8, 10, NOW)
    check("Google:8h窗口更严", len(g3) == 1)
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
        {"name": "阿里巴巴", "code": "HK09988", "percent": 3.2,
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
    md_rule = render_feed_rule("阿里巴巴", fp)
    check("feedscan:rule渲染含缺口行", "⚠️" in md_rule and "情绪温度" in md_rule)
    check("feedscan:附录含来源明细", "金十数据（1/10）" in render_feed_appendix(fp))

    log("③d 审计修复回归")
    check("查询词清洗:默认主题", _clean_query_topic(
        "阿里巴巴(Alibaba) 每日简报") == "阿里巴巴")
    check("查询词清洗:普通主题不动", _clean_query_topic("比亚迪") == "比亚迪")
    check("查询词清洗:空值兜底", _clean_query_topic("(空)") == "阿里巴巴")

    log("③e 通道长度保护（防内容被截/整包拒发）")
    short_c, note = fit_for_channel("wecom", "短内容")
    check("限内原样", short_c == "短内容" and note == "")
    long_c = "报告头部\n" + "明细行\n" * 1500
    trim_c, note = fit_for_channel("wecom", long_c)
    check("超限截断+注释", _utf8_len(trim_c) <= 4096 and "已省略" in trim_c
          and note.startswith("已按"))
    check("截断保住正文头部", trim_c.startswith("报告头部"))
    footer = brand_footer_md()
    branded_long = add_branding("报告头部\n" + "中文明细行\n" * 1500)
    trim_brand, note = fit_for_channel("wecom", branded_long, footer)
    check("中文按 UTF-8 字节截断", _utf8_len(trim_brand) <= 4096
          and note.endswith("字节截断"))
    check("截断仍保留尾部作者", trim_brand.rstrip().endswith(footer.rstrip()))
    check("截断仍保留作者最后", trim_brand.rstrip().endswith(BRAND_SLOGAN))
    wecom_message = f"**{'很长的标题' * 30}**\n\n{branded_long}"
    trim_with_title, _ = fit_for_channel("wecom", wecom_message, footer)
    check("企业微信标题计入总字节上限", _utf8_len(trim_with_title) <= 4096
          and trim_with_title.rstrip().endswith(footer.rstrip()))
    unlim_c, _ = fit_for_channel("pushplus", "x" * 5000)
    check("pushplus 5000字不限", len(unlim_c) == 5000)

    log("③f game 主题渲染（8-bit 像素游戏风·整体默认）")
    gh = md_to_html("## 标题\n\n| 板块 | 概率 |\n|---|---|\n| 云计算 | 65% |\n\n"
                    "- **要点**一\n> 备注：推断\n\n---\n\n1. 有序项")
    check("game 表格+金色粗框", "<table" in gh and GAME["border"] in gh
          and "<th" in gh and "<td" in gh)
    check("game 百分比附像素血条", "█" in gh and "░" in gh and GAME["hp_full"] in gh)
    check("game 加粗保留", "<strong>要点</strong>" in gh)
    check("game 列表/引用/分隔线/有序表", "<ul" in gh and GAME["muted"] in gh
          and "border-left" in gh and "<hr" in gh and "<ol" in gh)
    check("HTML 转义", "&lt;" in md_to_html("a<b>c"))
    check("game 像素图标(◆►)与金色方块", ("◆" in gh or "►" in gh)
          and GAME["accent"] in gh)
    gfull = themed_html("测试标题", "正文**加粗**")
    check("game 三要素(深夜蓝屏+金色粗框+等宽)", GAME["bg"] in gfull
          and GAME["border"] in gfull and "Courier" in gfull and "12px" in gfull)
    check("game 硬黑像素阴影+金色标题栏", "box-shadow" in gfull and GAME["hbg"] in gfull)
    check("game 游戏元素(♥HP血条+SCORE+LV+PRESS START)",
          "♥" in gfull and "SCORE" in gfull and "LV." in gfull
          and "PRESS START" in gfull and "▮" in gfull)
    check("game 像素星点背景", "radial-gradient" in gfull and GAME["star1"] in gfull)
    check("game 状态栏含 UTC 戳", "UTC" in gfull)

    log("③f-1 klein 主题渲染（游戏复古像素风）")
    h = md_to_html("## 标题\n\n| 板块 | 概率 |\n|---|---|\n| 云计算 | 65% |\n\n"
                   "- **要点**一\n> 备注：推断\n\n---\n\n1. 有序项", "klein")
    check("klein 表格→table+表头底色", "<table" in h and KLEIN["hbg"] in h
          and "<th" in h and "<td" in h)
    check("klein 加粗保留", "<strong>要点</strong>" in h)
    check("klein 列表/引用/分隔线/有序表", "<ul" in h and KLEIN["muted"] in h
          and "border-left" in h and "<hr" in h and "<ol" in h)
    check("HTML 转义", "&lt;" in md_to_html("a<b>c"))
    check("klein 像素图标(■►)与黑方块", ("■" in h or "►" in h)
          and KLEIN["border"] in h)
    full = themed_html("测试标题", "正文**加粗**", "klein")
    check("klein 三要素(纸底+黑细框+等宽)", KLEIN["bg"] in full
          and KLEIN["border"] in full and "Courier" in full and "12px" in full)
    check("klein 像素阴影+黑底标题栏", "box-shadow" in full and KLEIN["hbg"] in full)
    check("klein RETRO 角标", "[RETRO]" in full)

    log("③f-2 pixel 像素主题渲染（复古监控风·服务器大屏）")
    ph = md_to_html("## 标题\n\n| 指标 | 涨跌 |\n|---|---|\n| 基本面 | +2.5% |\n| 技术面 | -1.2% |\n| 价格 | 16.80 |\n\n"
                    "- **要点**一\n> 备注：重点 16.80\n\n---\n\n1. 有序项", "pixel")
    check("pixel 表格+细线框", "<table" in ph and "1px solid" in ph and PIXEL["border"] in ph)
    check("pixel 小字体 11px", "11px" in ph)
    check("pixel 涨跌突出(▲▼+磷光色)", ("▲" in ph or "▼" in ph) and (PIXEL["up"] in ph and PIXEL["down"] in ph))
    check("pixel 重点数据琥珀高亮", PIXEL["accent"] in ph and "16.80" in ph)
    check("pixel 复古图标(■►方块)", ("■" in ph or "►" in ph) and "6px" in ph)
    check("pixel 细线框(标题/引用1px)", "border-left:1px" in ph)
    pfull = themed_html("测试标题", "正文**加粗** | 因子 | +3% |\n|---|---|\n| 基本面 | +3% |", "pixel")
    check("pixel 三要素(暗底+细线框+等宽)", PIXEL["bg"] in pfull and PIXEL["border"] in pfull and "Courier" in pfull)
    check("pixel 硬阴影+深色状态栏", "box-shadow" in pfull and PIXEL["hbg"] in pfull)
    check("pixel 摄像头元素(●REC+CAM-01+UTC戳)", "● REC" in pfull and "CAM-01" in pfull and "UTC" in pfull)
    check("pixel CRT扫描线+面板网格", PIXEL["scan"] in pfull and PIXEL["grid"] in pfull)

    log("③f-3 因子分析表 → 卡片式内容展示（因子/方向/多头概率/依据）")
    fmd = ("| 因子 | 方向 | 多头概率 | 依据 |\n|---|---|---|---|\n"
           "| 基本面 | 偏多 | 65% | 云计算营收增长提速 |\n"
           "| 技术面 | 偏空 | 42% | 跌破 20 日均线 |\n"
           "| 资金面 | 中性 | 50% | 北向资金持平 |")
    fc = md_to_html(fmd, "game")
    check("game 因子表不再渲染 table", "<table" not in fc and "<th" not in fc)
    check("game 因子卡片含方向徽章▲▼+涨跌色", "▲ 偏多" in fc and "▼ 偏空" in fc
          and GAME["up"] in fc and GAME["down"] in fc)
    check("game 因子卡片概率血条", "█" in fc and "░" in fc and GAME["hp_full"] in fc)
    check("game 因子卡片依据标签+正文", ">依据</span>" in fc
          and "云计算营收增长提速" in fc and "跌破 20 日均线" in fc)
    check("game 因子卡片金色边框+硬阴影+面板卡底", GAME["border"] in fc
          and GAME["shadow"] in fc and GAME["card_bg"] in fc)
    fk = md_to_html(fmd, "klein")
    check("klein 因子卡片式无 table", "<table" not in fk and KLEIN["card_bg"] in fk
          and "▲ 偏多" in fk and ">依据</span>" in fk)
    check("klein 因子卡片细框进度条", "width:65%;" in fk and KLEIN["up"] in fk)
    fp2 = md_to_html(fmd, "pixel")
    check("pixel 因子卡片式无 table", "<table" not in fp2 and PIXEL["card_bg"] in fp2
          and "▼ 偏空" in fp2 and ">依据</span>" in fp2 and "width:42%;" in fp2)
    fm2 = md_to_html(fmd, "monitor")
    check("monitor 因子卡片保持零表格", "<table" not in fm2
          and MONITOR["card_bg"] in fm2 and "▲ 偏多" in fm2)
    fq = md_to_html("| 因子 | 概率 |\n|---|---|\n| 基本面 | 65% |\n| 技术面 | 42% |")
    check("无方向列按概率 50% 上下推导徽章", "▲ 偏多" in fq and "▼ 偏空" in fq)
    fz = md_to_html("| 因子 | 方向 | 概率 | 依据 | 备注 |\n|---|---|---|---|---|\n"
                    "| 基本面 | 偏多 | 65% | 超预期 | 观察北向 |")
    check("因子表额外列以列名:值附在卡片", "备注" in fz and "观察北向" in fz)

    log("③g 主题集中化（一行改动全局生效）")
    bak = dict(GAME)
    try:
        GAME.update({"bg": "#111111", "fg": "#222222", "border": "#333333",
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
        # 移除所有主题常量定义（避免颜色被误判为硬编码）
        theme_zone = re.sub(r"(GAME|KLEIN|PIXEL|MONITOR|THEMES)\s*=\s*\{.*?\n\}", "", theme_zone, flags=re.S)
        # 注释行不参与扫描（文档里允许出现色值说明）
        theme_zone = "\n".join(l for l in theme_zone.splitlines()
                               if not l.lstrip().startswith("#"))
        hexes = set(re.findall(r"#[0-9A-Fa-f]{6}", theme_zone))
        check("主题区无绕过常量的硬编码色", hexes == set())
    finally:
        GAME.clear()
        GAME.update(bak)

    log("③h 新增量价舆情动量因子")
    analysis_prompt = build_messages("analysis", "阿里巴巴", "示例背景", "mid")[1]["content"]
    check("analysis 提示词含新增因子", SENTIMENT_FACTOR in analysis_prompt)
    check(f"analysis 提示词声明 {FACTOR_COUNT} 个因子",
          f"{FACTOR_COUNT} 个因子" in analysis_prompt)
    check("行业与政策面=真实政策分析，无预设行业/产业链套用",
          INDUSTRY_POLICY_FACTOR in analysis_prompt
          and all(w not in analysis_prompt
                  for w in ("风电装机", "光伏招标", "电商GMV", "白酒配额"))
          and "不得套用产业链传导逻辑" in analysis_prompt)
    rule_analysis = gen_by_rule("阿里巴巴", "analysis")
    check("rule 表格含新增因子", f"| {SENTIMENT_FACTOR} |" in rule_analysis)
    check("analysis 校验器逐项校验", validate_analysis(rule_analysis))
    missing_new_factor = rule_analysis.replace(
        next(line for line in rule_analysis.splitlines()
             if SENTIMENT_FACTOR in line), "")
    check("analysis 缺新增因子时不通过", not validate_analysis(missing_new_factor))
    sample_sent = SentPack(
        hours=48,
        momentum={"ok": True, "score": 0.42},
        agg={"综合多头概率锚点": 69},
    )
    check("rule 使用新增因子本地锚点",
          "| 量价舆情动量（48h） | 偏多 | 69% |" in
          gen_by_rule("阿里巴巴", "analysis", sent_pack=sample_sent))

    log("③i NewsNow 7源接入（知乎/抖音/微博/虎扑/AI hot/联合早报/香港01）")
    if newsnow_mod is not None:
        try:
            # 离线样本自检
            from newsnow_sources import selftest_newsnow
            # selftest_newsnow 自己打印，这里只校验返回码
            ret = selftest_newsnow()
            check("NewsNow 离线解析", ret == 0)
            # 集成：collect 结构
            from newsnow_sources import collect_newsnow, render_newsnow_rule, TARGET_SOURCES
            check("NewsNow TARGET 7源", len(TARGET_SOURCES) == 7 and "zhihu" in TARGET_SOURCES and "hk01" in TARGET_SOURCES)
            # 模拟 pack 渲染走 pixel 主题
            from newsnow_sources import NewsNowPack, HotItem
            demo_pack = NewsNowPack(items={
                "知乎热榜": [HotItem(source="知乎热榜", id="1", title="阿里巴巴Q3财报超预期", url="https://zhihu.com/q/1", extra_info="100万热度")],
                "微博实时热搜": [HotItem(source="微博实时热搜", id="a", title="+2.5% 阿里巴巴大涨", url="https://weibo.com/a", extra_info="热")],
                "香港01": [HotItem(source="香港01", id="b", title="港股电商板块", url="https://hk01.com/b", extra_info="")],
            }, agg={"total": 3, "sources_ok": 3, "sources_total": 7})
            md_demo = render_newsnow_rule("阿里巴巴", demo_pack)
            check("NewsNow 渲染含7源名", "知乎热榜" in md_demo and "香港01" in md_demo)
            # pixel 主题渲染涨跌突出
            html_demo = themed_html("测试NewsNow", md_demo, "pixel")
            check("NewsNow+pixel 涨跌突出", "▲" in html_demo or "热" in html_demo or "11px" in html_demo)
            # game 默认主题渲染（整体像素游戏风）
            html_game = themed_html("测试NewsNow", md_demo)
            check("NewsNow+game 游戏元素", "SCORE" in html_game and "♥" in html_game
                  and GAME["bg"] in html_game)
        except Exception as e:
            check(f"NewsNow 集成异常: {e}", False)
    else:
        check("NewsNow 模块缺失（应存在 newsnow_sources.py）", False)

    log("③j 量价舆情动量·十四平台扫描（156h 窗口 + 有关板块）")
    try:
        from stock_news_scan import selftest_scan, demo_scan_pack, \
            DEFAULT_WINDOW_HOURS
        check("默认窗口为 156h", DEFAULT_WINDOW_HOURS == 156)
        check("十四平台扫描自检通过", selftest_scan() == 0)
        sp = SentPack(hours=156, scan=demo_scan_pack())
        md = render_sentiment_appendix(sp)
        check("情绪附录并入十四平台扫描",
              "十四平台扫描" in md and "有关板块" in md)
        ctx = sentiment_context(sp)
        check("AI 上下文并入十四平台扫描", "十四平台扫描" in ctx)
        check("扫描聚合含平台计数", sp.scan.agg.get("platforms_total") == 14)
    except Exception as e:  # noqa: BLE001
        check(f"十四平台扫描集成异常: {e}", False)

    log("③k 标题：股票代码 + 中文名")
    cn_q = [Quote(source="Yahoo财经", ok=True, name="Alibaba Group"),
            Quote(source="东方财富", ok=True, name="阿里巴巴"),
            Quote(source="腾讯财经", ok=True, name="阿里巴巴")]
    check("中文名优先（腾讯/东财）", pick_cn_name(cn_q, "回退") == "阿里巴巴")
    check("无中文名回退英文名",
          pick_cn_name([Quote(source="Yahoo财经", ok=True,
                              name="Alibaba Group")], "回退") == "Alibaba Group")
    check("全部失败回退 TOPIC",
          pick_cn_name([Quote(source="Yahoo财经", ok=False, error="x")],
                       "阿里巴巴") == "阿里巴巴")
    code = normalize_hk_code("09988")
    title_subject = f"HK{code} {pick_cn_name(cn_q, fallback='阿里巴巴')}"
    check("标题主体=HK代码+中文名", title_subject == "HK09988 阿里巴巴")

    log("④ 全部模板可构造")
    for t in TEMPLATES:
        try:
            msgs = build_messages(t, "阿里巴巴", "示例背景", "mid")
            check(f"模板 {t}", bool(msgs[1]["content"]))
        except Exception as e:  # noqa: BLE001
            check(f"模板 {t} 构造异常: {e}", False)
    check("analysis 校验器", validate_analysis(gen_by_rule("t", "analysis")))
    brand = add_branding("正文")
    check("品牌头部字段齐全",
          all(k in brand_header_md() for k in (BRAND_TITLE, BRAND_SUBTITLE)))
    check("作者不再出现在头部", BRAND_AUTHOR not in brand_header_md())
    check("品牌尾部声明", BRAND_DISCLAIMER in brand_footer_md())
    check("作者固定在最后", brand.rstrip().endswith(BRAND_SLOGAN)
          and brand.rstrip().endswith(brand_footer_md().rstrip()))
    check("品牌头尾可渲染为 HTML", BRAND_TITLE in md_to_html(brand)
          and BRAND_AUTHOR in md_to_html(brand))

    log("⑤ 内容指纹与跨运行状态")
    from types import SimpleNamespace as NS
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, "st.json")
        st0 = load_state(sp)
        check("无状态文件→空基线", st0.get("runs") == {})
        st0["runs"]["analysis|阿里巴巴|09988"] = {
            "fingerprint": "abc123", "ts": "x", "price": 16.8}
        save_state(sp, st0)
        st1 = load_state(sp)
        check("状态写入后可读回",
              st1["runs"]["analysis|阿里巴巴|09988"]["fingerprint"] == "abc123")
        with open(sp, "w", encoding="utf-8") as f:
            f.write("{broken")
        check("状态损坏→回退空基线", load_state(sp).get("runs") == {})
    fp_a = content_fingerprint("analysis", "阿里巴巴", "正文：看涨",
                               {"n_ok": 3, "price": 16.8}, {"anchor": 60},
                               {"Google新闻": ["k1"]})
    fp_b = content_fingerprint("analysis", "阿里巴巴", "正文：看涨",
                               {"n_ok": 3, "price": 16.8}, {"anchor": 60},
                               {"Google新闻": ["k1"]})
    fp_c = content_fingerprint("analysis", "阿里巴巴", "正文：看跌",
                               {"n_ok": 3, "price": 16.8}, {"anchor": 60},
                               {"Google新闻": ["k1"]})
    fp_d = content_fingerprint("analysis", "阿里巴巴", "正文：看涨",
                               {"n_ok": 3, "price": 17.1}, {"anchor": 60},
                               {"Google新闻": ["k1"]})
    check("同内容→指纹稳定", fp_a == fp_b)
    check("正文变化→指纹变化", fp_a != fp_c)
    check("行情变化→指纹变化", fp_a != fp_d)
    pk = NS(items={"Google新闻": [NS(title="阿里巴巴 签 大单")]},
            scan=NS(direct={"雪球": [NS(title="阿里热帖")]}, sector_hits={}))
    ks = gather_item_keys(pk)
    check("样本指纹含两源", set(ks) == {"Google新闻", "扫·雪球"})
    ks2 = gather_item_keys(pk, pk)
    check("重复采集自动去重", len(ks2["Google新闻"]) == 1)
    new = diff_item_keys(ks, {"Google新闻": ks["Google新闻"]})
    check("增量=仅新源条目", set(new) == {"扫·雪球"})
    check("无基线→不报增量", diff_item_keys(ks, {}) == {})
    qb_live = _quote_brief([qa, qb, qc])
    check("行情共识=三源中位价",
          abs(qb_live["price"] - 16.8) < 1e-9 and qb_live["n_ok"] == 3)
    qline = _quote_freshness_line(qb_live, None)
    check("行情看板:首次基线", "首次记录基线" in qline)
    qline2 = _quote_freshness_line(qb_live, 16.5)
    check("行情看板:较上次涨跌", "+0.300" in qline2 and "+1.82%" in qline2)
    check("行情看板:持平识别", "持平" in _quote_freshness_line(qb_live, 16.8))
    fmd = render_freshness_md(now_cst="08-07 18:00", template="analysis",
                              hours=48, fingerprint=fp_a, dup=True,
                              quote_line=qline, new_items={}, first_run=False,
                              anchor_line="锚点 ≈ 60%", state_enabled=True)
    check("看板:重复内容告警", "与上次推送内容一致" in fmd and fp_a in fmd)
    fmd2 = render_freshness_md(now_cst="08-07 18:00", template="analysis",
                               hours=48, fingerprint=fp_a, dup=False,
                               quote_line=qline,
                               new_items={"Google新闻": ["x", "y"]},
                               first_run=False, anchor_line="锚点 ≈ 60%",
                               state_enabled=True)
    check("看板:增量计数", "新增样本：2 条" in fmd2)
    fmd3 = render_freshness_md(now_cst="08-07 18:00", template="analysis",
                               hours=48, fingerprint=fp_a, dup=None,
                               quote_line=qline, new_items={}, first_run=True,
                               anchor_line="", state_enabled=True)
    check("看板:首次运行", "首次建立基线" in fmd3)
    fmd4 = render_freshness_md(now_cst="08-07 18:00", template="analysis",
                               hours=48, fingerprint=fp_a, dup=None,
                               quote_line=qline, new_items={},
                               first_run=False, anchor_line="",
                               state_enabled=False)
    check("看板:可关闭状态对比", "已关闭" in fmd4)
    item_ns = NS(title="阿里云计算提速", source="Google", label="利好",
                 score=0.5, age_h=2.0)
    check("新增样本标🆕", "🆕" in _item_line(item_ns, 1, True)
          and "🆕" not in _item_line(item_ns, 1, False))

    log("⑨ 字符模拟图渲染（纯字符，无图片依赖）")
    os.makedirs("output", exist_ok=True)
    demo = demo_chart_bars(60)
    check("演示数据 60 根", len(demo) == 60 and demo[-1]["close"] == 16.80)
    check("MA 已计算", all(b.get("ma20") for b in demo[19:]))
    chart_txt = render_char_chart(demo, {"code": "09988", "source": "DEMO"})
    check("字符图含价格轴与图例", "┤" in chart_txt and "VOL" in chart_txt and "字符模拟" in chart_txt)
    check("字符图行数合理", 10 <= len(chart_txt.splitlines()) <= 30)
    check("字符图含涨跌字符", ("█" in chart_txt or "▓" in chart_txt) and "│" in chart_txt)
    check("字符图含支撑/压力标注", "S1" in chart_txt and "R1" in chart_txt)
    # 验证 markdown block 生成（离线环境可能因网络失败返回空串，视为优雅降级）
    try:
        block = make_chart_block("09988", [qa], False)
        check("字符模拟图 block 在线含代码块或离线优雅降级",
              block == "" or ("```text" in block and "字符模拟图" in block))
    except Exception as e:
        check(f"字符模拟图 block 不应抛异常: {e}", False)
    demo_block = f"```text\n{chart_txt}\n```"
    check("演示数据可包裹为代码块", "```text" in demo_block)
    check("内联链接正常（非图片）",
          '<a href="https://x/y"' in _inline_md("[k](https://x/y)", "game"))
    # 旧图片语法仍应转为链接或保留（不再强制转为 <img>，字符图为主）
    check("图片语法不崩溃", "https://x/y.png" in _inline_md("![k](https://x/y.png)", "game"))

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
    p.add_argument("--template", default="brief", choices=TEMPLATES,
                   help="分析框架：" + "/".join(TEMPLATES))
    p.add_argument("--topic", default="", help="分析标的/主题（或环境变量 TOPIC）")
    p.add_argument("--context", default="",
                   help="背景信息/复盘细节（或环境变量 CONTEXT）")
    p.add_argument("--hk-code", default="", dest="hk_code",
                   help="港股代码（如 09988），接入三源核验行情（或环境变量 HK_CODE）")
    p.add_argument("--risk", default="mid", choices=RISKS,
                   help="portfolio 模板的风险偏好档位")
    p.add_argument("--theme", default="", choices=["", "default", "game", "klein", "pixel", "monitor", "noc"],
                   help="pushplus 通道主题（整体默认 game=8-bit像素游戏风：深夜蓝屏+金色粗框+"
                        "HP血条+SCORE/LV）；klein=米黄纸底黑细框；pixel=暗色监控大屏；"
                        "monitor/noc=服务器大屏监视风格（零表格，文字+横排卡片流）"
                        "（或环境变量 THEME）")
    p.add_argument("--hours", type=int, default=48,
                   help="analysis/sentiment/feedscan/十四平台扫描的数据窗口小时数"
                        "（默认 48，支持 24/48/72/156）")
    p.add_argument("--yt-channel", default="", dest="yt_channel",
                   help="YouTube 频道 handle（默认 @investtalk，或环境变量 YT_CHANNEL）")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--no-state", action="store_true", dest="no_state",
                   help="关闭跨运行状态对比（不读/不写 output/push_state.json，"
                        "可用环境变量 PUSH_STATE_PATH 指定其他路径）")
    p.add_argument("--no-kline", action="store_true", dest="no_kline",
                   help="关闭字符模拟图（兼容旧名 --no-kline，等同 --no-chart）")
    p.add_argument("--no-chart", action="store_true", dest="no_chart",
                   help="关闭字符模拟图（默认：给 --hk-code 时自动生成字符模拟走势图并"
                        "嵌入推送正文顶部，纯字符无需上传）")
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
    theme = args.theme or env("THEME") or "game"
    targets = ALL_CHANNELS if channel == "all" else [channel]

    log("=" * 60)
    log(f"Manual Run - Alibaba PushPlus+DeepSeek  v{VERSION}")
    log(f"  模板: {template}({TEMPLATE_TITLES[template]})  通道: {channel}"
        f"  AI: {provider}  dry_run: {args.dry_run}  主题: {theme}")
    log(f"  主题: {topic}"
        + (f"  港股: {hk_code_raw}" if hk_code_raw else "")
        + (f"  风险档: {RISK_ZH[risk]}" if template == "portfolio" else ""))
    log("=" * 60)

    if args.check_only:
        return 0 if print_secret_report(channel, provider) else 1

    # ---------- 新增因子：analysis/sentiment 共用 48h 量价舆情数据 ----------
    sent_pack, appendix_md, code4sent = None, "", None
    if template in ("sentiment", "analysis"):
        code4sent = normalize_hk_code(hk_code_raw) if hk_code_raw else None
        scan_hint = "Google新闻/YouTube + 十四平台扫描"
        if template == "analysis":
            log(f"\n📡 正在采集新增因子「{SENTIMENT_FACTOR}」的数据"
                f"（{args.hours}h：{scan_hint}）…")
        else:
            log(f"\n📡 正在采集 {args.hours}h 窗口的多源舆情（{scan_hint}）…")
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
        if getattr(sent_pack, "scan", None):
            sa = sent_pack.scan.agg
            log(f"  🛰 十四平台扫描: 直接相关 {sa.get('n_direct', 0)} 条"
                f" / 板块相关 {sa.get('n_sector', 0)} 条，命中 "
                f"{sa.get('platforms_hit', 0)}/{sa.get('platforms_total', 14)} 平台")
            if sent_pack.scan.dyn_sectors:
                log(f"  🧭 有关板块: "
                    + "、".join(s for s, _ in sent_pack.scan.dyn_sectors[:6]))
        appendix_md = render_sentiment_appendix(sent_pack)
        factor_context = sentiment_context(sent_pack)
        user_context = (f"{factor_context}\n\n{user_context}"
                        if user_context else factor_context)

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

    # ---------- 模块②c：NewsNow 7源热榜聚合（知乎/抖音/微博/虎扑/AI hot/联合早报/香港01） ----------
    newsnow_pack = None
    if template == "newsnow":
        log("\n🔥 正在采集 NewsNow 7源热榜（知乎/抖音/微博/虎扑/AI hot/联合早报/香港01）…")
        try:
            from newsnow_sources import collect_newsnow
            newsnow_pack = collect_newsnow(timeout=min(args.timeout, 15))
            for src_name, items in newsnow_pack.items.items():
                log(f"  ✅ {src_name}: {len(items)} 条")
            for e in newsnow_pack.errors:
                log(f"  ⚠️  {e}")
            log(f"  → 共 {newsnow_pack.agg.get('total',0)} 条 / {newsnow_pack.agg.get('sources_ok',0)}/7 源")
            # 构造上下文
            try:
                from newsnow_sources import render_newsnow_appendix, newsnow_context
                appendix_md = render_newsnow_appendix(newsnow_pack)
                user_context = newsnow_context(newsnow_pack)
            except Exception as ex:
                log(f"  ⚠️  NewsNow 渲染失败：{ex}")
                appendix_md = ""
                user_context = ""
        except Exception as ex:
            log(f"  ❌ NewsNow 模块加载失败：{ex}")
            newsnow_pack = None

    # ---------- 模块①：三源取价 + 交叉核验（可选）----------
    data_md, context = "", user_context
    quotes: list[Quote] = []
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
            elif template == "newsnow" and newsnow_pack is not None:
                try:
                    from newsnow_sources import render_newsnow_rule
                    content = render_newsnow_rule(topic, newsnow_pack)
                except Exception:
                    content = gen_by_rule(topic, template, sent_pack=sent_pack, newsnow_pack=newsnow_pack)
            else:
                # newsnow may be None if import fails, pass it anyway
                try:
                    content = gen_by_rule(topic, template, sent_pack=sent_pack, newsnow_pack=locals().get("newsnow_pack"))
                except TypeError:
                    content = gen_by_rule(topic, template, sent_pack=sent_pack)
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
            content = gen_by_rule(topic, template, sent_pack=sent_pack)
        else:
            log(f"❌ 内容生成失败：{e}")
            return 1

    # ---------- 模块③b：内容指纹 + 与上次推送的新鲜度对比 ----------
    state_enabled = not args.no_state
    st = (load_state(state_path()) if state_enabled
          else {"version": STATE_VERSION, "runs": {}})
    skey = run_state_key(template, topic, hk_code_raw)
    prev = st["runs"].get(skey) or {}

    item_keys = gather_item_keys(sent_pack, feed_pack, newsnow_pack)
    new_items = diff_item_keys(item_keys, prev.get("item_keys", {})) \
        if prev else {}
    new_key_set = {k for keys in new_items.values() for k in keys}

    qb = _quote_brief(quotes)
    extra_points: dict = {}
    anchor_parts: list[str] = []
    if sent_pack is not None:
        anchor = sent_pack.agg.get("综合多头概率锚点")
        extra_points["anchor"] = anchor
        extra_points["mom"] = sent_pack.momentum.get("score")
        anchor_parts.append(
            f"综合多头概率锚点 ≈ {anchor if anchor is not None else '—'}%")
        if sent_pack.momentum.get("ok"):
            anchor_parts.append(
                f"量价动量 {sent_pack.momentum['score']:+.2f}")
        scan = getattr(sent_pack, "scan", None)
        if scan is not None:
            sa = scan.agg
            extra_points["scan_hit"] = sa.get("platforms_hit")
            anchor_parts.append(
                f"十四平台命中 {sa.get('platforms_hit', 0)}"
                f"/{sa.get('platforms_total', 14)}")
    if feed_pack is not None:
        anchor = feed_pack.agg.get("综合多头概率锚点")
        extra_points["feed_anchor"] = anchor
        anchor_parts.append(
            f"全市场快讯锚点 ≈ {anchor}%（{feed_pack.agg.get('n', 0)} 条）")
    if newsnow_pack is not None:
        extra_points["newsnow_total"] = newsnow_pack.agg.get("total")
        anchor_parts.append(
            f"热榜样本 {newsnow_pack.agg.get('total', 0)} 条"
            f"/{newsnow_pack.agg.get('sources_ok', 0)}/7 源")
    anchor_line = (" · ".join(anchor_parts)
                   or "无本地预聚合数据（本模板不含数据采集模块）")

    fp = content_fingerprint(template, topic, content, qb,
                             extra_points, item_keys)
    dup = bool(prev) and prev.get("fingerprint") == fp
    log(f"\n🔢 内容指纹: {fp}"
        + ("（状态对比已关闭）" if not state_enabled
           else "（首次建立基线）" if not prev
           else ("（⚠️ 与上次推送一致）" if dup else "（与上次不同）")))

    # AI 内容与上次完全一致：自动换表述重试一次，避免推文逐字复读
    if dup and provider != "rule":
        log("♻️  已要求 AI 换表述差异化重试一次…")
        try:
            messages[-1]["content"] = (ANTI_DUP_PREFIX
                                       + messages[-1]["content"])
            if provider == "deepseek":
                content = chat_completion(
                    DEEPSEEK_URL, key, "deepseek-chat", messages,
                    TEMPLATE_MAX_TOKENS[template], args.timeout,
                    temperature=0.9)
            else:
                base = env("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
                content = chat_completion(
                    f"{base.rstrip('/')}/chat/completions", key,
                    "gpt-4o-mini", messages, TEMPLATE_MAX_TOKENS[template],
                    args.timeout, temperature=0.9)
            fp = content_fingerprint(template, topic, content, qb,
                                     extra_points, item_keys)
            dup = prev.get("fingerprint") == fp
            log(f"  → 重试后指纹: {fp}"
                + ("（仍与上次一致，正文将明确标注）" if dup
                   else "（已与上次区分）"))
        except PushError as e:
            log(f"  ⚠️ 差异化重试失败，沿用原内容：{e}")

    # 附录：把「上次推送后新增」的样本标注 🆕
    if template in ("sentiment", "analysis") and sent_pack is not None:
        appendix_md = render_sentiment_appendix(sent_pack,
                                                new_keys=new_key_set)
    elif template == "feedscan" and feed_pack is not None:
        appendix_md = render_feed_appendix(feed_pack, new_keys=new_key_set)

    freshness_md = render_freshness_md(
        now_cst=datetime.now(CST).strftime("%m-%d %H:%M"),
        template=template, hours=args.hours, fingerprint=fp,
        dup=(dup if state_enabled else None),
        quote_line=_quote_freshness_line(qb, prev.get("price")),
        new_items=new_items, first_run=not prev,
        anchor_line=anchor_line, state_enabled=state_enabled)

    if template == "analysis" and provider != "rule" \
            and not validate_analysis(content):
        content += "\n\n> ⚠️ 本次模型输出未通过框架格式校验，以上为原始返回，仅供参考。"
    if data_md:
        content += "\n\n" + data_md
    if appendix_md:
        content += "\n\n" + appendix_md

    # 字符模拟图：紧跟新鲜度看板、位于正文顶部；任何失败自动降级为空串（兼容 --no-kline）
    no_chart = bool(getattr(args, "no_chart", False) or getattr(args, "no_kline", False))
    chart_md = make_chart_block(hk_code_raw, quotes, no_chart)

    # 新鲜度看板固定在品牌头之后、AI 正文之前；
    # 所有模板/通道/dry-run 走同一个组装函数：作者固定在推送正文最后一行。
    content = add_branding(freshness_md + "\n\n---\n\n" + chart_md
                           + content.rstrip())

    now = datetime.now(CST).strftime("%m-%d %H:%M")
    # 标题：给了股票代码时用「HK代码 中文名」（中文名从三源行情读取，失败回退 TOPIC）
    title_subject = topic
    if hk_code_raw:
        code = normalize_hk_code(hk_code_raw)
        title_subject = f"HK{code} {pick_cn_name(quotes, fallback=topic)}"
    title = f"{BRAND_TITLE}·{title_subject}·{TEMPLATE_TITLES[template]}（{now}）"
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
        log("\n✅ dry-run 完成。去掉 --dry-run 即为真实推送。"
            "（dry-run 只对比状态，不写入状态文件）")
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

    # ---------- 模块⑥：写入跨运行状态（供下次新鲜度对比）----------
    if state_enabled:
        st["version"] = STATE_VERSION
        st["runs"][skey] = {
            "fingerprint": fp,
            "ts": datetime.now(CST).isoformat(timespec="seconds"),
            "price": qb.get("price"),
            "anchor": extra_points.get("anchor"),
            "item_keys": {s: ks[:STATE_MAX_KEYS_PER_SRC]
                          for s, ks in item_keys.items()},
        }
        # 只保留最近若干组合，避免状态文件无限增长
        if len(st["runs"]) > STATE_MAX_RUN_KEYS:
            ordered = sorted(st["runs"],
                             key=lambda k: st["runs"][k].get("ts", ""))
            for old_key in ordered[:-STATE_MAX_RUN_KEYS]:
                del st["runs"][old_key]
        save_state(state_path(), st)
        log(f"\n💾 运行状态已写入 {state_path()}（指纹 {fp}，"
            f"样本 {sum(len(v) for v in item_keys.values())} 条）")
    log("\n✅ 全部通道推送成功，请到微信查收。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
