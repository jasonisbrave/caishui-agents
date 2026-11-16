# -*- coding: utf-8 -*-
"""AnkiConnect 桥（协议 v6）。对齐 Learning/AGENTS.md「Anki 集成」约定：

- 接口 http://127.0.0.1:8765，需本地 Anki 运行中 + AnkiConnect 插件；
- 由 Python 后端代理调用（不带 Origin 头），避开 AnkiConnect 浏览器 Origin 白名单；
- 牌组结构 `牌组::科目::章节`；卡片字段直接用 note 字段值，不用渲染后的 question/answer；
- 回写 answerCards ease：错=1、含糊=2、对=3、秒杀=4；绝不改写 .apkg 文件。

Anki 未运行时全部接口优雅降级为 {online: false}。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import config as cfgmod


def _anki_cfg() -> dict:
    return cfgmod.load_config().get("anki") or {}


def _request(action: str, params: dict | None = None):
    cfg = _anki_cfg()
    url = cfg.get("url", "http://127.0.0.1:8765")
    timeout = int(cfg.get("timeout_seconds", 6))
    body = json.dumps({"action": action, "version": 6, "params": params or {}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("error") is not None:
        raise RuntimeError(f"AnkiConnect: {data['error']}")
    return data.get("result")


def status() -> dict:
    cfg = _anki_cfg()
    if not cfg.get("enabled", True):
        return {"online": False, "reason": "配置已禁用（anki.enabled=false）"}
    try:
        return {"online": True, "version": _request("version")}
    except Exception as exc:  # 未运行/超时/插件缺失 一律视为离线
        return {"online": False, "reason": "Anki 未运行或 AnkiConnect 不通（启动 Anki 桌面端后重试）"}


def deck_overview() -> dict:
    """科目层（牌组::科目）到期/新卡计数。

    注意：getDeckStats 返回的 name 只有末段且父级聚合计数不可靠（截断/上限），
    故改用 findCards 按 `deck:"科目"` 查询计数——该查询天然覆盖全部子牌组。
    """
    st = status()
    if not st["online"]:
        return {**st, "decks": []}
    names = _request("deckNames") or []
    subjects = sorted({"::".join(n.split("::")[:2]) for n in names if "::" in n and '"' not in n})
    decks = []
    for subj in subjects:
        due = _request("findCards", {"query": f'deck:"{subj}" is:due'}) or []
        new = _request("findCards", {"query": f'deck:"{subj}" is:new'}) or []
        decks.append({"name": subj, "due": len(due), "new": len(new)})
    return {"online": True, "decks": decks}


def quiz_cards(deck: str, mode: str = "due", limit: int = 20) -> dict:
    """按科目牌组抽卡：is:due（到期复习）或 is:new（新卡覆盖）。"""
    st = status()
    if not st["online"]:
        return {**st, "cards": []}
    if '"' in deck or "\\" in deck:
        raise ValueError("非法牌组名")
    if mode not in ("due", "new"):
        mode = "due"
    limit = max(1, min(int(limit), 100))
    query = f'deck:"{deck}" is:{mode}'
    ids = _request("findCards", {"query": query}) or []
    cards = []
    for c in (_request("cardsInfo", {"cards": ids[:limit]}) or []):
        cards.append({
            "cardId": c.get("cardId"),
            "deck": c.get("deckName", ""),
            "model": c.get("modelName", ""),
            "fields": {k: v.get("value", "") for k, v in (c.get("fields") or {}).items()},
        })
    return {"online": True, "total": len(ids), "cards": cards}


def answer(card_id: int, ease: int) -> dict:
    st = status()
    if not st["online"]:
        return st
    ease = int(ease)
    if ease not in (1, 2, 3, 4):
        raise ValueError("ease 必须为 1/2/3/4（错/含糊/对/秒杀）")
    result = _request("answerCards", {"answers": [{"cardId": int(card_id), "ease": ease}]})
    return {"online": True, "ok": bool(result and result[0])}
