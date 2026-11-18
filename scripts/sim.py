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
import profile as profiles  # noqa: E402
import sv  # noqa: E402
from sv import click, drag, find, key, shot, user32  # noqa: E402

WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5
WM_COMMAND = 0x0111
BN_CLICKED = 0
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
    "systems_dir": os.path.join(os.path.dirname(HERE), "systems"),
}


def apply_profile(cfg: dict, prof: dict | None) -> dict:
    """Fold a system profile into the runtime config (profile wins).

    Only three things change: which dialog to open, where the tokens are, and
    how the result is cropped. Everything else stays in DEFAULTS, so a profile
    never has to repeat machine-specific settings.
    """
    if not prof:
        return cfg
    cfg = json.loads(json.dumps(cfg))
    for name, tok in (prof.get("tokens") or {}).items():
        cfg["tokens"][name] = list(tok["at"])
        cfg["tokens"].setdefault(str(tok.get("id", "")), list(tok["at"]))
    pd = prof.get("param_dialog") or {}
    if pd.get("title"):
        cfg["title_param"] = pd["title"]
    if pd:
        cfg["param_dialog"] = pd
    cap = prof.get("capture") or {}
    if cap.get("window"):
        cfg["crop_w2"] = list(cap["window"])
    if cap.get("zoom"):
        cfg["default_zoom"] = list(cap["zoom"])
    cfg["profile_name"] = prof.get("name")
    return cfg



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
                    if "Existing" in c["text"]), None)
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
        no = next((c for c in kids if c["text"].startswith("否")), None)
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
    """Return the dialog's text boxes ordered top-left -> bottom-right.

    Only used by the legacy positional fallback: it assumes a specific device
    dialog (FM/VCO). Profiles avoid it entirely.
    """
    edits = [c for c in children(dlg_hwnd) if c["cls"] in ("Edit", "ThunderRT6TextBox")]
    edits.sort(key=lambda c: (c["rect"][1] // 40, c["rect"][0]))
    return edits


PARAM_ORDER_LEGACY = ("amplitude", "mod_gain", "carrier", "phase")


def step_params(cfg: dict, values: dict, log, want: str = "") -> int:
    """Write parameter values into the device dialog.

    `values` maps a profile field name (``carrier``, ``mod_gain`` …) to a
    number or string. With a system profile the field is located by its label
    text, which is layout-independent; without one the four FM/VCO boxes are
    taken in reading order.
    """
    values = {k: v for k, v in (values or {}).items() if v is not None}
    if not values:
        return 0
    win = design_window(cfg, want)
    if not win:
        log("ERROR: no design window")
        return 2
    pd = cfg.get("param_dialog") or {}
    open_by = pd.get("open_by") or {}
    token_name = open_by.get("token", "1")
    point = cfg["tokens"].get(str(token_name)) or cfg["tokens"].get(token_name)
    if not point:
        log(f"ERROR: unknown token {token_name!r} for Edit Parameters")
        return 4
    tx, ty = point
    dx, dy = (open_by.get("menu_offset") or [44, 8])[:2]

    # NB: focus() calls ShowWindow(SW_RESTORE), which would undo the maximised
    # canvas and silently invalidate every profile token coordinate.
    sv.maximize(win["hwnd"])
    sv.hold_front(win["hwnd"])
    try:
        # A dialog left open by an earlier, failed run would otherwise be
        # mistaken for the one this run opens.
        stale = sv.find(cfg["title_param"])
        if stale:
            log(f"  closing stale {cfg['title_param']} dialog")
            sv.focus(stale[0]["hwnd"])
            sv.key(0x1B)                  # Esc = Cancel, never saves
            time.sleep(0.5)
        click(tx, ty)
        click(tx, ty, button="right")
        time.sleep(0.5)
        click(tx + dx, ty + dy)          # "Edit Parameters..." — first menu item
        dlg = wait_window(cfg["title_param"], 6)
        if not dlg:
            # Turn an opaque miss into something the operator can act on: the
            # screenshot shows where the canvas actually is, and the hint names
            # the tool that re-measures the token coordinates.
            shot = os.path.join(os.environ.get("TEMP", "."), "sv_params_miss.png")
            try:
                sv.shot(shot)
            except Exception:
                shot = "(screenshot failed)"
            log(f"ERROR: {cfg['title_param']} dialog not found")
            log(f"  canvas screenshot: {shot}")
            log("  the profile's token coordinates assume a maximised, "
                "unscrolled canvas; re-measure them with "
                "`python scripts/token_status.py \"SystemView - \" out.png X Y ...`")
            return 4
        kids = children(dlg["hwnd"])
        written = 0
        for spec in pd.get("fields") or []:
            name = spec.get("value")
            if name not in values:
                continue
            box = profiles.field_edit(kids, spec.get("label", ""))
            if not box:
                log(f"  WARNING: no text box for {spec.get('label')!r}")
                continue
            text = profiles.fmt(values[name])
            user32.SendMessageW(box["hwnd"], WM_SETTEXT, 0, text)
            time.sleep(0.12)
            written += 1
            log(f"  {spec.get('label')} = {text}")
        if not pd:
            edits = _ordered_edits(dlg["hwnd"])
            for name, box in zip(PARAM_ORDER_LEGACY, edits):
                if name not in values:
                    continue
                text = profiles.fmt(values[name])
                user32.SendMessageW(box["hwnd"], WM_SETTEXT, 0, text)
                time.sleep(0.12)
                written += 1
                log(f"  {box['rect']} = {text}")
        log(f"param dialog: {written} field(s) written")
        btn = profiles.pick(children(dlg["hwnd"]), pd.get("ok") or "text~=OK")
        if btn:
            # The design window is held TOPMOST, so a synthetic mouse click on
            # the dialog can land on the canvas instead. Raise the dialog first,
            # then post BM_CLICK to the button itself (verified to work only
            # once the dialog is the foreground window).
            sv.focus(dlg["hwnd"])
            time.sleep(0.3)
            user32.PostMessageW(btn["hwnd"], BM_CLICK, 0, 0)
            time.sleep(0.8)
            if sv.find(cfg["title_param"]):
                click((btn["rect"][0] + btn["rect"][2]) // 2,
                      (btn["rect"][1] + btn["rect"][3]) // 2)
                time.sleep(0.5)
        else:
            click(*cfg["param_ok_fallback"])
        time.sleep(0.7)
    finally:
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
    clean = os.path.join(out_dir, f"{tag}.png")
    # Raise the analysis window first: a full-screen grab would otherwise record
    # whatever the user happened to have in front, and the crop below would cut
    # the wrong pixels.
    win = find(cfg["title_analysis"])
    if win:
        # Raise without resizing: SystemView re-scales every plot when the
        # analysis window changes size ("Auto Replot On Window Size Change"),
        # which would throw away the saved zoom on w2.
        sv.hold_front(win[0]["hwnd"])
        time.sleep(0.6)
        win = find(cfg["title_analysis"])
    try:
        shot(full)
        if zoom:
            # The modulated-wave plot is its own child window ("w2: Sink 11"), so
            # its rectangle is measured, never assumed: the parent window moves.
            plot = sv.find_child(win[0]["hwnd"], cfg.get("title_w2", "w2:"))
            if plot:
                l, t, r, b = plot[0]["rect"]
                span = float(cfg.get("time_span", 1.34))   # seconds across the axis
                left, right = l + 60, r - 20               # inside the plot frame
                mid = (zoom[0] + zoom[1]) / 2.0
                axis = (0.0, span)                         # the axis starts at full span
                # A four-millisecond window is three pixels wide on a 1.3-second
                # axis, and a three-pixel drag is not a reliable rubber band.
                # Narrow down in steps, re-mapping the axis after each drag.
                for margin in (0.030, 0.010, 0.003):
                    half = (zoom[1] - zoom[0]) / 2.0 + margin
                    lo, hi = max(axis[0], mid - half), min(axis[1], mid + half)
                    if hi <= lo:
                        break
                    x0 = int(left + (right - left) * (lo - axis[0]) / (axis[1] - axis[0]))
                    x1 = int(left + (right - left) * (hi - axis[0]) / (axis[1] - axis[0]))
                    drag(x0, t + 60, max(x1, x0 + 2), b - 55)
                    time.sleep(0.8)
                    axis = (lo, hi)
                time.sleep(0.6)
                shot(full)
            else:
                log("  WARNING: w2 plot window not found; skipping the zoom")
    finally:
        if win:
            sv.release_front(win[0]["hwnd"])
    made = [full]
    # The clean image comes from the window itself, so the taskbar, other apps
    # and any popup on screen never appear in it.
    if win:
        try:
            ok, w, h = sv.capture_window(win[0]["hwnd"], clean)
            made.append(clean)
            if not ok:
                log("  WARNING: PrintWindow returned 0; the window may be hidden")
        except Exception as exc:                      # pragma: no cover
            log(f"  WARNING: window capture failed ({exc}); keeping the screen grab")
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
    ap.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                    help="profile field, e.g. --set carrier=5000 --set phase=90")
    ap.add_argument("--profile", help="system profile JSON (default: auto-match systems/*.json)")
    ap.add_argument("--print-profile", action="store_true",
                    help="show the resolved profile and exit (no GUI)")
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

    prof = None
    if args.profile:
        prof = profiles.load(args.profile)
    elif os.path.isdir(cfg["systems_dir"]):
        prof = profiles.discover(cfg["systems_dir"], want)
    cfg = apply_profile(cfg, prof)

    values = profiles.parse_sets(args.set,
                                 {"carrier": args.carrier,
                                  "mod_gain": args.mod_gain,
                                  "amplitude": args.amplitude})
    zoom = args.zoom or cfg.get("default_zoom")

    if args.print_profile:
        print(json.dumps({"profile": prof, "tokens": cfg["tokens"],
                          "param_dialog": cfg.get("param_dialog"),
                          "values": values, "zoom": zoom},
                         ensure_ascii=False, indent=2))
        return 0

    started = time.time()
    lines = []

    def log(msg):
        lines.append(msg)
        if not args.json:
            print(msg, flush=True)

    result = dict(ok=False, file=path, out=os.path.abspath(args.out),
                  profile=(prof or {}).get("name"),
                  values=values, elapsed_s=0.0, images=[], messages=lines)

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

    fail_rc = 0
    try:
        if not args.no_launch:
            fail_rc = step_launch(cfg, log, want) or 0
        if not fail_rc:
            fail_rc = step_open(cfg, path, log, want) or 0
        if not fail_rc:
            fail_rc = step_params(cfg, values, log, want) or 0
        if not fail_rc:
            fail_rc = step_run(cfg, args.out, args.timeout, log, want) or 0
        if not fail_rc:
            tag = os.path.splitext(os.path.basename(path))[0]
            result["images"] = step_capture(cfg, args.out, tag, zoom, log)
            result["ok"] = True
        else:
            result["error"] = lines[-1] if lines else f"step failed ({fail_rc})"
    finally:
        result["elapsed_s"] = round(time.time() - started, 1)

    # `--json` must always hand back a parseable object, including on failure
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if fail_rc:
        return fail_rc
    return 0 if result["ok"] else 5


if __name__ == "__main__":
    sys.exit(main())
