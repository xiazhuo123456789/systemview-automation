# Changelog

All notable changes to this skill. Format: [Keep a Changelog](https://keepachangelog.com/),
versioning: [SemVer](https://semver.org/).

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
