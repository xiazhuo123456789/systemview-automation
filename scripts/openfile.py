import ctypes, ctypes.wintypes as wt, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv import user32, enum_windows, find, click

WM_SETTEXT = 0x000C
BM_CLICK = 0x00F5


def children(hwnd):
    out = []
    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, l):
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, cls, 128)
        r = wt.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        out.append(dict(hwnd=h, text=buf.value, cls=cls.value, id=user32.GetDlgCtrlID(h),
                        rect=(r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def dump(title_sub):
    hits = find(title_sub)
    for w in hits:
        print('DIALOG', w['hwnd'], w['rect'], w['title'])
        for c in children(w['hwnd']):
            print('   ', c['hwnd'], c['id'], c['cls'], c['rect'], repr(c['text'])[:80])


def set_file(title_sub, path, button_sub=('打开', '&O', 'Open')):
    w = find(title_sub)[0]
    kids = children(w['hwnd'])
    edits = [c for c in kids if c['cls'] == 'Edit']
    target = None
    for e in edits:
        if 'svu' in e['text'].lower() or e['text'] == '':
            target = e
            break
    if target is None:
        target = edits[-1]
    print('edit', target['hwnd'], repr(target['text']))
    user32.SendMessageW(target['hwnd'], WM_SETTEXT, 0, path)
    time.sleep(0.4)
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(target['hwnd'], buf, 512)
    print('readback', repr(buf.value))
    btn = None
    for c in kids:
        if c['cls'] == 'Button' and any(s in c['text'] for s in button_sub):
            btn = c
    print('button', btn['hwnd'], repr(btn['text']))
    user32.SendMessageW(btn['hwnd'], BM_CLICK, 0, 0)


if __name__ == '__main__':
    if sys.argv[1] == 'dump':
        dump(sys.argv[2])
    elif sys.argv[1] == 'open':
        set_file(sys.argv[2], sys.argv[3])
    else:
        print(__doc__ or 'usage: python openfile.py dump <title> | open <title> <path>')
