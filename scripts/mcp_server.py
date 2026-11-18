#!/usr/bin/env python3
"""Minimal MCP server for the SystemView automation skill.

Zero dependencies: speaks MCP over stdio (newline-delimited JSON-RPC 2.0),
so any MCP client can use it — Claude Desktop/Code, Cursor, Cline, Zed,
Continue, or your own agent loop.

    python scripts/mcp_server.py

Three tools:
    systemview_run         open a .svu, optionally set device parameters,
                           run the simulation, capture the analysis windows
    systemview_inspect     list live SystemView windows and the token map of
                           a .svu (no clicking, no run)
    systemview_screenshot  capture the current analysis window to a PNG

Every tool returns MCP content: a JSON text block plus, when a picture was
produced, an inline PNG image block.

Logging goes to stderr only — stdout is the protocol channel.
"""

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import sv  # noqa: E402

SERVER_NAME = "systemview-automation"
SERVER_VERSION = "1.0.0"
PROTOCOL = "2024-11-05"

SIM = os.path.join(HERE, "sim.py")


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- helpers

def _run_sim(argv, timeout=180):
    """Run sim.py with --json and return (rc, parsed, raw_stderr).

    sim.py writes UTF-8. Decode explicitly: on a Chinese Windows the default
    locale is cp936, and letting subprocess decode with it kills the reader
    thread ("gbk codec can't decode byte 0xae") and silently returns "".
    """
    cmd = [sys.executable, SIM] + argv + ["--json"]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       timeout=timeout, env=env)
    out = (p.stdout or "").strip()
    try:
        data = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception:
        data = {"ok": False, "raw_stdout": out[-2000:]}
    return p.returncode, data, (p.stderr or "")[-2000:]


def _image_block(path):
    import base64
    with open(path, "rb") as f:
        b = f.read()
    return {"type": "image", "data": base64.b64encode(b).decode(),
            "mimeType": "image/png"}


def _text_block(obj):
    return {"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=2)}


def _windows():
    out = []
    for w in sv.enum_windows():
        t = w["title"]
        if t.startswith("SystemView") or "Recent SystemView" in t:
            out.append({"hwnd": w["hwnd"], "class": w["cls"],
                        "title": t, "rect": list(w["rect"])})
    return out


# ---------------------------------------------------------------- tools

def tool_run(a):
    path = a.get("file")
    if not path:
        raise ValueError("file is required")
    argv = ["--file", path]
    for k, v in (a.get("set") or {}).items():
        argv += ["--set", "%s=%s" % (k, v)]
    if a.get("out"):
        argv += ["--out", a["out"]]
    if a.get("timeout"):
        argv += ["--timeout", str(a["timeout"])]
    if a.get("zoom"):
        argv += ["--zoom", str(a["zoom"][0]), str(a["zoom"][1])]
    if a.get("config"):
        argv += ["--config", a["config"]]

    rc, data, err = _run_sim(argv, timeout=(a.get("timeout") or 60) + 120)
    content = [_text_block({"exit_code": rc, "result": data,
                            "stderr_tail": err or None})]
    imgs = data.get("images") or []
    if imgs and os.path.exists(imgs[-1]):
        content.append(_image_block(imgs[-1]))
    return content, rc == 0


def tool_inspect(a):
    info = {"windows": _windows()}
    path = a.get("file")
    if path:
        rc, data, err = _run_sim(["--file", path, "--print-profile"], timeout=90)
        info["profile"] = data
        info["exit_code"] = rc
        if err:
            info["stderr_tail"] = err
    info["systemview_running"] = bool(info["windows"])
    return [_text_block(info)], True


def tool_screenshot(a):
    sub = a.get("title") or "SystemView Analysis"
    cands = [w for w in sv.enum_windows() if sub in w["title"]]
    if a.get("kind") == "design":
        cands = [w for w in sv.enum_windows()
                 if w["title"].startswith("SystemView - ")]
    if not cands:
        return [_text_block({"ok": False,
                             "error": "no window matching %r" % sub,
                             "windows": _windows()})], False
    cands.sort(key=lambda w: (w["rect"][2] - w["rect"][0]) *
               (w["rect"][3] - w["rect"][1]), reverse=True)
    win = cands[0]
    d = a.get("out") or os.path.join(tempfile.gettempdir(), "sv-mcp")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, a.get("name") or ("shot-%d.png" % int(time.time())))
    sv.hold_front(win["hwnd"])
    try:
        time.sleep(0.5)
        ok, w, h = sv.capture_window(win["hwnd"], p)
    finally:
        sv.release_front(win["hwnd"])
    content = [_text_block({"ok": bool(ok), "path": p, "width": w, "height": h,
                            "window": win["title"]})]
    if ok and os.path.exists(p):
        content.append(_image_block(p))
    return content, bool(ok)


TOOLS = [
    {
        "name": "systemview_run",
        "description": ("Open an ELANIX SystemView .svu, optionally change device "
                        "parameters (carrier, mod_gain, amplitude), run the "
                        "simulation and capture the analysis windows as PNG. "
                        "Returns the output paths and an inline picture."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string",
                         "description": "Absolute path to the .svu file"},
                "set": {"type": "object",
                        "description": 'Device parameters, e.g. {"carrier": 5000, "mod_gain": 30}'},
                "out": {"type": "string", "description": "Output directory"},
                "timeout": {"type": "integer", "description": "Seconds to wait for plots to settle"},
                "zoom": {"type": "array", "items": {"type": "number"},
                         "description": "[t0, t1] in seconds to zoom the modulated-wave window"},
                "config": {"type": "string", "description": "Alternative config.json"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "systemview_inspect",
        "description": ("Read-only: list live SystemView windows, and if a .svu is "
                        "given, return its token map (what each token is, where it "
                        "is, how it is wired). Never clicks, never runs."),
        "inputSchema": {
            "type": "object",
            "properties": {"file": {"type": "string"}},
        },
    },
    {
        "name": "systemview_screenshot",
        "description": ("Capture one SystemView window to a PNG without running "
                        "anything. kind='design' picks the design canvas instead of "
                        "the analysis window."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Window title fragment (default 'SystemView Analysis')"},
                "kind": {"type": "string", "enum": ["analysis", "design"]},
                "out": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
]

HANDLERS = {
    "systemview_run": tool_run,
    "systemview_inspect": tool_inspect,
    "systemview_screenshot": tool_screenshot,
}


# ---------------------------------------------------------------- protocol

def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        fn = HANDLERS.get(name)
        if not fn:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": "unknown tool: %s" % name}}
        try:
            content, ok = fn(args)
        except Exception as e:  # keep the server alive
            log("tool %s failed: %r" % (name, e))
            content, ok = [_text_block({"ok": False, "error": str(e)})], False
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"content": content, "isError": not ok}}
    if method in ("shutdown", "exit"):
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": "method not found: %s" % method}}


def main():
    log("%s %s ready (stdio)" % (SERVER_NAME, SERVER_VERSION))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            log("bad json: %r" % line[:200])
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
