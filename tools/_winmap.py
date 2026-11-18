"""Print every SystemView window with its owning process id.

Read-only. Used to tell apart the instances this assistant spawned from the
one the user is working in, before closing anything.
"""
import ctypes
import os
import sys
from ctypes import wintypes as wt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import sv  # noqa: E402


def pids_of(name="SysVu_32.exe"):
    import subprocess

    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, encoding="mbcs", errors="replace",
    ).stdout
    pids = set()
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def main():
    wanted = pids_of()
    rows = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if not sv.user32.IsWindowVisible(h):
            return True
        n = sv.user32.GetWindowTextLengthW(h)
        if not n:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        sv.user32.GetWindowTextW(h, buf, n + 1)
        title = buf.value
        if "SystemView" not in title and "SvuUtil" not in title:
            return True
        pid = wt.DWORD()
        sv.user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value not in wanted:
            return True
        r = wt.RECT()
        sv.user32.GetWindowRect(h, ctypes.byref(r))
        cls = ctypes.create_unicode_buffer(256)
        sv.user32.GetClassNameW(h, cls, 256)
        rows.append((pid.value, h, cls.value, title, (r.left, r.top, r.right, r.bottom)))
        return True

    sv.user32.EnumWindows(cb, 0)
    for pid, h, cls, title, rect in sorted(rows):
        print(f"{pid:>6} {h:>9} {cls:<20} {title[:58]:<58} {rect}")
    print(f"-- {len(rows)} window(s) across {len({r[0] for r in rows})} process(es)")


if __name__ == "__main__":
    main()
