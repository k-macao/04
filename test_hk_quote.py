#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_hk_quote.py — 免费港股行情模块测试
  - 离线解析自检：用内置真实抓包样本验证 腾讯/东财/Yahoo 解析
  - normalize_code 各种输入写法
  - fetch_quote 降级逻辑（断网时返回 None 不抛异常）
运行：python test_hk_quote.py   （或 pytest test_hk_quote.py）
"""
import json
import unittest

import hk_quote


class TestNormalize(unittest.TestCase):
    def test_variants(self):
        cases = {
            "00700": "00700", "0700": "00700", "700": "00700",
            "0700.HK": "00700", "hk00700": "00700", "HK:0700": "00700",
            "9988": "09988", "03690": "03690", "3690": "03690",
        }
        for raw, want in cases.items():
            self.assertEqual(hk_quote.normalize_code(raw), want, raw)


class TestParsersOffline(unittest.TestCase):
    def test_tencent_00700(self):
        q = hk_quote.parse_tencent(hk_quote.FIXTURES["tencent_00700"], "00700")
        self.assertIsNotNone(q)
        self.assertEqual(q["price"], 478.8)
        self.assertEqual(q["high"], 483.2)
        self.assertEqual(q["low"], 475.4)
        self.assertEqual(q["change"], -0.4)
        self.assertEqual(q["change_pct"], -0.08)
        self.assertEqual(q["pe"], 17.47)
        self.assertEqual(q["pb"], 3.46)
        self.assertEqual(q["turnover_rate"], 0.18)
        self.assertEqual(q["amplitude"], 1.63)
        self.assertEqual(q["currency"], "HKD")
        self.assertEqual(q["name"], "腾讯控股")
        self.assertEqual(q["time"], "2026/08/07 16:08:23")
        self.assertEqual(q["high_52w"], 677.7)
        self.assertEqual(q["low_52w"], 411.0)
        self.assertEqual(q["market_cap"], 4348807140000.0)

    def test_tencent_09988(self):
        q = hk_quote.parse_tencent(hk_quote.FIXTURES["tencent_09988"], "09988")
        self.assertIsNotNone(q)
        self.assertEqual(q["price"], 123.8)
        self.assertEqual(q["pe"], 20.23)
        self.assertEqual(q["change_pct"], -0.48)
        self.assertEqual(q["name"], "阿里巴巴-W")

    def test_eastmoney_00700(self):
        q = hk_quote.parse_eastmoney(json.loads(hk_quote.FIXTURES["eastmoney_00700"]), "00700")
        self.assertIsNotNone(q)
        self.assertEqual(q["price"], 478.8)
        self.assertEqual(q["high"], 483.2)
        self.assertEqual(q["pb"], 3.42)
        self.assertEqual(q["turnover_rate"], 0.18)
        self.assertEqual(q["amplitude"], 1.63)
        self.assertIsNone(q["pe"])   # 东财 HK 接口无 PE

    def test_yahoo_00700(self):
        q = hk_quote.parse_yahoo(json.loads(hk_quote.FIXTURES["yahoo_00700"]), "00700")
        self.assertIsNotNone(q)
        self.assertEqual(q["price"], 478.8)
        self.assertEqual(q["currency"], "HKD")
        self.assertEqual(q["volume"], 16320039)
        self.assertEqual(q["high_52w"], 683.0)

    def test_cross_source_consistency(self):
        """三源解析结果应互相一致（同一抓包日期的收盘行情）"""
        t = hk_quote.parse_tencent(hk_quote.FIXTURES["tencent_00700"], "00700")
        e = hk_quote.parse_eastmoney(json.loads(hk_quote.FIXTURES["eastmoney_00700"]), "00700")
        y = hk_quote.parse_yahoo(json.loads(hk_quote.FIXTURES["yahoo_00700"]), "00700")
        for src in (e, y):
            self.assertAlmostEqual(t["price"], src["price"], places=1)
            self.assertAlmostEqual(t["high"], src["high"], places=1)
            self.assertAlmostEqual(t["low"], src["low"], places=1)


class TestFetchDegradation(unittest.TestCase):
    def test_fetch_quote_no_crash(self):
        """断网/被限制环境下 fetch_quote 返回 None 而非抛异常（视图降级静态）"""
        try:
            q = hk_quote.fetch_quote("00700")
            self.assertTrue(q is None or q.get("price"))
        except Exception:  # noqa: BLE001
            self.fail("fetch_quote 不应在数据源失败时抛异常")

    def test_fetch_quote_invalid_code(self):
        self.assertIsNone(hk_quote.fetch_quote("!!!"))
        self.assertIsNone(hk_quote.fetch_quote(""))


class TestTradeViewIntegration(unittest.TestCase):
    def test_kline_view_data(self):
        """测试服务器端 /api/chart 对应视图函数能否生成正确的 60 根字符模拟图数据与指标（兼容旧 /api/kline）"""
        import server_dashboard
        # 新名 get_chart_view，旧名 get_kline_view 仍保留兼容
        fn = getattr(server_dashboard, "get_chart_view", None) or getattr(server_dashboard, "get_kline_view")
        d = fn("09988", tf="daily", count=60)
        self.assertEqual(d["code"], "09988")
        self.assertEqual(len(d["bars"]), 60)
        self.assertIn("open", d["bars"][0])
        self.assertIn("close", d["bars"][-1])
        self.assertIn("ma5", d["bars"][-1])
        self.assertIn("ma10", d["bars"][-1])
        self.assertIn("ma20", d["bars"][-1])
        self.assertIsNotNone(d["support"])
        self.assertIsNotNone(d["resistance"])
        # 兼容旧名
        if hasattr(server_dashboard, "get_kline_view"):
            d2 = server_dashboard.get_kline_view("09988", tf="daily", count=60)
            self.assertEqual(len(d2["bars"]), 60)

    def test_tradeview_html_present(self):
        """测试 render_server_monitor_html 渲染出的 HTML 是否包含字符模拟图交互组件"""
        import server_dashboard
        html = server_dashboard.render_server_monitor_html("09988")
        self.assertIn("tradeview-section", html)
        # 新版为 CHAR SIMULATION，兼容旧版 TRADEVIEW 关键字
        self.assertTrue("CHAR SIMULATION" in html or "TRADEVIEW" in html)
        self.assertIn("tradeview-char-canvas", html)
        self.assertIn("tradeview-vol-canvas", html)
        self.assertTrue("generateDefaultChartBars" in html or "generateDefaultKlineBars" in html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
