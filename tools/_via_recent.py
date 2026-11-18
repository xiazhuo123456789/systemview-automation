"""Finish a File>Open that landed on the Recent list: click Existing..., fill the
path, press Open.

  python _via_recent.py "<path to .svu>"
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402
import openfile  # noqa: E402

BM_CLICK = 0x00F5


def main():
    path = os.path.abspath(sys.argv[1])
    dlg = sv.find("Recent SystemView Files")
    if not dlg:
        print("no Recent dialog")
        return 2
    for c in openfile.children(dlg[0]["hwnd"]):
        if "Existing" in c["text"]:
            sv.user32.SendMessageW(c["hwnd"], BM_CLICK, 0, 0)
            print("clicked Existing...")
            break
    time.sleep(1.2)
    openfile.set_file("Open SystemView File", path)
    time.sleep(2.0)
    print("now:", [w["title"] for w in sv.find("SystemView - ")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
