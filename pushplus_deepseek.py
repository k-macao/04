#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pushplus_deepseek.py — DeepSeek 生成内容 → 多通道推送（PushPlus / 企业微信 / Server酱 / 控制台）

用法：
    python pushplus_deepseek.py                          # 真实推送（默认 pushplus + deepseek）
    python pushplus_deepseek.py --dry-run                # 只生成不推送，打印全部细节（联调用）
    python pushplus_deepseek.py --check-only             # 只检查所需 Secrets 是否已配置
    python pushplus_deepseek.py --channel all --ai-provider rule --topic "每日一句"

所需的 GitHub Secrets（按所选通道 / AI 提供商而定）：
    PUSHPLUS_TOKEN      channel ∈ {pushplus, all} 时必需（https://www.pushplus.plus 个人中心获取）
    WECOM_KEY           channel ∈ {wecom, all} 时必需（企业微信群机器人 webhook key）
    SERVERCHAN_SENDKEY  channel ∈ {serverchan, all} 时必需（Server酱 Turbo SendKey）
    DEEPSEEK_API_KEY    ai-provider = deepseek 时必需
    OPENAI_API_KEY      ai-provider = openai 时必需（可选 OPENAI_BASE_URL 覆盖接口地址）
    TOPIC               任意模式可选，覆盖默认内容主题
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
# --channel all 展开为三个真实通道（console 单独选择即可，避免制造噪音）
ALL_CHANNELS = ["pushplus", "wecom", "serverchan"]


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

def gen_by_rule(topic: str) -> str:
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    return textwrap.dedent(f"""\
        **{topic}**

        - 运行时间：{now}（北京时间）
        - 工作流：Manual Run - Goldwind PushPlus+DeepSeek
        - 内容模式：rule（未调用 AI，使用内置模板）

        > 如需 AI 生成内容：运行时把 ai_provider 选为 deepseek，
        > 并确认仓库 Secrets 中已配置 DEEPSEEK_API_KEY。""")


def chat_completion(url: str, api_key: str, model: str, topic: str,
                    timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "你是一位简洁专业的中文资讯编辑，输出 Markdown，不要寒暄。"},
            {"role": "user",
             "content": (f"请围绕「{topic}」生成一份今日简报：3~5 个要点，"
                         "每个要点一句话；结尾一句小结。全文不超过 250 字。")},
        ],
        "temperature": 0.7,
        "max_tokens": 600,
    }
    status, body = http_post_json(url, payload,
                                  {"Authorization": f"Bearer {api_key}"}, timeout)
    if status != 200:
        raise PushError(f"AI 接口返回 HTTP {status}：{body[:400]}")
    try:
        return json.loads(body)["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise PushError(f"AI 接口返回格式异常：{body[:400]}") from e


def generate_content(provider: str, topic: str, timeout: int) -> str:
    if provider == "rule":
        return gen_by_rule(topic)
    if provider == "deepseek":
        key = env("DEEPSEEK_API_KEY")
        if not key:
            raise PushError("缺少 Secret：DEEPSEEK_API_KEY（ai_provider=deepseek 必需）")
        return chat_completion(DEEPSEEK_URL, key, "deepseek-chat", topic, timeout)
    if provider == "openai":
        key = env("OPENAI_API_KEY")
        if not key:
            raise PushError("缺少 Secret：OPENAI_API_KEY（ai_provider=openai 必需）")
        base = env("OPENAI_BASE_URL") or DEFAULT_OPENAI_BASE_URL
        return chat_completion(f"{base.rstrip('/')}/chat/completions",
                               key, "gpt-4o-mini", topic, timeout)
    raise PushError(f"未知 AI 提供商：{provider}")


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
    p.add_argument("--topic", default="",
                   help="内容主题（默认取环境变量 TOPIC，再退到内置主题）")
    p.add_argument("--timeout", type=int, default=30, help="网络超时秒数（默认 30）")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    channel, provider = args.channel, args.ai_provider
    topic = args.topic or env("TOPIC") or DEFAULT_TOPIC
    targets = ALL_CHANNELS if channel == "all" else [channel]

    log("=" * 56)
    log("Manual Run - Goldwind PushPlus+DeepSeek")
    log(f"  通道: {channel}  AI: {provider}  dry_run: {args.dry_run}")
    log(f"  主题: {topic}")
    log("=" * 56)

    # ---------- 模式 1：只检查 Secrets ----------
    if args.check_only:
        return 0 if print_secret_report(channel, provider) else 1

    # ---------- 模式 2/3：生成内容（dry-run 与真实推送共用）----------
    try:
        content = generate_content(provider, topic, args.timeout)
    except PushError as e:
        if args.dry_run and "缺少 Secret" in str(e):
            # dry-run 下联调时允许缺 AI Key：降级为模板内容，保证整条管线可预览
            log(f"⚠️  {e}")
            log("⚠️  dry-run 模式：降级使用 rule 模板继续演示管线")
            content = gen_by_rule(topic)
        else:
            log(f"❌ 内容生成失败：{e}")
            return 1

    now = datetime.now(CST).strftime("%m-%d %H:%M")
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
