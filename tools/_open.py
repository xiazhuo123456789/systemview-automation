"""Open a .svu in the already-running SystemView instance (blank frame or any window).

  python _open.py "<path to .svu>"
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402
import openfile  # noqa: E402

MENU_FILE = (21, 37)
MENU_OPEN_EXISTING = (110, 177)


def main():
    path = os.path.abspath(sys.argv[1])
    want = os.path.splitext(os.path.basename(path))[0]
    same = [w for w in sv.find("SystemView - ") if want in w["title"]]
    if same:
        sv.maximize(same[0]["hwnd"])
        print("already open:", same[0]["title"])
        return 0
    blank = [w for w in sv.find("SystemView") if " - " not in w["title"]]
    target = blank[0] if blank else (sv.find("SystemView - ") or [None])[0]
    if not target:
        print("no SystemView window")
        return 2
    sv.maximize(target["hwnd"])
    time.sleep(0.6)
    sv.click(*MENU_FILE)
    time.sleep(0.4)
    sv.click(*MENU_OPEN_EXISTING)
    time.sleep(1.0)
    openfile.set_file("Open SystemView File", path)
    time.sleep(2.0)
    print("now:", [w["title"] for w in sv.find("SystemView - ")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
