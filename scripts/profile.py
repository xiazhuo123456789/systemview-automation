#!/usr/bin/env python3
"""System profiles: describe *what is on the canvas* instead of coding it.

A profile is a small JSON file under ``systems/`` that says, for one .svu
family:

* which token is which (by canvas coordinate),
* which parameter dialog belongs to it and how its fields are labelled,
* how to capture the result.

Nothing in this module touches the GUI; it only reads JSON and matches
control lists. That keeps it unit-testable and keeps ``sim.py`` free of
per-system knowledge, which is what makes the skill extensible: adding a new
device dialog means adding a profile, not editing code.

Profile schema (all keys optional)
----------------------------------
{
  "name": "fm-demo",
  "match": ["调频演示", "fm_demo"],          // file stems this profile fits
  "tokens": {                                 // logical name -> canvas point
      "fm":  {"id": 1, "at": [381, 477]},
      "noise": {"id": 7, "at": [490, 575]}
  },
  "param_dialog": {
      "title": "FM/VCO",                      // window-title substring
      "open_by": {"token": "fm", "menu_offset": [44, 8]},
      "fields": [                             // label text -> CLI value name
          {"label": "Amplitude", "value": "amplitude"},
          {"label": "Mod Gain",  "value": "mod_gain"},
          {"label": "Frequency", "value": "carrier"},
          {"label": "Phase",     "value": "phase"}
      ],
      "ok": "text~=OK"                        // selector, see pick()
  },
  "capture": {"window": [18, 690, 940, 1035], "zoom": [0.0437, 0.0477]}
}

Control selectors (`pick`)
--------------------------
  "text~=Substring"   first control whose text contains Substring (case-insensitive)
  "text=Exact"        exact text match
  "cls=Edit"          first control of that Win32 class
  "cls=Edit[2]"       the third one (zero-based)
  "id=0x1234"         by control id
  "#3"                the fourth control in the list, whatever it is
"""
from __future__ import annotations

import glob
import json
import os

REQUIRED = ("name",)


def load(path: str) -> dict:
    """Read one profile file and validate the bits sim.py relies on."""
    with open(path, encoding="utf-8") as fh:
        prof = json.load(fh)
    if not isinstance(prof, dict):
        raise ValueError(f"{path}: profile must be a JSON object")
    missing = [k for k in REQUIRED if k not in prof]
    if missing:
        raise ValueError(f"{path}: missing keys {missing}")
    prof.setdefault("match", [])
    prof.setdefault("tokens", {})
    prof.setdefault("capture", {})
    prof.setdefault("_path", path)
    # normalise token points to plain ints so callers never see lists of str
    for name, tok in prof["tokens"].items():
        at = tok.get("at") or [0, 0]
        tok["at"] = [int(at[0]), int(at[1])]
    return prof


def discover(systems_dir: str, stem: str) -> dict | None:
    """Find the profile whose ``match`` list best fits a file stem.

    Falls back to ``_template.json``'s sibling defaults: if nothing matches we
    return None and the caller keeps its built-in behaviour.
    """
    best, best_len = None, 0
    for path in sorted(glob.glob(os.path.join(systems_dir, "*.json"))):
        if os.path.basename(path).startswith("_"):
            continue
        try:
            prof = load(path)
        except (OSError, ValueError):
            continue
        for needle in prof.get("match", []):
            if needle and needle.lower() in stem.lower() and len(needle) > best_len:
                best, best_len = prof, len(needle)
    return best


# ------------------------------------------------------------------ selectors
def _text(c: dict) -> str:
    return (c.get("text") or "").strip()


def pick(controls: list[dict], spec: str | None) -> dict | None:
    """Resolve one selector (see module docstring) against a control list."""
    if not spec:
        return None
    spec = spec.strip()
    if spec.startswith("text~="):
        needle = spec[6:].lower()
        return next((c for c in controls if needle in _text(c).lower()), None)
    if spec.startswith("text="):
        want = spec[5:].strip().lower()
        return next((c for c in controls if _text(c).lower() == want), None)
    if spec.startswith("cls="):
        want = spec[4:]
        idx = 0
        if want.endswith("]") and "[" in want:
            want, _, num = want.partition("[")
            idx = int(num.rstrip("]"))
        hits = [c for c in controls if c.get("cls") == want]
        return hits[idx] if len(hits) > idx else None
    if spec.startswith("id="):
        want_id = int(spec[3:], 0)
        return next((c for c in controls if c.get("id") == want_id), None)
    if spec.startswith("#"):
        idx = int(spec[1:])
        return controls[idx] if len(controls) > idx else None
    raise ValueError(f"bad selector: {spec!r}")


def field_edit(controls: list[dict], label: str) -> dict | None:
    """Find the text box that belongs to a labelled field.

    SystemView lays device dialogs out as *label to the left, edit to the
    right* (sometimes label above, edit below). So: find the Static whose text
    starts with `label`, then take the nearest Edit that sits to its right on
    roughly the same row, else the first Edit below it.
    """
    label = label.strip().lower()
    statics = [c for c in controls
               if c.get("cls") in ("Static", "ThunderRT6Label")
               and _text(c).lower().startswith(label)]
    edits = [c for c in controls
             if c.get("cls") in ("Edit", "ThunderRT6TextBox")]
    if not statics:
        return None
    lab = statics[0]
    lx0, ly0, lx1, ly1 = lab["rect"]
    row_slack = max(12, (ly1 - ly0))
    right = [e for e in edits
             if e["rect"][0] >= lx0 and abs(e["rect"][1] - ly0) <= row_slack]
    if right:
        return min(right, key=lambda e: (abs(e["rect"][1] - ly0), e["rect"][0]))
    below = [e for e in edits if e["rect"][1] > ly1]
    if below:
        return min(below, key=lambda e: e["rect"][1])
    return None


# ------------------------------------------------------------------- values
def parse_sets(items, base: dict | None = None) -> dict:
    """Turn ``["carrier=5000", "mod_gain=30"]`` into ``{"carrier": 5000, ...}``.

    Numbers are converted when they parse as floats; everything else stays a
    string so text fields (file names, modes) also work.
    """
    out = dict(base or {})
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"--set expects NAME=VALUE, got {item!r}")
        key, _, raw = item.partition("=")
        key, raw = key.strip(), raw.strip()
        try:
            out[key] = float(raw) if any(ch in raw for ch in ".eE") else int(raw)
        except ValueError:
            out[key] = raw
    return out


def fmt(value) -> str:
    """Render a value the way SystemView's text boxes expect it."""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
