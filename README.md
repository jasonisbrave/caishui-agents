# 财税备考 Agent 工作台（caishui-agents）

日常财税备考（CPA / 中级 / 税务师）专用的本地网页工作台：**不打开 OpenCode / Kimi Code**，让它们回归开发与日常工作。浏览器访问本机端口即可完成备考计划与对话学习。

- 技能：复用 [pass-all-exams](https://github.com/SolarAscent/pass_all_exams) 技能（`examctl.py` + `SKILL.md`），路径在 `config.json` 指向（支持 `~` 写法，自动展开）。
- 模型：偏好 Kimi。两种接入方式，自动选择：
  1. **Kimi API**（推荐，流式）：`sk-kimi-` 前缀密钥走 `https://api.kimi.com/coding/v1`（Kimi Code 订阅控制台可创建，也在 config.json 填 `llm.kimi_api_key`）；传统 Moonshot 平台密钥则把 `llm.kimi_base_url` 改回 `https://api.moonshot.cn/v1`。
  2. **kimi CLI 无头调用**（无需 API key，复用 Kimi Code 订阅，非流式）：检测到本机 `kimi` 命令即启用。
- 零第三方依赖：Python 3.10+ stdlib（`http.server` + `urllib`），前端原生 JS 无构建。

## 快速开始

```powershell
cd caishui-agents
.\start.ps1          # 或双击 start.bat，或：python server.py
# 自动打开 http://127.0.0.1:8642
```

### 新环境从零开始（clone 后无缝启动）

1. `git clone` 本仓库，进入目录；
2. 安装 pass-all-exams 技能（提供 `examctl.py`）：
   ```powershell
   git clone https://github.com/SolarAscent/pass_all_exams.git "$HOME\.opencode\skill\pass-all-exams"
   ```
   放其他目录也行，下一步在 config 里指对路径即可；
3. 复制 `config.example.json` 为 `config.json`（start 脚本会自动做），按需修改三个路径（`~` 会按用户目录展开）；
4. Kimi 接入二选一：`config.json` 填 `llm.kimi_api_key`，或本机装有 Kimi Code CLI（`kimi`）自动降级；
5. `.\start.ps1` → 总览/刷题（Anki）/日历即用；没有 pass-all-exams 状态库时相关页为空、对话页照常可用，`examctl init` 建课程后数据自动出现。

> 双击入口推荐 `start.bat`（崩溃时会暂停显示错误）。`start.ps1`/`stop.ps1` 为纯 ASCII 编码，兼容 Windows PowerShell 5.1 与 pwsh 7。

**退出**：网页右上角「退出」按钮（确认后服务整体关闭，端口释放）；或运行 `.\stop.ps1`（等效）；服务前台运行时也可 Ctrl+C。

首次使用：复制 `config.example.json` 为 `config.json`（start.ps1 会自动做），按需修改：

| 配置项 | 说明 | 默认 |
|---|---|---|
| `port` / `host` | 本地监听 | `8642` / `127.0.0.1`（仅本机） |
| `pass_all_exams_home` | 学习状态库根目录 | `~/.pass-all-exams` |
| `skill_dir` | pass-all-exams 技能目录 | `~/.opencode/skill/pass-all-exams` |
| `learning_agents_md` | 备考约定文档（可选，注入教练系统提示） | 空 = 不注入 |
| `llm.provider` | `auto` / `moonshot` / `kimi_cli` / `none` | `auto` |
| `llm.kimi_api_key` | Kimi API 密钥（**gitignored，勿提交**；`sk-kimi-` 前缀） | 空 |
| `llm.kimi_base_url` | OpenAI 兼容端点 | `https://api.kimi.com/coding/v1` |
| `llm.model` | 模型名 | `kimi-latest` |

## 功能（v0.3）

| 标签页 | 能力 |
|---|---|
| 总览 | 读取 `state.json`：各课程进度条、考点掌握数、错题/卡片数、考试倒计时、最近会话 |
| 备考计划 | 一键调用 `examctl status / summary`（只读）；`resume / drill` 跳转教练对话并自动携带课程实时状态 |
| 刷题 | 直连本机 **AnkiConnect**（协议 v6，Python 代理绕开浏览器 Origin 限制）：科目级牌组选择（到期/新卡计数）、到期复习/新卡覆盖两种模式、抽卡作答自评（错1/含糊2/对3/秒杀4 → `answerCards` 回写）、题目卡与挖空卡字段自适应；Anki 未运行时优雅离线 |
| 日历 | 三层月历：考试日（红）/ 复习到期 `review_due`（橙）/ 学习痕迹 `updated_at`（绿）；今天高亮、点日期看明细 |
| 对话 | Kimi 备考教练，流式输出（Kimi API）+ **Markdown 预览渲染**；勾选「携带备考上下文」时注入 SKILL.md + Learning/AGENTS.md + 课程快照；左侧**历史会话**：自动保存、全文搜索、一键恢复续聊、可删除（后端 `history/` 目录持久化，不受浏览器清缓存影响）；右侧**草稿纸**：刷题先打草稿，一键誊到输入框，自动保存（localStorage）；教练给出的回写命令渲染为**确认卡片**——点「执行」才写入状态库 |

## 架构

```
浏览器（原生单页）
   │ HTTP / SSE
server.py  ── ThreadingHTTPServer，静态托管 + /api 路由
   ├── skill_bridge.py ── 课程发现 / 状态快照 / examctl 子进程（UTF-8 强制）
   └── kimi_client.py  ── moonshot SSE 流 | kimi -p 无头；教练系统提示组装
                            │
        ~/.pass-all-exams（只读）
        Moonshot API（api.moonshot.cn/v1）或本机 kimi CLI
```

## 安全边界（对齐 Learning 仓库红线）

- **读自由，写过门**：`status/summary` 只读直调；五个写命令（`record-point / record-error / resolve-error / add-card / log-session`）必须由教练以 ```examctl``` 代码块给出、经确认卡片二次确认（前端弹窗 + 后端 `confirm=true` 双闸）后才执行，且强制校验 `--course` 合法性。`init / archive-course / restore-course` 仍走命令行手动。
- 服务只绑定 `127.0.0.1`，单用户本机使用。
- `config.json` 含密钥，已被 `.gitignore` 排除。

## 路线图

- ~~v0.2：教练工具循环——经确认后回写状态~~ ✅ 已实现（确认卡片机制）
- ~~v0.3：UI 打磨、移动端布局、学习日历视图~~ ✅ 已实现
- ~~v0.4：Anki 集成（AnkiConnect 刷题页）~~ ✅ 已实现
  - ~~对话历史持久化~~ ✅ v0.4.2 已实现（后端 `history/` + 搜索/恢复/删除）；~~Markdown 预览~~ ✅ 已实现
- **2027 考季排期**（考纲发布后启动，按序）：
  1. **教练×Anki 联动**：换角度重测错题时，教练按题库分工自动抽卡（真题→「真题精炼」/「CPA(专业)」；知识点→基础牌组；冲刺→「只做好题」），作答判分后 `answerCards` 回写 + `resolve-error` 落库，闭环错题修复
  2. **开课向导**：网页内完成新课程 `init`、写入 `exam_date`（保持 counts 一致）、资料入库——写操作沿用确认卡片双闸
  3. **考期提醒**：考试日 ≤30 天总览置顶标红 + 启动时提示当日复习到期
- 随用随做的小项：草稿纸按课程分页；日历导出 ICS。

## Anki 集成说明（v0.4）

- **前提**：本机 Anki 桌面端运行中 + AnkiConnect 插件（接口 `http://127.0.0.1:8765`，可在 `config.json` 的 `anki` 段调整/停用）。
- **牌组**：按 Learning 仓库约定的 `牌组::科目::章节` 结构，刷题页以科目层为单元（章节自动聚合）。
- **卡片字段**：题目卡 `question/options/answer/notes`、挖空卡 `问题/答案/笔记`，直接用字段值（不用渲染版），前端自动识别。
- **回写**：自评四档对应 `answerCards` ease 1–4，SRS 排程与 AnkiWeb 同步仍由 Anki 自己负责；**不改写 .apkg 文件**。
- 题库分工（真题精炼/打好基础/只做好题/CPA(专业)）由教练在对话中遵循 Learning/AGENTS.md 约定引导。

## 排障记录（btw）

本项目搭建过程中踩过的坑与结论，备查：

1. **start.ps1 双击闪退**：脚本含中文且为无 BOM UTF-8，双击走的 Windows PowerShell 5.1 按 GBK 解析，中文字节被错读成未闭合引号 → 解析错误闪退，服务从未启动（表现为「端口无法访问」）。**修复**：`start.ps1`/`stop.ps1` 一律纯 ASCII，5.1 与 pwsh 7 双兼容；另加 `start.bat` 作为双击入口（崩溃时 `pause` 显示错误）。教训：给双击运行的 .ps1 写中文，必须带 BOM 或干脆纯 ASCII。
2. **端口被占但「新服务照常启动」**：Windows 下 `HTTPServer` 默认的 `SO_REUSEADDR` 允许多个进程同时监听同一端口，旧进程（旧代码）继续抢答请求，表现为「改了代码但接口行为不变、shutdown 返回 400」。**根治（已内置）**：`server.py` 自定义 `Server(allow_reuse_address = False)`，端口被占时第二个实例立即报错退出并给出中文提示，不再静默共存。临时排查仍可用 `Get-NetTCPConnection -LocalPort <端口> -State Listen` 找 OwningProcess 清理；按端口定位比按命令行匹配可靠（`python server.py` 相对路径启动时命令行里没有项目名）。
3. **`sk-kimi-` 前缀密钥的端点**：Moonshot 旧平台（`api.moonshot.cn` / `api.moonshot.ai`）对此类 key 返回 401，正确端点是 **`https://api.kimi.com/coding/v1`**（Kimi 平台 OpenAI 兼容，可用模型 `kimi-latest`、`k3.1-pro` 等，思考型模型会先输出 `reasoning_content` 再输出正文）。判断依据：`/v1/models` 实测 + 前缀约定（`sk-kimi-` → kimi.com）。
4. **`.ps1` 默认关联改成 pwsh 7**（Windows 11）：
   - Store 版 pwsh 不出现在「默认应用」候选列表，其执行别名（`WindowsApps` 下 0 字节重定向）在「打开方式→浏览」里会被拒；
   - `winget install Microsoft.PowerShell` 会因检测到 Store 版已装同版本而拒绝真正安装（报成功但没落盘）；
   - PowerShell 7.7.0 起官方不再发布 MSI，只有 ZIP / MSIX。
   - **最终方案**：官方 ZIP 版解压到 `%LOCALAPPDATA%\Programs\PowerShell\`（校验 hashes.sha256），在 `HKCU\Software\Classes\Applications\pwsh.exe` 注册 `shell\open\command` 并挂入 `.ps1\OpenWithProgids`，右键「打开方式→PowerShell 7→始终」。验证用 `Start-Process xxx.ps1`（等效双击）看 `PSHOME` 是否指向该目录；UserChoice 注册表残留旧 ProgId 不影响实际行为。`UserChoice` 有系统哈希保护，脚本改不动，只能在「打开方式」界面选。

## 致谢

- [pass-all-exams](https://github.com/SolarAscent/pass_all_exams)（by [SolarAscent](https://github.com/SolarAscent)）：本项目的备考技能核心——考点映射、教学闭环、错题修复与间隔复习状态机（`examctl.py` + `SKILL.md`），工作台的进度总览、备考计划与状态回写均建立在其上。
- [Kimi](https://www.kimi.com/)（Moonshot AI）：教练对话模型与 OpenAI 兼容 API。
- [Anki](https://apps.ankiweb.net/) 与 [AnkiConnect](https://github.com/FooSoft/anki-connect)：间隔重复刷题与本地接口集成。

## 许可证

[MIT](LICENSE) © 2026 jasonisbrave。依赖的 pass-all-exams 技能同样为 MIT 许可。

