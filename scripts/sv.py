import ctypes, ctypes.wintypes as wt, json, os, time, sys

try:                                    # Chinese window titles on a cp936 console
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
try:
    ctypes.WinDLL('shcore').SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

GWL_STYLE = -16
WS_MAXIMIZE = 0x01000000
SW_HIDE = 0
SW_SHOW = 5
SW_MAXIMIZE = 3
SW_RESTORE = 9
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hidden.json')


def enum_windows():
    out = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if user32.IsWindowVisible(h):
            n = user32.GetWindowTextLengthW(h)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                r = wt.RECT()
                user32.GetWindowRect(h, ctypes.byref(r))
                cls = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(h, cls, 256)
                out.append(dict(hwnd=h, title=buf.value, cls=cls.value,
                                rect=(r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumWindows(cb, 0)
    return out


def find_child(parent, sub, cls=None):
    """Like find(), but only among the descendants of one window.

    Each analysis plot lives in its own MDI child window, so a plot title never
    turns up in the top-level enumeration. The rectangles are still screen
    coordinates, so a caller can click them directly.
    """
    out = []

    def _info(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        title = ''
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            title = buf.value
        cls_name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_name, 256)
        return title, cls_name.value

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _):
        title, cls_name = _info(hwnd)
        if sub.lower() in title.lower() and (cls is None or cls == cls_name):
            r = wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append({"hwnd": hwnd, "cls": cls_name, "title": title,
                        "rect": [r.left, r.top, r.right, r.bottom]})
        return True

    user32.EnumChildWindows(parent, _cb, 0)
    return out


def find(sub, cls=None):
    hits = [w for w in enum_windows() if sub in w['title'] and (cls is None or w['cls'] == cls)]
    return hits


def hide_others(keep_subs):
    keep = set()
    for w in enum_windows():
        for k in keep_subs:
            if k in w['title']:
                keep.add(w['hwnd'])
    skip_cls = {'Shell_TrayWnd', 'Progman', 'WorkerW', 'Windows.UI.Core.CoreWindow'}
    saved = []
    for w in enum_windows():
        if w['hwnd'] in keep or w['cls'] in skip_cls:
            continue
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(w['hwnd'], buf, 512)
        saved.append(dict(hwnd=w['hwnd'], title=buf.value))
        user32.ShowWindow(w['hwnd'], SW_HIDE)
    json.dump(saved, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False)
    return len(saved)


def restore():
    if not os.path.exists(STATE):
        return 0
    saved = json.load(open(STATE, encoding='utf-8'))
    n = 0
    for s in saved:
        if user32.IsWindow(s['hwnd']):
            user32.ShowWindow(s['hwnd'], SW_SHOW)
            n += 1
    os.remove(STATE)
    return n


def hold_front(hwnd):
    """Keep the window above everything for as long as we need to click into
    it. Needed when another always-on-top app (chat client, browser) sits in
    front: NOTOPMOST restores normal order immediately, so stay TOPMOST."""
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def release_front(hwnd):
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


def bring_to_front(hwnd):
    """Windows refuses SetForegroundWindow to a background process; bounce the
    window through TOPMOST first, which is allowed and does the job."""
    flags = SWP_NOMOVE | SWP_NOSIZE
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
    time.sleep(0.25)


def maximize(hwnd, w=1930, h=1030):
    """Fill the screen. Tries the MDI-native maximize first: SystemView's design
    canvas is an MDI child, and SetWindowPos alone leaves it floating at the
    saved size, which silently invalidates every profile token coordinate."""
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    time.sleep(0.35)
    user32.SetWindowPos(hwnd, 0, -10, -10, w, h, 0x0040)
    bring_to_front(hwnd)
    time.sleep(0.4)


def focus(hwnd):
    user32.ShowWindow(hwnd, SW_RESTORE)
    bring_to_front(hwnd)
    time.sleep(0.3)


def capture_window(hwnd, path):
    """Save one window's own pixels with PrintWindow (no taskbar, no overlays).

    ImageGrab records the screen, so anything on top of the window leaks into
    the picture; PrintWindow asks the window to paint itself into a memory
    bitmap instead. SystemView is plain GDI, but PW_RENDERFULLCONTENT (2) is
    needed anyway for windows composited by DWM.
    """
    import ctypes
    from ctypes import wintypes as wt
    from PIL import Image

    class BIH(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                    ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                    ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                    ("biClrImportant", wt.DWORD)]

    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError(f"window {hwnd} has no size ({w}x{h})")
    gdi32 = ctypes.windll.gdi32
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)
    bi = BIH()
    bi.biSize, bi.biWidth, bi.biHeight = ctypes.sizeof(BIH), w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    # A window can be reported larger than it paints (ownerdraw frames, or a
    # stale rect while maximized); the untouched margin comes back pure black.
    from PIL import ImageChops
    bg = Image.new("RGB", img.size, (0, 0, 0))
    bbox = ImageChops.difference(img, bg).getbbox()
    if bbox and (bbox[2] - bbox[0]) > 200 and (bbox[3] - bbox[1]) > 200:
        img = img.crop(bbox)
    img.save(path)
    return bool(ok), img.width, img.height


def shot(path):
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    img.save(path)
    return img.size


def _move(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.06)


def click(x, y, button='left', double=False):
    _move(x, y)
    down = 0x0002 if button == 'left' else 0x0008
    up = 0x0004 if button == 'left' else 0x0010
    n = 2 if double else 1
    for _ in range(n):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)
    time.sleep(0.25)


def drag(x0, y0, x1, y1, steps=18):
    _move(x0, y0)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.12)
    for i in range(1, steps + 1):
        _move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(0.012)
    time.sleep(0.1)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    time.sleep(0.25)


def key(vk, times=1):
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.06)


def ctrl(vk):
    user32.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.03)
    key(vk)
    user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.2)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'shot':
        print(shot(sys.argv[2]))
    elif cmd == 'list':
        for w in enum_windows():
            print(w['hwnd'], w['rect'], w['cls'], w['title'][:70])
    elif cmd == 'hide':
        print(hide_others(sys.argv[2:]))
    elif cmd == 'restore':
        print(restore())
    elif cmd == 'click':
        click(int(sys.argv[2]), int(sys.argv[3]))
    elif cmd == 'rclick':
        click(int(sys.argv[2]), int(sys.argv[3]), 'right')
    elif cmd == 'dbl':
        click(int(sys.argv[2]), int(sys.argv[3]), 'left', True)
    elif cmd == 'drag':
        drag(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
    elif cmd == 'max':
        maximize(int(sys.argv[2]))
    elif cmd == 'key':
        key(int(sys.argv[2]))
    elif cmd == 'ctrl':
        ctrl(int(sys.argv[2]))
