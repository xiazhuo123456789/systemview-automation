---
name: systemview-automation
description: Drive ELANIX SystemView 5.0 (.svu) on Windows from the command line — open a system, read every token's type and connections, edit device parameters, run the simulation, and capture the plot windows as PNG. Use when a task involves SystemView simulations (通信原理/调频/频谱实验, .svu files, SysVu_32.exe), when a screenshot of a SystemView result must be reproduced or explained, or when someone asks for an FM/QAM/audio-processing simulation figure produced by the real desktop tool rather than by a plotting script.
license: MIT
compatibility: Windows 10/11, 1920x1080 at 125% scaling, Python 3.10+ with Pillow, SystemView 5.0 installed at E:\SYSTEMVIEW\SysVu_32.exe. Needs an interactive desktop session; it clicks real windows.
metadata:
  version: "2.0.0"
  author: 夏卓
  tested-with: SystemView v5.0 Build 046 / Python 3.12 / Windows 11
allowed-tools: Bash Read Write Edit
---

# SystemView 5.0 automation

Drive the 1999-era VB6 program `SysVu_32.exe` from scripts: open a `.svu`,
identify tokens, change parameters, run, capture plots.

## One command → a figure

```bash
python scripts/sim.py --file "E:\path\demo.svu" --out out\
```

That opens the system, sets the FM carrier and modulation index you ask for,
runs `Run System and Auto Plot`, waits for the plots to settle, and writes a
PNG plus a JSON summary. Everything else in this skill exists to make that
call reliable and to explain what the resulting picture can and cannot prove.

## When to use

- Reproduce or improve a SystemView figure (调频/频谱/音频处理 实验).
- Check what a token actually is: the status bar prints type **and** every
  connection (`Function: Freq Mod, Input from 5, Output to 6, 11.`).
- Answer "is this really an FM simulation?" — see `references/params.md`.

## Workflow

1. **Launch** — `.svu` has no file association, so start the exe, then
   `File → Open Existing System…`. `scripts/sim.py` does this for you.
2. **Normalize the window** — `SetWindowPos(-10,-10,1930,1030)`;
   `ShowWindow(SW_MAXIMIZE)` does nothing to this MDI frame.
3. **Identify** — click a token, screenshot the status strip
   (`scripts/token_status.py`) since the status bar is VB-drawn and has no
   child HWND.
4. **Edit** — right-click → `Edit Parameters…`, enumerate the dialog's
   controls *every time* (handles change per open), `WM_SETTEXT` each field,
   then `BM_CLICK` OK. Always reopen and screenshot to verify.
5. **Run** — `Shift+F5`. The toolbar must show
   `Auto System run completed at HH:MM:SS` for *this* run.
6. **Capture** — `sv.py shot`. Drag a box inside a plot to zoom.

## Rules

- Never trust coordinates without re-measuring; the canvas scrolls.
- Never verify a write with `GetWindowText` (returns `Text1`).
- Never submit parameters through the Source Library's OK (resets noise).
- Never edit a deliverable `.svu` in place — copy first, hash-compare after.
- If a window or control is missing, stop and report; do not click blind.
- **Never close a window you did not open.** The full-screen
  `SystemView by ELANIX` frame hosts every design window; closing it exits the
  program and takes the user's unsaved workspace with it.

## Files

| Path | Purpose |
|---|---|
| `scripts/sim.py` | one-command pipeline (open → set → run → capture) |
| `scripts/sv.py` | window/click/screenshot primitives |
| `scripts/openfile.py` | drive the Win32 open dialog |
| `scripts/token_status.py` | batch-read token types off the status bar |
| `references/layout.md` | token map, coordinates, window semantics |
| `references/params.md` | dialog fields, math, "can you see FM" criteria |
| `references/pitfalls.md` | 17 failure modes with fixes |
| `examples/` | a real capture produced by `sim.py` |
| `tools/` | manual recovery helpers, **not** part of the normal flow |

Details are in `references/` — read only the file you need.

## Honest limits

`--carrier/--mod-gain` needs the token coordinates in `config.json` to match the
open system **and** the canvas not to have been scrolled; when in doubt, run
without them (open → run → capture is the verified path) and edit parameters by
hand once, then re-measure with `scripts/token_status.py`.
