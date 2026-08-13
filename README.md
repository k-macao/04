# 04 - 文件合并工具

一个强大的 Python 文件合并工具集，支持多种格式和场景的合并操作。

## 📦 功能特性

### 1. 文件合并 (`merge.py`)
- **文本文件合并** - 支持去重、添加标题、排序、自定义分隔符
- **JSON 文件合并** - 支持深合并、列表拼接/去重策略
- **CSV 文件合并** - 自动对齐不同表头、支持去重
- **二进制文件合并** - 适用于图片、音频等
- **自动检测合并** - 根据扩展名自动选择策略
- **文件夹合并** - 合并多个文件夹，同名文件智能合并

### 2. 归并算法 (`merge_algorithms.py`)
- **合并两个有序数组** - O(n+m)
- **合并 K 个有序数组** - 最小堆实现 O(N log K)
- **归并排序** - 稳定排序 O(n log n)
- **合并区间** - 经典算法题

## 🚀 快速开始

### 安装
```bash
# 无需外部依赖，纯 Python 实现
git clone https://github.com/k-macao/04.git
cd 04
```

### 基本使用

#### Python API
```python
from merge import merge_text_files, merge_json_files, merge_csv_files, merge_files

# 文本合并
merge_text_files(["a.txt", "b.txt"], "merged.txt", deduplicate=True, add_filename_header=True)

# JSON 深合并
merge_json_files(["data1.json", "data2.json"], "merged.json", deep_merge=True)

# CSV 合并，自动对齐表头
merge_csv_files(["a.csv", "b.csv"], "merged.csv", deduplicate=True)

# 自动检测
merge_files(["a.txt", "b.txt"], "out.txt", strategy="auto")

# 文件夹合并
from merge import merge_folders
merge_folders(["folder1", "folder2"], "merged_folder", conflict_strategy="merge")
```

#### 合并算法
```python
from merge_algorithms import merge_two_sorted, merge_k_sorted, merge_sort, merge_intervals

merge_two_sorted([1,3,5], [2,4,6])  # [1,2,3,4,5,6]
merge_k_sorted([[1,4,7],[2,5,8],[3,6,9]])  # [1,2,3,4,5,6,7,8,9]
merge_sort([5,2,8,1,9])
merge_intervals([[1,3],[2,6],[8,10]])
```

### CLI 命令行

```bash
# 文本合并
python merge.py text file1.txt file2.txt -o merged.txt --deduplicate --header --sort

# JSON 合并
python merge.py json data1.json data2.json -o merged.json --deep-merge --list-strategy unique

# CSV 合并
python merge.py csv a.csv b.csv -o merged.csv --deduplicate

# 自动检测
python merge.py auto file1 file2 file3 -o output --strategy auto

# 文件夹合并
python merge.py folder dir1 dir2 -o merged_dir --conflict merge
```

## 📁 项目结构
```
04/
├── merge.py                # 核心文件合并工具
├── merge_algorithms.py     # 归并算法实现
├── test_merge.py           # 测试用例
├── examples/               # 示例文件
│   ├── file1.txt
│   ├── file2.txt
│   ├── data1.json
│   ├── data2.json
│   ├── a.csv
│   └── b.csv
└── README.md
```

## 🧪 运行测试
```bash
python test_merge.py
python merge_algorithms.py
```

## 🔧 高级特性

### 深合并示例
```python
from merge import deep_merge_dicts

base = {"a": 1, "b": {"x": 10}, "c": [1,2]}
incoming = {"b": {"y": 20}, "c": [3,4], "d": 2}
result = deep_merge_dicts(base, incoming)
# {"a": 1, "b": {"x": 10, "y": 20}, "c": [1,2,3,4], "d": 2}
```

### CSV 表头对齐
输入:
- a.csv: id,name,age
- b.csv: id,name,city

输出自动合并为: id,name,age,city，并补全缺失字段

## 📲 微信推送 Workflow（PushPlus + DeepSeek）

仓库内置手动触发的工作流 **Manual Run - Alibaba PushPlus+DeepSeek**（`.github/workflows/r.yml`）：
用 DeepSeek 生成内容，通过 PushPlus 推送到微信。

### 前置条件：配置 Secrets

仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 何时必需 | 获取方式 |
|---|---|---|
| `PUSHPLUS_TOKEN` | 通道为 `pushplus`/`all` | [pushplus.plus](https://www.pushplus.plus) 登录后个人中心复制 token |
| `DEEPSEEK_API_KEY` | AI 为 `deepseek` | [platform.deepseek.com](https://platform.deepseek.com) 创建 API Key |
| `WECOM_KEY` | 通道为 `wecom`/`all` | 企业微信群机器人 webhook 地址中 `key=` 后的部分 |
| `SERVERCHAN_SENDKEY` | 通道为 `serverchan`/`all` | Server酱 Turbo 的 SendKey |
| `OPENAI_API_KEY` | AI 为 `openai` | OpenAI 控制台（可选变量 `OPENAI_BASE_URL`） |

### 运行方式

**Actions → Manual Run - Alibaba PushPlus+DeepSeek → Run workflow**：

- `dry_run=false`：**真实推送**到微信（默认）
- `dry_run=true`：只生成内容打印到日志，不推送（联调用）
- `channel`：pushplus / wecom / serverchan / console / all
- `ai_provider`：deepseek / rule（固定模板，不耗 API）/ openai
- `topic`：内容主题，留空默认"阿里巴巴(Alibaba) 每日简报"
- `theme`：pushplus 推送的 HTML 主题（整体默认 **game** = 8-bit 像素游戏风：深夜蓝游戏屏 + 金色粗框 + 硬黑像素阴影 + ♥HP血条/★LV/SCORE 游戏元素）；可选 `klein`（米黄纸底 + 黑细框复古）、`pixel`（暗色监控大屏）、`default`（普通 Markdown）
- `hours`：量价舆情动量/十四平台扫描/全市场快讯的数据窗口，支持 24/48/72/**156** 小时（156h≈6.5 天，覆盖一个完整交易周）

主题预览：`examples/theme_preview.html`（game/klein/pixel 三主题对比）与
`examples/game_theme_preview.html`（game 单独大图），可用 `examples/gen_theme_previews.py` 重新生成。

### 📊 推送自带字符模拟图（纯字符，无图片，微信直接可见）

只要给了 `hk_code`（默认 `09988`），每次推送自动在正文顶部附一段**字符模拟走势图**：

1. **取数**：Yahoo Finance 日级 OHLC 为主源，东方财富日级数据兜底（均免 Key，取最近 60 个交易日）
2. **渲染**：纯字符等宽模拟图（无图片依赖）——涨 `█` 跌 `▓` 影线 `│`，
   叠加 MA5 `·` / MA10 `×` / MA20 `+` 点位、成交量字符条 `▁▂▃▄▅▆▇█`、近 20 日 S1/R1 支撑压力位虚线 `─`
3. **嵌入**：直接以 Markdown 代码块 ````text```` / HTML `<pre>` 嵌入推送正文（PushPlus HTML 主题、企微、Server酱、console 均可显示，无需 CDN 与图床）
4. **示例**：
```text
09988.HK 字符模拟走势（近 52 日 · YAHOO）
 17.20 ┤      █
 16.80 ┤  █ █ █ │ · ·
       └──────────────────────┘
   VOL │▁▂▃▄▅▆▇█▂▃▄
S1 15.90 ── 支撑  ·  R1 17.40 ── 压力
```

- 任何一步失败（网络/渲染）都会**自动降级**：本次推送不含字符图，绝不影响发送
- 本地 `--dry-run`：控制台直接打印字符图预览
- `--no-chart`（兼容 `--no-kline`）可关闭
- **无需额外权限**：纯字符无需提交图片回仓库，`permissions: contents: read` 即可；已移除图片上传与 jsDelivr CDN 流程

### 分析框架与新增因子

当前工作流提供 12 套模板。选择 `analysis` 时会逐行输出以下 7 个因子，新增的
**量价舆情动量（48h）**不会再被合并到普通消息/情绪面：

1. 基本面（业绩/订单/毛利率）
2. 行业与政策面（平台经济监管/云计算/AI 等真实政策动态）
3. 技术面（趋势/量价/关键价位）
4. 资金面（主力/北向/两融动向）
5. 消息面与情绪面（公告/舆情/行业事件）
6. 估值面（PE/PB 与历史分位）
7. **量价舆情动量（48h）**：基于窗口内价格/成交量、新闻和社媒样本，先本地预聚合，再交给 AI 分析
8. **十四平台股票扫描（窗口跟随 `--hours`，支持 156h）**：输入股票代码后，在最近 156 小时内
   检索十四个平台（**财经 7 源**：Google新闻/财联社电报/华尔街见闻/格隆汇/金十数据/MKTNews/雪球；
   **社媒 7 源**：知乎/微博/抖音/虎扑/AI hot/联合早报/香港01），找出该股票的**相关新闻**
   （按代码/名称/别名直接命中）与**有关板块**（档案预设板块 + 新闻动态提取「XX板块」），
   逐条本地情绪打标后随附录输出，并注入 AI 上下文。

展示样式：`analysis` 输出的「因子 | 方向 | 多头概率 | 依据」在 HTML 推送中以
**卡片式内容展示**（不再是表格）——每个因子一张卡片：卡头为因子名 + 方向徽章
（▲偏多绿 / ▼偏空红 / ●中性灰），卡身为大号多头概率 + 概率条（game 主题为像素
血条 █░，其余主题为细框进度条）和「依据」标签正文；无【方向】列时按概率 50%
上下自动推导徽章。AI/rule 的 Markdown 输出契约不变，卡片化在渲染层完成。

当 `analysis` 搭配 `hk_code` 运行时，脚本会自动采集该新增因子所需的数据；采集失败会明确标注数据缺口，不会伪造概率。

### 统一品牌头与声明

所有模板、所有通道（含 dry-run/console）的最终结果都会自动加入统一品牌信息：

- **标题**：章鱼 AI 全景分析（同时作为推送标题前缀）
- **副标题**：全网多个境内境外多个大模型混合部署 AI 调研平台
- **尾部声明**：声明：仅供参考，不作为投资建议。
- **最后一行作者信息**：`作者：章鱼 ai` 及平台定位说明；不再放在标题下方。

作者和声明由实际推送入口 `pushplus_deepseek.py` 统一组装。企业微信等有长度上限的通道会
按 UTF-8 字节截断正文，但会保留尾部声明和最后一行作者信息。

工作流会先运行 **Check required secrets** 步骤：缺少所需 Secret 时立即变红并指出缺哪一个。

### 数据新鲜度看板（每次推送可验证"有没有更新"）

每次推送正文顶部固定输出 **🧭 数据新鲜度 · 本次运行指纹**：

- **行情对比**：三源共识价 + 在线源数 + 行情时间，并标注与上次推送的涨跌差/持平；
- **🆕 新增样本**：与上次运行相比，数据窗口内新增的条数与来源分布，
  附录中新增条目标 🆕 角标；
- **本地计算**：综合多头概率锚点、量价动量、十四平台命中数；
- **🔢 内容指纹**：由正文+行情+锚点+样本集合计算（不含时间戳）。
  与上次完全一致时醒目标注「⚠️ 与上次推送内容一致（窗口内无新增信号）」，
  否则标注「✅ 与上次推送相比已更新」；首次运行建立基线。

指纹与上次一致且使用 AI 时，会自动追加差异化要求换表述重试一次，避免推文逐字复读。
跨运行状态存于 `output/push_state.json`（已 gitignore），工作流用
`actions/cache` 持久化；本地调试可用环境变量 `PUSH_STATE_PATH` 指定路径，
或 `--no-state` 关闭对比。

命令行本地调试：

```bash
python pushplus_deepseek.py --check-only          # 只检查 Secret 配置
python pushplus_deepseek.py --dry-run             # 生成但不推送
python pushplus_deepseek.py --template analysis --hk-code 09988 --hours 48 --dry-run
python pushplus_deepseek.py --template sentiment --hk-code 09988 --topic 阿里巴巴 --hours 156 --dry-run
python pushplus_deepseek.py --channel all         # 三个通道全部推送
```

### 量价舆情动量 · 十四平台股票扫描（`stock_news_scan.py`）

单独使用（不依赖推送通道，纯标准库）：

```bash
# 输入股票代码，检索最近 156 小时内相关新闻与有关板块
python stock_news_scan.py --code 09988 --name 阿里巴巴 --hours 156

# 只给代码也能跑（内置档案自动补全名称/别名/板块）
python stock_news_scan.py --code 9988.HK

# 追加自定义板块关键词 / JSON 输出 / 离线自检
python stock_news_scan.py --code 00700 --name 腾讯 --sectors 游戏,AI --json
python stock_news_scan.py --selftest
```

输出分三组：**直接相关新闻**（代码/名称/别名命中）、**板块相关快讯**（板块关键词命中）、
**有关板块**（档案预设 + 从命中标题动态提取「XX板块」，子串伪影按频次归属吸收）。
带可靠时间戳的条目严格按 156h 过滤；雪球/社媒热榜为实时快照、标记「实时」不参与过滤。
任何单源失败只进「数据缺口」，不拉高命中数、不伪造数据。

## 📈 免费港股实时行情（`hk_quote.py` + 大屏 view 接入）

大屏监视界面 `server_dashboard.py` 已接入免费港股实时行情，无任何 API Key：

- **数据源对比（2026-08-07 实测）**：① 腾讯财经 `qt.gtimg.cn`（字段最全：现价/开高低/昨收/量额/涨跌/PE/振幅/市值/52周高低/币种）✅ 稳定；② 东方财富 `push2.eastmoney.com`（JSON 最干净，HK 无 PE，偶发 502 自动换 host 重试）✅；③ Yahoo Finance chart API（无 PE/成交额，境内访问不稳）✅ 参考源；新浪 `hq.sinajs.cn`（需 Referer）与 Stooq CSV 实测 ❌。
- **默认链路**：腾讯财经(主) → 东方财富(备) → 静态演示兜底。视图横幅实时显示「🟢 实时行情 (LIVE) · 数据源 · 行情时间」或「⚠️ 演示数据 (STATIC DEMO)」。
- **📊 字符模拟图 · 智能行情交互视图**：大屏已集成 **字符模拟图交互视图 (Char Simulation Chart Studio)**，支持双模式切换——① **字符点阵模拟图**（纯字符点阵渲染、60 周期历史与移动均线 MA5/10/20、实时成交量字符条、支撑压力位标注 S1/R1，涨 `█` 跌 `▓` 影线 `│`，100% 兼容静态文件与离线环境不白屏）；② **TradingView 官方高级图表控件**（支持一键切换加载官方 `s3.tradingview.com` 实时专业插件）。支持 `09988 阿里巴巴`、`00700 腾讯控股`、`03690 美团`、`BABA 阿里美股` 等多标的，以及分时(1D)/5日(5D)/日级(Daily)/周级/月级 多周期切换。
- **后端接口支持**：前端每 30 秒自动轮询 `/api/quote` 更新价格卡片，`/api/chart`（兼容 `/api/kline`）返回标准化 60 根多空均线字符模拟图数据与指标 JSON，`/api/stock` 返回叠加实时行情的完整视图 JSON。

```bash
python hk_quote.py 00700            # 单只股票标准化行情（3 位小数 HKD）
python hk_quote.py --selftest       # 三源真实网络对比测试（哪个好）
python hk_quote.py --fixture-test   # 离线解析自检（内置真实抓包样本）
python test_hk_quote.py             # 单元测试（8 项）
python server_dashboard.py          # 启动大屏（8080，自动接入实时行情）
```

环境变量：`HK_QUOTE_CHAIN=tencent,eastmoney,yahoo`（链路）、`HK_QUOTE_TIMEOUT=3.5`（秒）、`HK_QUOTE_NO_LIVE=1`（强制静态演示）。

### A 股实时行情（沪深，免 Key）

`hk_quote.py` 现已同时支持 **港股（5 位）与 A 股（6 位）**，自动识别市场：

| 代码写法 | 识别结果 |
|---|---|
| `09988` / `9988.HK` / `hk00700` | 港股 |
| `600519` / `600519.SH` / `sh600519` | 沪A（上交所，6 位且首位 6/9） |
| `000001` / `000001.SZ` / `sz000001` | 深A（深交所，6 位且首位 0/1/2/3） |

- **A 股数据源**：腾讯财经 `qt.gtimg.cn/q=sh600519` / `sz000001`（字段最全，含 PE/PB/换手/振幅/总市值）；东方财富 `push2.eastmoney.com`（`secid=1.600519` / `0.000001`，价格 ×100，**带 PE/PB**，区别于港股接口无 PE）。
- **币种自动标注**：港股 `HKD`，A 股 `CNY`；CLI 打印自动切换「港元/元」。

```bash
python hk_quote.py 600519            # 沪A 贵州茅台实时行情（CNY）
python hk_quote.py 000001.SZ --json  # 深A 平安银行 JSON
python hk_quote.py --fixture-test    # 离线解析自检（含 A 股真实抓包样本）
python test_hk_quote.py              # 单元测试（含 A 股解析与市场识别）
```

## 🧠 股票研报生成与推送（`stock_report.py` + 大屏输入框）

新增**「填入港股 / A 股代码 → 实时查询行情 → AI 分析出研报 → 推送」**的一站式能力，
复用仓库内已有的 `hk_quote`（实时行情）与 `pushplus_deepseek`（DeepSeek/OpenAI/rule 分析 + 多通道推送）。

### 命令行

```bash
python stock_report.py 600519                     # 沪A 贵州茅台：打印研报（预览，不推送）
python stock_report.py sz000001 --template analysis
python stock_report.py 09988 --ai-provider deepseek --channel pushplus --push
python stock_report.py 600519.SH --channel all --push   # 三通道真实推送
python stock_report.py --selftest                 # 离线自检（市场识别 + 研报组装）
python stock_report.py --check-only               # 只检查 Secrets
```

- **AI 提供方**：`--ai-provider auto`（默认，Actions 下拉同名）或留空时自动判断——配了 `DEEPSEEK_API_KEY` 走 DeepSeek（模块内模型），否则降级 `rule` 规则模板（不耗 API、可离线演示）。也可显式指定 `deepseek` / `openai` / `rule`。
- **通道**：console（预览）/ pushplus / wecom / serverchan / all；默认 `--dry-run` 只打印，加 `--push` 才真实推送。
- **主题**：`--theme game/klein/pixel/monitor`（推送 HTML 主题，同 `pushplus_deepseek.py`）。

### 大屏输入框（`server_dashboard.py`）

大屏顶部新增 **🧠 AI 研报输入栏**：填入任意港股/A 股代码（如 `09988` / `600519` / `000001.SZ`），
选择推送通道后点「⚡ 生成研报并推送」，前端调用后端 **`POST /api/report`**：

1. 后端实时取行情（`hk_quote`，港股+A 股，失败自动标注数据缺口、绝不伪造）；
2. 用模块内模型（DeepSeek，未配 Key 自动降级 rule）按 `analysis` 模板生成多空因子研报；
3. 组装品牌头尾 + 实时行情核验块，按所选通道推送；
4. 前端在大屏内嵌面板直接渲染研报（`monitor` 主题 HTML，零表格卡片风）。

```bash
python server_dashboard.py            # 启动大屏（8080），打开后在顶部输入框填代码即可
curl -X POST http://localhost:8080/api/report \
     -H 'Content-Type: application/json' \
     -d '{"code":"600519","channel":"console","dry_run":true}'
```

> 未内置演示档案的标的（A 股 / 任意港股代码）在大屏会生成**中性占位档案**：价格/估值来自实时行情，
> 七大因子与快讯标注为演示占位，正式分析以「🧠 AI 研报」输出为准。

## 📝 Git 合并演示

本分支 `arena/019fc917-04` 已实现完整的合并功能，可通过 PR 合并到 main:

```bash
git checkout main
git merge arena/019fc917-04
# 或通过 GitHub PR 合并
```

## License
MIT
