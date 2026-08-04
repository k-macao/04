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
    python pushplus_deepseek.py                       # 默认: brief + pushplus + deepseek

Secrets（keyless 数据源无需配置）：
    PUSHPLUS_TOKEN / WECOM_KEY / SERVERCHAN_SENDKEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
环境变量（可选）：TOPIC / CONTEXT / HK_CODE / RISK(low|mid|high)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

CHANNELS = ["pushplus", "wecom", "serverchan", "console", "all"]
ALL_CHANNELS = ["pushplus", "wecom", "serverchan"]
PROVIDERS = ["deepseek", "rule", "openai"]
RISKS = ["low", "mid", "high"]
RISK_ZH = {"low": "低", "mid": "中", "high": "高"}

TEMPLATES = ["brief", "analysis", "scan", "picker", "fusion",
             "plan", "earnings", "portfolio", "review", "regime"]
TEMPLATE_TITLES = {
    "brief": "简报", "analysis": "多空因子分析", "scan": "市场情报扫描",
    "picker": "选股器·未来30日", "fusion": "技术面×基本面融合",
    "plan": "交易计划·进出场风控", "earnings": "财报前瞻",
    "portfolio": "组合配置优化", "review": "交易复盘改进", "regime": "市场形态识别",
}
TEMPLATE_MAX_TOKENS = {
    "brief": 600, "analysis": 900, "scan": 1400, "picker": 1600,
    "fusion": 1300, "plan": 1500, "earnings": 1300, "portfolio": 1500,
    "review": 1300, "regime": 1100,
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


# ================================================================ 模块②：分析框架（10 套模板）

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
    if template == "scan":
        user = (
            "扫一遍今天全球市场，总结推动股价的 5 大力量。"
            "重点关注宏观事件、板块轮动、情绪变化，区分重点与噪音。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 力量 | 方向 | 对港股影响概率 | 逻辑（≤20字） | 相关板块 |\n"
            "|---|---|---|---|---|\n（恰好 5 行）\n\n"
            "- **重点**：2 条今日真正值得跟踪的\n- **噪音**：2 条看似热闹但可忽略的\n"
            "- **今日结论**：1~2 句，给出港股整体偏多/偏空概率\n\n"
            "概率取整数%。全文≤600字。" + RULES_TAIL)
    elif template == "picker":
        user = (
            "根据当下市场环境，挑出未来 30 天高概率的股票 3~5 只"
            "（范围：港股/A股，风电及新能源链优先）。每只说清楚为什么看好、"
            "关键风险、什么情况下要止损。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 股票 | 方向 | 30日上涨概率 | 看好逻辑（≤20字） | 关键风险 | 止损触发 |\n"
            "|---|---|---|---|---|---|\n（3~5 行）\n\n"
            "- **首选**：1 句话点名胜率最高的一只\n"
            "- **弃权说明**：若环境不适合开新仓，明说并给理由\n\n"
            "概率取整数%。全文≤800字。" + RULES_TAIL)
    elif template == "fusion":
        user = (
            f"分析「{topic}」，结合 K 线结构、财报和最新新闻，给出明确的看多还是看空。\n\n"
            + ctx +
            "严格按此格式输出：\n\n"
            "| 维度 | 判断 | 多头概率 | 要点（≤18字） |\n|---|---|---|---|\n"
            "| K线结构 |  |  |  |\n| 基本面/财报 |  |  |  |\n"
            "| 最新消息 |  |  |  |\n| 资金与情绪 |  |  |  |\n\n"
            "- **结论**：明确写「看多」或「看空」+ 信心概率%\n"
            "- **关键点位**：支撑 S1/S2、压力 R1/R2（有行情数据时按真实价格算，"
            "否则标注推断）\n- **适合风格**：短线/波段/长线三选一 + 一句理由\n\n"
            "全文≤500字。" + RULES_TAIL)
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
            "全文≤600字。" + RULES_TAIL)
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
            "全文≤550字。" + RULES_TAIL)
    elif template == "portfolio":
        user = (
            f"根据我的风险偏好【{RISK_ZH[risk]}】，设计一个分散的股票组合"
            "（港股/A股，风电新能源为重点再加其他板块）。各板块怎么配、"
            "为什么要这些头寸、多久调整一次。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 板块 | 配置比例 | 代表标的 | 配置理由（≤18字） |\n|---|---|---|---|\n"
            "（4~6 行，比例合计 100%，含现金档）\n\n"
            "- **头寸原则**：单票上限%、单板块上限%\n"
            "- **再平衡**：频率（如每季度）+ 2 条触发式调整条件\n"
            "- **预期特征**：该风险档位的预期波动 1 句\n\n"
            "全文≤700字。" + RULES_TAIL)
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
                "全文≤600字。" + RULES_TAIL)
        else:
            user = (
                "用户未提供具体交易细节。输出一份《交易复盘框架》：\n"
                "1) 需要记录哪些字段（进出场价/仓位/理由/情绪）；"
                "2) 错误分类清单（择时/仓位/纪律/信息）；"
                "3) 心理偏差自查表（各给一句自查问题）；"
                "4) 说明把交易细节粘贴到 context 输入后，可获得逐条复盘。\n\n"
                "全文≤500字。" + RULES_TAIL)
    elif template == "regime":
        user = (
            "判断当前市场是趋势、震荡、风险偏好高还是低。"
            "在这个环境下交易策略应该怎么调整，交易员常掉的坑是什么。\n\n" + ctx +
            "严格按此格式输出：\n\n"
            "| 属性 | 判定 | 概率 | 依据（≤18字） |\n|---|---|---|---|\n"
            "| 趋势市 | 是/否 |  |  |\n| 震荡市 | 是/否 |  |  |\n"
            "| 风险偏好高 | 是/否 |  |  |\n| 高波动 | 是/否 |  |  |\n\n"
            "- **环境一句话**：当前最贴切的 regime 标签\n"
            "- **策略调整**：仓位/持仓周期/止损宽度/可用品类 各 1 条\n"
            "- **常见坑**：该环境下交易员最常犯的 2~3 个错误\n\n"
            "全文≤450字。" + RULES_TAIL)
    elif template == "analysis":
        factors_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(FACTORS))
        user = (
            f"请对「{topic}」按以下 6 个因子逐一做多空分析。{ctx}"
            "每个因子给出【方向】和【多头概率】：多头概率 = 该因子当前指向"
            "上涨/利多的把握，50% 中性，>50% 偏多，<50% 偏空。\n\n"
            f"因子列表（必须全部覆盖，顺序不可变）：\n{factors_text}\n\n"
            "严格按以下 Markdown 格式输出，不要增删表格行：\n\n"
            "| 因子 | 方向 | 多头概率 | 依据（≤20字） |\n|---|---|---|---|\n"
            "| （逐因子填写） |\n\n"
            "- **综合判断**：方向+综合多头概率（如「震荡偏多，约 58%」）\n"
            "- **关键风险**：1~2 条\n- **数据局限**：一句话\n\n"
            "概率取整数%，全文≤450字。" + RULES_TAIL)
    else:  # brief
        user = (f"请围绕「{topic}」生成一份今日简报：3~5 个要点，"
                "每个要点一句话；结尾一句小结。全文不超过 250 字。\n\n" + ctx)
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


# ================================================================ 模块③：推送通道

def push_pushplus(title: str, content: str, timeout: int) -> str:
    token = env("PUSHPLUS_TOKEN")
    if not token:
        raise PushError("缺少 Secret：PUSHPLUS_TOKEN")
    status, body = http_post_form(PUSHPLUS_URL, {
        "token": token, "title": title, "content": content, "template": "markdown",
    }, timeout)
    code = None
    try:
        code = json.loads(body).get("code")
    except json.JSONDecodeError:
        pass
    if status == 200 and code == 200:
        return "发送成功"
    raise PushError(f"PushPlus 返回异常（HTTP {status}）：{body[:400]}")


def push_wecom(title: str, content: str, timeout: int) -> str:
    key = env("WECOM_KEY")
    if not key:
        raise PushError("缺少 Secret：WECOM_KEY")
    payload = {"msgtype": "markdown",
               "markdown": {"content": f"**{title}**\n\n{content}"}}
    status, body = http_post_json(f"{WECOM_URL}?key={key}", payload, timeout=timeout)
    try:
        errcode = json.loads(body).get("errcode")
    except json.JSONDecodeError:
        errcode = None
    if status == 200 and errcode == 0:
        return "发送成功"
    raise PushError(f"企业微信机器人返回异常（HTTP {status}）：{body[:400]}")


def push_serverchan(title: str, content: str, timeout: int) -> str:
    sendkey = env("SERVERCHAN_SENDKEY")
    if not sendkey:
        raise PushError("缺少 Secret：SERVERCHAN_SENDKEY")
    status, body = http_post_form(SERVERCHAN_URL.format(sendkey=sendkey),
                                  {"title": title, "desp": content}, timeout)
    try:
        code = json.loads(body).get("code")
    except json.JSONDecodeError:
        code = None
    if status == 200 and code == 0:
        return "发送成功"
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
    p.add_argument("--template", default="brief", choices=TEMPLATES,
                   help="分析框架：" + "/".join(TEMPLATES))
    p.add_argument("--topic", default="", help="分析标的/主题（或环境变量 TOPIC）")
    p.add_argument("--context", default="",
                   help="背景信息/复盘细节（或环境变量 CONTEXT）")
    p.add_argument("--hk-code", default="", dest="hk_code",
                   help="港股代码（如 02208），接入三源核验行情（或环境变量 HK_CODE）")
    p.add_argument("--risk", default="mid", choices=RISKS,
                   help="portfolio 模板的风险偏好档位")
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
    targets = ALL_CHANNELS if channel == "all" else [channel]

    log("=" * 60)
    log("Manual Run - Goldwind PushPlus+DeepSeek  v2")
    log(f"  模板: {template}({TEMPLATE_TITLES[template]})  通道: {channel}"
        f"  AI: {provider}  dry_run: {args.dry_run}")
    log(f"  主题: {topic}"
        + (f"  港股: {hk_code_raw}" if hk_code_raw else "")
        + (f"  风险档: {RISK_ZH[risk]}" if template == "portfolio" else ""))
    log("=" * 60)

    if args.check_only:
        return 0 if print_secret_report(channel, provider) else 1

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
        context = (line if not user_context
                   else f"{line}\n补充背景：{user_context}")

    # ---------- 模块②：内容生成 ----------
    try:
        if provider == "rule":
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

    # ---------- 模块③：真实推送 ----------
    results: dict[str, str] = {}
    failures = 0
    for ch in targets:
        log(f"\n📤 正在通过 {ch} 推送…")
        try:
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
