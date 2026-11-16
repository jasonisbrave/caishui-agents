# -*- coding: utf-8 -*-
"""财税备考 Agent 工作台 —— 本地单用户 Web 服务。

零第三方依赖（Python 3.10+ stdlib）：
    python server.py
默认 http://127.0.0.1:8642 ，配置见 config.json（模板 config.example.json）。

路由：
    GET  /                     静态单页
    GET  /api/config           前端安全配置视图
    GET  /api/courses          课程列表（读 state.json）
    GET  /api/course?slug=     单课程快照
    POST /api/exam             {action, course?, args?, confirm?} → examctl（只读直调；写命令需 confirm+args）
    POST /api/chat             {messages, course?} → Kimi SSE 流（moonshot）/单次（kimi CLI）
    POST /api/shutdown         优雅退出整个服务（网页右上角「退出」按钮调用）
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import config as cfgmod
import kimi_client
import skill_bridge
import anki_bridge
import history_store

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
                 ".ico": "image/x-icon"}
MAX_BODY = 1 << 20  # 1 MiB


class Server(ThreadingHTTPServer):
    # Windows 下 SO_REUSEADDR 会允许多进程静默共占同一端口（旧代码抢答新请求的根源），
    # 显式关闭：端口被占直接报错，快速失败。
    allow_reuse_address = False
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "caishui-agents/0.1"

    # ---------- 基础 ----------
    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _send_static(self, rel: str):
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        data = target.read_bytes()
        ext = target.suffix.lower()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(ext, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---------- GET ----------
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self._send_static("index.html")
        elif path == "/api/config":
            self._send_json(cfgmod.public_config(cfgmod.load_config()))
        elif path == "/api/courses":
            self._send_json({"courses": skill_bridge.list_courses()})
        elif path == "/api/course":
            qs = urllib.parse.parse_qs(parsed.query)
            slug = (qs.get("slug") or [""])[0]
            snap = skill_bridge.snapshot(slug)
            self._send_json(snap if snap is not None else {"error": f"课程不存在：{slug}"}, 200 if snap else 404)
        elif path == "/api/calendar":
            self._send_json(skill_bridge.calendar_data())
        elif path == "/api/anki/status":
            self._send_json(anki_bridge.status())
        elif path == "/api/history/list":
            self._send_json({"sessions": history_store.list_sessions()})
        elif path == "/api/history/get":
            qs = urllib.parse.parse_qs(parsed.query)
            sid = (qs.get("id") or [""])[0]
            sess = history_store.get(sid)
            self._send_json(sess if sess is not None else {"error": "会话不存在"}, 200 if sess else 404)
        elif path == "/api/history/search":
            qs = urllib.parse.parse_qs(parsed.query)
            q = (qs.get("q") or [""])[0]
            self._send_json({"sessions": history_store.search(q)})
        elif path == "/api/anki/decks":
            try:
                self._send_json(anki_bridge.deck_overview())
            except Exception as exc:
                self._send_json({"online": False, "error": str(exc), "decks": []})
        elif path.startswith("/static/"):
            self._send_static(path[len("/static/"):])
        else:
            self._send_json({"error": "not found"}, 404)

    # ---------- POST ----------
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/shutdown":  # 免请求体，立即优雅退出
            self._send_json({"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        body = self._read_body()
        if body is None:
            self._send_json({"error": "请求体须为 JSON（≤1MiB）"}, 400)
            return
        if path == "/api/exam":
            action = str(body.get("action", ""))
            course = str(body.get("course", ""))
            args = body.get("args")
            confirm = bool(body.get("confirm", False))
            if args is not None and not isinstance(args, str):
                args = None
            self._send_json(skill_bridge.safe_examctl(action, course, args, confirm))
        elif path == "/api/anki/quiz":
            deck = str(body.get("deck", ""))
            mode = str(body.get("mode", "due"))
            try:
                limit = int(body.get("limit", 20))
            except (TypeError, ValueError):
                limit = 20
            try:
                self._send_json(anki_bridge.quiz_cards(deck, mode, limit))
            except Exception as exc:
                self._send_json({"online": False, "error": str(exc), "cards": []})
        elif path == "/api/anki/answer":
            try:
                self._send_json(anki_bridge.answer(int(body.get("cardId", 0)), int(body.get("ease", 0))))
            except Exception as exc:
                self._send_json({"online": False, "error": str(exc)})
        elif path == "/api/history/save":
            try:
                self._send_json(history_store.save(body))
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
        elif path == "/api/history/delete":
            self._send_json({"ok": history_store.delete(str(body.get("id", "")))})
        elif path == "/api/chat":
            self._handle_chat(body)
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_chat(self, body: dict):
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            self._send_json({"error": "messages 不能为空"}, 400)
            return
        clean = []
        for m in messages[-40:]:
            role = m.get("role")
            content = str(m.get("content", ""))
            if role in ("system", "user", "assistant") and content.strip():
                clean.append({"role": role, "content": content[:60000]})
        course = body.get("course") or None
        if course is not None and not isinstance(course, str):
            course = None

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        try:
            for ev in kimi_client.chat_events(clean, course):
                data = json.dumps(ev, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # 客户端断开


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    cfg = cfgmod.load_config()
    provider = cfgmod.resolve_provider(cfg)
    pub = cfgmod.public_config(cfg)
    host, port = cfg["host"], int(cfg["port"])
    try:
        httpd = Server((host, port), Handler)
    except OSError as exc:
        print(f"✗ 端口 {port} 无法监听（{exc}）。")
        print("  可能原因：已有一个工作台实例在运行（先在网页点「退出」或运行 stop.ps1），")
        print("  或其他程序占用了该端口。")
        raise SystemExit(1)
    url = f"http://{host}:{port}"
    print("─" * 52)
    print("财税备考 Agent 工作台 v0.3")
    print(f"  地址     {url}")
    print(f"  Kimi接入 {provider}" + (f"（模型 {pub['model']}）" if provider == "moonshot" else "（本机 kimi -p 无头，非流式）"))
    print(f"  状态库   {pub['pass_all_exams_home']}（存在={pub['home_exists']}）")
    if provider == "none":
        print("  ⚠ 未配置 KIMI_API_KEY 且未找到 kimi CLI：对话页不可用，总览/计划页可用")
    print("  Ctrl+C 停止")
    print("─" * 52)
    if cfg.get("open_browser", True) and not os.environ.get("NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    print("\n已退出（可关闭浏览器标签页）")


if __name__ == "__main__":
    main()
