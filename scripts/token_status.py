"""Read what each token on the SystemView canvas is, without OCR.

SystemView draws its status line itself (there is no msctls_statusbar32
child window), so GetWindowText cannot read it. The only reliable channel
is to click a token and screenshot the status strip, then let a human or a
vision model read the stitched image.

usage:
    python token_status.py "<window title substring>" out.png x1 y1 [x2 y2 ...]

The stitched PNG gets one row per token: a label line ("token at X,Y")
followed by the status-strip crop taken right after clicking that point.

Typical status text:
    Source: Sinusoid, Input from None, Output to 5. Click right mouse button
    Function: Freq Mod, Input from 5, Output to 6, 11. Click right mouse ...
    Adder: Non Parametric, Input from 1, 7, Output to 8, 9. ...
    Sink: Analysis, Input from 1, Output to None. ...

The design window must end up above any maximized Analysis child window,
otherwise the strip area shows plot pixels instead of the status line; that
is why the window is held topmost for the duration of the capture.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sv import find, click, shot, user32, maximize
from PIL import Image, ImageDraw

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001


def status_rect(rect):
    # The status line sits just above the window's bottom edge. Keep the strip
    # narrow (<=1000 px): overlays such as the agent UI's floating pill live on
    # the right side of the screen and would otherwise cover the text.
    l, t, r, b = rect
    return (max(l + 5, 0), b - 58, l + min(1000, r - l), b - 26)


def hold_front(hwnd):
    flags = SWP_NOMOVE | SWP_NOSIZE
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)


def release_front(hwnd):
    flags = SWP_NOMOVE | SWP_NOSIZE
    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)


def main():
    title, out = sys.argv[1], sys.argv[2]
    pts = [int(v) for v in sys.argv[3:]]
    assert len(pts) % 2 == 0, 'give x y pairs'
    w = find(title)[0]
    maximize(w['hwnd'])                 # canonical 1920x1080 coordinate space
    time.sleep(0.4)
    w = find(title)[0]
    box = status_rect(w['rect'])
    tmp = os.path.join(os.path.dirname(os.path.abspath(out)), '_ts_tmp.png')
    rows = []
    try:
        hold_front(w['hwnd'])
        for i in range(0, len(pts), 2):
            x, y = pts[i], pts[i + 1]
            click(x, y)
            time.sleep(0.45)
            hold_front(w['hwnd'])      # clicking a token must not raise a child
            shot(tmp)
            rows.append(((x, y), Image.open(tmp).crop(box).copy()))
    finally:
        release_front(w['hwnd'])
        if os.path.exists(tmp):
            os.remove(tmp)
    W = max(c.width for _, c in rows)
    H = sum(c.height + 18 for _, c in rows)
    canvas = Image.new('RGB', (W, H), (16, 16, 16))
    d = ImageDraw.Draw(canvas)
    yy = 0
    for (x, y), c in rows:
        d.text((2, yy + 3), 'token at %d,%d' % (x, y), fill=(0, 255, 0))
        yy += 18
        canvas.paste(c, (0, yy))
        yy += c.height
    canvas = canvas.resize((int(W * 1.6), int(H * 1.6)), Image.LANCZOS)
    canvas.save(out)
    print(out, canvas.size)


if __name__ == '__main__':
    main()
