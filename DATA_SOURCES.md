# 数据源配置说明

> 最后更新：2026-08-14　·　覆盖 **17 个舆情数据源**（财经快讯 7 源 + 社媒热榜 10 源，2026-08-13 由 7 源扩充至 10 源：新增今日头条 / 百度 / B 站）+ **境外（美股）行情 4 源**（2026-08-14 新增，带交叉验证）。

> 行情链路另计：港股/A股走 `hk_quote.py`（腾讯主→东财备→Yahoo 核验）；美股走 `us_quote.py`（腾讯美股/东财美股/Yahoo/Stooq 四源交叉验证，详见本文 二、3）。

本项目全部采集器仅依赖 Python 标准库，任何单源失败只记入「数据缺口」，不中断整体流程。

---

## 一、总览

### 社媒热榜 10 源（`newsnow_sources.py`，实时快照，不做时间窗口过滤）

| 键名 | 源名 | 端点 | 协议 | 鉴权/前置 | 编码 |
|---|---|---|---|---|---|
| `zhihu` | 知乎热榜 | `zhihu.com/api/v3/feed/topstory/hot-list-web` | JSON | 无（仅 UA） | utf-8 |
| `douyin` | 抖音热搜 | `douyin.com/aweme/v1/web/hot/search/list/` | JSON | Cookie 预热（`login.douyin.com`） | utf-8 |
| `weibo` | 微博实时热搜 | `s.weibo.com/top/summary?cate=realtimehot` | HTML 正则 | **内置 SUB Cookie**（见下） | utf-8 |
| `hupu` | 虎扑热搜 | `bbs.hupu.com/topic-daily-hot` | HTML 正则 | 无 | utf-8 |
| `aihot` | AI hot | `aihot.virxact.com/api/public/items` → 降级 `feed/all.xml` | JSON → RSS | 无 | utf-8 |
| `zaobao` | 联合早报 | `zaochenbao.com/realtime/` | HTML 正则 | gb2312 → utf-8 → gbk 三重解码 | gb2312 |
| `hk01` | 香港01 | `web-data.api.hk01.com` ×2 → `hk01.com/hot` → `most-popular` | JSON → HTML | 多端点逐个降级 | utf-8 |
| `toutiao` 🆕 | 今日头条热榜 | `toutiao.com/hot-event/hot-board/?origin=toutiao_pc` | JSON | Cookie 预热（`toutiao.com`） | utf-8 |
| `baidu` 🆕 | 百度实时热点 | `top.baidu.com/api/board?platform=wise&tab=realtime` | JSON | 移动端 UA + Referer | utf-8 |
| `bilibili` 🆕 | B站热榜 | `api.bilibili.com/x/web-interface/popular` | JSON | UA + Referer | utf-8 |

### 财经快讯 7 源（`stock_news_scan.py`，带时间戳的按 `--hours` 窗口过滤）

| 源 | 协议 | 说明 |
|---|---|---|
| Google 新闻 | RSS 检索 | 以股票关键词检索，窗口内条目计直接相关 |
| 财联社电报 | JSON | 秒级时间戳，严格窗口过滤 |
| 华尔街见闻快讯 | JSON（JS 壳剥离） | 同上 |
| 格隆汇事件 | HTML/JSON | 同上 |
| 金十数据 | JSON（JS 壳剥离） | 同上 |
| MKTNews 快讯 | JSON | 同上 |
| 雪球热门股票 | JSON | Cookie 预热（`xueqiu.com/hq`）；实时热榜，标记「实时」不过滤 |

### 境外（美股）行情 4 源（`us_quote.py`，2026-08-14 新增）

| 键名 | 源 | 端点 | 角色 | 备注 |
|---|---|---|---|---|
| `tencent` | 腾讯财经(美股) | `qt.gtimg.cn/q=us{CODE}`（GBK 管道串） | **主源** | 字段最全：价/涨跌/PE/52周/市值（USD） |
| `eastmoney` | 东方财富(美股) | `push2...secid={105\|106\|107}.{CODE}` | 备源 | 交易所未知自动逐个试（NASDAQ/NYSE/AMEX），价 ×1000 |
| `yahoo` | Yahoo Finance | `query1 finance chart/{CODE}` | 核验 | 双 host 容灾，含盘前盘后时间戳 |
| `stooq` | Stooq(延迟) | `stooq.com/q/l/?s={code}.us&...e=csv` | 核验/兜底 | **延迟 ≥15 分钟**，只参与核验、不充当主源 |

**交叉验证规则**：四源同采 → 中位价为共识价 → 逐源算偏离度：
- 最大偏离 ≤ **0.8%** → ✅ 一致（N/N 源交叉验证通过）
- ≤ **2%** → 🟡 基本一致（仍标注逐源偏离）
- > **2%** → ❌ 分歧（点名离群源）；仅 1 源成功 → ⚠️ 明示「无法交叉验证」

代码识别：`NVDA` / `aapl.us` / `NASDAQ:NVDA` / `NVDA.OQ` 等写法统一归一；
`hk_quote.detect_market` 返回 `market="us"` 后全链路（研报/九章投研/大屏/字符图）自动走美股链路。

---

## 二、每源配置项

### 全局共用

- **超时**：所有抓取函数签名 `fetch_xxx(timeout=15)`；CLI 经 `--timeout` 控制
  （`stock_report.py --timeout`、`stock_news_scan.py --timeout`），`newsnow` 主流程里截断到 `min(timeout, 15)`。
- **UA**：统一携带 `newsnow-py/1.0` / `stock-scan/1.0` 标识 UA，部分源额外带真实浏览器 UA 防风控。
- **隔离**：每个源独立 try/except，失败文案进 `pack.errors`（报告里渲染为「⚠️ 数据缺口」）。

### 需要 Cookie 的源

| 源 | Cookie 机制 | 过期处理 |
|---|---|---|
| 微博 `weibo` | 模块常量 `WEIBO_COOKIE`（`SUB=...`，匿名访客级） | 失效后返回 HTML 不含热搜表 → 解析为空。**更换方式**：用浏览器访问 `s.weibo.com/top/summary?cate=realtimehot`，从请求头复制 `Cookie` 里的 `SUB=` 值替换常量 |
| 抖音 `douyin` | 运行时 CookieJar 预热（先请求 `login.douyin.com`）| 自动，无需手工 |
| 今日头条 `toutiao` 🆕 | 运行时 CookieJar 预热（先请求 `toutiao.com`）+ `Referer` | 自动，无需手工 |
| 雪球 | 运行时 CookieJar 预热（先请求 `xueqiu.com/hq`） | 自动，无需手工 |

### 降级链（单源内多链路）

- **AI hot**：JSON API 200 且解析非空 → 直接返回；否则降级 RSS `feed/all.xml`。
- **香港01**：4 个端点依次尝试（v1 JSON → v2 JSON → `/hot` HTML → `/most-popular` HTML），全部失败时报最后一个错误。
- **联合早报**：gb2312 解码 → utf-8 → gbk 兜底，防乱码。
- **今日头条/百度/B 站** 🆕：接口返回 200 但解析为空时显式抛错「解析为空（接口结构可能变更）」，避免把风控空页当作无新闻。

---

## 三、检查验证数据库（`source_check_db.py`）🆕

SQLite 持久化每次检查：**运行台账 + 逐源明细 + 违例字段**，用于追踪某个源何时开始报错、报错率与延迟。

### 命令

```bash
python source_check_db.py               # 离线校验 14 源（社媒10样本 + 境外行情4样本），不落网
python source_check_db.py --live        # 真抓取：社媒 10 源 + 境外行情 4 源 + 财经快讯 7 源
python source_check_db.py --report      # 打印最近一次运行报告（不重新检查）
python source_check_db.py --history toutiao   # 单源历史记录（报错率/延迟趋势）
python source_check_db.py --history us_stooq  # 境外行情源键名带 us_ 前缀
python source_check_db.py --db my.db    # 指定库文件（默认 SOURCE_CHECK_DB 或 ./source_check.db）
python source_check_db.py --only zhihu,baidu --live   # 只检查指定源
python source_check_db.py --selftest    # 内存库自检（不落盘不触网）
```

### 状态与校验规则

| 状态 | 含义 |
|---|---|
| ✅ `ok` | 抓取/解析成功，字段校验全通过 |
| ⚠️ `warn` | 结果为空，或有违例：标题缺失/超长、链接缺失/非 http(s)、重复标题超 30%、条目数异常（>50） |
| ❌ `fail` | 抓取或解析抛异常（错误截断 200 字入库） |

境外行情源附加字段规则：价格必须 >0、币种必须 USD、涨跌幅 ±25% 外视为异常熔断、
有昨收但缺涨跌幅记字段不完整；Stooq 恒为延迟源，标注但不惩罚。

### 表结构

```sql
check_runs(run_id, mode, started_at, finished_at, total, ok, warn, fail, db_version)
source_checks(id, run_id→check_runs, source_key, source_name, group_name,
              status, items_count, violations_count, latency_ms,
              error, detail(JSON 违例), checked_at)
```

> 库文件为本地产物，已加入 `.gitignore`（`source_check.db` / `*.db`）。

---

## 四、新增数据源 SOP（以本次新增 3 源为范例）

在 `newsnow_sources.py` 按约定 5 步接入，即可被扫描器、推送管线、校验库自动识别：

1. **常量 + 离线样本**：定义 `XXX_URL` 与 `XXX_SAMPLE`（真实响应裁剪到 2 条，便于离线自检）。
2. **解析器** `parse_xxx(text) -> List[HotItem]`：缺标题/链接的条目跳过；可做 URL 补齐（如头条按 `ClusterId` 拼 trending 链接、B 站按 `bvid` 拼视频链接）。
3. **抓取器** `fetch_xxx(timeout) -> List[HotItem]`：负责 Cookie 预热/降级链；解析为空要显式抛错。
4. **注册**：`FETCHERS[key]`、`TARGET_SOURCES`、`SAMPLES[key]` 三处登记同一键名。
5. **自检 + 文档**：在 `selftest_newsnow()` 加解析断言，`source_check_db.py --selftest` 会自动覆盖新源；更新本文件第一节总览表。

---

## 五、常见故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 微博 `warn`：结果为空 | `WEIBO_COOKIE` 过期 | 按第二节表格更换 `SUB=` 值 |
| 头条/抖音返回空 | 风控拦截（无 Cookie 上下文） | 重跑即可（预热是即时的）；连续失败查 `--live` 报告的 error |
| 某源全 `fail`、其余正常 | 该站接口改版 | 看 `source_checks.error` 与历史：`--history <键名>`；必要时改解析器 |
| 全部源超时 | 本机网络/出口受限 | 加大 `--timeout`，或先离线模式验证解析器 |
| 报告里 `warn` 重复标题 | 上游接口返回多卡片重复内容 | 一般可忽略；违例只告警、不拦截 |

> ⚠️ 所有源数据均为公开热榜快照，仅供研究参考，非投资建议。
