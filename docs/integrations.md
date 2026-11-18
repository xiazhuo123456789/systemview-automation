# 接入任何智能体（不只某一个）

这个 skill 不依赖任何一家 agent 的 SDK、账号或专有协议。它的全部依赖是
**Python 3 + Pillow + Windows Win32 窗口 API**，能力入口是三个普通命令行脚本。
因此接入方式有三层，从最通用到最贴合，任选其一即可。

---

## 第 0 层：纯命令行（任何 agent、任何语言、甚至人）

不需要"安装成 skill"。任何能执行 shell 命令的智能体（Claude Code、Codex CLI、
Cursor、Cline、Windsurf、Gemini CLI、Aider、自研 agent、CI 机器人）都可以直接：

```bash
python scripts/sim.py --file "D:\lab\demo.svu" --set carrier=5000 --set mod_gain=30 --out out\ --json
```

- 成功退出码 `0`，失败 `2/3/4/5`（含义见 README）。
- `--json` 把结果打到 stdout：`{"ok": true, "images": [...], "elapsed_s": 12.4, "messages": [...]}`。
- `--dry-run` 只打印计划，不碰鼠标——适合让 agent 先规划和确认。

这一层就是**可延展性的底座**：agent 只需要会 `subprocess`。

## 第 1 层：Agent Skills 目录规范（`SKILL.md`）

如果你用的运行时支持 "Agent Skills"（一个目录 + 一个带 frontmatter 的
`SKILL.md`，靠 `description` 里的触发词被发现），把这个目录放进去即可。
**目录名必须保持 `systemview-automation`**，因为规范要求 frontmatter 的
`name` 与父目录同名。

常见位置（各工具的路径随版本变化，以官方文档为准）：

| 运行时 | 常见位置 |
|---|---|
| Claude Code | `~/.claude/skills/systemview-automation/`（个人级）或 `<project>/.claude/skills/`（项目级） |
| Codex CLI（OpenAI） | `~/.codex/skills/systemview-automation/`（若版本不认 skills，用第 0 层） |
| Cursor / Cline / Windsurf / Copilot | 放进仓库后按各自规则引用；或直接把本目录当"项目资料"，让 agent 读 `SKILL.md` |
| 自研 / 其它 | 任何"读一个 markdown 决定怎么做"的机制都适用 |

渐进披露（规范要求，也省 token）：

1. 只有 `SKILL.md` 的 frontmatter（`name` / `description` / `compatibility`）常驻上下文；
2. 命中之后才读 `SKILL.md` 正文（一条命令、五步流程、规则）；
3. 需要细节时才读 `references/*.md`（布局、参数、坑）和 `docs/*.md`。

即使某个运行时完全不认 `SKILL.md`，把这句话交给它也能工作：
**"先读 `SKILL.md`，按里面的命令执行。"**

## 第 2 层：包成函数 / MCP 工具

**MCP 已经写好了，不用自己包**：`scripts/mcp_server.py` 是自带实现的 MCP
server（stdio + JSON-RPC 2.0，零依赖），暴露三个工具：

| 工具 | 作用 |
|---|---|
| `systemview_run` | 打开 `.svu` → 改参数 → 跑仿真 → 截图，返回 JSON + 内嵌 PNG |
| `systemview_inspect` | 只读：正在运行的窗口列表；给了 `file` 还返回 token 清单 |
| `systemview_screenshot` | 只截图不跑仿真，`kind=design` 可抓设计画布 |

客户端配置（Claude Desktop / Cursor / Cline / Zed / Continue 都是这个形状）：

```json
{
  "mcpServers": {
    "systemview": {
      "command": "python",
      "args": ["E:\\path\\to\\systemview-automation\\scripts\\mcp_server.py"]
    }
  }
}
```

返回值是标准 MCP `content` 数组：一段 JSON 文本 + 一张 `image` block（base64
PNG），所以模型能直接看到图。手工验证：

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python scripts/mcp_server.py
```

---

如果只想自己做 function calling / LangChain tool，把 `sim.py` 包一层即可，
参数一一对应：

```json
{
  "name": "systemview_run",
  "description": "Open a SystemView .svu, optionally change device parameters, run the simulation and capture the analysis windows as PNG.",
  "parameters": {
    "type": "object",
    "properties": {
      "file":     { "type": "string", "description": "Absolute path to the .svu file" },
      "set":      { "type": "object", "description": "Device parameters, e.g. {\"carrier\": 5000, \"mod_gain\": 30}" },
      "out":      { "type": "string", "description": "Output directory" },
      "timeout":  { "type": "integer", "description": "Seconds to wait for the plots to settle" }
    },
    "required": ["file"]
  }
}
```

映射到命令：

```
python scripts/sim.py --file <file> [--set k=v ...] --out <out> --timeout <n> --json
```

返回的 `images` 就是可以回传给模型的图片路径。整个适配层通常 20 行以内，
因为**没有任何一次点击是写死在代码里的**——坐标来自 `config.json` 与
`systems/*.json`，新系统只需要加一个 profile。

---

## 换一个被控软件怎么办

`sim.py` 里的"打开 → 改参数 → 运行 → 等稳定 → 截图"是通用骨架，与具体软件
无关；变化的部分全在 profile 与 `config.json`：

- 换一个 SystemView 系统（不同 token 布局）→ 新增 `systems/<name>.json`；
- 换一个对话框（参数在别的窗口里）→ 在 profile 里声明 `param_dialog`；
- 换一个**完全不同的老软件** → 复用 `scripts/sv.py`（枚举窗口、找控件、
  置顶、PrintWindow 截图、按 pid 关窗），自己写一个新的 `sim.py`。

`sv.py` 的原语契约见 [`extending.md`](extending.md)。
