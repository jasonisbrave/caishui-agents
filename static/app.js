/* 财税备考工作台 v0.1 —— 前端逻辑（原生 JS，无构建） */
"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { config: null, courses: [], history: [], streaming: false };

/* ---------- 通用 ---------- */
async function getJSON(url) {
  const r = await fetch(url);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}

function fmtDate(iso) {
  if (!iso) return "未设考期";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d)) return iso;
  const days = Math.ceil((d - new Date()) / 86400000);
  return days >= 0 ? `${iso}（还有 ${days} 天）` : `${iso}（已考）`;
}

/* ---------- 状态栏 ---------- */
async function loadConfig() {
  state.config = await getJSON("/api/config");
  const c = state.config;
  const prov =
    c.provider === "moonshot" ? `Kimi API · ${c.model}` :
    c.provider === "kimi_cli" ? "kimi CLI（订阅鉴权，非流式）" :
    `<span class="off">Kimi 未接入</span>`;
  $("#statusBar").innerHTML =
    `Kimi接入：<b>${prov}</b><br>状态库：${c.home_exists ? "已连接" : '<span class="off">路径无效</span>'}`;
}

/* ---------- 总览 ---------- */
async function loadCourses() {
  const grid = $("#courseGrid");
  try {
    const j = await getJSON("/api/courses");
    state.courses = j.courses || [];
  } catch (e) {
    grid.innerHTML = `<p class="hint">读取失败：${e.message}</p>`;
    return;
  }
  if (!state.courses.length) { grid.innerHTML = '<p class="hint">状态库中没有课程。</p>'; return; }
  grid.innerHTML = state.courses.map((c) => {
    const n = c.counts || {};
    const total = n.points_total || 0, done = n.points_done || 0;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const past = c.exam_date && new Date(c.exam_date + "T00:00:00") < new Date();
    const last = c.last_session;
    const lastTxt = last ? `${last.action || ""} ${last.topic || ""}（${(last.ts || last.date || "").slice(0, 10)}）` : "无会话记录";
    return `<div class="card">
      <div class="name"><span>${c.slug}</span><span class="badge${past ? " past" : ""}">${past ? "已考" : (c.mode || "在修")}</span></div>
      <div class="meter"><i style="width:${pct}%"></i></div>
      <div class="meta"><span>进度 ${done}/${total}（${pct}%）</span><span>错题 ${n.errors ?? "-"}</span><span>卡片 ${n.cards ?? "-"}</span></div>
      <div class="meta"><span>${fmtDate(c.exam_date)}</span></div>
      <div class="last">最近：${lastTxt}</div>
    </div>`;
  }).join("");
  const opts = state.courses.map((c) => `<option value="${c.slug}">${c.slug}</option>`).join("");
  $("#planCourse").innerHTML = opts;
  $("#ctxCourse").innerHTML = opts;
}

/* ---------- 备考计划 ---------- */
async function runExam(act) {
  const course = $("#planCourse").value;
  const out = $("#examOut");
  out.hidden = false;
  out.textContent = `执行 examctl ${act} --course "${course}" …`;
  try {
    const r = await fetch("/api/exam", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: act, course }),
    });
    const j = await r.json();
    out.textContent = (j.stdout || "") + (j.stderr ? `\n[stderr]\n${j.stderr}` : "") + (j.ok ? "" : `\n[exit ${j.exit}]`);
  } catch (e) { out.textContent = `调用失败：${e.message}`; }
}

function coachJump(kind) {
  const course = $("#planCourse").value;
  $("#ctxEnabled").checked = true;
  $("#ctxCourse").value = course;
  switchTab("chat");
  const prompt = kind === "resume"
    ? `/exam ${course} resume：请基于该课程当前状态，从我还没掌握的点继续教学，一次一个窄阶段。`
    : `/exam ${course} drill：请提取当前薄弱点，用真题题型做主动回忆式抽查（含干扰项）。`;
  $("#chatText").value = prompt;
  sendChat();
}

/* ---------- 对话（SSE） ---------- */
function addMsg(role, text, tag) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  const t = document.createElement("span");
  t.className = "tag"; t.textContent = tag || (role === "user" ? "我" : "教练");
  const body = document.createElement("span");
  body.textContent = text;
  div.append(t, body);
  $("#chatLog").appendChild(div);
  $("#chatLog").scrollTop = $("#chatLog").scrollHeight;
  return body;
}

async function sendChat() {
  if (state.streaming) return;
  const text = $("#chatText").value.trim();
  if (!text) return;
  $("#chatText").value = "";
  addMsg("user", text);
  const useCtx = $("#ctxEnabled").checked && $("#ctxCourse").value;
  const course = useCtx ? $("#ctxCourse").value : null;

  state.streaming = true;
  $("#btnSend").disabled = true;
  const bodyEl = addMsg("assistant", "", course ? `教练 · ${course}` : "教练");
  bodyEl.style.whiteSpace = "pre-wrap";   // 流式期间纯文本原样显示
  try {
    const r = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [...state.history, { role: "user", content: text }], course }),
    });
    if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
    const reader = r.body.getReader();
    const decoder = new TextDecoder();
    let buf = "", acc = "", done = false;
    while (!done) {
      const { value, done: rdDone } = await reader.read();
      if (rdDone) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        let ev; try { ev = JSON.parse(line.slice(5)); } catch { continue; }
        if (ev.type === "delta") { acc += ev.text; bodyEl.textContent = acc; $("#chatLog").scrollTop = $("#chatLog").scrollHeight; }
        else if (ev.type === "error") { acc += `\n⚠ ${ev.message}`; bodyEl.textContent = acc; }
        else if (ev.type === "done") { done = true; }
      }
    }
    state.history.push({ role: "user", content: text }, { role: "assistant", content: acc });
    if (state.history.length > 30) state.history = state.history.slice(-30);
    bodyEl.style.whiteSpace = "";
    bodyEl.innerHTML = renderAssistant(acc);   // 完成后按 Markdown 预览渲染（examctl 块 → 确认卡片）
    saveSession();
  } catch (e) {
    addMsg("error", `请求失败：${e.message}`);
  } finally {
    state.streaming = false;
    $("#btnSend").disabled = false;
  }
}

/* ---------- 绑定 ---------- */
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
$("#btnRefresh").addEventListener("click", loadCourses);
document.querySelectorAll("#tab-plan [data-act]").forEach((b) =>
  b.addEventListener("click", () => {
    const act = b.dataset.act;
    if (act === "resume" || act === "drill") coachJump(act); else runExam(act);
  }));
$("#btnSend").addEventListener("click", sendChat);
$("#btnClear").addEventListener("click", () => { state.history = []; $("#chatLog").innerHTML = ""; });
$("#chatText").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

/* ---------- 日历 ---------- */
const cal = { month: null, data: null };

async function loadCalendar() {
  try { cal.data = await getJSON("/api/calendar"); }
  catch (e) { $("#calGrid").innerHTML = `<p class="hint">读取失败：${e.message}</p>`; return; }
  renderCalendar();
}

function renderCalendar() {
  if (!cal.month) cal.month = new Date();
  const y = cal.year = cal.month.getFullYear(), m = cal.month.getMonth();
  $("#calTitle").textContent = `${y} 年 ${m + 1} 月`;
  const grid = $("#calGrid");
  const first = new Date(y, m, 1);
  const startOffset = (first.getDay() + 6) % 7;           // 周一为行首
  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const todayStr = new Date().toISOString().slice(0, 10);
  let html = "";
  for (let i = 0; i < startOffset; i++) html += "<span class='cal-cell empty'></span>";
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    const ev = (cal.data && cal.data.by_date[ds]) || {};
    const dueN = Object.values(ev.due || {}).reduce((s, a) => s + a.length, 0);
    const studyN = Object.values(ev.studied || {}).reduce((s, n) => s + n, 0);
    const cls = ["cal-cell", ds === todayStr ? "today" : "", ev.exams?.length ? "has-exam" : "", dueN ? "has-due" : ""].filter(Boolean).join(" ");
    html += `<span class="${cls}" data-date="${ds}">
      <b>${d}</b>
      ${ev.exams?.length ? `<i class="dot exam" title="考试：${ev.exams.join("、")}"></i>` : ""}
      ${dueN ? `<em class="mini due">${dueN} 到期</em>` : ""}
      ${studyN ? `<em class="mini study">${studyN} 点</em>` : ""}
    </span>`;
  }
  grid.innerHTML = html;
  grid.querySelectorAll(".cal-cell[data-date]").forEach((c) =>
    c.addEventListener("click", () => showDay(c.dataset.date)));
  showDay(todayStr);
}

function showDay(ds) {
  const box = $("#calDetail");
  const ev = (cal.data && cal.data.by_date[ds]) || {};
  if (!ev.exams?.length && !Object.keys(ev.due || {}).length && !Object.keys(ev.studied || {}).length) {
    box.innerHTML = `<b>${ds}</b><span class="hint">无记录</span>`;
    return;
  }
  const rows = [`<b>${ds}</b>`];
  if (ev.exams?.length) rows.push(`<div><i class="dot exam"></i> 考试：${ev.exams.map(esc).join("、")}</div>`);
  for (const [course, pts] of Object.entries(ev.due || {}))
    rows.push(`<div><i class="dot due"></i> ${esc(course)} 复习到期：${pts.map(esc).join("；")}</div>`);
  for (const [course, n] of Object.entries(ev.studied || {}))
    rows.push(`<div><i class="dot study"></i> ${esc(course)} 学习 ${n} 个考点</div>`);
  box.innerHTML = rows.join("");
}

$("#calPrev").addEventListener("click", () => { cal.month.setMonth(cal.month.getMonth() - 1); renderCalendar(); });
$("#calNext").addEventListener("click", () => { cal.month.setMonth(cal.month.getMonth() + 1); renderCalendar(); });
$("#calToday").addEventListener("click", () => { cal.month = new Date(); renderCalendar(); });

/* ---------- Anki 刷题 ---------- */
const quiz = { cards: [], idx: 0, stat: { 1: 0, 2: 0, 3: 0, 4: 0 } };

async function loadAnki() {
  const dot = $("#ankiDot");
  $("#ankiStatus").textContent = "检测中…";
  try {
    const st = await getJSON("/api/anki/status");
    dot.classList.toggle("off", !st.online);
    dot.title = st.online ? `Anki 在线（协议 ${st.version}）` : "Anki 离线";
    if (!st.online) {
      $("#ankiStatus").textContent = "Anki 离线：启动 Anki 桌面端后点「刷新牌组」";
      return;
    }
    const dk = await getJSON("/api/anki/decks");
    const decks = dk.decks || [];
    const groups = {};
    decks.forEach((d) => {
      const top = d.name.split("::")[0];
      (groups[top] = groups[top] || []).push(d);
    });
    $("#quizDeck").innerHTML = Object.entries(groups).map(([top, list]) =>
      `<optgroup label="${esc(top)}">` +
      list.map((d) => `<option value="${esc(d.name)}">${esc(d.name.split("::").slice(1).join("::"))}（到期 ${d.due} / 新 ${d.new}）</option>`).join("") +
      `</optgroup>`).join("");
    const dueAll = decks.reduce((s, d) => s + d.due, 0);
    $("#ankiStatus").textContent = `在线 · ${decks.length} 个科目牌组 · 全部到期 ${dueAll} 张`;
    dot.title += ` · 到期 ${dueAll}`;
  } catch (e) { $("#ankiStatus").textContent = "读取失败：" + e.message; }
}

function splitFields(fields) {
  // 两类卡片（Learning/AGENTS.md 约定）：题目卡 question/options/answer/notes；挖空卡 问题/答案/笔记
  if (fields.question !== undefined) {
    return {
      type: "mcq",
      q: fields.question || "",
      opts: (fields.options || "").split("||").filter(Boolean),
      ans: (fields.answer || "").split("||").filter(Boolean).map(Number),
      notes: fields.notes || "",
    };
  }
  return { type: "basic", q: fields["问题"] || "", opts: [], ans: [], a: fields["答案"] || "", notes: fields["笔记"] || "" };
}

const LTRS = ["A", "B", "C", "D", "E", "F"];

function renderQuizCard() {
  const c = quiz.cards[quiz.idx];
  if (!c) { finishQuiz(); return; }
  $("#quizProgress").textContent = `第 ${quiz.idx + 1} / ${quiz.cards.length} 张`;
  $("#quizCount").textContent = `错 ${quiz.stat[1]} · 含糊 ${quiz.stat[2]} · 对 ${quiz.stat[3]} · 秒杀 ${quiz.stat[4]}`;
  $("#quizDeckName").textContent = `${c.deck} · ${c.model}`;
  const f = splitFields(c.fields);
  $("#quizQ").textContent = f.q;
  $("#quizOpts").innerHTML = f.opts.map((o, i) => `<li><b>${LTRS[i]}.</b> ${esc(o)}</li>`).join("");
  $("#quizReveal").hidden = true;
  $("#quizNotes").textContent = "";
  $("#quizA").textContent = "";
  $("#quizShow").hidden = false;
  $("#quizGrades").hidden = true;
  quiz._cur = { cardId: c.cardId, f };
}

async function revealQuiz() {
  const { f } = quiz._cur;
  if (f.type === "mcq") {
    $("#quizA").innerHTML = "答案：<b>" + f.ans.map((n) => LTRS[n - 1] || n).join("、") + "</b>";
  } else {
    $("#quizA").innerHTML = "答案：<b>" + esc(f.a) + "</b>";
  }
  $("#quizNotes").textContent = f.notes || "";
  $("#quizReveal").hidden = false;
  $("#quizShow").hidden = true;
  $("#quizGrades").hidden = false;
}

async function gradeQuiz(ease) {
  const { cardId } = quiz._cur;
  quiz.stat[ease]++;
  try {
    const r = await fetch("/api/anki/answer", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cardId, ease }),
    });
    const j = await r.json();
    if (!j.online || !j.ok) console.warn("Anki 回写未成功", j);
  } catch (err) { console.warn("Anki 回写失败", err); }
  quiz.idx++;
  renderQuizCard();
}

function finishQuiz() {
  $("#quizCard").innerHTML = `<p class="hint">本轮完成：对+秒杀 ${quiz.stat[3] + quiz.stat[4]} / ${quiz.cards.length}（含糊 ${quiz.stat[2]}、错 ${quiz.stat[1]}）。</p>
    <p class="hint">错/含糊的考点可去「对话」页让教练换角度重测并记入错题本。</p>`;
  $("#quizShow").hidden = true;
  $("#quizGrades").hidden = true;
  loadAnki();
}

async function startQuiz() {
  const deck = $("#quizDeck").value;
  if (!deck) { alert("Anki 离线或没有可用牌组：请先启动 Anki 桌面端，再点「刷新牌组」。"); return; }
  const mode = document.querySelector(".seg-btn.active").dataset.mode;
  const r = await fetch("/api/anki/quiz", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deck, mode, limit: parseInt($("#quizLimit").value, 10) }),
  });
  const j = await r.json();
  if (!j.online) { alert("Anki 离线：" + (j.error || "")); return; }
  if (!j.cards.length) { alert("没有符合条件的卡（换「新卡」模式或换个科目试试）"); return; }
  quiz.cards = j.cards; quiz.idx = 0; quiz.stat = { 1: 0, 2: 0, 3: 0, 4: 0 };
  $("#quizArea").hidden = false;
  $("#quizCard").innerHTML = `
    <div class="quiz-deck" id="quizDeckName"></div>
    <div class="quiz-q" id="quizQ"></div>
    <ul class="quiz-opts" id="quizOpts"></ul>
    <div id="quizReveal" class="quiz-reveal" hidden>
      <div class="quiz-a" id="quizA"></div>
      <div class="quiz-notes" id="quizNotes"></div>
    </div>`;
  renderQuizCard();
}

$("#ankiRefresh").addEventListener("click", loadAnki);
$("#quizStart").addEventListener("click", startQuiz);
$("#quizShow").addEventListener("click", revealQuiz);
document.querySelectorAll(".seg-btn").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
  }));
document.querySelectorAll(".grade").forEach((b) =>
  b.addEventListener("click", () => gradeQuiz(parseInt(b.dataset.ease, 10))));

/* ---------- Markdown 渲染（轻量实现，无外部依赖） ---------- */
function inlineMd(s) {
  return s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<i>$2</i>");
}

function mdToHtml(text) {
  const lines = String(text).split("\n");
  let html = "", i = 0, para = [];
  const flushPara = () => {
    if (para.length) { html += `<p>${inlineMd(para.join("<br>"))}</p>`; para = []; }
  };
  while (i < lines.length) {
    const line = lines[i];
    // 围栏代码块（普通代码，examctl 块已在入口被抽走）
    if (/^\s*```/.test(line)) {
      flushPara();
      const buf = [];
      i++;
      while (i < lines.length && !/^\s*```/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++; // 跳过闭合围栏
      html += `<pre class="md-code">${esc(buf.join("\n"))}</pre>`;
      continue;
    }
    // 标题
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flushPara(); const lv = h[1].length; html += `<div class="md-h md-h${lv}">${inlineMd(esc(h[2]))}</div>`; i++; continue; }
    // 分隔线
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flushPara(); html += "<hr class='md-hr'>"; i++; continue; }
    // 引用块
    if (/^\s*>\s?/.test(line)) {
      flushPara();
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      html += `<blockquote class="md-quote">${inlineMd(esc(buf.join("<br>")))}</blockquote>`;
      continue;
    }
    // 表格（| 分隔 + 第二行为分隔行）
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && /-/.test(lines[i + 1])) {
      flushPara();
      const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => inlineMd(esc(c.trim())));
      const head = cells(rows[0]);
      let t = "<table class='md-table'><thead><tr>" + head.map((c) => `<th>${c}</th>`).join("") + "</tr></thead><tbody>";
      for (let r = 2; r < rows.length; r++) t += "<tr>" + cells(rows[r]).map((c) => `<td>${c}</td>`).join("") + "</tr>";
      html += t + "</tbody></table>";
      continue;
    }
    // 无序 / 有序列表
    if (/^\s*[-*]\s+/.test(line)) {
      flushPara();
      const buf = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++; }
      html += "<ul class='md-ul'>" + buf.map((x) => `<li>${inlineMd(esc(x))}</li>`).join("") + "</ul>";
      continue;
    }
    if (/^\s*\d+[.、)]\s+/.test(line)) {
      flushPara();
      const buf = [];
      while (i < lines.length && /^\s*\d+[.、)]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*\d+[.、)]\s+/, "")); i++; }
      html += "<ol class='md-ol'>" + buf.map((x) => `<li>${inlineMd(esc(x))}</li>`).join("") + "</ol>";
      continue;
    }
    if (!line.trim()) { flushPara(); i++; continue; }
    para.push(esc(line));
    i++;
  }
  flushPara();
  return html;
}

/* ---------- examctl 命令确认卡片 ---------- */
function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function cmdCardHtml(cmd) {
  const action = cmd.split(/\s+/)[0];
  return `<div class="cmd-card">
    <div class="cmd-head">待确认命令 · <code>${esc(action)}</code></div>
    <pre class="cmd-body">${esc(cmd)}</pre>
    <div class="cmd-actions">
      <button class="primary small cmd-run" data-cmd="${esc(cmd)}">执行</button>
      <button class="ghost small cmd-copy" data-cmd="${esc(cmd)}">复制</button>
      <span class="cmd-result hint"></span>
    </div>
  </div>`;
}

/* 教练消息渲染：Markdown 预览 + 仅 ```examctl 块生成确认卡片 */
function renderAssistant(text) {
  const cards = [];
  const stripped = String(text).replace(/```examctl\s*\n([\s\S]*?)```/g, (m, c) => {
    const cmd = c.trim();
    if (!cmd) return m;
    cards.push(cmd);
    return "\x00CARD" + (cards.length - 1) + "\x00";
  });
  let html = mdToHtml(stripped);
  html = html.replace(/\x00CARD(\d+)\x00/g, (m, idx) => cmdCardHtml(cards[+idx]));
  return html;
}

async function runCmdCard(btn) {
  const cmd = btn.dataset.cmd;
  const card = btn.closest(".cmd-card");
  const result = card.querySelector(".cmd-result");
  const action = cmd.split(/\s+/)[0];
  const rest = cmd.slice(action.length).trim();
  const mArg = rest.match(/--course\s+"([^"]+)"/) || rest.match(/--course\s+(\S+)/);
  if (!btn.disabled && !confirm(`确认执行写操作？\n\n${cmd}\n\n将写入真实学习状态库。`)) return;
  btn.disabled = true;
  result.textContent = "执行中…";
  try {
    const r = await fetch("/api/exam", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, course: mArg ? mArg[1] : "", args: rest, confirm: true }),
    });
    const j = await r.json();
    if (j.ok) {
      result.textContent = "✓ 已执行" + (j.stdout ? `：${(j.stdout || "").trim().slice(0, 120)}` : "");
      btn.textContent = "已执行";
      loadCourses(); loadCalendar();
    } else {
      result.textContent = "✗ " + (j.stderr || `exit ${j.exit}`).slice(0, 200);
      btn.disabled = false;
    }
  } catch (e) { result.textContent = "✗ " + e.message; btn.disabled = false; }
}

document.addEventListener("click", (e) => {
  const run = e.target.closest(".cmd-run");
  if (run) { runCmdCard(run); return; }
  const copy = e.target.closest(".cmd-copy");
  if (copy) {
    navigator.clipboard?.writeText(copy.dataset.cmd).then(() => { copy.textContent = "已复制"; });
  }
});

/* ---------- 草稿纸 ---------- */
const SCRATCH_KEY = "caishui_scratchpad_v1";
const scratch = $("#scratchPad");
const scratchMeta = $("#scratchMeta");
function loadScratch() {
  try { scratch.value = localStorage.getItem(SCRATCH_KEY) || ""; } catch { scratch.value = ""; }
  updateScratchMeta();
}
function saveScratch() {
  try { localStorage.setItem(SCRATCH_KEY, scratch.value); } catch { /* 存储不可用时静默 */ }
}
function updateScratchMeta() {
  const lines = scratch.value ? scratch.value.split("\n").length : 0;
  scratchMeta.textContent = `${scratch.value.length} 字 · ${lines} 行`;
}
scratch.addEventListener("input", () => { saveScratch(); updateScratchMeta(); });
$("#btnScratchToInput").addEventListener("click", () => {
  const t = scratch.value.trim();
  if (!t) return;
  const box = $("#chatText");
  box.value = box.value ? box.value + "\n" + t : t;
  box.focus();
});
$("#btnScratchClear").addEventListener("click", () => {
  if (scratch.value && !confirm("清空草稿纸？内容不可恢复。")) return;
  scratch.value = "";
  saveScratch();
  updateScratchMeta();
});

/* ---------- 历史会话 ---------- */
const hist = { currentId: null };

async function saveSession() {
  if (!state.history.length) return;
  const first = state.history.find((m) => m.role === "user");
  try {
    const r = await fetch("/api/history/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: hist.currentId,
        title: (first ? first.content : "未命名会话").slice(0, 60),
        course: ($("#ctxEnabled").checked && $("#ctxCourse").value) || "",
        messages: state.history,
      }),
    });
    const j = await r.json();
    if (j.id) hist.currentId = j.id;
    loadHistoryList($("#historySearch").value);
  } catch { /* 保存失败不打断对话 */ }
}

async function loadHistoryList(q = "") {
  try {
    const url = q.trim() ? `/api/history/search?q=${encodeURIComponent(q.trim())}` : "/api/history/list";
    const j = await getJSON(url);
    hist.sessions = j.sessions || [];
    renderHistoryList();
  } catch (e) { $("#historyList").innerHTML = `<p class="hint">读取失败：${e.message}</p>`; }
}

function renderHistoryList() {
  const box = $("#historyList");
  if (!hist.sessions || !hist.sessions.length) {
    box.innerHTML = '<p class="hint">' + ($("#historySearch").value ? "无匹配会话" : "暂无历史会话") + "</p>";
    return;
  }
  box.innerHTML = hist.sessions.map((s) => `
    <div class="hist-item${s.id === hist.currentId ? " active" : ""}" data-id="${esc(s.id)}">
      <div class="hist-title">${esc(s.title || "未命名")}</div>
      <div class="hist-meta">${esc((s.updated_at || "").slice(5, 16))} · ${s.n} 条${s.course ? " · " + esc(s.course) : ""}</div>
      ${s.snippet ? `<div class="hist-snippet">${esc(s.snippet)}</div>` : ""}
      <button class="hist-del" data-id="${esc(s.id)}" title="删除">×</button>
    </div>`).join("");
}

async function openSession(id) {
  try {
    const s = await getJSON(`/api/history/get?id=${encodeURIComponent(id)}`);
    if (!s || !Array.isArray(s.messages)) return;
    hist.currentId = id;
    state.history = s.messages.slice(-40);
    $("#chatLog").innerHTML = "";
    for (const m of s.messages) {
      if (m.role === "user") addMsg("user", m.content);
      else { const b = addMsg("assistant", "", "教练"); b.innerHTML = renderAssistant(m.content); }
    }
    if (s.course && $("#ctxCourse").querySelector(`option[value="${CSS.escape(s.course)}"]`)) {
      $("#ctxEnabled").checked = true;
      $("#ctxCourse").value = s.course;
    }
    $("#chatLog").scrollTop = $("#chatLog").scrollHeight;
    renderHistoryList();
  } catch (e) { alert("读取会话失败：" + e.message); }
}

function newSession() {
  state.history = [];
  hist.currentId = null;
  $("#chatLog").innerHTML = "";
  renderHistoryList();
}

$("#btnNewChat").addEventListener("click", newSession);
$("#btnClear").addEventListener("click", newSession);
let _searchTimer;
$("#historySearch").addEventListener("input", (e) => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => loadHistoryList(e.target.value), 300);
});
$("#historyList").addEventListener("click", (e) => {
  const del = e.target.closest(".hist-del");
  if (del) {
    e.stopPropagation();
    if (!confirm("删除这条历史会话？不可恢复。")) return;
    fetch("/api/history/delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: del.dataset.id }),
    }).then(() => {
      if (del.dataset.id === hist.currentId) newSession();
      loadHistoryList($("#historySearch").value);
    });
    return;
  }
  const item = e.target.closest(".hist-item");
  if (item) openSession(item.dataset.id);
});

/* ---------- 视图：字号 / 日夜主题 ---------- */
const FONT_KEY = "caishui_zoom_v1";
const THEME_KEY = "caishui_theme_v1";
let zoomLevel = 1;
function setZoom(z, save = true) {
  zoomLevel = Math.min(1.4, Math.max(0.8, Math.round(z * 20) / 20));
  document.body.style.zoom = zoomLevel;
  if (save) { try { localStorage.setItem(FONT_KEY, String(zoomLevel)); } catch { } }
}
function applyTheme(t) {
  document.documentElement.dataset.theme = t === "dark" ? "dark" : "light";
  $("#themeToggle").textContent = t === "dark" ? "☀️" : "🌙";
}
function toggleTheme() {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  try { localStorage.setItem(THEME_KEY, next); } catch { }
}
$("#fontMinus").addEventListener("click", () => setZoom(zoomLevel - 0.05));
$("#fontPlus").addEventListener("click", () => setZoom(zoomLevel + 0.05));
$("#themeToggle").addEventListener("click", toggleTheme);

/* ---------- 退出 ---------- */
async function quit() {
  if (!confirm("确定退出吗？\n本地服务将整体关闭，浏览器标签页可随后手动关闭。")) return;
  const btn = $("#btnQuit");
  btn.disabled = true;
  btn.textContent = "关闭中…";
  try {
    await fetch("/api/shutdown", { method: "POST" });
  } catch { /* 服务已无响应，大概率已关闭 */ }
  $("#byeOverlay").classList.add("show");
}
$("#btnQuit").addEventListener("click", quit);

(async function init() {
  switchTab("overview");
  try { applyTheme(localStorage.getItem(THEME_KEY) || "light"); } catch { applyTheme("light"); }
  try { setZoom(parseFloat(localStorage.getItem(FONT_KEY) || "1") || 1, false); } catch { setZoom(1, false); }
  loadScratch();
  try { await loadConfig(); } catch { $("#statusBar").textContent = "配置读取失败"; }
  await loadCourses();
  loadCalendar();
  loadAnki();
  loadHistoryList();
})();
