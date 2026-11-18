# Extending this skill

Three ways to make it cover a system this skill has never seen.
All of them are data or small pure functions — **no edit to the automation
loop is needed**.

---

## 1. Add a system profile (the usual case)

A *system profile* is a JSON file in `systems/`. It tells the runner three
things: which windows/dialog belong to the file, where the tokens sit on the
canvas, and which parameter labels go to which CLI value.

```jsonc
// systems/fm-voice.json
{
  "name": "fm-voice",                       // unique; reported as result.profile
  "match": ["调频通信系统仿真", "fm_voice"],  // substring of the .svu path or window title
  "tokens": {
    "source":   { "id": 0,  "at": [142, 468] },
    "fm":       { "id": 1,  "at": [381, 477] },
    "noise":    { "id": 7,  "at": [490, 575] },
    "sink_mod": { "id": 11, "at": [318, 705] }
  },
  "param_dialog": {
    "title": "FM/VCO",                       // window title fragment of the dialog
    "open_by": { "token": "fm", "menu_offset": [44, 8] },
    "fields": [
      { "label": "Amplitude", "value": "amplitude" },
      { "label": "Mod Gain",  "value": "mod_gain"  },
      { "label": "Frequency", "value": "carrier"   }
    ],
    "ok": "text~=OK"
  },
  "capture": { "window": [18, 690, 940, 1035], "zoom": [0.0437, 0.0477] }
}
```

Recipe:

1. `cp systems/_template.json systems/<your-system>.json` (files starting with
   `_` are skipped by discovery, which is why the template never matches).
2. Open your `.svu`, click each token once, and read `token at X,Y` from the
   status bar (`scripts/token_status.py` prints a labelled strip for a list of
   points). Put those pixels in `tokens.*.at`.
3. Open the parameter dialog by hand, screenshot it, and copy the **label text
   exactly as drawn** (`Amplitude (v)` → `"Amplitude"` works because matching
   is `startswith`).
4. Run `python scripts/sim.py --file <your.svu> --print-profile` — it resolves
   and prints the profile without touching the GUI. Iterate on the JSON until
   the numbers look right.
5. Run for real: `python scripts/sim.py --file <your.svu> --set carrier=5000 --out out`.

`match` is longest-substring wins; `discover()` is called with the file stem,
so `"调频演示"` matches `调频演示-可见已调波.svu`.

### Field labels are located, not indexed

`profile.field_edit()` finds the `Static`/`ThunderRT6Label` whose text starts
with your label, then picks the nearest `Edit`/`ThunderRT6TextBox` to its right
on the same row (falling back to the nearest one below). That means a dialog
whose layout shifts between versions keeps working as long as the labels do.
Every selector also accepts raw alternatives:

| selector        | meaning                                    |
|-----------------|--------------------------------------------|
| `text~=Mod Gain`| case-insensitive substring on control text |
| `text=OK`       | exact text                                 |
| `cls=Button[0]` | nth control of that class                  |
| `#3`            | third control in enumeration order         |

---

## 2. Add a device dialog to an existing system

If your system already has a profile but you need a *second* dialog (say a
`Gauss Noise` box next to `FM/VCO`), do **not** fork `sim.py`. Add the dialog
to the profile and call it from `--set`:

```jsonc
"param_dialogs": {
  "fm":    { "title": "FM/VCO",       "token": "fm",    "fields": [...] },
  "noise": { "title": "Gaussian Noise", "token": "noise", "fields": [
      { "label": "Std Deviation", "value": "noise_sigma" },
      { "label": "Mean",          "value": "noise_mean"  } ] }
}
```

`step_params()` already loops over the dialog's `fields`; the only change is
which `open_by.token` is used, and that is data.

> Order matters on this software: opening a *Source Library* dialog and pressing
> its `OK` resets that token to library defaults. Change sources first, noise
> last, and re-read the box afterwards (see `references/pitfalls.md` §2).

---

## 3. Add a new action (run, capture, zoom, export)

The automation loop is five small steps, each an ordinary function that takes
`cfg` and returns an exit code:

```
step_launch → step_open → step_params → step_run → step_capture
```

To add behaviour, write a function with the same shape and insert it in
`main()`:

```python
def step_export(cfg, out_dir, log, want=""):
    win = design_window(cfg, want)
    if not win:
        log("ERROR: no design window")
        return 2
    sv.focus(win["hwnd"])
    click(*cfg["menu_file"]); time.sleep(0.4)
    click(64, 245)                      # File → Save System
    log("saved")
    return 0
```

### `sv.py` primitive contract

| call | contract |
|------|----------|
| `find(sub, cls=None)` | first top-level window whose title contains `sub`; `None` if absent. Never raises. |
| `enum_windows()` | list of `{hwnd, title, cls, rect}` for visible top-level windows. |
| `maximize(hwnd)` | `SetWindowPos` to `(-10,-10,1930,1030)` — the canvas coordinate system used by every profile assumes **exactly** this. |
| `hold_front(hwnd)` / `release_front(hwnd)` | TOPMOST bounce so synthetic clicks land; Windows refuses `SetForegroundWindow` from a background process, so this is mandatory before `click`. |
| `click(x, y, button="left", double=False)` | physical pixels, DPI-aware (`SetProcessDpiAwareness(2)` runs at import). |
| `drag(x0,y0,x1,y1,steps=18)` | for rubber-band zoom inside an analysis plot. |
| `key(vk)` / `ctrl(vk)` | single keystroke helpers (`VK_F5 = 0x74`). |
| `shot(path)` | full-screen grab; returns the path. |

Everything is `ctypes` + `PIL` — no `pywin32`, no `pyautogui`, no browser.

---

## What not to extend

* **Do not add OCR.** The status bar is VB6-drawn and has no child window; it is
  read by screenshot for humans, not parsed by the runner.
* **Do not add a "close all windows" helper.** This software is single-instance
  and the MDI frame looks like a blank window; closing by title kills the user's
  work. See `references/pitfalls.md` §15.
* **Do not hard-code menu coordinates** for anything except the first item of a
  context menu (`menu_offset`), because menu entries shift with content.
