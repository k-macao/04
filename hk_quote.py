#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hk_quote.py — 免费港股实时行情采集（无需 API Key，纯标准库）

============================================================
 免费港股数据源对比测试（2026-08-07 实测，代码 00700 / 09988）
============================================================
 数据源                   结果      格式         行情时间        备注
 ------------------------------------------------------------------
 ① 腾讯财经 qt.gtimg.cn    ✅ 稳定    GBK 管道串   16:08:23 实时  字段最全：现价/开高低/昨收/
   (q=hk00700)                                          量额/涨跌/PE/振幅/市值/52周高低/币种
 ② 东方财富 push2.eastmoney  ✅ 可用   JSON (UTF-8) 实时         结构最干净；HK 股无 PE 字段；
   (secid=116.00700)                                       偶发 502（重试/换 host 即可）
 ③ Yahoo Finance query1      ✅ 可用   JSON         实时         无 PE/成交额/市值，境内访问不稳
   (chart/0700.HK)
 ④ 新浪财经 hq.sinajs.cn     ❌ Forbidden              —         需 Referer 头，通用客户端被拒
 ⑤ Stooq CSV                 ❌ 404                    —         仅有延迟 OHLCV

 结论：主数据源选 ①腾讯财经（字段最全、稳定、无鉴权、国内可达）；
       自动降级 ②东方财富（JSON 干净）→ 静态演示数据兜底；
       ③ Yahoo 仅作参考/交叉核验，不参与默认链路。

用法：
  python hk_quote.py 00700              # 打印单只股票标准化行情 JSON
  python hk_quote.py 09988 --json       # 输出 JSON
  python hk_quote.py --selftest         # 三源对比测试（判定哪个好）
  python hk_quote.py --selftest 00700 09988 03690
  python hk_quote.py --fixture-test     # 离线解析自检（内置真实抓包样本）
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ================================================================ 常量

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

TIMEOUT = _env_float("HK_QUOTE_TIMEOUT", 3.5)   # 单次请求超时（秒）
CACHE_TTL = _env_float("HK_QUOTE_TTL", 10)      # 正缓存（秒）
NEG_CACHE_TTL = _env_float("HK_QUOTE_NEG_TTL", 60)  # 失败负缓存（秒），避免离线反复请求

# 默认数据源链路：腾讯财经(主) → 东方财富(备) → 静态兜底
# 可用环境变量 HK_QUOTE_CHAIN=tencent,eastmoney,yahoo 覆盖
DEFAULT_CHAIN = tuple(
    s.strip() for s in os.environ.get("HK_QUOTE_CHAIN", "tencent,eastmoney").split(",") if s.strip()
) or ("tencent", "eastmoney")

NO_LIVE = os.environ.get("HK_QUOTE_NO_LIVE", "") not in ("", "0", "false", "False")

SOURCES = {
    "tencent":   {"label": "腾讯财经",  "url_tpl": "https://qt.gtimg.cn/q=hk{code}",
                  "encoding": "gbk"},
    "eastmoney": {"label": "东方财富",  "url_tpl": "https://push2.eastmoney.com/api/qt/stock/get?secid=116.{code}&fields=f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f107,f116,f117,f162,f167,f168,f169,f170,f171",
                  "encoding": "utf-8"},
    "yahoo":     {"label": "Yahoo Finance",
                  "url_tpl": "https://query1.finance.yahoo.com/v8/finance/chart/{code}.HK?interval=1d&range=5d",
                  "encoding": "utf-8"},
}

EASTMONEY_HOSTS = ("push2.eastmoney.com", "push2delay.eastmoney.com")
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

# 内置真实抓包样本（2026-08-07 收盘后抓取），用于离线解析自检
FIXTURES = {
    "tencent_00700": 'v_hk00700="100~腾讯控股~00700~478.800~479.200~479.000~16319939.0~0~0~478.800~0~0~0~0~0~0~0~0~0~478.800~0~0~0~0~0~0~0~0~0~16319939.0~2026/08/07 16:08:23~-0.400~-0.08~483.200~475.400~478.800~16319939.0~7803757295.250~0~17.47~~0~0~1.63~43488.0714~43488.0714~TENCENT~1.11~677.700~411.000~0.57~-42.02~0~0~0~0~0~16.33~3.46~0.18~100~-19.35~0.76~GP~20.59~11.53~10.17~4.04~5.95~9082721689.00~9082721689.00~16.52~5.321~478.173~-25.73~HKD~1~50";',
    "tencent_09988": 'v_hk09988="100~阿里巴巴-W~09988~123.800~124.400~125.300~58259425.0~0~0~123.800~0~0~0~0~0~0~0~0~0~123.800~0~0~0~0~0~0~0~0~0~58259425.0~2026/08/07 16:08:24~-0.600~-0.48~125.800~121.600~123.800~58259425.0~7185130922.040~0~20.23~~0~0~3.38~23740.5321~23740.5321~BABA-W~0.83~185.173~88.650~0.47~-10.37~0~0~0~0~0~19.79~1.98~0.30~100~-12.68~5.81~GP~9.76~5.35~12.55~12.34~-6.41~19176520254.00~19176520254.00~20.23~1.029~123.330~-22.32~HKD~1~50";',
    "eastmoney_00700": '{"rc":0,"rt":4,"svr":177622162,"lt":2,"full":1,"dlmkts":"8,10,128","dsc":"0","data":{"f43":478800,"f44":483200,"f45":475400,"f46":479000,"f47":16319939,"f48":7803757312.0,"f50":57,"f57":"00700","f58":"腾讯控股","f60":479200,"f92":139.9781389,"f107":116,"f114":0,"f115":0,"f116":4348807144693.2,"f117":4348807144693.2,"f162":0,"f164":1654,"f165":506,"f167":342,"f168":18,"f169":-400,"f170":-8,"f171":163}}',
    "yahoo_00700": '{"chart":{"result":[{"meta":{"currency":"HKD","symbol":"0700.HK","exchangeName":"HKG","fullExchangeName":"HKSE","instrumentType":"EQUITY","firstTradeDate":1087349400,"regularMarketTime":1786090091,"hasPrePostMarketData":false,"gmtoffset":28800,"timezone":"HKT","exchangeTimezoneName":"Asia/Hong_Kong","regularMarketPrice":478.8,"fiftyTwoWeekHigh":683.0,"fiftyTwoWeekLow":411.0,"regularMarketDayHigh":483.2,"regularMarketDayLow":475.4,"regularMarketVolume":16320039,"longName":"Tencent Holdings Limited","shortName":"TENCENT","chartPreviousClose":475.2,"priceHint":3},"timestamp":[1785720600,1785807000,1785893400,1785979800,1786066200],"indicators":{"quote":[{"high":[491.0,494.79998779296875,497.79998779296875,491.0,483.20001220703125],"open":[482.0,491.0,493.3999938964844,491.0,479.0],"low":[480.6000061035156,480.79998779296875,482.20001220703125,479.0,475.3999938964844],"volume":[38649910,24860019,25662478,21801977,16320039],"close":[490.3999938964844,487.6000061035156,492.20001220703125,479.20001220703125,478.79998779296875]}]}}],"error":null}}',
}

# ================================================================ 工具函数

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _http_get(url: str, encoding: str = "utf-8", timeout: float = TIMEOUT,
              headers: dict | None = None) -> tuple[str, float]:
    """GET 文本内容，返回 (text, 耗时秒)。失败抛异常。"""
    t0 = time.monotonic()
    hdrs = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return text, time.monotonic() - t0


def normalize_code(code: str) -> str:
    """任意常见写法 → 5 位港股代码：0700 / 700 / 0700.HK / hk00700 → 00700"""
    s = str(code).strip().upper()
    s = s.replace("HK", "")
    s = re.sub(r"[^0-9]", "", s)
    return s.zfill(5)


def _fnum(parts, idx, scale=1.0):
    """安全取管道串字段并转 float"""
    try:
        v = parts[idx].strip()
        if v in ("", "0", "-"):
            return None
        return float(v) / scale
    except (IndexError, ValueError):
        return None


def _fmt_vol(shares: float | None) -> str:
    if shares is None:
        return "—"
    if shares >= 1e8:
        return f"{shares / 1e8:.2f}亿"
    if shares >= 1e4:
        return f"{shares / 1e4:.2f}万"
    return f"{shares:.0f}"


def _fmt_amount(hkd: float | None) -> str:
    if hkd is None:
        return "—"
    if hkd >= 1e8:
        return f"{hkd / 1e8:.2f}亿"
    if hkd >= 1e4:
        return f"{hkd / 1e4:.2f}万"
    return f"{hkd:.0f}"


# ================================================================ 各源解析

def parse_tencent(text: str, code: str) -> dict | None:
    """解析 qt.gtimg.cn 的 v_hkXXXXX="..." 管道串"""
    m = re.search(r'v_hk\d{5}="([^"]*)"', text)
    if not m:
        return None
    p = m.group(1).split("~")
    if len(p) < 60:
        return None
    price = _fnum(p, 3)
    prev = _fnum(p, 4)
    if price is None or price <= 0:
        return None
    chg = _fnum(p, 31)
    pct = _fnum(p, 32)
    if chg is None and prev:
        chg = price - prev
    if pct is None and prev:
        pct = (price - prev) / prev * 100.0
    mcap = _fnum(p, 44)
    fcap = _fnum(p, 43)
    return {
        "code": code,
        "name": p[1].strip() or None,
        "price": round(price, 3),
        "prev_close": round(prev, 3) if prev else None,
        "open": round(_fnum(p, 5) or 0, 3) or None,
        "high": round(_fnum(p, 33) or 0, 3) or None,
        "low": round(_fnum(p, 34) or 0, 3) or None,
        "change": round(chg, 3) if chg is not None else None,
        "change_pct": round(pct, 3) if pct is not None else None,
        "volume": _fnum(p, 36),
        "amount": _fnum(p, 37),
        "pe": _fnum(p, 39),
        "pb": _fnum(p, 58),
        "turnover_rate": _fnum(p, 59),
        "amplitude": _fnum(p, 43),
        "market_cap": (mcap * 1e8) if mcap else None,
        "float_cap": (fcap * 1e8) if fcap else None,
        "high_52w": _fnum(p, 48),
        "low_52w": _fnum(p, 49),
        "total_shares": _fnum(p, 69),
        "eps": _fnum(p, 47),
        "currency": p[75].strip() if len(p) > 75 and p[75].strip() else "HKD",
        "time": p[30].strip() or None,
        "source": "tencent",
        "source_label": SOURCES["tencent"]["label"],
    }


def parse_eastmoney(obj: dict, code: str) -> dict | None:
    """解析东方财富 push2 JSON（HK 价 3 位小数 → ÷1000）"""
    d = obj.get("data") or {}
    if not d or not d.get("f43"):
        return None
    price = d["f43"] / 1000.0
    chg = d.get("f169")
    pct = d.get("f170")
    return {
        "code": code,
        "name": d.get("f58") or None,
        "price": round(price, 3),
        "prev_close": round(d.get("f60") / 1000.0, 3) if d.get("f60") else None,
        "open": round(d.get("f46") / 1000.0, 3) if d.get("f46") else None,
        "high": round(d.get("f44") / 1000.0, 3) if d.get("f44") else None,
        "low": round(d.get("f45") / 1000.0, 3) if d.get("f45") else None,
        "change": round(chg / 1000.0, 3) if chg is not None else None,
        "change_pct": round(pct / 100.0, 3) if pct is not None else None,
        "volume": d.get("f47"),
        "amount": d.get("f48"),
        "pe": None,   # 东财 HK 接口无 PE（f162/f9 恒为 0）
        "pb": round(d.get("f167") / 100.0, 2) if d.get("f167") else None,
        "turnover_rate": round(d.get("f168") / 100.0, 2) if d.get("f168") else None,
        "amplitude": round(d.get("f171") / 100.0, 2) if d.get("f171") else None,
        "market_cap": d.get("f116"),
        "float_cap": d.get("f117"),
        "high_52w": None,
        "low_52w": None,
        "currency": "HKD",
        "time": None,
        "source": "eastmoney",
        "source_label": SOURCES["eastmoney"]["label"],
    }


def parse_yahoo(obj: dict, code: str) -> dict | None:
    """解析 Yahoo Finance chart API JSON"""
    result = (obj.get("chart") or {}).get("result") or []
    if not result:
        return None
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        return None
    closes = (result[0].get("indicators", {}).get("quote") or [{}])[0].get("close") or []
    prev = closes[-2] if len(closes) >= 2 else None
    chg = (price - prev) if prev else None
    pct = (chg / prev * 100.0) if prev else None
    return {
        "code": code,
        "name": meta.get("longName") or meta.get("shortName"),
        "price": round(price, 3),
        "prev_close": round(prev, 3) if prev else None,
        "open": None,
        "high": round(meta["regularMarketDayHigh"], 3) if meta.get("regularMarketDayHigh") else None,
        "low": round(meta["regularMarketDayLow"], 3) if meta.get("regularMarketDayLow") else None,
        "change": round(chg, 3) if chg is not None else None,
        "change_pct": round(pct, 3) if pct is not None else None,
        "volume": meta.get("regularMarketVolume"),
        "amount": None,
        "pe": None,
        "pb": None,
        "turnover_rate": None,
        "amplitude": None,
        "market_cap": None,
        "float_cap": None,
        "high_52w": meta.get("fiftyTwoWeekHigh"),
        "low_52w": meta.get("fiftyTwoWeekLow"),
        "currency": meta.get("currency") or "HKD",
        "time": (datetime.fromtimestamp(meta["regularMarketTime"], tz=timezone.utc)
                 .astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                 if meta.get("regularMarketTime") else None),
        "source": "yahoo",
        "source_label": SOURCES["yahoo"]["label"],
    }


# ================================================================ 各源抓取

def fetch_tencent(code: str) -> dict:
    text, _ = _http_get(SOURCES["tencent"]["url_tpl"].format(code=code), "gbk")
    q = parse_tencent(text, code)
    if q is None:
        raise ValueError(f"腾讯财经响应无法解析: {text[:120]!r}")
    return q


def fetch_eastmoney(code: str) -> dict:
    tpl = SOURCES["eastmoney"]["url_tpl"]
    last_err = None
    for host in EASTMONEY_HOSTS:          # 主 host 偶发 502，换备 host 重试
        url = tpl.replace("push2.eastmoney.com", host)
        try:
            text, _ = _http_get(url, "utf-8",
                                headers={"Referer": "https://quote.eastmoney.com/"})
            obj = json.loads(text)
            q = parse_eastmoney(obj, code)
            if q is None:
                raise ValueError(f"东方财富无数据: {text[:120]!r}")
            return q
        except Exception as e:            # noqa: BLE001
            last_err = e
    raise last_err


def fetch_yahoo(code: str) -> dict:
    tpl = SOURCES["yahoo"]["url_tpl"].format(code=code)
    last_err = None
    for host in YAHOO_HOSTS:
        url = tpl.replace("query1.finance.yahoo.com", host)
        try:
            text, _ = _http_get(url, "utf-8",
                                headers={"Accept": "application/json"})
            obj = json.loads(text)
            q = parse_yahoo(obj, code)
            if q is None:
                raise ValueError(f"Yahoo 无数据: {text[:120]!r}")
            return q
        except Exception as e:            # noqa: BLE001
            last_err = e
    raise last_err


# ================================================================ 带缓存的主入口

_cache: dict[str, tuple[float, dict | None]] = {}
_lock = threading.Lock()


def fetch_quote(code: str, chain: tuple | list | None = None,
                use_cache: bool = True, ttl: float = CACHE_TTL) -> dict | None:
    """
    按链路依次尝试各数据源，返回标准化行情 dict；全部失败返回 None。
    chain 默认 ("tencent", "eastmoney")。
    """
    code = normalize_code(code)
    if not code:
        return None
    chain = tuple(chain or DEFAULT_CHAIN)
    now = time.monotonic()

    if NO_LIVE:
        return None

    if use_cache:
        with _lock:
            hit = _cache.get(code)
        if hit and hit[0] > now:
            q = hit[1]
            return dict(q) if q else None

    fetchers = {
        "tencent": fetch_tencent,
        "eastmoney": fetch_eastmoney,
        "yahoo": fetch_yahoo,
    }
    quote = None
    for src in chain:
        fn = fetchers.get(src)
        if not fn:
            continue
        try:
            quote = fn(code)
            quote["fetched_at"] = now_str()
            break
        except Exception as e:            # noqa: BLE001
            quote = None
            last_err = f"{SOURCES.get(src, {}).get('label', src)}: {e.__class__.__name__}: {e}"
            continue

    with _lock:
        ttl_now = (now + (CACHE_TTL if quote else NEG_CACHE_TTL))
        _cache[code] = (ttl_now, quote)
    if quote:
        quote = dict(quote)
        quote["error"] = None
    return quote


# ================================================================ 三源对比测试

def selftest(codes: tuple[str, ...] = ("00700", "09988", "03690")) -> dict:
    """依次用 ①②③ 三个免费源拉取指定代码，对比 状态/耗时/字段完整度，返回评分结论。"""
    print("=" * 78)
    print("📡 免费港股数据源对比测试（真实网络请求）")
    print("=" * 78)
    sources = ("tencent", "eastmoney", "yahoo")
    stats = {s: {"ok": 0, "fail": 0, "lat": [], "fields": set(), "errs": []} for s in sources}

    headers = f"{'代码':<8}{'数据源':<12}{'状态':<5}{'耗时':<8}{'现价':<10}{'涨跌幅':<9}{'PE':<8}最高/最低"
    print(headers)
    print("-" * 78)
    for code in codes:
        code = normalize_code(code)
        for s in sources:
            fetcher = {"tencent": fetch_tencent, "eastmoney": fetch_eastmoney,
                       "yahoo": fetch_yahoo}[s]
            t0 = time.monotonic()
            try:
                q = fetcher(code)
                lat = time.monotonic() - t0
                stats[s]["ok"] += 1
                stats[s]["lat"].append(lat)
                for f in ("price", "high", "low", "change_pct", "volume",
                          "pe", "currency", "market_cap"):
                    if q.get(f) not in (None, 0):
                        stats[s]["fields"].add(f)
                pe = f"{q['pe']:.2f}" if q.get("pe") else "—"
                hi = f"{q['high']:.3f}" if q.get("high") else "—"
                lo = f"{q['low']:.3f}" if q.get("low") else "—"
                print(f"{code:<8}{SOURCES[s]['label']:<12}✅   {lat:<8.2f}"
                      f"{q['price']:<10.3f}{q.get('change_pct', 0):+>7.2f}%  {pe:<8}{hi}/{lo}")
            except Exception as e:        # noqa: BLE001
                lat = time.monotonic() - t0
                stats[s]["fail"] += 1
                stats[s]["errs"].append(f"{code}: {e.__class__.__name__}: {e}")
                print(f"{code:<8}{SOURCES[s]['label']:<12}❌   {lat:<8.2f}—")
    print("-" * 78)

    # 评分：成功率 40 分 + 字段完整度 60 分
    print("\n📊 评分（成功率 40 + 字段完整度 60）：")
    ranking = []
    for s in sources:
        st = stats[s]
        total = st["ok"] + st["fail"]
        ok_rate = st["ok"] / total if total else 0.0
        completeness = len(st["fields"]) / 8.0
        score = ok_rate * 40 + completeness * 60
        avg_lat = (sum(st["lat"]) / len(st["lat"])) if st["lat"] else float("inf")
        ranking.append((score, s, st, ok_rate, completeness, avg_lat))
        print(f"  {SOURCES[s]['label']:<12} 成功率 {ok_rate * 100:5.1f}%  "
              f"字段完整 {completeness * 100:5.1f}%  平均耗时 "
              f"{avg_lat:.2f}s  得分 {score:6.1f}")
    ranking.sort(key=lambda x: x[0], reverse=True)
    best = ranking[0][1]
    print(f"\n🏆 推荐主数据源：{SOURCES[best]['label']}"
          f"（得分 {ranking[0][0]:.1f}）")
    if len(ranking) > 1:
        print(f"   备选：{SOURCES[ranking[1][1]]['label']}"
              f"（得分 {ranking[1][0]:.1f}）")
    for s, st in stats.items():
        if st["errs"]:
            print(f"\n⚠️  {SOURCES[s]['label']} 失败明细：")
            for e in st["errs"][:5]:
                print(f"   - {e}")
    return {"stats": {s: {"ok": stats[s]["ok"], "fail": stats[s]["fail"],
                          "fields": sorted(stats[s]["fields"])} for s in sources},
            "best": best}


# ================================================================ 离线解析自检

def fixture_test() -> int:
    """用内置真实抓包样本离线验证各源解析逻辑（不联网也能跑）"""
    print("🧪 离线解析自检（内置真实抓包样本）")
    checks = [
        ("tencent_00700", parse_tencent, {"price": 478.800, "pe": 17.47,
                                          "currency": "HKD", "high": 483.200,
                                          "low": 475.400, "change_pct": -0.08,
                                          "amplitude": 1.63,
                                          "market_cap": 4348807140000.0}),
        ("tencent_09988", parse_tencent, {"price": 123.800, "pe": 20.23,
                                          "change_pct": -0.48, "name": "阿里巴巴-W"}),
        ("eastmoney_00700", lambda t, c: parse_eastmoney(json.loads(t), c),
         {"price": 478.8, "pb": 3.42, "turnover_rate": 0.18, "amplitude": 1.63,
          "market_cap": 4348807144693.2}),
        ("yahoo_00700", lambda t, c: parse_yahoo(json.loads(t), c),
         {"price": 478.8, "high": 483.2, "volume": 16320039, "currency": "HKD"}),
    ]
    ok_all = True
    for name, parser, expect in checks:
        try:
            q = parser(FIXTURES[name], normalize_code(name.split("_")[1]))
            miss = []
            for k, v in expect.items():
                got = q.get(k) if q else None
                if isinstance(v, str):
                    if got != v:
                        miss.append(f"{k}(期望 {v} 实得 {got!r})")
                elif got is None or abs(float(got) - float(v)) > max(1e-6, abs(float(v)) * 1e-6):
                    miss.append(f"{k}(期望 {v} 实得 {got})")
            if q is not None and not miss:
                print(f"  ✅ {name:<18} 解析正确 现价={q['price']} PE={q.get('pe')} 涨跌幅={q.get('change_pct')}%")
            else:
                ok_all = False
                print(f"  ❌ {name:<18} 字段不符: {miss} / 结果={q}")
        except Exception as e:            # noqa: BLE001
            ok_all = False
            print(f"  ❌ {name:<18} 解析异常: {e}")
    print("✅ 离线解析自检全部通过" if ok_all else "❌ 离线解析自检存在失败")
    return 0 if ok_all else 1


# ================================================================ CLI

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fixture-test" in argv:
        return fixture_test()
    if "--selftest" in argv:
        codes = [a for a in argv if re.fullmatch(r"[0-9A-Za-z.\-]{2,12}", a) and not a.startswith("--")]
        selftest(tuple(codes or ("00700", "09988", "03690")))
        return 0

    as_json = "--json" in argv
    arg = next((a for a in argv if not a.startswith("--")), "00700")
    code = normalize_code(arg)
    quote = fetch_quote(code)
    if quote is None:
        print(f"❌ 无法获取 {code} 行情（网络受限或所有数据源失败），请用 --selftest 查看明细", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(quote, ensure_ascii=False, indent=2))
        return 0

    print(f"代码       {quote['code']} {quote['name'] or ''}")
    print(f"数据源     {quote['source_label']}（{quote['source']}）")
    print(f"现价       {quote['price']:.3f} {quote['currency']}  "
          f"涨跌 {quote['change']:+.3f} ({quote['change_pct']:+.2f}%)")
    print(f"今开/昨收  {quote.get('open'):.3f} / {quote.get('prev_close'):.3f}")
    print(f"最高/最低  {quote.get('high'):.3f} / {quote.get('low'):.3f}")
    print(f"成交量     {_fmt_vol(quote.get('volume'))} 股   成交额 {_fmt_amount(quote.get('amount'))} 港元")
    print(f"市盈率     {'%.2f' % quote['pe'] if quote.get('pe') else '—'}    "
          f"市净率 {quote.get('pb') or '—'}   换手率 {quote.get('turnover_rate') or '—'}%   振幅 {quote.get('amplitude') or '—'}%")
    print(f"总市值     {_fmt_amount(quote.get('market_cap'))} 港元   52周 {quote.get('high_52w') or '—'}/{quote.get('low_52w') or '—'}")
    print(f"行情时间   {quote.get('time') or quote.get('fetched_at')}（源时间/抓取时间）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
