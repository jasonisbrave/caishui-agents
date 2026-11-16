# -*- coding: utf-8 -*-
"""Kimi 调用层：两种 provider，统一事件流接口。

- moonshot：Moonshot OpenAI 兼容 API，SSE 流式（需 KIMI_API_KEY）。
- kimi_cli：本机 `kimi -p` 无头调用，复用 Kimi Code 订阅鉴权，非流式（一次性返回）。

统一输出事件序列：{"type":"delta","text":...}* → {"type":"done",...} | {"type":"error",...}
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import config as cfgmod
import skill_bridge

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _read_text_or(path: Path, fallback: str) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fallback


def build_coach_system_prompt(course_slug: str | None) -> str:
    """备考教练系统提示 = pass-all-exams SKILL.md + Learning/AGENTS.md 财税约定 + 硬规则。"""
    cfg = cfgmod.load_config()
    skill_md = _read_text_or(Path(cfg["skill_dir"]) / "SKILL.md", "（未找到 SKILL.md）")
    agents_md = _read_text_or(Path(cfg["learning_agents_md"]), "（未找到 Learning/AGENTS.md）")
    today = _dt.date.today().isoformat()
    header = (
        "你是用户的财税备考教练（CPA/中级/税务师），运行在本地网页工作台中。\n"
        f"今天：{today}。请遵循下面两份规范开展教学，输出使用中文。\n"
    )
    hard_rules = (
        "\n# 工作台硬规则（最高优先级）\n"
        "1. 反幻觉：教学/判答回复必须区分「资料依据 / 合理推断 / 待确认」三类，未知就说未知。\n"
        "2. 状态回写（v0.2）：需要记录进度时，输出独立的 ```examctl``` 代码块，格式为：\n"
        "   ```examctl\n   record-point --course \"<课程>\" --point \"<考点>\" --level must --status mastered "
        "--source material --verification \"<实际验证依据>\" --review-due YYYY-MM-DD\n   ```\n"
        "   只用这五个写命令：record-point / record-error / resolve-error / add-card / log-session。"
        "用户在界面点「执行」之前命令不会运行——**绝不能声称已记录**，措辞用「建议记录」。"
        "一个代码块一条命令；阶段结束时把该记的命令集中给出。\n"
        "3. 状态一致性：counts 的 must mastered 必须与 points 实际状态一致（must mastered == points_done）；"
        "mastered 只能在该课程声明的验证方式通过后标记，并给 verification/review-due。\n"
        "4. 引用进度数据时以快照中的 state.json 与 JSONL 为准，不凭记忆编造数字。\n"
        "5. 一次只推进一个窄阶段（Map/Teach/Drill/Diagnose/Repair/Review），阶段末给下一步建议。\n"
        "6. Anki：工作台「刷题」页已直连 AnkiConnect（到期/新卡抽题、ease 1-4 回写），"
        "教学分工遵循上文 Anki 集成约定（真题形态用「真题精炼」、知识点卡用基础牌组、冲刺用「只做好题2026」）。\n"
    )
    ctx = ""
    if course_slug:
        ctx = (
            "\n# 当前课程实时状态（由工作台注入）\n"
            + skill_bridge.snapshot_prompt_text(course_slug)
            + "\n请基于以上状态决定从哪里继续（/exam resume 语义），不要重复已 mastered 的点。\n"
        )
    return header + "\n# 技能规范：pass-all-exams SKILL.md\n" + skill_md + hard_rules + ctx + (
        "\n# 仓库级财税备考约定：Learning/AGENTS.md\n" + agents_md
    )


def _sse_events(stream) :
    """解析 OpenAI 兼容 SSE 流，产出 delta 文本与可选 usage。"""
    for raw in stream:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices") or []
        if choices:
            delta = (choices[0].get("delta") or {}).get("content")
            if delta:
                yield {"type": "delta", "text": delta}
        if chunk.get("usage"):
            yield {"type": "usage", "usage": chunk["usage"]}


def moonshot_stream(messages: list[dict], model: str, timeout: int):
    cfg = cfgmod.load_config()
    llm = cfg["llm"]
    key = cfgmod.kimi_api_key(cfg)
    url = llm["kimi_base_url"].rstrip("/") + "/chat/completions"
    body = json.dumps({"model": model, "messages": messages, "stream": True}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            yield from _sse_events(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        yield {"type": "error", "message": f"Moonshot API HTTP {exc.code}：{detail}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        yield {"type": "error", "message": f"Moonshot API 连接失败：{exc}"}


def kimi_cli_once(messages: list[dict], timeout: int = 600):
    """`kimi -p` 无头单轮：把多轮消息压成一份提示词。"""
    cfg = cfgmod.load_config()
    bin_name = cfg["llm"].get("kimi_cli_bin", "kimi")
    exe = shutil.which(bin_name)
    if not exe:
        yield {"type": "error", "message": f"未找到 {bin_name} 可执行文件"}
        return
    lines = []
    for msg in messages:
        role = {"system": "【系统设定】", "user": "【用户】", "assistant": "【教练】"}.get(msg["role"], "【?】")
        lines.append(f"{role}\n{msg['content']}")
    prompt = "\n\n".join(lines) + "\n\n【任务】按系统设定输出回应。"
    try:
        proc = subprocess.run(
            [exe, "-p", prompt, "--output-format", "text"],
            cwd=str(Path(__file__).resolve().parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        yield {"type": "error", "message": f"kimi CLI 超时（>{timeout}s）"}
        return
    except OSError as exc:
        yield {"type": "error", "message": f"kimi CLI 启动失败：{exc}"}
        return
    text = ANSI_RE.sub("", proc.stdout or "").strip()
    if proc.returncode != 0 and not text:
        yield {"type": "error", "message": f"kimi CLI 退出码 {proc.returncode}：{(proc.stderr or '').strip()[:400]}"}
        return
    if text:
        yield {"type": "delta", "text": text}


def chat_events(messages: list[dict], course_slug: str | None):
    """统一入口：解析 provider，注入教练系统提示，产出事件流。"""
    cfg = cfgmod.load_config()
    llm = cfg["llm"]
    provider = cfgmod.resolve_provider(cfg)
    if provider == "none":
        yield {"type": "error", "message": "无可用 Kimi 接入：请在 config.json 配置 kimi_api_key，或安装 kimi CLI 后重试。"}
        return
    final_messages = list(messages)
    if course_slug:
        final_messages = [{"role": "system", "content": build_coach_system_prompt(course_slug)}] + final_messages
    timeout = int(llm.get("request_timeout_seconds", 300))
    if provider == "moonshot":
        inner = moonshot_stream(final_messages, llm.get("model", "kimi-latest"), timeout)
    else:
        inner = kimi_cli_once(final_messages, max(timeout, 600))
    had_error = False
    for ev in inner:
        if ev["type"] == "error":
            had_error = True
        yield ev
    if not had_error:
        yield {"type": "done", "provider": provider, "model": llm.get("model", "")}
