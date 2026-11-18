"""Put a known file back into a design window (used to undo an accidental open).

  python _reopen.py "<window title substring>" "<path to .svu>"
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402
import openfile  # noqa: E402

MENU_FILE = (21, 37)
MENU_OPEN_EXISTING = (110, 177)
BM_CLICK = 0x00F5


def main():
    sub, path = sys.argv[1], os.path.abspath(sys.argv[2])
    wins = [w for w in sv.find("SystemView - ") if sub in w["title"]]
    if not wins:
        print("no design window for", sub)
        return 1
    win = wins[0]
    sv.maximize(win["hwnd"])
    time.sleep(0.6)
    sv.click(*MENU_FILE)
    time.sleep(0.4)
    sv.click(*MENU_OPEN_EXISTING)
    time.sleep(1.0)
    openfile.set_file("Open SystemView File", path)
    time.sleep(2.0)
    # answer "save changes?" with No
    for w in sv.find("SystemView", cls="#32770"):
        for c in openfile.children(w["hwnd"]):
            if c["cls"] == "Button" and c["text"].strip().startswith("否"):
                sv.user32.SendMessageW(c["hwnd"], BM_CLICK, 0, 0)
                print("save prompt -> No")
                time.sleep(1.5)
    print("now:", [w["title"] for w in sv.find("SystemView - ")])
    return 0


if __name__ == "__main__":
    sys.exit(main())
