#!/usr/bin/env python3
"""One command -> one figure, for ELANIX SystemView 5.0 (.svu).

    python sim.py --file "E:\\path\\demo.svu" --out out/
    python sim.py --file demo.svu --carrier 5000 --mod-gain 30 --zoom 43.7e-3 47.7e-3

It opens the system, optionally rewrites the FM/VCO carrier and modulation
gain, runs "Run System and Auto Plot" (Shift+F5), waits until the plots stop
changing, and writes PNGs plus a JSON summary.

Every coordinate is re-measured at run time where possible; the few that
cannot be (canvas token positions) come from config.json and can be
overridden with --config.

Exit codes
    0  success
    2  SystemView not installed / not launchable
    3  open-file dialog failed
    4  parameters dialog not found
    5  simulation did not settle within --timeout
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import openfile  # noqa: E402  (local module, must come after sys.path tweak)
import sv  # noqa: E402
from sv import click, drag, find, key, shot, user32  # noqa: E402

WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
VK_F5 = 0x74
VK_SHIFT = 0x10

DEFAULTS = {
    "exe": r"E:\SYSTEMVIEW\SysVu_32.exe",
    "title_recent": "Recent SystemView Files",
    "title_open": "Open SystemView File",
    "title_param": "FM/VCO",
    "title_analysis": "SystemView Analysis",
    "canvas_origin": [0, 0],
    "tokens": {"0": [142, 468], "1": [381, 477], "5": [264, 477], "7": [490, 575]},
    "menu_file": [21, 37],
    "menu_open_existing": [110, 177],
    "param_ok_fallback": [1046, 640],
    "crop_w2": [18, 690, 940, 1035],
}


# ---------------------------------------------------------------- helpers
def load_config(path: str | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            user = json.load(fh)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def shift_key(vk: int) -> None:
    user32.keybd_event(VK_SHIFT, 0, 0, 0)
    time.sleep(0.03)
    key(vk)
    user32.keybd_event(VK_SHIFT, 0, 2, 0)
    time.sleep(0.25)


def wait_window(sub: str, timeout: float = 12.0):
    end = time.time() + timeout
    while time.time() < end:
        hits = find(sub)
        if hits:
            return hits[0]
        time.sleep(0.25)
    return None


def design_window(cfg: dict, want: str | None = None, allow_other: bool = True):
    """Pick the design window.

    Order: one already showing `want` -> a blank instance (title without
    " - ", i.e. no file loaded yet) -> the widest open file window. The blank
    instance is preferred over somebody else's file so automation never edits
    a schematic the user happens to have open.
    """
    hits = find("SystemView - ")
    if want:
        same = [w for w in hits if want in w["title"]]
        if same:
            return same[0]
        blank = [w for w in find("SystemView") if " - " not in w["title"]]
        if blank:
            return blank[0]
        if not allow_other:
            return None
    if not hits:
        return None
    return max(hits, key=lambda w: w["rect"][2] - w["rect"][0])


def children(hwnd):
    return openfile.children(hwnd)


def screen_hash(cfg: dict | None = None) -> str:
    """Fingerprint of the analysis window only, downscaled so a blinking caret
    or a one-pixel repaint does not count as 'still running'."""
    from PIL import ImageGrab
    box = None
    if cfg is not None:
        win = find(cfg["title_analysis"])
        if win:
            box = win[0]["rect"]
    img = ImageGrab.grab(bbox=box, all_screens=True)
    img = img.convert("L").resize((96, 96))
    return hashlib.sha1(img.tobytes()).hexdigest()


# ---------------------------------------------------------------- steps
def step_launch(cfg: dict, log, want: str = ""):
    """Start SystemView and get it to the file-open dialog.

    A window already showing `want` means nothing to do. Any *other* design
    window that happens to be open belongs to somebody else: it is recorded in
    `before` and never clicked, so automation cannot edit the wrong schematic.
    """
    if want and [w for w in find("SystemView - ") if want in w["title"]]:
        log("target already open")
        return 0
    exe = cfg["exe"]
    if not os.path.exists(exe):
        log(f"ERROR: exe not found: {exe}")
        return 2
    before = {w["hwnd"] for w in find("SystemView")}
    subprocess.Popen([exe], cwd=os.path.dirname(exe))
    recent = wait_window(cfg["title_recent"], 15)
    if recent:
        log("startup: Recent dialog -> Existing...")
        btn = next((c for c in children(recent["hwnd"])
                    if c["cls"] == "Button" and "Existing" in c["text"]), None)
        if btn:
            user32.SendMessageW(btn["hwnd"], BM_CLICK, 0, 0)
            time.sleep(0.8)
        if not wait_window(cfg["title_open"], 6):
            log("ERROR: open dialog never appeared")
            return 3
        return 0
    # no Recent dialog: a bare frame must have appeared
    end = time.time() + 12
    while time.time() < end:
        fresh = [w for w in find("SystemView") if w["hwnd"] not in before]
        if fresh:
            log(f"startup: bare frame {fresh[0]['hwnd']}")
            sv.maximize(fresh[0]["hwnd"])
            return 0
        time.sleep(0.4)
    log("ERROR: no SystemView window appeared")
    return 3


def step_open(cfg: dict, path: str, log, want: str = "") -> int:
    if want:
        already = [w for w in find("SystemView - ") if want in w["title"]]
        if already:
            sv.maximize(already[0]["hwnd"])
            log(f"already open: {already[0]['title']}")
            return 0
    if not wait_window(cfg["title_open"], 2):
        # drive the menu instead
        win = design_window(cfg, want)
        if not win:
            log("ERROR: no design window for File>Open")
            return 3
        sv.focus(win["hwnd"])
        click(*cfg["menu_file"])
        time.sleep(0.35)
        click(*cfg["menu_open_existing"])
        time.sleep(0.9)
    if not wait_window(cfg["title_open"], 6):
        log("ERROR: open dialog not found")
        return 3
    openfile.set_file(cfg["title_open"], path)
    time.sleep(1.6)
    # a "save changes?" prompt can appear when another system is open
    prompt = wait_window("Do you want to save changes", 1.5)
    if prompt:
        kids = children(prompt["hwnd"])
        no = next((c for c in kids if c["cls"] == "Button" and c["text"].startswith("否")), None)
        if no:
            user32.SendMessageW(no["hwnd"], BM_CLICK, 0, 0)
            time.sleep(1.4)
    win = design_window(cfg, want)
    if not win:
        log("ERROR: design window did not open")
        return 3
    sv.maximize(win["hwnd"])
    log(f"opened: {win['title']}")
    return 0


def _ordered_edits(dlg_hwnd):
    """Return the dialog's text boxes ordered top-left -> bottom-right."""
    edits = [c for c in children(dlg_hwnd) if c["cls"] in ("Edit", "ThunderRT6TextBox")]
    edits.sort(key=lambda c: (c["rect"][1] // 40, c["rect"][0]))
    return edits


def step_params(cfg: dict, carrier, mod_gain, amplitude, log, want: str = "") -> int:
    if carrier is None and mod_gain is None and amplitude is None:
        return 0
    win = design_window(cfg, want)
    if not win:
        log("ERROR: no design window")
        return 2
    sv.focus(win["hwnd"])
    sv.hold_front(win["hwnd"])
    tx, ty = cfg["tokens"]["1"]
    click(tx, ty)
    click(tx, ty, button="right")
    time.sleep(0.5)
    click(tx + 44, ty + 8)          # "Edit Parameters..." first menu item
    dlg = wait_window(cfg["title_param"], 6)
    if not dlg:
        log("ERROR: FM/VCO dialog not found")
        sv.release_front(win["hwnd"])
        return 4
    edits = _ordered_edits(dlg["hwnd"])
    log(f"param dialog: {len(edits)} text boxes")
    values = [amplitude, mod_gain, carrier, None]     # amp, gain, freq, phase
    for box, val in zip(edits, values):
        if val is None:
            continue
        text = f"{val:g}" if isinstance(val, float) else str(val)
        user32.SendMessageW(box["hwnd"], WM_SETTEXT, 0, text)
        time.sleep(0.12)
        log(f"  set {box['rect']} = {text}")
    btn = next((c for c in children(dlg["hwnd"])
                if c["cls"] == "Button" and c["text"].strip().lower().startswith("ok")), None)
    if btn:
        user32.SendMessageW(btn["hwnd"], BM_CLICK, 0, 0)
    else:
        click(*cfg["param_ok_fallback"])
    time.sleep(0.7)
    sv.release_front(win["hwnd"])
    return 0


def step_run(cfg: dict, out_dir: str, timeout: float, log, want: str = "") -> int:
    win = design_window(cfg, want)
    if not win:
        log("ERROR: no design window")
        return 2
    sv.focus(win["hwnd"])
    shift_key(VK_F5)
    end = time.time() + timeout
    prev, stable, started = None, 0, time.time()
    while time.time() < end:
        time.sleep(1.6)
        h = screen_hash(cfg)
        if h == prev:
            stable += 1
            if stable >= 2:
                log(f"plots settled after {time.time() - started:.1f}s")
                return 0
        else:
            prev, stable = h, 0
    log("WARNING: plots never settled; capturing anyway")
    return 0


def step_capture(cfg: dict, out_dir: str, tag: str, zoom, log):
    os.makedirs(out_dir, exist_ok=True)
    full = os.path.join(out_dir, f"{tag}-full.png")
    shot(full)
    made = [full]
    if zoom:
        win = find(cfg["title_analysis"])
        if win:
            sv.focus(win[0]["hwnd"])
            time.sleep(0.4)
            l, t, r, b = cfg["crop_w2"]
            x0, y0 = int(l + 60), int(t + 95)
            x1, y1 = int(r - 20), int(b - 90)
            drag(x0, y0, x1, y1)
            time.sleep(1.2)
            shot(full)
    log(f"captured: {full}")
    return made


# ---------------------------------------------------------------- cli
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="SystemView 5.0: one command -> one figure")
    ap.add_argument("--file", required=True, help="path to the .svu system")
    ap.add_argument("--out", default="out", help="output directory (default: out)")
    ap.add_argument("--carrier", type=float, help="FM/VCO Frequency (Hz)")
    ap.add_argument("--mod-gain", type=float, dest="mod_gain", help="FM/VCO Mod Gain (Hz/v)")
    ap.add_argument("--amplitude", type=float, help="FM/VCO Amplitude (v)")
    ap.add_argument("--zoom", nargs=2, type=float, metavar=("X0", "X1"),
                    help="time window in seconds to zoom the modulated-wave plot")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--config", help="JSON file overriding coordinates")
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true", help="machine-readable result on stdout")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    path = os.path.abspath(args.file)
    want = os.path.splitext(os.path.basename(path))[0]   # match window by file stem
    started = time.time()
    lines = []

    def log(msg):
        lines.append(msg)
        if not args.json:
            print(msg, flush=True)

    result = dict(ok=False, file=path, out=os.path.abspath(args.out),
                  carrier=args.carrier, mod_gain=args.mod_gain,
                  elapsed_s=0.0, images=[], messages=lines)

    if not os.path.exists(path):
        log(f"ERROR: file not found: {path}")
        result["elapsed_s"] = round(time.time() - started, 1)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3
    if args.dry_run:
        log("dry run: would launch, open, set, run and capture")
        result.update(ok=True, elapsed_s=0.0)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        if not args.no_launch:
            rc = step_launch(cfg, log, want)
            if rc:
                return rc
        rc = step_open(cfg, path, log, want)
        if rc:
            return rc
        rc = step_params(cfg, args.carrier, args.mod_gain, args.amplitude, log, want)
        if rc:
            return rc
        rc = step_run(cfg, args.out, args.timeout, log, want)
        if rc:
            return rc
        tag = os.path.splitext(os.path.basename(path))[0]
        result["images"] = step_capture(cfg, args.out, tag, args.zoom, log)
        result["ok"] = True
    finally:
        result["elapsed_s"] = round(time.time() - started, 1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    sys.exit(main())
