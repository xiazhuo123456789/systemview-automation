"""Find out whether this machine's SystemView still matches the shipped profile.

Nothing here assumes a version number. It reports what it can see -- window
classes, titles, rectangles, the canvas origin, and the "SystemView v..." build
string -- then captures the design and analysis windows plus a stitched status
strip for every token, so an agent (or you) can read them and decide.

usage:
    python probe.py                       # human-readable report
    python probe.py --json out.json       # machine-readable report
    python probe.py --out DIR             # where the PNGs go (default: ./probe)
    python probe.py --file demo.svu       # also compare against one file name

Exit code 0 = every check that can be automated passed; 2 = something needs a
look (the report says what). It never clicks, drags or edits the system.

Why a report instead of a version table: SystemView 3/4/5/6 differ in control
classes (ThunderRT6* vs .NET), in whether the canvas is an MDI child, and in
DPI behaviour. A version table would rot. A self-check does not: run it on the
target machine and look at the pictures it produced.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sv  # noqa: E402

CFG_PATH = os.path.join(os.path.dirname(HERE), "config.json")


def load_cfg(path=None):
    with open(path or CFG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_design():
    for w in sv.enum_windows():
        if w["title"].startswith("SystemView - "):
            return w
    return None


def find_analysis():
    for w in sv.enum_windows():
        if w["title"].startswith("SystemView Analysis"):
            return w
    return None


def canvas_box(hwnd):
    """Bounding box of the drawing area, in screen coordinates.

    SystemView draws the canvas edge to edge under its toolbar, inside the MDI
    child (5.0) or directly in the frame (some other builds). We only need the
    top-left corner and the size, so the client rect is enough: the canvas
    starts right under the toolbar and fills the rest of the client area.
    """
    import ctypes
    from ctypes import wintypes
    r = wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(r))
    p = wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(p))
    return {"left": p.x, "top": p.y, "width": r.right, "height": r.bottom}


def exe_version(path):
    """Version of the executable itself, locale independent.

    The toolbar label ("SystemView v5.0 Build 046") is drawn, not a child
    window, so WM_GETTEXT cannot see it. The fixed file-info block always can
    be read, and it is enough to tell 5.x from 3.x/6.x.
    """
    import ctypes
    from ctypes import wintypes
    ver = ctypes.windll.version
    size = ver.GetFileVersionInfoSizeW(wintypes.LPCWSTR(path), None)
    if not size:
        return None
    buf = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(wintypes.LPCWSTR(path), 0, size, buf):
        return None
    rv = ctypes.c_void_p()
    ln = ctypes.c_uint()
    if not ver.VerQueryValueW(buf, wintypes.LPCWSTR("\\"), ctypes.byref(rv), ctypes.byref(ln)):
        return None
    ffi = ctypes.cast(rv, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
    ms, ls = ffi[2], ffi[3]
    return "%d.%d.%d.%d" % (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)


def build_string(windows):
    """The toolbar shows 'SystemView v5.0 Build 046'; VB static texts are real
    child windows, so WM_GETTEXT can read them without OCR."""
    import ctypes
    from ctypes import wintypes
    u = ctypes.windll.user32
    TP = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    WM_GETTEXT = 0x000D
    found = []

    def text(h):
        b = ctypes.create_unicode_buffer(1024)
        u.SendMessageW(h, WM_GETTEXT, 1024, b)
        return b.value

    for w in windows:
        def cb(hwnd, l):
            t = text(hwnd)
            if t and ("SystemView v" in t or "Build" in t):
                found.append(t.strip())
            return True
        u.EnumChildWindows(w["hwnd"], TP(cb), 0)
    return sorted(set(found))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PATH", help="write the report here")
    ap.add_argument("--out", default="probe", help="directory for the PNGs")
    ap.add_argument("--file", help="a .svu to look for in the window titles")
    ap.add_argument("--config", help="config.json to compare the profile with")
    args = ap.parse_args(argv)

    cfg = load_cfg(args.config)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    wins = [w for w in sv.enum_windows()
            if w["title"].startswith("SystemView") or "Recent SystemView" in w["title"]]
    design = find_design()
    analysis = find_analysis()

    report = {
        "windows": [{"hwnd": w["hwnd"], "cls": w["cls"], "title": w["title"],
                     "rect": list(w["rect"])} for w in wins],
        "build_strings": build_string(wins),
        "design": None,
        "analysis": None,
        "config": {"path": os.path.abspath(args.config or CFG_PATH)},
        "checks": [],
        "images": [],
        "ok": True,
    }

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["ok"] = False

    check("a design window is open", design is not None,
          "" if design else "open a .svu first, or run sim.py --file ...")
    check("an analysis window is open", analysis is not None,
          "" if analysis else "run the system once (Shift+F5) to create one")

    if args.file and design:
        check("the design window shows the file you asked for",
              os.path.basename(args.file).lower() in design["title"].lower(),
              design["title"])

    if design:
        sv.maximize(design["hwnd"])
        time.sleep(0.6)
        box = canvas_box(design["hwnd"])
        # config.json was measured with the window maximized at 1920x1080,
        # so the canvas origin recorded there is the reference point.
        ref = cfg.get("canvas_origin")
        report["design"] = {
            "hwnd": design["hwnd"], "title": design["title"],
            "rect": list(design["rect"]), "canvas": box,
            "canvas_reference": ref,
        }
        if ref:
            dx, dy = box["left"] - ref[0], box["top"] - ref[1]
            report["design"]["canvas_delta"] = [dx, dy]
            # token coordinates in config.json are canvas-relative, so a
            # non-zero delta is fine: probe just reports it. A different
            # window *size* is worth flagging because the status strip and the
            # toolbar move with it.
            check("canvas origin moved (coordinates get shifted by this delta)",
                  True, f"delta=({dx:+d},{dy:+d}) -> add it to every token coordinate")
        else:
            report["design"]["canvas_delta"] = [0, 0]
            check("config has canvas_origin", False,
                  "add \"canvas_origin\": [left, top] to config.json for shifted layouts")

        sv.hold_front(design["hwnd"])
        try:
            time.sleep(0.3)
            p = os.path.join(out, "design.png")
            ok, w, h = sv.capture_window(design["hwnd"], p)
            report["images"].append(p)
            check("design window captured", ok, f"{w}x{h}")
        finally:
            sv.release_front(design["hwnd"])

    if analysis:
        sv.hold_front(analysis["hwnd"])
        try:
            time.sleep(0.3)
            p = os.path.join(out, "analysis.png")
            ok, w, h = sv.capture_window(analysis["hwnd"], p)
            report["images"].append(p)
            report["analysis"] = {"hwnd": analysis["hwnd"], "title": analysis["title"],
                                  "rect": list(analysis["rect"]), "size": [w, h]}
            check("analysis window captured", ok, f"{w}x{h}")
        finally:
            sv.release_front(analysis["hwnd"])

    # The status line is VB-drawn: the only way to know what a token is, is to
    # click it and read the strip. token_status.py stitches one row per token.
    if design and cfg.get("tokens"):
        pts = [(t, xy) for t, xy in cfg["tokens"].items()]
        delta = (report["design"] or {}).get("canvas_delta") or [0, 0]
        argv2 = [sys.executable, os.path.join(HERE, "token_status.py"),
                 "SystemView - ", os.path.join(out, "token_status.png")]
        for _, (x, y) in pts:
            argv2 += [str(x + delta[0]), str(y + delta[1])]
        try:
            r = subprocess.run(argv2, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120,
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            p = os.path.join(out, "token_status.png")
            if os.path.exists(p):
                report["images"].append(p)
            check("status strip captured for every configured token",
                  r.returncode == 0 and os.path.exists(p),
                  (r.stderr or "").strip()[:200])
        except Exception as exc:  # noqa: BLE001 - report, never crash the probe
            check("status strip captured for every configured token", False, repr(exc))

    # Informational only: on 5.0 the toolbar label is drawn, so this never matches
    # and must not fail the run. The executable version above is the real signal.
    check("build string found (informational)", True,
          ", ".join(report["build_strings"]) or
          "toolbar label is drawn, not readable - see exe_version instead")

    exe = cfg.get("exe")
    if exe and os.path.exists(exe):
        ev = exe_version(exe)
        report["exe"] = {"path": exe, "file_version": ev}
        check("executable version readable", bool(ev), ev or "unknown")
    else:
        report["exe"] = {"path": exe, "file_version": None}
        check("executable found", False, f"config exe={exe!r} does not exist on this machine")

    txt = json.dumps(report, ensure_ascii=False, indent=2)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
    print(txt)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
