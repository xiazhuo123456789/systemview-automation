# 换一台机器 / 换一个版本：让它自己检测

这个 skill 是在 **SystemView 5.0 Build 046**（1999 年，VB6）上逆向出来的。
但代码里**没有**任何"如果版本是 X 就……"的判断——原因是版本矩阵必然过期，
而且我也只见过 5.0。取而代之的是一条原则：

> 不猜版本，运行时自己看。看窗口、看控件、看画布、看截出来的图。

下面这五步就是"自己看"的完整流程。任何智能体读到这段都能照着做；
换机器、换版本、改分辨率、换 DPI，都走同一条路。

---

## 第 0 步：先跑一次自检

```bash
python scripts/probe.py --out probe --json probe.json
```

它**不点击、不拖动、不修改**任何系统，只做四件事：

1. 列出所有 `SystemView*` 窗口（`hwnd`、类名、标题、矩形）；
2. 读出画布原点 `canvas`（客户区左上角，屏幕坐标）和 `.exe` 的文件版本；
3. 抓 `probe/design.png`、`probe/analysis.png` 两张图；
4. 对 `config.json` 里登记的每个 token 抓一条状态栏，拼成 `probe/token_status.png`。

退出码 `0` = 自动能查的都过了；`2` = 报告里 `checks[].ok=false` 的那几条要人工看一眼。
报告长这样：

```json
{
  "executable version readable": true,
  "design": {"rect": [-10,-10,1930,1030],
             "canvas": {"left": 0, "top": 54, "width": 1920, "height": 966},
             "canvas_delta": [0, 0]},
  "exe": {"path": "E:\\SYSTEMVIEW\\SysVu_32.exe", "file_version": "5.0.0.0"},
  "checks": [{"check": "...", "ok": true, "detail": "..."}]
}
```

## 第 1 步：对窗口——只认标题，不认类名

```python
[w for w in sv.enum_windows() if w["title"].startswith("SystemView - ")]        # 设计窗
[w for w in sv.enum_windows() if w["title"].startswith("SystemView Analysis")]  # 分析窗
"Recent SystemView Files" in w["title"]                                          # 最近文件
```

`ThunderRT6FormDC` / `ThunderRT6MDIForm` 这些类名**只用来区分，不用来识别**：
换成 6.x 以后它们会变成 .NET 的 `WindowsForms10.*`，但标题约定没变。
`sv.find(cls=...)` 可以按类名过滤，不传就只按标题。

## 第 2 步：对控件——按文本找，不按坐标找

对话框里的控件一律用"文本等于 / 包含"来定位，`config.json` 里存的是**规则**不是点：

```json
"param": {"title": "FM/VCO",
          "fields": [{"label": "Mod Gain (Hz/v)", "set": "mod_gain"},
                     {"label": "Frequency (Hz)",   "set": "carrier"}]}
```

匹配顺序（`scripts/profile.py` 的 `pick`）：`text==` 精确 → `cls==` → `text~=` 子串。
**必须精确优先**，否则 `OK` 会先命中 `Apply to tokens`（这条踩过，见 `pitfalls.md` §7）。

写值走 `WM_SETTEXT` + 回读校验；点按钮必须 `sv.focus(dlg)` 之后
`PostMessageW(btn, BM_CLICK)`（`SendMessage(WM_COMMAND)` 对 VB6 无效，§8）。

## 第 3 步：对坐标——相对画布，不相对屏幕

`config.json` 的 `tokens` 是**在画布原点处**量出来的屏幕坐标，同时登记
`"canvas_origin": [0, 54]`（最大化时画布左上角）。运行时：

```python
dx = canvas_box(design)["left"] - canvas_origin[0]
dy = canvas_box(design)["top"]  - canvas_origin[1]
click(tx + dx, ty + dy)
```

这样窗口挪动、任务栏变化、标题栏高度不同都不影响。**但是**还有两个变量
它管不了，必须人工确认（第 4 步）：

- **画布滚动了**：`.svu` 里的 token 坐标是画布坐标，画布一滚，屏幕坐标就偏；
- **窗口尺寸不是测量时那个**：SystemView 会把画布内容和滚动条一起重排。

## 第 4 步：用截图核对（这一步不能自动化）

看 `probe/design.png`：token 是画布上 32×32 的灰底小方块，左上角有蓝色编号。
拿它和 `config.json` 的 `tokens` 对一眼：

- 方块位置对得上 → 坐标可用，继续；
- 整体平移 → 改 `canvas_origin`；
- 整体错乱（画布被滚过）→ 先把画布滚到左上角（拖滚动条到最左/最上），再跑 `probe.py`。

再看 `probe/token_status.png`：**每行开头是 token 编号和坐标，下面是点它之后的状态栏**。
正常应该看到

```
Function: Freq Mod,  Input from 5, Output to 6, 11.
Adder: Non Parametric,  Input from 1, 7, Output to 8, 9.
Sink: Analysis,  Input from 1, Output to None.
```

如果每一行都是**同一句话**（比如 `Finished MetaSystem Auto-Link Updates`），
说明点没落在 token 上——回到上一步查坐标。这张图是唯一的"我到底点到了什么"的证据，
因为 SystemView 的状态栏是 VB 自己画的，没有 `msctls_statusbar32` 子窗，读不到文本。

## 第 5 步：跑一次空系统，验证"改参数 → 运行 → 出图"

```bash
python scripts/sim.py --file demo.svu --out out --json
```

期望：`ok:true`、`images` 有两张、`messages` 里有 `plots settled after N s`。
出现这三条就说明这条机器上整条链路是通的：

```json
{"ok": true, "elapsed_s": 12.4,
 "messages": ["target already open", "plots settled after 6.8s", "captured: ..."]}
```

失败时按 `checks` 逐条排查；`plots never settled` 一般意味着
分析窗口没被真正重画（多半是设计窗没拿到焦点），见 `pitfalls.md` §21。

---

## 具体版本的已知差异（只写见过的，不编）

| 方面 | 5.0 Build 046（实测） | 其它版本怎么办 |
|---|---|---|
| 窗口类名 | `ThunderRT6Main` / `ThunderRT6MDIForm` / `ThunderRT6FormDC` | 只按标题找，类名不参与识别 |
| 画布 | MDI 子窗内一块自绘区域，原点 `(0,54)`（最大化 1920×1080 / 125%） | 跑 `probe.py` 读 `design.canvas` |
| 版本号 | 工具栏画的是静态文本（读不到），`.exe` 文件版本 `5.0.0.0` | `probe.py` 读 exe 版本；也可 Help → About |
| 运行 | `F5` = 只跑；`Shift+F5` = 跑并自动出图 | 菜单 `System → Run System and Auto Plot` 是等价入口 |
| 状态栏 | VB 自绘，无子窗，只能截图 | `token_status.py` 拼图 |
| 保存提示 | `#32770 "SystemView"`，按钮 `是(&Y)/否(&N)/取消` | 英文版是 `Yes/No/Cancel`，按文本找 |

## 换一个系统（不是换版本）怎么办

`systems/<name>.json` 里放这个 `.svu` 的 token 表与参数绑定，
`--system <name>` 指定即可；没有就临时在命令行里 `--set k=v`，用 `config.json` 的 tokens。
布局一变就重新量一遍坐标（第 3–4 步），**不要**去改 `sim.py`。

## 一条命令的总结

```bash
# 换机器/换版本后的第一件事
python scripts/probe.py --out probe --json probe.json     # 看 checks 和两张图
python scripts/sim.py --file demo.svu --out out --json    # 再验证一次闭环
```

过了这两关，`sim.py` / `mcp_server.py` 的行为与在本机完全一致——
因为它们读的是同一个 `config.json`，而这个自检流程保证 `config.json` 描述的是**这台机器**。
