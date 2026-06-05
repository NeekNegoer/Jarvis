"""
computer_use_server.py — an MCP server that gives Jarvis's brain hands and eyes.

This wraps computer.py and speaks the Model Context Protocol over stdio, so the
`claude` CLI brain can call tools like screenshot/click/type directly — and, crucially,
get screenshots back as inline images it can actually SEE.

It's a hand-written JSON-RPC 2.0 stdio server (one JSON message per line). We don't use
the official `mcp` Python SDK because that needs Python 3.10+ and this venv is 3.9.
Protocol refs: MCP stdio transport, methods initialize / tools/list / tools/call.

stdout is the protocol channel — ONLY JSON-RPC goes there. All logging goes to stderr.
"""

from __future__ import annotations

import base64
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import computer

MEMORY_FILE = Path(__file__).parent / "memory" / "about_you.md"

SERVER_NAME = "computer"
SERVER_VERSION = "1.0.0"


def log(*a):
    print("[computer-mcp]", *a, file=sys.stderr, flush=True)


# --- Tool definitions -------------------------------------------------------------
# Each: name -> (description, json-schema properties, required, handler)
def _num(desc):
    return {"type": "number", "description": desc}


TOOLS = {
    "screenshot": {
        "description": "Take a screenshot of the screen and return it as an image so you "
                       "can see the current state. Pixel coordinates in this image are "
                       "logical points: a pixel at (x,y) is exactly where click(x,y) clicks. "
                       "Take a screenshot before acting so you know what's on screen.",
        "schema": {"type": "object", "properties": {}},
        "handler": lambda a: _screenshot_result(),
    },
    "screen_info": {
        "description": "Get the screen size in logical points and the retina scale factor.",
        "schema": {"type": "object", "properties": {}},
        "handler": lambda a: _text(computer.screen_info()),
    },
    "click": {
        "description": "Left-click at logical point (x, y).",
        "schema": {"type": "object", "properties": {"x": _num("x"), "y": _num("y")},
                   "required": ["x", "y"]},
        "handler": lambda a: _ok(computer.click(a["x"], a["y"]), f"clicked ({a['x']},{a['y']})"),
    },
    "double_click": {
        "description": "Double-click at logical point (x, y).",
        "schema": {"type": "object", "properties": {"x": _num("x"), "y": _num("y")},
                   "required": ["x", "y"]},
        "handler": lambda a: _ok(computer.double_click(a["x"], a["y"]), "double-clicked"),
    },
    "right_click": {
        "description": "Right-click (context menu) at logical point (x, y).",
        "schema": {"type": "object", "properties": {"x": _num("x"), "y": _num("y")},
                   "required": ["x", "y"]},
        "handler": lambda a: _ok(computer.right_click(a["x"], a["y"]), "right-clicked"),
    },
    "move_mouse": {
        "description": "Move the mouse to logical point (x, y) without clicking.",
        "schema": {"type": "object", "properties": {"x": _num("x"), "y": _num("y")},
                   "required": ["x", "y"]},
        "handler": lambda a: _ok(computer.move_mouse(a["x"], a["y"]), "moved"),
    },
    "scroll": {
        "description": "Scroll the wheel by dx, dy lines. Positive dy scrolls up.",
        "schema": {"type": "object",
                   "properties": {"dx": _num("horizontal lines"), "dy": _num("vertical lines")}},
        "handler": lambda a: _ok(computer.scroll(int(a.get("dx", 0)), int(a.get("dy", 0))), "scrolled"),
    },
    "type_text": {
        "description": "Type Unicode text into the currently focused field.",
        "schema": {"type": "object", "properties": {"text": {"type": "string"}},
                   "required": ["text"]},
        "handler": lambda a: _ok(computer.type_text(a["text"]), "typed"),
    },
    "key": {
        "description": "Press a key or key-combo, e.g. 'return', 'cmd+c', 'cmd+shift+t', 'esc'.",
        "schema": {"type": "object", "properties": {"combo": {"type": "string"}},
                   "required": ["combo"]},
        "handler": lambda a: _ok(computer.key(a["combo"]), f"pressed {a['combo']}"),
    },
    "list_ui_elements": {
        "description": "List the clickable UI elements (buttons, fields, links, menu items) "
                       "of the frontmost app, with their names and logical-point centers. Use "
                       "this to find something to click reliably instead of guessing pixels.",
        "schema": {"type": "object", "properties": {}},
        "handler": lambda a: _text(computer.list_ui_elements()),
    },
    "click_element": {
        "description": "Find a UI element of the frontmost app whose name contains the given "
                       "text and click its center. The reliable way to click a named button.",
        "schema": {"type": "object", "properties": {"name": {"type": "string"},
                   "exact": {"type": "boolean"}}, "required": ["name"]},
        "handler": lambda a: _text(computer.click_element(a["name"], a.get("exact", False))),
    },
    "frontmost_app": {
        "description": "Get the name and pid of the frontmost (active) application.",
        "schema": {"type": "object", "properties": {}},
        "handler": lambda a: _text(computer.frontmost_app()),
    },
    "open_app": {
        "description": "Open (or switch to) an application by name, e.g. 'Safari', 'Mail'.",
        "schema": {"type": "object", "properties": {"name": {"type": "string"}},
                   "required": ["name"]},
        "handler": lambda a: _text(computer.open_app(a["name"])),
    },
    "run_applescript": {
        "description": "Run an AppleScript and return its output. The most reliable way to "
                       "control scriptable apps (Mail, Calendar, Notes, Safari, Finder, Music...). "
                       "Prefer this over clicking when the app is scriptable. If the script is "
                       "destructive (deletes files, empties trash, sends mail/messages, shuts "
                       "down), it will be BLOCKED until you pass confirm=true — first ask Pietro "
                       "out loud to confirm, then call again with confirm true.",
        "schema": {"type": "object", "properties": {
            "script": {"type": "string"},
            "confirm": {"type": "boolean", "description": "set true only after Pietro confirms"}},
            "required": ["script"]},
        "handler": lambda a: _text(_guarded_applescript(a["script"], a.get("confirm", False))),
    },
    "remember": {
        "description": "Save a durable fact or preference about Pietro to long-term memory so "
                       "you recall it in future sessions. Use for stable, reusable info (how he "
                       "likes things, who he is, recurring context) — NOT secrets or one-offs.",
        "schema": {"type": "object", "properties": {"fact": {"type": "string"}},
                   "required": ["fact"]},
        "handler": lambda a: _text(_remember(a["fact"])),
    },
}


import re

# Deterministic safety net: these patterns are irreversible/high-impact. We block them at the
# tool boundary unless confirm=true, so safety doesn't depend on the model "remembering" to ask.
# Patterns match the LOWERCASED script with re.DOTALL, so `.*` spans the multi-line AppleScripts
# these operations are normally written as (an earlier version missed multi-line send/delete).
_DESTRUCTIVE = [
    (r"\brm\s+(-|/|~|\$|\.|\w|\*)", "a shell delete command"),  # rm with any path-ish arg
    (r"\bsudo\b", "a sudo command"),
    (r"empty\s+the?\s*trash|empty trash", "emptying the Trash"),
    # "delete" inside a scriptable app (mail/finder/notes/calendar/photos/music/reminders…)
    (r'tell application "(mail|finder|messages|notes|calendar|photos|music|reminders)".*\bdelete\b',
     "deleting items"),
    (r"\bdelete\b.*\b(file|folder|item|message|mailbox|event|note|every|disk)", "deleting items"),
    # power commands — require the verb to actually refer to the machine (bare "sleep 2" is fine)
    (r"\b(shut\s*down|restart)\b.*\b(computer|system|mac|os)\b", "a power command"),
    (r'tell application "(system events|finder)" to (shut down|restart|sleep)', "a power command"),
    # sending mail/messages — key off the app tell OR a send+target combo
    (r'tell application "(mail|messages)".*\bsend\b', "sending a message/email"),
    (r"\bsend\b.*\b(message|mail|email|imessage|to recipient)\b", "sending a message/email"),
]


def _guarded_applescript(script: str, confirm: bool) -> dict:
    if not confirm:
        low = script.lower()
        for pat, why in _DESTRUCTIVE:
            if re.search(pat, low, re.S):  # re.S so `.*` crosses newlines
                return {"blocked": True, "reason": why,
                        "message": ("This is destructive (" + why + "). Ask Pietro to confirm "
                                    "out loud, then call run_applescript again with confirm=true.")}
    return computer.run_applescript(script)


def _remember(fact: str) -> dict:
    fact = (fact or "").strip()
    if not fact:
        return {"saved": False, "reason": "empty fact"}
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"- {fact}  _(learned {stamp})_\n")
    return {"saved": True, "fact": fact}


# --- Result helpers ---------------------------------------------------------------
def _text(obj):
    return [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}]


def _ok(_ret, msg):
    return [{"type": "text", "text": json.dumps({"ok": True, "did": msg})}]


def _screenshot_result():
    info = computer.screenshot()
    if "error" in info:
        return [{"type": "text", "text": json.dumps(info, ensure_ascii=False)}]
    with open(info["path"], "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return [
        {"type": "text", "text": json.dumps(
            {"width": info["width"], "height": info["height"],
             "note": "pixel (x,y) here == click(x,y)"})},
        {"type": "image", "data": b64, "mimeType": "image/png"},
    ]


# --- JSON-RPC plumbing ------------------------------------------------------------
def _tools_list():
    return [{"name": n, "description": t["description"], "inputSchema": t["schema"]}
            for n, t in TOOLS.items()]


def handle(req: dict):
    """Return a response dict, or None for notifications (no reply)."""
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        proto = (req.get("params") or {}).get("protocolVersion", "2024-11-05")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }}

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": _tools_list()}}

    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if not tool:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        try:
            content = tool["handler"](args)
            return {"jsonrpc": "2.0", "id": rid, "result": {"content": content, "isError": False}}
        except Exception as e:
            log("tool error:", traceback.format_exc())
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": f"Error running {name}: {e}"}],
                "isError": True}}

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return None


def main():
    log(f"starting (accessibility={computer.has_accessibility()}, "
        f"screen_recording={computer.has_screen_recording()})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            log("bad json:", line[:120])
            continue
        try:
            resp = handle(req)
        except Exception:
            log("handler crashed:", traceback.format_exc())
            resp = {"jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32603, "message": "internal error"}}
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
