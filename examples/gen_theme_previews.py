#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 PushPlus HTML 主题预览（与真实渲染代码同步）。

输出：
    examples/guizang_theme_preview.html  电子杂志 × 电子墨水竖版长页面
    examples/theme_preview.html          guizang/game/klein/pixel/monitor 对比
    examples/game_theme_preview.html     game 单独预览（兼容旧入口）
    examples/server_monitor_preview.html 服务器大屏静态预览

用法：python3 examples/gen_theme_previews.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pushplus_deepseek import themed_html  # noqa: E402

SAMPLE_MD = """# 先看证据，再谈方向

**阿里巴巴 · 每日研究简报**。这不是一张被拉长的仪表盘，而是一份从实时行情、关键变量到风险边界连续展开的编辑型长页。

## 一页速览

| 指标 | 当前值 | 变化 | 观察 |
|---|---|---|---|
| 共识价 | 16.80 HKD | +2.50% | 三源一致 |
| 多头概率 | 65% | 上调 4pct | 偏多 |
| 风险线 | 15.90 HKD | 不变 | 跌破复核 |

> 关键不是猜下一根 K 线，而是确认基本面、价格与资金信号是否同时持续。

## 七因子信号

| 因子 | 方向 | 多头概率 | 依据 |
|---|---|---|---|
| 基本面 | 偏多 | 65% | 云计算营收增长提速，业绩超预期 |
| 技术面 | 偏空 | 42% | 仍在 20 日均线下方，短线承压 |
| 资金面 | 偏多 | 71% | 主力连续三日净流入，量价配合 |
| 消息与情绪 | 中性 | 50% | 公告平淡，舆情多空均衡 |

## 交易与验证

1. 先验证下一期云业务收入与利润率是否同步改善。
2. 再观察 16.20—16.80 区间能否形成有效支撑。
3. 若跌破 15.90 且成交量放大，重新评估偏多判断。

- **催化剂**：业绩发布、回购进度、云业务订单。
- **反方证据**：消费修复偏弱、竞争投入上升、监管预期变化。
- **纪律**：观点随证据更新，不把单一新闻当作趋势。

---

## 结论

当前证据组合仍然**偏多但不追高**。把 16.80 视为验证区，而不是确定性目标；所有判断以新数据和风险线为边界。

> 声明：仅供研究参考，不构成投资建议。
"""

PAGE_SHELL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
html,body{{margin:0;min-height:100%;background:#17191a}}
body{{padding:18px 10px 42px}}
.preview-shell{{max-width:780px;margin:0 auto}}
.preview-label{{margin:30px 0 9px;color:#aeb7b0;font:10px/1.6 'Courier New',monospace;letter-spacing:2px}}
.preview-foot{{margin:9px 0 24px;color:#69736d;font:10px/1.6 'Courier New',monospace;letter-spacing:1px;text-align:center}}
@media(max-width:520px){{body{{padding:0}}.preview-label,.preview-foot{{display:none}}}}
</style></head>
<body><main class="preview-shell">{body}</main></body></html>"""

THEME_LABELS = {
    "guizang": (
        "[ THEME: guizang · 电子杂志 × 电子墨水 · 默认竖版长页 ]",
        "[ PREVIEW ] 暖纸底 · 墨黑 Hero · 衬线标题 · 等宽元信息 · 发丝线 · rowline · 手机连续阅读",
    ),
    "monitor": (
        "[ THEME: monitor · 服务器大屏监视风格 · 零表格 ]",
        "[ PREVIEW ] 深空暗底 · 荧光青绿 · 横排卡片流 · HUD",
    ),
    "game": (
        "[ THEME: game · 8-bit 像素游戏风 ]",
        "[ PREVIEW ] 深夜蓝游戏屏 · 金色粗框 · HP / LV / SCORE",
    ),
    "klein": (
        "[ THEME: klein · 游戏复古像素风 ]",
        "[ PREVIEW ] 米黄纸底 · 黑细框 · 像素图标",
    ),
    "pixel": (
        "[ THEME: pixel · 复古监控风 ]",
        "[ PREVIEW ] 暗色服务器大屏 · REC 摄像头元素 · UTC",
    ),
}


def _block(theme: str) -> str:
    label, foot = THEME_LABELS[theme]
    return (
        f'<div class="preview-label">{label}</div>\n'
        + themed_html("章鱼 AI · 阿里巴巴 · 机构级研究简报", SAMPLE_MD, theme)
        + f'\n<div class="preview-foot">{foot}</div>'
    )


def _page(title: str, body: str) -> str:
    return PAGE_SHELL.format(title=title, body=body)


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    (out_dir / "guizang_theme_preview.html").write_text(
        _page("Guizang 主题预览 · 电子杂志 × 电子墨水竖版长页", _block("guizang")),
        encoding="utf-8",
    )
    body = "\n".join(_block(t) for t in ("guizang", "monitor", "game", "klein", "pixel"))
    (out_dir / "theme_preview.html").write_text(
        _page("PushPlus 主题预览 · Guizang / Monitor / Game / Klein / Pixel", body),
        encoding="utf-8",
    )
    (out_dir / "game_theme_preview.html").write_text(
        _page("Game 主题预览 · 8-bit 像素游戏风", _block("game")),
        encoding="utf-8",
    )
    try:
        from server_dashboard import export_static_files

        export_static_files()
    except Exception as exc:  # 静态主题预览不应被大屏导出失败阻塞
        print(f"⚠️ 服务器大屏静态预览未更新：{exc}")
    print("已生成 guizang_theme_preview.html / theme_preview.html / game_theme_preview.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
