# 坑：症状 → 原因 → 解法

## 1. 参数写了但没生效，而且对话框自己关了

**症状**：`WM_SETTEXT` 成功返回，点"OK"后重开对话框，值还是旧的。
**原因**：点击坐标偏出按钮，落到对话框空白处或 Cancel 上；VB6 对话框点空白/Cancel 会**静默关闭并丢弃修改**。
**解法**：写入后**必须重开对话框截图看值**。别用 `GetWindowText` 验证（见坑 2）。

## 2. `GetWindowText` 读出来永远是 `Text1`

**症状**：`GetWindowTextW(4422, ...)` 返回 `Text1`，即使框里显示 `50`。
**原因**：这些是 `ThunderRT6TextBox`，窗口文本返回的是 VB 控件**名**，不是内容。
**解法**：只能截图读。要程序化判断，就截图后自己看图。

## 3. 从 Source Library 的 OK 进参数，噪声被重置

**症状**：改完噪声 `Std Dev = 0`，再动一次信号源（走 `Library...` → 选器件 → `Parameters...` → 库窗口 `OK`），
噪声又变回 `10e-3`。
**原因**：Source Library 的 OK 会用库里的默认参数重刷所有该库 token。
**解法**：**先改信源，最后改噪声**；噪声只从 `右键 token → Edit Parameters...` 进。

## 4. `Ctrl+D` 不刷新图

**症状**：改完参数按 `Ctrl+D`，分析窗口的数字和图一点没变，还以为参数没生效。
**原因**：`Ctrl+D` 只是把分析窗口调到前面。
**解法**：用 `Shift+F5`（`System → Run System and Auto Plot`）。
凭据是工具栏变成 `Auto System run completed at HH:MM:SS`——时间必须是你刚才那一刻。

## 5. `.svu` 双击打不开

**症状**：`Start-Process foo.svu` 弹出"选择一个应用以打开此 .svu 文件"，列出 VS / TRAE / VMware / WPS。
**原因**：`SysVu_32.exe` 不注册文件关联。
**解法**：先 `Start-Process E:\SYSTEMVIEW\SysVu_32.exe -WorkingDirectory E:\SYSTEMVIEW`，
再在程序里 `File → Open Existing System...`。

## 6. Delete 键删不掉器件

**症状**：选中 token 按 Delete，毫无反应。
**原因**：设计画布的删除不在标准键盘处理里。
**解法**：右键 → `Delete Token`；或菜单 `Tokens → Delete`。

## 7. 读不到状态栏文本

**症状**：想用 `GetWindowText` 拿状态栏，枚举子窗口找不到任何 `msctls_statusbar32`。
**原因**：SystemView 的状态栏是 VB **自绘**的，不是公共控件。
**解法**：截图状态栏条带再读（`scripts/token_status.py`）。区域取窗口底边上方 `b-58 .. b-26`。

## 8. 截到的不是状态栏，而是别的窗口/直方图

**症状**：拼出来的图里是 "16 轮 581 步"（别的 App）或 w5 直方图的坐标轴。
**原因**：①SystemView 不在前台；②更常见的是**分析窗口最大化后盖住了设计窗口的状态栏**。
**解法**：截图前把设计窗口 `SetWindowPos(HWND_TOPMOST)` 顶上去，**保持到采样结束**再
`HWND_NOTOPMOST`（只 `SetForegroundWindow` 会被 Win10+ 拒绝）。
条带宽度限 1000 px，避开屏幕右侧的悬浮条。

## 9. 坐标全错位

**症状**：点 (142,468) 点到了左边 Navigator 调色板，状态栏显示 `Generic Router...`。
**原因**：设计窗口被还原成小窗（实测变成 `(560,198,1360,883)`）。
**解法**：动手前先 `sv.py max <hwnd>`，并在脚本里**再 find 一次**重算矩形。
`ShowWindow(SW_MAXIMIZE)` 对这种 MDI 窗体无效，要用 `SetWindowPos(h,0,-10,-10,1930,1030,SWP_SHOWWINDOW)`。

## 10. `Ctrl+S` 没保存

**症状**：按 `Ctrl+S` 后文件大小/时间不变。
**原因**：焦点在分析窗口时，`Ctrl+S` 不落到主窗口。
**解法**：`File → Save System`（菜单 (21,37) → 该项在 (89,245)）。

## 11. 关窗口卡死

**症状**：关闭时标题变 `SystemView (未响应)`。
**解法**：`Stop-Process -Name SysVu_32 -Force`。别指望它自己恢复。

## 12. 把交付文件改坏了

**解法**：动手前 `Copy-Item` 一份到工作目录，只在副本上改；收尾用 `Get-FileHash` 核对原件 SHA256 未变。

## 13. 加大调制增益后整条链路崩了

**症状**：`w3` 变成 0–200 的实心块、`w4` 铺满整个频段、`w5` 铺到 240。
**原因**：音频源是 8-bit 无符号 PCM，带约 127 直流；$f_i = f_c + K_f(127+m)$ 被推高，
超过 $f_s/2 = 12$ kHz 后鉴频器失效。
**解法**：$K_f$ 控制在 30 左右，或换成正弦源（幅度 1，无直流）再加大 $K_f$。

## 14. 分析窗口的缩放会丢吗

实测：在波形区拖框缩放后 `File → Save System`，缩放**会随文件保存**，重开即是放大状态。
但换参数重跑会重画，缩放通常保留；不确定就现场重新框选一次。

---

# 以下是"自动化会伤到别人"的三条硬教训

## 15. SystemView 是单实例，`--no-launch` 也保不了你

**症状**：新起一个 `SysVu_32.exe`，在它弹出的 `Open SystemView File` 里按"打开"，
结果文件被装进了**已经在运行的那个窗口**，别人正在编辑的图被换掉。
**原因**：VB6 程序共用进程/主框架，新进程只是又挂了一个 MDI 框架，`Open` 落到最后激活的
那个设计窗。
**解法**：自动化只在自己确认过的窗口上操作；`sim.py` 用 `want`（文件名主干）匹配标题，
匹配不到就**报错退出**，绝不退化成"点屏幕上最上面那个"。运行时不要同时手工开同一套系统。

## 16. 菜单项位置会变，不能写死坐标

**症状**：`click(21,37)` 打开 File 菜单，再 `click(110,177)`，本该是
`Open Existing System...`，实际弹出 `Recent SystemView Files`。
**原因**：File 菜单里 `Open Recent System...` 在 `Open Existing System...` **上面**，
菜单项顺序/数量随最近文件变化，写死的 y 就指到了别的项。
**解法**：**按文本找菜单项**（`dump` / UI Automation 读 `MenuItem` 名），
或绕开菜单：在 `Recent SystemView Files` 里点 `&Existing...`
（该按钮类名是 `ThunderRT6CommandButton`，**不是** `Button`，按类名过滤会漏）。

## 17. 批量"关空白窗口"会关掉主框架

**症状**：`_tidy.py close-blank` 关了几个"标题里没有 ` - `"的窗口，整个 SystemView 进入
`Releasing resources and closing SystemView...`，所有设计窗和分析窗一起消失。
**原因**：那个看起来"空白"的全屏 `SystemView by ELANIX` 是**承载 MDI 子窗的主框架**，
不是垃圾窗口；`WM_CLOSE` 它等于退出程序。
**解法**：**永不按标题批量关窗**。只关你自己记录过 hwnd、且确认是本次新建的那些；
收尾时如果状态不明，宁可留着让用户自己点。

> 以上三条都是真事故：文件 SHA256 前后一致（磁盘没坏），但用户内存里的窗口视图全丢了。
> 自动化的边界就画在这里——**能读、能跑、能截图的都做，能"关"的一律不做**。

