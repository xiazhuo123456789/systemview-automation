"""Dismiss a SystemView "save changes?" prompt by choosing No (does not save)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sv  # noqa: E402
import openfile  # noqa: E402

BM_CLICK = 0x00F5

done = 0
for w in sv.find("SystemView", cls="#32770"):
    kids = openfile.children(w["hwnd"])
    texts = [c["text"] for c in kids if c["cls"] == "Button"]
    if not texts:
        continue
    print("dialog", w["hwnd"], w["rect"], texts)
    for c in kids:
        if c["cls"] != "Button":
            continue
        t = c["text"].strip()
        if t.startswith("否") or t.lower() in ("no", "&no"):
            sv.user32.SendMessageW(c["hwnd"], BM_CLICK, 0, 0)
            print("clicked No:", t)
            done += 1
            break
time.sleep(0.5)
print("dismissed", done)
