#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pushplus_deepseek.py — DeepSeek 生成内容 → 多通道推送（PushPlus / 企业微信 / Server酱 / 控制台）

用法：
    python pushplus_deepseek.py                          # 真实推送（默认 pushplus + deepseek）
    python pushplus_deepseek.py --dry-run                # 只生成不推送，打印全部细节（联调用）
    python pushplus_deepseek.py --check-only             # 只检查所需 Secrets 是否已配置
    python pushplus_deepseek.py --template analysis      # 多空因子分析（每因子方向+多头概率）
    python pushplus_deepseek.py --channel all --ai-provider rule --topic "每日一句"

所需的 GitHub Secrets（按所选通道 / AI 提供商而定）：
    PUSHPLUS_TOKEN      channel ∈ {pushplus, all} 时必需（https://www.pushplus.plus 个人中心获取）
    WECOM_KEY           channel ∈ {wecom, all} 时必需（企业微信群机器人 webhook key）
    SERVERCHAN_SENDKEY  channel ∈ {serverchan, all} 时必需（Server酱 Turbo SendKey）
    DEEPSEEK_API_KEY    ai-provider = deepseek 时必需
    OPENAI_API_KEY      ai-provider = openai 时必需（可选 OPENAI_BASE_URL 覆盖接口地址）
    TOPIC               任意模式可选，覆盖默认内容主题
    CONTEXT             可选，注入最新行情/公告等背景，供 AI 给出概率时参考
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------- 常量

PUSHPLUS_URL = "http://www.pushplus.plus/send"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
WECOM_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
SERVERCHAN_URL = "https://sctapi.ftqq.com/{sendkey}.send"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"

DEFAULT_TOPIC = "金风科技(Goldwind) 每日简报"
CST = timezone(timedelta(hours=8), "CST")  # 北京时间

CHANNELS = ["pushplus", "wecom", "serverchan", "console", "all"]
PROVIDERS = ["deepseek", "rule", "openai"]
TEMPLATES = ["brief", "analysis"]  # brief=简报；analysis=多空因子分析框架
# --channel all 展开为三个真实通道（console 单独选择即可，避免制造噪音）
ALL_CHANNELS = ["pushplus", "wecom", "serverchan"]

# 多空因子分析框架：每个因子都会得到 方向(多/空/中性) + 多头概率(%)
FACTORS = [
    "基本面（业绩/订单/毛利率）",
    "行业与政策面（风电装机/招标/电价政策）",
    "技术面（趋势/量价/关键价位）",
    "资金面（主力/北向/两融动向）",
    "消息面与情绪面（公告/舆情/行业事件）",
    "估值面（PE/PB 与历史分位）",
]


# ---------------------------------------------------------------- 工具

def log(msg: str = "") -> None:
    print(msg, flush=True)


class PushError(RuntimeError):
    """推送或生成过程中的可预期失败（缺 Secret、API 返回错误等）。"""


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


def http_post(url: str, data: bytes, content_type: str,
              headers: dict | None = None, timeout: int = 30) -> tuple[int, str]:
    """POST 请求，返回 (HTTP 状态码, 响应文本)。网络层异常统一转成 PushError。"""
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", content_type)
    req.add_header("User-Agent", "pushplus-deepseek/1.0 (+github-actions)")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # 服务器返回了错误状态码：body 里通常有原因
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise PushError(f"网络请求失败 {url}: {e.reason}") from e
    except TimeoutError as e:
        raise PushError(f"网络请求超时 {url}") from e


def http_post_json(url: str, payload: dict, headers: dict | None = None,
                   timeout: int = 30) -> tuple[int, str]:
    return http_post(url, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                     "application/json", headers, timeout)


def http_post_form(url: str, fields: dict, timeout: int = 30) -> tuple[int, str]:
    return http_post(url, urllib.parse.urlencode(fields).encode("utf-8"),
                     "application/x-www-form-urlencoded", None, timeout)


# ---------------------------------------------------------------- Secrets 检查

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


def check_secrets(channel: str, provider: str) -> list[str]:
    """返回缺失的 Secret 名列表（什么都不缺则返回空列表）。"""
    return [name for name in required_secrets(channel, provider) if not env(name)]


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
        log("")
        log("❌ 请前往 仓库 Settings → Secrets and variables → Actions 补齐以上 Secret 后重试。")
        return False
    log("  → 全部所需 Secrets 已就绪 ✅")
    return True


# ---------------------------------------------------------------- 内容生成

def gen_by_rule(topic: str, template: str = "brief") -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    if template == "analysis":
        rows = "\n".join(
            f"| {f} | 中性 | 50% | 示例占位，待 AI 填充 |" for f in FACTORS)
        return "\n".join([
            f"**{topic} · 多空因子分析框架**（rule 演示模板，概率均为占位示例）",
            "",
            "| 因子 | 方向 | 多头概率 | 依据 |",
            "|---|---|---|---|",
            rows,
            "",
            "- **综合判断**：示例——运行时将 ai_provider 选为 deepseek，由 AI 逐因子给出真实多空概率",
            "- **关键风险**：示例——同上",
            "- **数据局限**：rule 模式不调用 AI、不含真实分析",
            "",
            f"> 运行时间：{now}（北京时间）。如需真实概率分析：ai_provider 选 deepseek",
            "> 并确认 Secrets 中已配置 DEEPSEEK_API_KEY。⚠️ 非投资建议，仅供参考。",
        ])
    return textwrap.dedent(f"""\
        **{topic}**

        - 运行时间：{now}（北京时间）
        - 工作流：Manual Run - Goldwind PushPlus+DeepSeek
        - 内容模式：rule（未调用 AI，使用内置模板）

        > 如需 AI 生成内容：运行时把 ai_provider 选为 deepseek，
        > 并确认仓库 Secrets 中已配置 DEEPSEEK_API_KEY。""")


def build_messages(template: str, topic: str, context: str) -> list[dict]:
    """按模板构造 AI 对话消息。"""
    if template == "analysis":
        if context:
            ctx_line = f"可参考的最新信息（用户提供，请优先采用）：\n{context}\n\n"
        else:
            ctx_line = ("注意：你无法访问实时行情与最新公告，请基于已有知识推断，"
                        "凡属推断的依据在末尾标注 *（推断）。\n\n")
        factors_text = "\n".join(f"{i+1}. {f}" for i, f in enumerate(FACTORS))
        user = (
            f"请对「{topic}」按以下 6 个因子逐一做多空分析。{ctx_line}"
            "每个因子给出【方向】和【多头概率】：多头概率 = 该因子当前指向上涨/利多的把握，"
            "50% 表示中性，>50% 偏多，<50% 偏空。\n\n"
            f"因子列表（必须全部覆盖，顺序不可变）：\n{factors_text}\n\n"
            "严格按以下 Markdown 格式输出，不要增删表格行，不要输出多余小节：\n\n"
            "| 因子 | 方向 | 多头概率 | 依据（≤20字） |\n"
            "|---|---|---|---|\n"
            "| （逐因子填写） |\n\n"
            "表格之后依次输出：\n"
            "- **综合判断**：加权各因子后的整体结论（格式：方向+综合多头概率，"
            "如「震荡偏多，综合多头概率约 58%」）\n"
            "- **关键风险**：1~2 条最可能打破结论的因素\n"
            "- **数据局限**：一句话说明实时数据缺失对概率的影响\n\n"
            "概率取整数百分比，全文不超过 450 字，"
            "末尾固定一行「⚠️ 非投资建议，仅供参考」。"
        )
        system = ("你是一位严谨的 A 股分析师，熟悉风电行业。"
                  "输出必须是简体中文 Markdown，不要寒暄，不要使用代码块。")
    else:
        user = (f"请围绕「{topic}」生成一份今日简报：3~5 个要点，"
                "每个要点一句话；结尾一句小结。全文不超过 250 字。")
        system = "你是一位简洁专业的中文资讯编辑，输出 Markdown，不要寒暄。"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


def validate_analysis(content: str) -> bool:
    """校验 analysis 输出：应含表头且 ≥6 行带百分号的因子行。"""
    if "| 因子" not in content:
        return False
    factor_rows = [ln for ln in content.splitlines()
                   if ln.strip().startswith("|") and "%" in ln]
    return len(factor_rows) >= len(FACTORS)


def chat_completion(url: str, api_key: str, model: str, messages: list[dict],
                    timeout: int) -> str:
    payload = {"model": model, "messages": messages,
               "temperature": 0.7, "max_tokens": 900}
    status, body = http_post_json(url, payload,
                                  {"Authorization": f"Bearer {api_key}"}, timeout)
    if status != 200:
        raise PushError(f"AI 接口返回 HTTP {status}：{body[:400]}")
    try:
        return json.loads(body)["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise PushError(f"AI 接口返回格式异常：{body[:400]}") from e


def generate_content(provider: str, topic: str, timeout: int,
                     template: str = "brief", context: str = "") -> str:
    if provider == "rule":
        return gen_by_rule(topic, template)
    messages = build_messages(template, topic, context)
    if provider == "deepseek":
        key = env("DEEPSEEK_API_KEY")
        if not key:
            raise PushError("缺少 Secret：DEEPSEEK_API_KEY（ai_provider=deepseek 必需）")
        content = chat_completion(DEEPSEEK_URL, key, "deepseek-chat",
                                  messages, timeout)
    elif provider == "openai":
        key = env("OPENAI_API_KEY")
        if not key:
            raise PushError("缺少 Secret：OPENAI_API_KEY（ai_provider=openai 必需）")
        base = env("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
        content = chat_completion(f"{base.rstrip('/')}/chat/completions",
                                  key, "gpt-4o-mini", messages, timeout)
    else:
        raise PushError(f"未知 AI 提供商：{provider}")
    # analysis 模板做格式校验：不合格时仍推送，但附加警示（不静默丢弃内容）
    if template == "analysis" and not validate_analysis(content):
        content += "\n\n> ⚠️ 本次模型输出未通过框架格式校验，以上为原始返回，仅供参考。"
    return content


# ---------------------------------------------------------------- 各通道推送

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
    "pushplus": push_pushplus,
    "wecom": push_wecom,
    "serverchan": push_serverchan,
    "console": push_console,
}


# ---------------------------------------------------------------- 主流程

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="DeepSeek 生成内容 → PushPlus/企业微信/Server酱 推送",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                   help="只生成内容并打印详情，不真实推送")
    p.add_argument("--check-only", action="store_true",
                   help="只检查所选 通道+AI 需要的 Secrets 是否配置，然后退出")
    p.add_argument("--channel", default="pushplus", choices=CHANNELS,
                   help="推送通道（默认 pushplus）")
    p.add_argument("--ai-provider", default="deepseek", choices=PROVIDERS,
                   dest="ai_provider", help="内容生成方式（默认 deepseek）")
    p.add_argument("--template", default="brief", choices=TEMPLATES,
                   help="brief=简报；analysis=多空因子分析（每因子方向+多头概率）")
    p.add_argument("--topic", default="",
                   help="内容主题（默认取环境变量 TOPIC，再退到内置主题）")
    p.add_argument("--context", default="",
                   help="注入最新行情/公告等背景（也可用环境变量 CONTEXT），"
                        "供 analysis 模板给出概率时参考")
    p.add_argument("--timeout", type=int, default=30, help="网络超时秒数（默认 30）")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    channel, provider = args.channel, args.ai_provider
    template = args.template
    topic = args.topic or env("TOPIC") or DEFAULT_TOPIC
    context = args.context or env("CONTEXT")
    targets = ALL_CHANNELS if channel == "all" else [channel]

    log("=" * 56)
    log("Manual Run - Goldwind PushPlus+DeepSeek")
    log(f"  通道: {channel}  AI: {provider}  模板: {template}  dry_run: {args.dry_run}")
    log(f"  主题: {topic}" + (f"  附带背景: {len(context)} 字" if context else ""))
    log("=" * 56)

    # ---------- 模式 1：只检查 Secrets ----------
    if args.check_only:
        return 0 if print_secret_report(channel, provider) else 1

    # ---------- 模式 2/3：生成内容（dry-run 与真实推送共用）----------
    try:
        content = generate_content(provider, topic, args.timeout,
                                   template=template, context=context)
    except PushError as e:
        if args.dry_run and "缺少 Secret" in str(e):
            # dry-run 下联调时允许缺 AI Key：降级为模板内容，保证整条管线可预览
            log(f"⚠️  {e}")
            log("⚠️  dry-run 模式：降级使用 rule 模板继续演示管线")
            content = gen_by_rule(topic, template)
        else:
            log(f"❌ 内容生成失败：{e}")
            return 1

    now = datetime.now(CST).strftime("%m-%d %H:%M")
    if template == "analysis":
        title = f"{topic}·多空因子分析（{now}）"
    else:
        title = f"{topic}（{now}）"
    log("\n📝 生成的内容：")
    log("-" * 56)
    log(f"# {title}\n\n{content}")
    log("-" * 56)

    # ---------- 模式 2：dry-run，不真实推送 ----------
    if args.dry_run:
        log("\n🧪 dry-run：跳过真实推送。各通道 Secret 就绪情况：")
        ok = True
        for ch in targets:
            missing = [n for n in required_secrets(ch, "rule") if not env(n)]
            if missing:
                log(f"  ⚠️  {ch}: 缺少 {', '.join(missing)}（真实推送时会失败）")
                ok = False
            else:
                log(f"  ✅ {ch}: 就绪")
        log("\n✅ dry-run 完成。去掉 --dry-run 即为真实推送。")
        return 0 if ok else 0  # dry-run 永远返回 0，便于先看日志排查

    # ---------- 模式 3：真实推送 ----------
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
        mark = "✅" if not r.startswith("失败") else "❌"
        log(f"  {mark} {ch}: {r}")
    if failures:
        log(f"\n❌ 共 {failures}/{len(targets)} 个通道失败（详见上方日志）")
        return 1
    log("\n✅ 全部通道推送成功，请到微信查收。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
