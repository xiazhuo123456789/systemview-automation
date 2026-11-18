# Changelog

All notable changes to this skill. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

## [2.0.2] — 2026-11-18

### Changed

- `README.md` 全文中文化（保留英文检索关键词段与所有命令/文件名），作为中文课程设计场景的主文档。
- 两张示例图重做：`screenshots/fm-demo-six-windows.png` 裁掉任务栏（1920×1012）；`screenshots/fm-demo-parameterised-1500hz.png` 用 `PrintWindow` 重新抓取（1552×824，无任务栏、无第三方弹窗遮挡）。

### Added

- `scripts/sv.py` 新增 `capture_window(hwnd, path)`：用 `PrintWindow(PW_RENDERFULLCONTENT)` 抓窗口自身位图并自动裁黑边，截图从此不受桌面遮挡影响。
- `scripts/sv.py` 新增 `find_child(parent, sub, cls)`：用 `EnumChildWindows` 找 MDI 子窗（分析窗口里的 `w0:`…`w5:` 都是子窗，`EnumWindows` 看不到）。

## [2.0.1] — 2026-11-18

Repository presentation and one new recovery tool.

### Added
- `screenshots/` with the two real captures, referenced from the top of
  `README.md` so the first thing a visitor sees is the figure one command
  produces.
- `tools/_winmap.py`: lists every SystemView window next to its process id,
  so several running instances can be told apart before closing anything.
- `references/pitfalls.md` §22: never close SystemView windows by title —
  the frame titled `SystemView by ELANIX` may be the MDI parent holding every
  open document.

### Changed
- `README.md` opens with the six-window capture instead of a code block, and
  documents both outputs of a run (`-full.png` and the cropped `.png`).
- `SKILL.md` files table points at `screenshots/`.

## [2.0.0] — 2026-11-18

Commercial-grade rewrite.

### Added
- `scripts/sim.py`: one command opens a `.svu`, rewrites FM/VCO parameters,
  runs `Run System and Auto Plot`, waits for the plots to settle, captures
  PNGs and prints a JSON result. Distinct exit codes (0/2/3/4/5).
- `config.json`: every coordinate in one place, overridable with `--config`.
- `README.md`, `requirements.txt`, `LICENSE` (MIT), this changelog.
- YAML frontmatter in `SKILL.md` (Agent Skills spec: `name`, `description`,
  `license`, `compatibility`, `metadata`, `allowed-tools`).

### Fixed
- `openfile.py` no longer hard-codes an absolute `_tools` path; it resolves
  its own directory, so the folder is relocatable.
- `token_status.py` re-maximizes and re-measures the window before sampling,
  which fixes the "clicks land on the palette" failure.

### Changed
- Documentation split by audience: `SKILL.md` (agent, short) →
  `references/*.md` (details on demand) → `README.md` (human).

## [1.0.0] — 2026-11-17

First working version, extracted from a 通信原理 course project.

### Added
- `scripts/sv.py` — window enumeration, DPI-aware screenshots, click/drag/key.
- `scripts/openfile.py` — drive the Win32 open dialog via `WM_SETTEXT` +
  `BM_CLICK`.
- `scripts/token_status.py` — read token type and connections off the
  VB-drawn status bar by screenshotting it.
- `references/` notes on layout, parameters and pitfalls.
