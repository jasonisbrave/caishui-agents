# -*- coding: utf-8 -*-
"""对话历史存储：每会话一个 JSON 文件，存于项目 history/ 目录（已 gitignore）。

放在后端而非 localStorage：不受浏览器配额/清缓存影响，可全文搜索。
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "history"
ID_RE = re.compile(r"^[0-9a-f]{8,24}$")
MAX_SESSIONS = 500
MAX_MESSAGES = 400
MAX_FILE_BYTES = 4 << 20  # 单会话 4MiB 上限


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir():
    HISTORY_DIR.mkdir(exist_ok=True)


def _valid_id(sid) -> bool:
    return bool(sid) and bool(ID_RE.match(str(sid)))


def _new_id() -> str:
    return f"{int(time.time() * 1000):x}{secrets.token_hex(3)}"


def save(payload: dict) -> dict:
    _ensure_dir()
    sid = str(payload.get("id") or "")
    if not _valid_id(sid):
        sid = _new_id()
    messages = [
        m for m in (payload.get("messages") or [])
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        and isinstance(m.get("content"), str) and m["content"].strip()
    ]
    messages = messages[-MAX_MESSAGES:]
    created = _load(sid) or {}
    data = {
        "id": sid,
        "title": str(payload.get("title") or "未命名会话")[:60],
        "course": str(payload.get("course") or "")[:80],
        "created_at": created.get("created_at") or _now(),
        "updated_at": _now(),
        "messages": messages,
    }
    text = json.dumps(data, ensure_ascii=False)
    if len(text.encode("utf-8")) <= MAX_FILE_BYTES:
        (HISTORY_DIR / f"{sid}.json").write_text(text + "\n", encoding="utf-8")
    return {"id": sid, "title": data["title"]}


def _load(sid) -> dict | None:
    if not _valid_id(sid):
        return None
    p = HISTORY_DIR / f"{sid}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _iter_files():
    _ensure_dir()
    return sorted(HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def list_sessions() -> list[dict]:
    out = []
    for p in _iter_files():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "id": d.get("id", p.stem),
            "title": d.get("title", ""),
            "course": d.get("course", ""),
            "updated_at": d.get("updated_at", ""),
            "n": len(d.get("messages", [])),
        })
        if len(out) >= MAX_SESSIONS:
            break
    return out


def get(sid) -> dict | None:
    return _load(sid)


def search(q: str) -> list[dict]:
    q = str(q or "").strip().lower()
    if not q:
        return list_sessions()
    res = []
    for p in _iter_files():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        hit_msg = None
        for m in d.get("messages", []):
            if q in str(m.get("content", "")).lower():
                hit_msg = m
                break
        if hit_msg is None and q not in str(d.get("title", "")).lower():
            continue
        content = hit_msg["content"] if hit_msg else d.get("title", "")
        idx = content.lower().find(q)
        start = max(0, idx - 20)
        snippet = ("…" if start > 0 else "") + content[start:idx + len(q) + 40] + "…"
        res.append({
            "id": d.get("id", p.stem), "title": d.get("title", ""), "course": d.get("course", ""),
            "updated_at": d.get("updated_at", ""), "n": len(d.get("messages", [])),
            "snippet": snippet,
        })
        if len(res) >= 50:
            break
    return res


def delete(sid) -> bool:
    if not _valid_id(sid):
        return False
    p = HISTORY_DIR / f"{sid}.json"
    if p.exists():
        p.unlink()
        return True
    return False
