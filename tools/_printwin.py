"""Capture one window's own pixels with PrintWindow (immune to overlays).

    python tools/_printwin.py "<window title substring>" out.png

Unlike ImageGrab, this asks the window to draw itself into a memory bitmap, so
anything that happens to be on top of it (other apps, popups, the taskbar) is
not in the result. Works on the VB6 GDI windows SystemView uses; PW_RENDERFULLCONTENT
(flag 2) is needed on Windows 8.1+ for windows that draw with DWM.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes as wt
from pathlib import Path

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


def find_window(sub: str) -> int:
    hits: list[tuple[int, str]] = []
    rows: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if sub.lower() in buf.value.lower():
                rows.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    hits = [(h, t) for h, t in rows if " - " in t] or rows
    if not hits:
        raise SystemExit(f"no visible window matching {sub!r}")
    hits.sort(key=lambda r: -len(r[1]))
    return hits[0][0]


def capture(hwnd: int, path: Path, flag: int = PW_RENDERFULLCONTENT) -> tuple[int, int]:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        raise SystemExit("window has no size")
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, flag)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h  # negative: top-down rows
    bi.biPlanes, bi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not ok:
        print("WARNING: PrintWindow returned 0; image may be blank")
    return w, h


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    hwnd = find_window(sys.argv[1])
    w, h = capture(hwnd, Path(sys.argv[2]))
    print(f"captured hwnd {hwnd} -> {sys.argv[2]} ({w}x{h})")
