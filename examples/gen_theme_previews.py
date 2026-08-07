#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 HTML 主题预览（与 pushplus_deepseek.py 的真实渲染代码同步）：
    examples/theme_preview.html       game/klein/pixel 三主题对比
    examples/game_theme_preview.html  game（8-bit 像素游戏风）单独预览
用法：
    python3 examples/gen_theme_previews.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pushplus_deepseek import themed_html  # noqa: E402

SAMPLE_MD = """**阿里巴巴 · 每日快报**

| 因子 | 方向 | 概率 |
|---|---|---|
| 基本面 | 偏多 | 65% |
| 技术面 | 偏空 | 42% |
| 资金面 | +2.5% 净流入 | 71% |
| 价格 | 16.80 | -1.2% |

- **要点**：云计算营收增长提速，业绩超预期
- 资金连续三日净流入，量价配合

> 备注：重点数据黄底凸显，涨跌按绿/红区分

---

1. 第一监控项：突破 20 日新高
2. 第二监控项：预警线 15.90 ▼

**结论**：偏多，目标价 18.20
"""

PAGE_SHELL = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="background:#17191a;margin:0;padding:14px 10px 30px;">
<div style="max-width:660px;margin:0 auto;">
{{body}}
</div>
</body></html>"""

THEME_LABELS = {
    "game": ("[ THEME: game · 8-bit 像素游戏风 · 整体默认 ]",
             "[ PREVIEW ] themed_html(theme_name='game') · 深夜蓝游戏屏 · 金色粗框 · "
             "硬黑像素阴影 · ♥HP血条 · ★LV · SCORE · PRESS START · UTC 时间戳"),
    "klein": ("[ THEME: klein · 游戏复古像素风 ]",
              "[ PREVIEW ] themed_html(theme_name='klein') · 米黄纸底 · 黑细框 · 像素图标 · RETRO 角标"),
    "pixel": ("[ THEME: pixel · 复古监控风 ]",
              "[ PREVIEW ] themed_html(theme_name='pixel') · 暗色服务器大屏 · 细线框 · "
              "REC 摄像头元素 · UTC 时间戳"),
}


def _block(theme: str) -> str:
    label, foot = THEME_LABELS[theme]
    return (
        f'<div style="color:#9fb5a8;font-family:\'Courier New\',monospace;'
        f'font-size:10px;letter-spacing:2px;margin:22px 0 8px;">{label}</div>\n'
        + themed_html("阿里巴巴 · 每日快报", SAMPLE_MD, theme)
        + f'\n<div style="margin-top:8px;color:#5c6f64;font-family:\'Courier New\',monospace;'
          f'font-size:10px;letter-spacing:1px;text-align:center;">{foot}</div>'
    )


def main() -> int:
    out_dir = Path(__file__).resolve().parent
    # 三主题对比页
    body = "\n".join(_block(t) for t in ("game", "klein", "pixel"))
    (out_dir / "theme_preview.html").write_text(
        PAGE_SHELL.format(title="主题预览 · game 像素游戏 / klein 复古 / pixel 监控")
        .replace("{body}", body),
        encoding="utf-8")
    # game 单独预览页
    (out_dir / "game_theme_preview.html").write_text(
        PAGE_SHELL.format(title="game 主题预览 · 8-bit 像素游戏风")
        .replace("{body}", _block("game")),
        encoding="utf-8")
    print("已生成 theme_preview.html / game_theme_preview.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
