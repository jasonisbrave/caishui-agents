# -*- coding: utf-8 -*-
"""pass-all-exams 技能桥接层：课程发现、状态快照、examctl 调用。

原则（对齐 Learning 仓库红线）：
- 本层对真实学习状态库只做「读」；写操作（record-* / log-session 等）不在此暴露，
  后续版本以显式确认的 agent 工具循环形式接入。
- subprocess 一律显式 UTF-8，避免 Windows 控制台代码页污染中文。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from config import load_config

SAFE_ACTIONS = ("status", "summary")  # 只读子命令白名单
WRITE_ACTIONS = ("record-point", "record-error", "resolve-error", "add-card", "log-session")
# init / archive-course / restore-course 属低频管理操作，仍走命令行手动执行
_SLUG_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff\- ]*$")


def _cfg() -> dict:
    return load_config()


def courses_root(cfg: dict | None = None) -> Path:
    cfg = cfg or _cfg()
    return Path(cfg["pass_all_exams_home"]) / "courses"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tail_jsonl(path: Path, n: int = 8) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _yaml_scalars(text: str) -> dict:
    """极简提取 course.yaml 顶层标量（不引入 PyYAML）。嵌套结构忽略。"""
    scalars: dict = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w\-]*)\s*:\s*(.+?)\s*$", line)
        if m and "#" not in m.group(1):
            value = m.group(2).strip().strip("\"'")
            scalars[m.group(1)] = value
    return scalars


def list_courses() -> list[dict]:
    root = courses_root()
    if not root.exists():
        return []
    items = []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "state.json").exists():
            continue
        state = _read_json(d / "state.json") or {}
        yaml_text = ""
        if (d / "course.yaml").exists():
            try:
                yaml_text = (d / "course.yaml").read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        meta = _yaml_scalars(yaml_text)
        counts = state.get("counts", {})
        sessions = _tail_jsonl(d / "sessions.jsonl", 1)
        items.append(
            {
                "slug": d.name,
                "exam_date": state.get("exam_date") or meta.get("exam_date", ""),
                "counts": counts,
                "mode": meta.get("mode", ""),
                "updated_at": counts.get("updated_at", ""),
                "last_session": sessions[-1] if sessions else None,
            }
        )
    return items


def snapshot(slug: str, tail_n: int = 10) -> dict | None:
    root = courses_root()
    d = root / slug
    if not _SLUG_RE.match(slug) or not d.is_dir():
        return None
    state = _read_json(d / "state.json")
    yaml_text = ""
    if (d / "course.yaml").exists():
        yaml_text = (d / "course.yaml").read_text(encoding="utf-8", errors="replace")
    snap = {
        "slug": slug,
        "state": state,
        "course_yaml": yaml_text[:4000],
        "recent_sessions": _tail_jsonl(d / "sessions.jsonl", tail_n),
        "recent_errors": _tail_jsonl(d / "errors.jsonl", tail_n),
        "recent_cards": _tail_jsonl(d / "cards.jsonl", min(tail_n, 5)),
    }
    return snap


def snapshot_prompt_text(slug: str) -> str:
    """把课程快照压成给 LLM 的上下文文本。"""
    snap = snapshot(slug)
    if snap is None:
        return f"（未找到课程 {slug} 的状态数据）"
    parts = [f"# 课程状态快照：{slug}", ""]
    parts.append("## state.json")
    parts.append(json.dumps(snap["state"], ensure_ascii=False, indent=2))
    parts.append("\n## course.yaml（节选）")
    parts.append(snap["course_yaml"] or "（无）")
    for key in ("recent_sessions", "recent_errors"):
        parts.append(f"\n## {key}（尾部 {len(snap[key])} 条）")
        for row in snap[key]:
            parts.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(parts)


def run_examctl(args: list[str], timeout: int = 120) -> dict:
    """运行 examctl.py；强制 UTF-8；返回结构化结果。"""
    cfg = _cfg()
    examctl = Path(cfg["skill_dir"]) / "scripts" / "examctl.py"
    if not examctl.exists():
        return {"ok": False, "exit": -1, "stdout": "", "stderr": f"未找到 examctl.py：{examctl}"}
    env = dict(os.environ)
    env["PASS_ALL_EXAMS_HOME"] = str(Path(cfg["pass_all_exams_home"]))
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, str(examctl), *args],
            cwd=str(examctl.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
        )
        return {"ok": proc.returncode == 0, "exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit": -1, "stdout": "", "stderr": f"examctl 超时（>{timeout}s）"}
    except OSError as exc:
        return {"ok": False, "exit": -1, "stdout": "", "stderr": str(exc)}


def safe_examctl(action: str, course: str, args: str | None = None, confirm: bool = False) -> dict:
    """只读动作直接放行；写动作必须显式 confirm 且带原始参数串（v0.2 确认门控）。"""
    if action in SAFE_ACTIONS:
        if not _SLUG_RE.match(course):
            return {"ok": False, "exit": -1, "stdout": "", "stderr": f"非法课程名：{course!r}"}
        return run_examctl([action, "--course", course])
    if action in WRITE_ACTIONS:
        if not confirm:
            return {"ok": False, "exit": -1, "stdout": "", "stderr": "写操作需要用户在界面确认（confirm=true）"}
        if not args or not args.strip():
            return {"ok": False, "exit": -1, "stdout": "", "stderr": "写操作缺少参数"}
        import shlex
        try:
            argv = shlex.split(args)
        except ValueError as exc:
            return {"ok": False, "exit": -1, "stdout": "", "stderr": f"参数解析失败：{exc}"}
        # 从参数中提取并校验 --course，防止误写其他目录
        target = None
        for i, tok in enumerate(argv):
            if tok == "--course" and i + 1 < len(argv):
                target = argv[i + 1]
                break
        if target is None or not _SLUG_RE.match(target):
            return {"ok": False, "exit": -1, "stdout": "", "stderr": "写操作必须携带合法的 --course 参数"}
        return run_examctl([action, *argv])
    return {"ok": False, "exit": -1, "stdout": "", "stderr": f"动作不在白名单：{action}"}


def calendar_data() -> dict:
    """三层日历数据：考试日 / 复习到期 / 学习痕迹（按 points.updated_at 计数）。"""
    root = courses_root()
    courses: list[dict] = []
    by_date: dict = {}
    if not root.exists():
        return {"courses": courses, "by_date": by_date}

    def bucket(date: str):
        return by_date.setdefault(date, {"exams": [], "due": {}, "studied": {}})

    for d in sorted(root.iterdir()):
        if not d.is_dir() or not (d / "state.json").exists():
            continue
        state = _read_json(d / "state.json") or {}
        slug = d.name
        exam_date = state.get("exam_date") or ""
        courses.append({"slug": slug, "exam_date": exam_date})
        if exam_date:
            bucket(exam_date)["exams"].append(slug)
        points = state.get("points") or {}
        if isinstance(points, dict):
            for name, meta in points.items():
                if not isinstance(meta, dict):
                    continue
                due = str(meta.get("review_due") or "").strip()
                if due:
                    bucket(due).setdefault("due", {}).setdefault(slug, []).append(
                        meta.get("short") or name
                    )
                day = str(meta.get("updated_at") or "").strip()
                if day:
                    b = bucket(day)
                    b["studied"][slug] = b["studied"].get(slug, 0) + 1
    return {"courses": courses, "by_date": by_date}
