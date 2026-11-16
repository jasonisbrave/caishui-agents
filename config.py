# -*- coding: utf-8 -*-
"""配置加载：config.json 覆盖默认值；密钥可放 config.json（gitignored）或环境变量。"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULTS: dict = {
    "host": "127.0.0.1",
    "port": 8642,
    "pass_all_exams_home": "D:/Code/Learning/Learning/.pass-all-exams",
    "skill_dir": "D:/Code/Learning/Learning/.opencode/skill/pass-all-exams",
    "learning_agents_md": "D:/Code/Learning/Learning/AGENTS.md",
    "llm": {
        "provider": "auto",            # auto | moonshot | kimi_cli | none
        "model": "kimi-latest",
        "kimi_base_url": "https://api.moonshot.cn/v1",
        "kimi_api_key": "",
        "kimi_api_key_env": "KIMI_API_KEY",
        "kimi_cli_bin": "kimi",
        "request_timeout_seconds": 300,
    },
    "anki": {
        "enabled": True,
        "url": "http://127.0.0.1:8765",
        "timeout_seconds": 6,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if CONFIG_PATH.exists():
        try:
            user_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg = _deep_merge(cfg, user_cfg)
        except (json.JSONDecodeError, OSError) as exc:
            raise SystemExit(f"config.json 解析失败：{exc}")
    return cfg


def kimi_api_key(cfg: dict) -> str:
    llm = cfg["llm"]
    return (
        llm.get("kimi_api_key", "").strip()
        or os.environ.get(llm.get("kimi_api_key_env", "KIMI_API_KEY"), "").strip()
    )


def resolve_provider(cfg: dict) -> str:
    """优先 Moonshot API（流式），其次本机 kimi CLI（订阅鉴权，非流式）。"""
    llm = cfg["llm"]
    choice = llm.get("provider", "auto")
    if choice in ("moonshot", "kimi_cli", "none"):
        if choice == "moonshot" and not kimi_api_key(cfg):
            return "none"
        if choice == "kimi_cli" and not shutil.which(llm.get("kimi_cli_bin", "kimi")):
            return "none"
        return choice
    # auto
    if kimi_api_key(cfg):
        return "moonshot"
    if shutil.which(llm.get("kimi_cli_bin", "kimi")):
        return "kimi_cli"
    return "none"


def public_config(cfg: dict) -> dict:
    """给前端的安全视图：不含密钥。"""
    llm = cfg["llm"]
    home = Path(cfg["pass_all_exams_home"])
    skill = Path(cfg["skill_dir"])
    agents_md = Path(cfg["learning_agents_md"])
    return {
        "provider": resolve_provider(cfg),
        "model": llm.get("model", ""),
        "base_url": llm.get("kimi_base_url", ""),
        "has_api_key": bool(kimi_api_key(cfg)),
        "port": cfg["port"],
        "pass_all_exams_home": str(home),
        "home_exists": home.exists(),
        "skill_dir_exists": skill.exists(),
        "examctl_exists": (skill / "scripts" / "examctl.py").exists(),
        "agents_md_exists": agents_md.exists(),
    }
