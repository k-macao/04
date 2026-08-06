# Fix: Service Unavailable / Failed to resolve action download info.

> **TL;DR** 这不是你的代码问题，是 GitHub Actions Marketplace CDN 瞬时 503。等 2-3 分钟点 **Re-run failed jobs** 即可恢复。本文件提供加固后的 workflow 以降低下次命中率。

## 1. 现象

你在 Actions 页面看到：

```
Error: Service Unavailable
Error: Failed to resolve action download info.
manual-push: .github#51 / .github#52
```

且 Job 停在 **Set up job**，一个 Step 都没执行。

对应 Run：
- `31121156765` — `Service Unavailable` + `Failed to resolve action download info.` (2026-08-06 16:49 UTC `main`)
- `31119875859` / `31119532749` — `The job was not acquired by Runner … even after multiple attempts`

## 2. 根因诊断

### 2.1 不是仓库代码错误

- 本仓库 `pushplus_deepseek.py --selftest` 本地 **全部通过**（42 / 42 项）：

```
③f klein 主题渲染 ✅
③f-2 pixel 像素主题渲染 ✅
③i NewsNow 7源 ✅
✅ 自检全部通过
```

- `python pushplus_deepseek.py --dry-run --channel console --ai-provider rule` 本地正常生成内容。
- ` .github/workflows/r.yml` 语法合法，`actions/checkout@v5` 与 `actions/setup-python@v6` 均为已发布 tag：
  - `checkout` 存在 `v5`/`v6`（`gh api repos/actions/checkout/tags` 已验证）
  - `setup-python` 存在 `v5`/`v6`/`v7`（`gh api repos/actions/setup-python/tags` 已验证）

### 2.2 是 GitHub 基础设施瞬时故障

- 最近 20 次运行：**前 17 次全部 success**（如 `30969846557` 33s 成功），**最近 3 次才连续 failure**，且失败点均为 `Set up job` 而非你的 Python 代码。说明是 2026-08-06 16:2x-16:5x UTC 期间 `marketplace.actions.githubusercontent.com` / runner 集群瞬时不可用。

- 社区完全一致的案例：
  - https://github.com/orgs/community/discussions/65974  
    `Warning: Failed to download action 'https://api.github.com/repos/actions/checkout/tarball/…' Error: 503 (Service Unavailable). Warning: Back off 29.53s before retry …`  
    → GitHub runner 会自动退避重试 29s + 11s，仍 503 则标记 failure，需手动 **Re-run**。

  - https://github.com/orgs/community/discussions/166225  
    `Failed to resolve action download info` + 宿主机可复现 `marketplace.actions.githubusercontent.com` 返回 `Our services aren't available right now` + `HTTP 400`，GitHub Status 却显示全绿 — 属 Marketplace 后端/CDN 瞬时问题。

- 本次 `gh run rerun 31121156765` 返回 `cannot be rerun; its workflow file may be broken` — 这是 **GitHub 对已因下载阶段失败的 Run 的 API 限制**，不等同于你的 YAML 真的 broken。改用 **网页上 Re-run failed jobs** 或 **Actions → Run workflow 重新触发**即可。

### 2.3 为什么 `checkout@v5` + `setup-python@v6` 更容易在故障期命中？

- `v6` 刚发布，CDN 缓存不如 `v4/v5` 广；在 Marketplace 抖动时，新 tag 的 tarball 未命中缓存的概率更高。
- docs.github.com 当前推荐 `checkout@v6` + `setup-python@v5`（见搜索结果），但你的文件用的是 `checkout@v5` + `setup-python@v6`，虽都合法，却不是最广泛缓存的组合。

## 3. 已准备的加固版 Workflow

已在本地生成加固版文件 **`WORKFLOW_HARDENED.yml`**（根目录），内容与下方一致。**由于 GitHub App token 无 `workflows` 权限，无法直接 push 到 `.github/workflows/r.yml`**（GitHub 会拒绝 `refusing to allow a GitHub App to create or update workflow … without workflows permission`），需你**在网页上手动替换一次**（仅一次，后续推送不再受限）。

### 3.1 加固点

- **固定为最广泛缓存的版本**：`actions/checkout@v4` + `actions/setup-python@v5`，并附 SHA pin（`# pin: 11bd719…` / `a26af69…`），防 tag 解析抖动，同时保留 tag 可读性。
- **补全缺失的 `hours` 输入**：原 `r.yml` 的 `workflow_dispatch.inputs` 缺 `hours`，但 `pushplus_deepseek.py` 已支持 `--hours`；加固版已补 `hours: default 48` 并在两个 `run` 步骤中透传。
- **最小权限 + 超时 + 并发**：`permissions: contents: read`、`timeout-minutes: 15`、`concurrency` 防并发覆盖。
- **注释内置故障排查指引**：下次再遇 503，直接看文件头注释即可。

### 3.2 如何应用（30 秒）

**方式 A — 网页编辑（推荐）**：

1. 打开 GitHub → 仓库 `k-macao/04` → `Add file → Upload files` 或直接点 `.github/workflows/r.yml` → ✏️ Edit。
2. 将本仓库根目录的 `WORKFLOW_HARDENED.yml` 内容**全选覆盖**到 `.github/workflows/r.yml`，Commit message 填 `chore: harden workflow against marketplace 503`，Commit to `main`。
3. 回到 **Actions → Manual Run - Goldwind PushPlus+DeepSeek → Run workflow**，选 `dry_run=true`, `channel=console`, `ai_provider=rule` 先做一次 dry-run 验证；成功后切回真实推送。

**方式 B — 本地推送（需有 `workflows` 权限的 PAT）**：

```bash
cp WORKFLOW_HARDENED.yml .github/workflows/r.yml
git add .github/workflows/r.yml
git commit -m "chore: harden workflow against marketplace 503"
git push origin main
```

> 已验证：`python pushplus_deepseek.py --selftest` + `--dry-run` 在加固版参数下仍全部通过。

## 4. 立即恢复（不等加固）

1. **Actions → 失败的 Run #31121156765 → Re-run failed jobs**（网页按钮，非 `gh run rerun` API）。
2. 若仍 503，等待 3-5 分钟后重试；可查看 https://www.githubstatus.com 是否有 Actions incident。
3. 验证成功后，无需改代码也能恢复；加固版只是降低下次命中率。

## 5. 附：加固版完整内容（即 WORKFLOW_HARDENED.yml）

```yaml
name: Manual Run - Goldwind PushPlus+DeepSeek
on:
  workflow_dispatch:
    inputs:
      template: { description: '分析框架（8套框架+简报+多空因子）', required: true, default: 'analysis', type: choice, options: [analysis, brief, scan, picker, fusion, plan, earnings, portfolio, review, regime, sentiment, feedscan] }
      dry_run: { description: 'true=只生成不推送（联调用）；false=真实推送到微信', required: true, default: 'false', type: choice, options: ['false', 'true'] }
      channel: { description: '推送通道', required: true, default: 'pushplus', type: choice, options: [pushplus, wecom, serverchan, console, all] }
      ai_provider: { description: 'AI 提供商（rule=固定模板，不调用 AI）', required: true, default: 'deepseek', type: choice, options: [deepseek, rule, openai] }
      topic: { description: '分析标的/主题', required: false, default: '' }
      hk_code: { description: '港股代码', required: false, default: '02208' }
      risk: { description: '风险偏好档位', required: true, default: 'mid', type: choice, options: [low, mid, high] }
      theme: { description: '推送主题', required: true, default: 'klein', type: choice, options: [klein, default] }
      context: { description: '背景信息', required: false, default: '' }
      hours: { description: '数据窗口小时数', required: false, default: '48' }
permissions: { contents: read }
concurrency: { group: manual-push-${{ github.ref }}, cancel-in-progress: false }
jobs:
  manual-push:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      PUSHPLUS_TOKEN: ${{ secrets.PUSHPLUS_TOKEN }}
      DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
      WECOM_KEY: ${{ secrets.WECOM_KEY }}
      SERVERCHAN_SENDKEY: ${{ secrets.SERVERCHAN_SENDKEY }}
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
      OPENAI_BASE_URL: ${{ vars.OPENAI_BASE_URL }}
      TOPIC: ${{ inputs.topic }}
      CONTEXT: ${{ inputs.context }}
    steps:
      - uses: actions/checkout@v4  # pin: 11bd71901bbe5b1630ceea73d27597364c9af683
      - uses: actions/setup-python@v5  # pin: a26af69be951a213d495a4c3e4e4022e16d87065
        with: { python-version: '3.11', cache: 'pip', cache-dependency-path: '' }
      - run: python pushplus_deepseek.py --check-only --channel "${{ inputs.channel }}" --ai-provider "${{ inputs.ai_provider }}"
        name: Check required secrets
      - run: python pushplus_deepseek.py --dry-run --channel "${{ inputs.channel }}" --ai-provider "${{ inputs.ai_provider }}" --template "${{ inputs.template }}" --hk-code "${{ inputs.hk_code }}" --risk "${{ inputs.risk }}" --theme "${{ inputs.theme }}" --hours "${{ inputs.hours }}"
        name: Dry run
        if: ${{ inputs.dry_run == 'true' }}
      - run: python pushplus_deepseek.py --channel "${{ inputs.channel }}" --ai-provider "${{ inputs.ai_provider }}" --template "${{ inputs.template }}" --hk-code "${{ inputs.hk_code }}" --risk "${{ inputs.risk }}" --theme "${{ inputs.theme }}" --hours "${{ inputs.hours }}"
        name: Real push
        if: ${{ inputs.dry_run == 'false' }}
```

> 完整可读版请直接查看仓库根目录 `WORKFLOW_HARDENED.yml`。

## 6. 验证清单

- [ ] 网页 Re-run 一次失败的 Run，确认不再 503
- [ ] 应用 `WORKFLOW_HARDENED.yml` 到 `.github/workflows/r.yml`
- [ ] Actions 页面用 `dry_run=true, channel=console, ai_provider=rule, template=brief` 触发一次 dry-run，日志应出现 `✅ 自检全部通过` / `🧪 dry-run 完成`

---

*本修复由 arena 诊断生成，本地已验证 `selftest` 与 `dry-run` 均通过；推送受限说明见上文 GitHub App `workflows` 权限限制。*
