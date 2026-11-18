# 财税备考 Agent 工作台

面向 CPA、中级会计和税务师备考的本地单页工作台，将课程进度、备考计划、Anki 刷题、学习日历和 Kimi 教练对话整合到浏览器中。

适合使用 [pass-all-exams](https://github.com/SolarAscent/pass_all_exams) 管理学习状态，并希望脱离 OpenCode / Kimi Code、专注备考的用户。

Windows 上安装 Python 3.10+ 后运行 `.\start.ps1`（也可双击 `start.bat`），默认打开 <http://127.0.0.1:8642>。后端仅使用 Python 标准库，前端使用原生 JavaScript，无需安装第三方依赖或执行构建。

## 快速开始

### 1. 准备技能与学习状态

完整使用课程计划和状态回写功能前，先安装提供 `examctl.py` 与 `SKILL.md` 的 pass-all-exams 技能：

```powershell
git clone https://github.com/SolarAscent/pass_all_exams.git "$HOME\.opencode\skill\pass-all-exams"
```

也可以安装到其他目录，再在 `config.json` 中修改 `skill_dir`。学习状态库默认位于 `~/.pass-all-exams`；尚未创建课程时，课程相关页面暂无数据，对话页仍可使用（需已配置 Kimi）。按 pass-all-exams 的说明创建课程后，各页面会读取到相应数据。

### 2. 启动工作台

```powershell
git clone https://github.com/jasonisbrave/caishui-agents.git
cd caishui-agents
.\start.ps1
```

也可以双击 `start.bat`，或运行 `python server.py`。通过 `start.ps1` 或 `start.bat` 首次启动时，会自动将 `config.example.json` 复制为 `config.json`；服务启动后默认自动打开浏览器。

> 双击入口推荐 `start.bat`，启动失败时会暂停并显示错误。`start.ps1` 与 `stop.ps1` 均为纯 ASCII 编码，兼容 Windows PowerShell 5.1 和 pwsh 7。

### 3. 配置 Kimi

`llm.provider` 默认为 `auto`，按以下顺序自动选择接入方式：

1. **Kimi API（推荐，流式）**：在 `config.json` 的 `llm.kimi_api_key` 中填写密钥，或设置 `KIMI_API_KEY` 环境变量。使用 `sk-kimi-` 前缀密钥时，保持 `llm.kimi_base_url` 为 `https://api.kimi.com/coding/v1`；使用传统 Moonshot 平台密钥时，将其改为 `https://api.moonshot.cn/v1`。
2. **kimi CLI（无需 API key，非流式）**：未配置 API key 时，如果本机 PATH 中存在 `kimi` 命令，则通过 `kimi -p` 调用并复用 Kimi Code 订阅鉴权。
3. **未接入**：两种方式均不可用时，对话页不可用，其他页面仍可读取本地数据。

### 4. 退出服务

点击网页右上角「退出」并确认，或运行 `.\stop.ps1`，即可关闭服务并释放端口；服务在前台运行时也可以按 Ctrl+C 退出。

## 配置

按需修改 `config.json`。路径配置支持 `~`，会自动展开为用户目录；下表默认值以首次启动时复制的 [`config.example.json`](config.example.json) 为准。

| 配置项 | 说明 | 默认值 |
|---|---|---|
| `host` / `port` | 本地监听地址与端口 | `127.0.0.1` / `8642` |
| `pass_all_exams_home` | 学习状态库根目录 | `~/.pass-all-exams` |
| `skill_dir` | pass-all-exams 技能目录 | `~/.opencode/skill/pass-all-exams` |
| `learning_agents_md` | 可选的备考约定文档，注入教练系统提示 | 空，不注入 |
| `llm.provider` | `auto` / `moonshot` / `kimi_cli` / `none` | `auto` |
| `llm.kimi_api_key` | Kimi API 密钥；`config.json` 已被 `.gitignore` 排除，勿提交 | 空 |
| `llm.kimi_api_key_env` | 读取 API key 的环境变量名 | `KIMI_API_KEY` |
| `llm.kimi_base_url` | OpenAI 兼容端点 | `https://api.kimi.com/coding/v1` |
| `llm.model` | 模型名 | `kimi-latest` |

## 功能

| 标签页 | 能力 |
|---|---|
| 总览 | 读取 `state.json`，展示各课程进度、考点掌握数、错题与卡片数、考试倒计时和最近会话 |
| 备考计划 | 只读调用 `examctl status / summary`；`resume / drill` 跳转教练对话，并携带课程实时状态 |
| 刷题 | 通过 Python 代理连接本机 AnkiConnect（协议 v6），按科目牌组选择到期复习或新卡覆盖模式，支持抽卡、作答、自评与 `answerCards` 回写；Anki 未运行时显示离线状态 |
| 日历 | 在月历中区分考试日、复习到期 `review_due` 和学习痕迹 `updated_at`，支持今天高亮与按日期查看明细 |
| 对话 | Kimi 备考教练，支持 API 流式输出、Markdown 预览、备考上下文注入、历史会话搜索与恢复、草稿纸，以及写命令确认卡片 |

对话页的补充说明：

- **上下文**：勾选「携带备考上下文」后，注入 `SKILL.md`、可选的 Learning/AGENTS.md 和课程快照。
- **历史会话**：自动保存到后端 `history/` 目录，支持全文搜索、恢复续聊和删除，不受浏览器清除缓存影响。
- **草稿纸**：内容自动保存到 localStorage，可一键誊到输入框。
- **状态回写**：教练给出的 `examctl` 写命令会渲染为确认卡片，只有用户主动确认后才执行。

## 架构

```text
浏览器（原生单页）
   │ HTTP / SSE
server.py —— ThreadingHTTPServer：静态托管 + /api 路由
   ├── skill_bridge.py  —— 课程发现、状态快照、examctl 子进程（强制 UTF-8）
   ├── kimi_client.py   —— Kimi API SSE 流 / kimi -p 无头调用、教练提示词组装
   ├── anki_bridge.py   —— AnkiConnect 抽卡与 answerCards 回写
   └── history_store.py —— 历史会话持久化、搜索与删除

外部资源：~/.pass-all-exams、Kimi OpenAI 兼容 API 或本机 kimi CLI、AnkiConnect
```

## 安全边界

- **读自由，写过门**：`status / summary` 只读直调；`record-point / record-error / resolve-error / add-card / log-session` 五个写命令必须由教练以 `examctl` 代码块给出，经确认卡片和前端弹窗确认，并携带后端要求的 `confirm=true` 后才执行。后端同时校验 `--course` 的合法性。
- `init / archive-course / restore-course` 不在网页写命令白名单内，仍需通过命令行手动执行。
- 服务默认仅绑定 `127.0.0.1`，用于单用户本机访问。
- `config.json` 可能包含密钥，已被 `.gitignore` 排除。

## Anki 集成

- **前提**：运行本机 Anki 桌面端并安装 AnkiConnect 插件。默认接口为 `http://127.0.0.1:8765`，可在 `config.json` 的 `anki` 段调整或停用。
- **牌组**：采用 `牌组::科目::章节` 结构，刷题页以科目层为单元，自动聚合章节。
- **卡片字段**：题目卡使用 `question / options / answer / notes`，挖空卡使用 `问题 / 答案 / 笔记`；前端直接读取字段值并自动识别。
- **回写**：错、含糊、对、秒杀四档分别对应 `answerCards` 的 ease 1–4。SRS 排程与 AnkiWeb 同步仍由 Anki 负责，工作台不改写 `.apkg` 文件。
- **题库分工**：真题精炼、打好基础、只做好题、CPA(专业) 等牌组的使用约定，由教练结合 Learning/AGENTS.md 引导。

## 路线图

- [x] v0.2：教练工具循环，经确认后回写状态（确认卡片机制）。
- [x] v0.3：UI 打磨、移动端布局、学习日历视图。
- [x] v0.4：AnkiConnect 刷题页。
- [x] v0.4.2：后端 `history/` 会话持久化，支持搜索、恢复和删除；Markdown 预览。
- [ ] **2027 考季排期**（考纲发布后按序启动）：
  1. **教练 × Anki 联动**：换角度重测错题时按题库分工抽卡，作答判分后通过 `answerCards` 回写并以 `resolve-error` 落库，闭环修复错题。
  2. **开课向导**：在网页内完成新课程 `init`、写入 `exam_date`、保持 counts 一致并入库资料；写操作沿用确认卡片双闸。
  3. **考期提醒**：考试日 ≤ 30 天时在总览置顶标红，并在启动时提示当日复习到期。
- [ ] 随用随做：草稿纸按课程分页；日历导出 ICS。

## 排障记录

本项目搭建过程中踩过的坑与结论，备查：

1. **`start.ps1` 双击闪退**：含中文的无 BOM UTF-8 脚本可能被 Windows PowerShell 5.1 按 GBK 错读，导致解析失败。现改为 `start.ps1` / `stop.ps1` 一律使用纯 ASCII，并提供启动失败时暂停显示错误的 `start.bat`。
2. **端口被占但第二个实例看似正常启动**：Windows 下 `HTTPServer` 默认的 `SO_REUSEADDR` 可能让旧进程继续响应请求。`server.py` 已设置 `Server(allow_reuse_address = False)`，端口被占时第二个实例会直接报错退出。可用 `Get-NetTCPConnection -LocalPort <端口> -State Listen` 查找 `OwningProcess`，按端口定位比按命令行匹配更可靠。
3. **`sk-kimi-` 前缀密钥返回 401**：Moonshot 旧平台端点不适用于此类 key，应使用 `https://api.kimi.com/coding/v1`；传统 Moonshot 平台密钥则使用 `https://api.moonshot.cn/v1`。
4. **Windows 11 的 `.ps1` 默认关联**：项目搭建时，Store 版 pwsh 未出现在「默认应用」候选列表中，最终使用官方 ZIP 版并注册当前用户的打开方式。此项只是系统环境记录，不是启动工作台的必要步骤。

## 致谢

- [pass-all-exams](https://github.com/SolarAscent/pass_all_exams)（[SolarAscent](https://github.com/SolarAscent)）：提供备考技能核心，包括考点映射、教学闭环、错题修复与间隔复习状态机。
- [Kimi](https://www.kimi.com/)（Moonshot AI）：提供教练对话模型与 OpenAI 兼容 API。
- [Anki](https://apps.ankiweb.net/) 与 [AnkiConnect](https://github.com/FooSoft/anki-connect)：提供间隔重复刷题与本地接口集成。

## 许可证

本项目采用 [MIT License](LICENSE)，Copyright (c) 2026 jasonisbrave。依赖的 pass-all-exams 技能同样采用 MIT 许可证。
