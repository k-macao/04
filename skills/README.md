# Skills Hub · 投研技能目录

本目录按 [Agent Skills](https://agentskills.io) 标准安装可复用 SKILL 包，
并接到章鱼 AI 的研报 / 推送 / 大屏入口。

## 已安装

| Skill | 来源 | 用途 | CLI / 模板名 |
|---|---|---|---|
| **equity-research** | rollingSirius v3.0.0 | 九章机构级个股深度 / 财报模式 + `dcf.py` | `equity` |
| **initiating-coverage** | Anthropic FS | 首次覆盖：公司研究（Task 1） | `initiate` |
| **earnings-preview** | Anthropic FS | 财报前瞻：情景 + 观察清单 | `earnings_preview` |
| **earnings-analysis** | Anthropic FS | 季报更新：beat/miss + 论点修订 | `earnings_update` |
| **model-update** | Anthropic FS | 模型/估值修订纪要 | `model_update` |
| **morning-note** | Anthropic FS | 晨会纪要（1 页） | `morning_note` |
| **catalyst-calendar** | Anthropic FS | 催化剂日历 | `catalysts` |
| **thesis-tracker** | Anthropic FS | 投资论点记分卡 | `thesis` |
| **sector-overview** | Anthropic FS | 行业格局 | `sector` |
| **idea-generation** | Anthropic FS | 选股/主题扫描 | `ideas` |

## 使用

```bash
# 列出已安装 skill 与版本
python skills_hub.py --list

# 按 skill 生成（默认 rule 骨架，不耗 API）
python skills_hub.py 09988 --skill morning_note --ai-provider rule
python skills_hub.py 600519 --skill initiate --ai-provider rule

# 经统一入口
python stock_report.py 09988 --template morning_note --ai-provider rule
python stock_report.py 09988 --template initiate --mode full

# 大屏：打开「🧩 Skills Hub」，选择 skill 后生成
python server_dashboard.py 8080
# GET  /api/skills
# POST /api/skills  {"code":"09988","skill":"morning_note","channel":"console"}
```

## 目录

```
skills/
├── README.md
├── NOTICE.md
├── catalog.json
├── equity-research/              → ../equity_research  (symlink)
└── anthropic-equity-research/    Apache-2.0 官方 9 技能
```

Agent 工具也可直接读 `skills/*/SKILL.md` 或 `.claude/skills/`。
