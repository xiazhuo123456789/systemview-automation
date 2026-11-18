"""Tidy helpers for a messy SystemView desktop.

  python _tidy.py ok          # click 确定/OK on any message box
  python _tidy.py cancel      # click 取消/Cancel on dialogs (Recent Files etc.)
  python _tidy.py close-blank # WM_CLOSE zero-size / untitled SystemView frames
  python _tidy.py close-title <substring>   # WM_CLOSE design windows by title
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402
import openfile  # noqa: E402

WM_CLOSE = 0x0010
BM_CLICK = 0x00F5
OK_TXT = ("确定", "OK", "是(&Y)")
CANCEL_TXT = ("取消", "Cancel", "Close")


def click_button(texts):
    n = 0
    for w in sv.find("", cls="#32770"):
        for c in openfile.children(w["hwnd"]):
            if c["cls"] != "Button":
                continue
            t = c["text"].strip()
            if any(t.startswith(x) or t == x for x in texts):
                sv.user32.SendMessageW(c["hwnd"], BM_CLICK, 0, 0)
                print("clicked", t, "on", w["title"])
                n += 1
                break
    return n


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ok"
    if cmd == "ok":
        print("clicked", click_button(OK_TXT))
    elif cmd == "cancel":
        print("clicked", click_button(CANCEL_TXT))
    elif cmd == "close-blank":
        n = 0
        for w in sv.find("SystemView"):
            l, t, r, b = w["rect"]
            if " - " not in w["title"] or (r - l) < 200:
                sv.user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
                print("closed", w["hwnd"], w["rect"], w["title"])
                n += 1
        print("closed", n)
    elif cmd == "close-title":
        sub = sys.argv[2]
        n = 0
        for w in sv.find(sub):
            sv.user32.PostMessageW(w["hwnd"], WM_CLOSE, 0, 0)
            print("closed", w["hwnd"], w["title"][:60])
            n += 1
        print("closed", n)
    time.sleep(0.4)


if __name__ == "__main__":
    main()
