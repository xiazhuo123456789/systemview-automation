"""One-off helper: close one SystemView design window without saving, so the
canvas scroll state is back to its default before the next run."""
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402

WM_CLOSE = 0x0010
BM_CLICK = 0x00F5

stem = sys.argv[1] if len(sys.argv) > 1 else ""
win = sv.design_window if hasattr(sv, "design_window") else None
hits = [w for w in sv.find("SystemView - ") if stem in w["title"]]
if not hits:
    print("no window for", stem)
    raise SystemExit(1)
h = hits[0]["hwnd"]
print("closing", h, hits[0]["title"])
sv.user32.PostMessageW(h, WM_CLOSE, 0, 0)
time.sleep(1.5)

import ctypes
from ctypes import wintypes

user32 = sv.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def kids(hwnd):
    out = []

    def cb(h, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, cls, 256)
        r = wintypes.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        out.append({"hwnd": h, "text": buf.value, "cls": cls.value,
                    "rect": (r.left, r.top, r.right, r.bottom)})
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return out


for w in sv.find("SystemView"):
    texts = [c["text"] for c in kids(w["hwnd"]) if c["cls"] == "Button"]
    if not any(t.strip() for t in texts):
        continue
    print("dialog:", w["title"], texts)
    for c in kids(w["hwnd"]):
        if c["cls"] != "Button":
            continue
        t = c["text"].strip()
        if t.startswith("否") or t.lower().startswith("n"):
            sv.user32.SendMessageW(c["hwnd"], BM_CLICK, 0, 0)
            print("clicked", t)
            break
time.sleep(0.8)
print("remaining:", [w["title"] for w in sv.find("SystemView - ")])
