"""
computer.py — Jarvis's hands and eyes for the WHOLE Mac.

System-wide computer use: take screenshots, move/click the mouse, type, press key
combos, scroll, open apps, read the on-screen UI elements of the frontmost app
(via the macOS Accessibility API), click a button/field by its name, and run
AppleScript. Works in any app — it's built on the system, not on any one program.

Design notes (from research, see RESEARCH.md):
  • Screenshots come from `screencapture` (Apple-maintained, reliable on macOS 26).
    They're captured at physical retina pixels, then downscaled to LOGICAL points so
    that a pixel you see in the screenshot maps 1:1 to a click coordinate — no retina
    math needed by the caller.
  • Mouse/keyboard use Quartz CGEvents in logical points.
  • The reliable way to "find a button and click it" is the Accessibility tree
    (real element titles + logical-point centers), not guessing pixels. Prefer
    list_ui_elements + click_element over vision when possible. AppleScript is even
    better for scriptable apps (Mail, Calendar, Notes, Safari...).

Two ways to use it:
  • As a library:  from computer import screenshot, click, ...
  • As a CLI (so Claude can drive it via its Bash tool):
        python computer.py screenshot
        python computer.py click 480 300
        python computer.py type "hello world"
        python computer.py key cmd+c
        python computer.py elements
        python computer.py click_text "Send"
        python computer.py open "Safari"
        python computer.py applescript 'tell application "Finder" to activate'
        python computer.py permissions
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import Quartz
from AppKit import NSWorkspace
import ApplicationServices as AS

LAST_SHOT = Path(tempfile.gettempdir()) / "jarvis_screen.png"

# ---------------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------------

def has_screen_recording() -> bool:
    try:
        return bool(Quartz.CGPreflightScreenCaptureAccess())
    except Exception:
        return False


def has_accessibility() -> bool:
    try:
        return bool(AS.AXIsProcessTrusted())
    except Exception:
        return False


def request_permissions() -> None:
    """Trigger the system permission prompts (user still toggles them in Settings)."""
    try:
        Quartz.CGRequestScreenCaptureAccess()
    except Exception:
        pass
    try:
        AS.AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True})
    except Exception:
        pass


# ---------------------------------------------------------------------------------
# Screen geometry
# ---------------------------------------------------------------------------------

def _main_scale() -> float:
    did = Quartz.CGMainDisplayID()
    mode = Quartz.CGDisplayCopyDisplayMode(did)
    w_px = Quartz.CGDisplayModeGetPixelWidth(mode)
    w_pt = Quartz.CGDisplayModeGetWidth(mode)
    return (w_px / w_pt) if w_pt else 1.0


def screen_info() -> dict:
    did = Quartz.CGMainDisplayID()
    bounds = Quartz.CGDisplayBounds(did)
    scale = _main_scale()
    return {
        "logical_width": int(bounds.size.width),
        "logical_height": int(bounds.size.height),
        "scale": scale,
        "note": "click/move coordinates are in logical points; (0,0) is top-left.",
    }


# ---------------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------------

def screenshot(path: str | None = None, to_logical: bool = True) -> dict:
    """Capture the screen to a PNG. Returns {path, width, height, scale}.

    By default the PNG is downscaled to logical points, so pixel (x,y) in the file
    is exactly where you'd click(x, y).
    """
    out = Path(path) if path else LAST_SHOT
    # -D 1 = capture only the MAIN display, so a pixel in the image maps to the same
    # logical-point space screen_info reports (avoids multi-monitor coordinate mismatch).
    proc = subprocess.run(["/usr/sbin/screencapture", "-x", "-D", "1", "-t", "png", str(out)],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        hint = ("Screen Recording permission is not granted yet. Grant it in System "
                "Settings > Privacy & Security > Screen & System Audio Recording, "
                "then fully quit and reopen the app you launched Jarvis from."
                if not has_screen_recording() else proc.stderr.strip())
        return {"error": hint, "screen_recording_granted": has_screen_recording()}

    scale = _main_scale()
    from PIL import Image
    img = Image.open(out)
    img.load()
    phys_w, phys_h = img.size
    if to_logical and scale and scale != 1.0:
        log_w, log_h = int(phys_w / scale), int(phys_h / scale)
        img = img.resize((log_w, log_h), Image.LANCZOS)
        img.save(out)
    else:
        log_w, log_h = phys_w, phys_h
    return {"path": str(out), "width": log_w, "height": log_h, "scale": scale}


# ---------------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------------

def _post(ev) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)


def move_mouse(x: float, y: float) -> None:
    _post(Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, (x, y), 0))


def _mouse_click(x: float, y: float, button: int, down_ev: int, up_ev: int, count: int = 1) -> None:
    move_mouse(x, y)
    time.sleep(0.02)
    for i in range(count):
        ev_down = Quartz.CGEventCreateMouseEvent(None, down_ev, (x, y), button)
        ev_up = Quartz.CGEventCreateMouseEvent(None, up_ev, (x, y), button)
        if count > 1:
            Quartz.CGEventSetIntegerValueField(ev_down, Quartz.kCGMouseEventClickState, i + 1)
            Quartz.CGEventSetIntegerValueField(ev_up, Quartz.kCGMouseEventClickState, i + 1)
        _post(ev_down)
        _post(ev_up)


def click(x: float, y: float) -> None:
    _mouse_click(x, y, Quartz.kCGMouseButtonLeft,
                 Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp)


def double_click(x: float, y: float) -> None:
    _mouse_click(x, y, Quartz.kCGMouseButtonLeft,
                 Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp, count=2)


def right_click(x: float, y: float) -> None:
    _mouse_click(x, y, Quartz.kCGMouseButtonRight,
                 Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp)


def scroll(dx: int = 0, dy: int = 0) -> None:
    # dy>0 scrolls up, dy<0 scrolls down (line units)
    ev = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, int(dy), int(dx))
    _post(ev)


# ---------------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------------

# US ANSI virtual keycodes for named keys and letters/digits.
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
    "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "`": 50,
    "return": 36, "enter": 36, "tab": 48, "space": 49, "delete": 51, "backspace": 51,
    "escape": 53, "esc": 53, "forwarddelete": 117, "home": 115, "end": 119,
    "pageup": 116, "pagedown": 121, "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

_MODFLAGS = {
    "cmd": Quartz.kCGEventFlagMaskCommand, "command": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "alt": Quartz.kCGEventFlagMaskAlternate, "option": Quartz.kCGEventFlagMaskAlternate,
    "ctrl": Quartz.kCGEventFlagMaskControl, "control": Quartz.kCGEventFlagMaskControl,
    "fn": Quartz.kCGEventFlagMaskSecondaryFn,
}


def key(combo: str) -> None:
    """Press a key or combo, e.g. 'return', 'cmd+c', 'cmd+shift+t', 'alt+left'."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    mods, base = parts[:-1], parts[-1]
    if base not in _KEYCODES:
        raise ValueError(f"Unknown key: {base!r}")
    flags = 0
    for m in mods:
        if m not in _MODFLAGS:
            raise ValueError(f"Unknown modifier: {m!r}")
        flags |= _MODFLAGS[m]
    code = _KEYCODES[base]
    down = Quartz.CGEventCreateKeyboardEvent(None, code, True)
    up = Quartz.CGEventCreateKeyboardEvent(None, code, False)
    if flags:
        Quartz.CGEventSetFlags(down, flags)
        Quartz.CGEventSetFlags(up, flags)
    _post(down)
    _post(up)


def type_text(text: str) -> None:
    """Type Unicode text into the focused field (layout-independent)."""
    for ch in text:
        for is_down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, is_down)
            Quartz.CGEventKeyboardSetUnicodeString(ev, len(ch), ch)
            _post(ev)
        time.sleep(0.004)


# ---------------------------------------------------------------------------------
# Apps + AppleScript
# ---------------------------------------------------------------------------------

def frontmost_app() -> dict:
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    if app is None:
        return {"name": None, "pid": None}
    return {"name": app.localizedName(), "pid": app.processIdentifier()}


def open_app(name: str) -> dict:
    subprocess.run(["open", "-a", name], check=True)
    time.sleep(0.6)
    return {"opened": name}


def run_applescript(script: str) -> dict:
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return {"ok": proc.returncode == 0,
            "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


# ---------------------------------------------------------------------------------
# Accessibility tree (find UI elements by name)
# ---------------------------------------------------------------------------------

def _c(*names):
    for n in names:
        if hasattr(AS, n):
            return getattr(AS, n)
    return None


_ROLE = _c("kAXRoleAttribute")
_TITLE = _c("kAXTitleAttribute")
_DESC = _c("kAXDescriptionAttribute")
_RDESC = _c("kAXRoleDescriptionAttribute")
_VALUE = _c("kAXValueAttribute")
_CHILD = _c("kAXChildrenAttribute")
_POS = _c("kAXPositionAttribute")
_SIZE = _c("kAXSizeAttribute")
_T_PT = _c("kAXValueTypeCGPoint", "kAXValueCGPointType")
_T_SZ = _c("kAXValueTypeCGSize", "kAXValueCGSizeType")
_AX_OK = getattr(AS, "kAXErrorSuccess", 0)  # success code is 0; tolerate a missing constant

_CLICKABLE = {"AXButton", "AXMenuButton", "AXPopUpButton", "AXLink", "AXCheckBox",
              "AXRadioButton", "AXMenuItem", "AXTextField", "AXTextArea", "AXTabButton",
              "AXSearchField", "AXComboBox", "AXDisclosureTriangle", "AXSlider"}


def _attr(el, a):
    if a is None:
        return None
    try:
        err, val = AS.AXUIElementCopyAttributeValue(el, a, None)
    except Exception:
        return None
    return val if err == _AX_OK else None


def _point(el):
    v = _attr(el, _POS)
    if v is None:
        return None
    try:
        ok, pt = AS.AXValueGetValue(v, _T_PT, None)
        return (pt.x, pt.y) if ok else None
    except Exception:
        return None


def _size(el):
    v = _attr(el, _SIZE)
    if v is None:
        return None
    try:
        ok, sz = AS.AXValueGetValue(v, _T_SZ, None)
        return (sz.width, sz.height) if ok else None
    except Exception:
        return None


def _label(el):
    for a in (_TITLE, _DESC, _VALUE, _RDESC):
        v = _attr(el, a)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _walk(el, out, depth=0, maxdepth=60):
    if el is None or depth > maxdepth or len(out) > 400:
        return
    role = _attr(el, _ROLE)
    if role in _CLICKABLE:
        pos, sz = _point(el), _size(el)
        if pos and sz and sz[0] > 0 and sz[1] > 0:
            out.append({
                "role": role,
                "name": _label(el),
                "center": [round(pos[0] + sz[0] / 2.0, 1), round(pos[1] + sz[1] / 2.0, 1)],
            })
    for kid in (_attr(el, _CHILD) or []):
        _walk(kid, out, depth + 1, maxdepth)


def list_ui_elements() -> dict:
    """List clickable UI elements of the frontmost app with logical-point centers."""
    if not has_accessibility():
        return {"error": "Accessibility permission not granted. See doctor.py.",
                "elements": []}
    app_info = frontmost_app()
    pid = app_info.get("pid")
    if not pid:
        return {"app": None, "elements": []}
    app_el = AS.AXUIElementCreateApplication(pid)
    out: list = []
    _walk(app_el, out)
    return {"app": app_info.get("name"), "count": len(out), "elements": out}


def click_element(name: str, exact: bool = False) -> dict:
    """Find a UI element whose name matches and click its center."""
    info = list_ui_elements()
    if info.get("error"):
        return info
    target = None
    for e in info["elements"]:
        n = e.get("name") or ""
        if (n == name) if exact else (name.lower() in n.lower()):
            target = e
            break
    if not target:
        return {"clicked": False, "reason": f"No element matching {name!r}.",
                "available": [e.get("name") for e in info["elements"] if e.get("name")][:40]}
    cx, cy = target["center"]
    click(cx, cy)
    return {"clicked": True, "element": target}


# ---------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------

def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def main(argv: list[str]) -> int:
    if not argv:
        _print({"error": "no command", "commands": [
            "screenshot", "screen_info", "move X Y", "click X Y", "double_click X Y",
            "right_click X Y", "scroll DX DY", "type TEXT", "key COMBO", "elements",
            "click_text NAME", "frontmost", "open APP", "applescript SCRIPT",
            "permissions", "request_permissions"]})
        return 1
    cmd, args = argv[0], argv[1:]
    try:
        if cmd == "screenshot":
            _print(screenshot())
        elif cmd == "screen_info":
            _print(screen_info())
        elif cmd == "move":
            move_mouse(float(args[0]), float(args[1])); _print({"ok": True})
        elif cmd == "click":
            click(float(args[0]), float(args[1])); _print({"ok": True})
        elif cmd == "double_click":
            double_click(float(args[0]), float(args[1])); _print({"ok": True})
        elif cmd == "right_click":
            right_click(float(args[0]), float(args[1])); _print({"ok": True})
        elif cmd == "scroll":
            scroll(int(args[0]), int(args[1])); _print({"ok": True})
        elif cmd == "type":
            type_text(" ".join(args)); _print({"ok": True})
        elif cmd == "key":
            key(args[0]); _print({"ok": True})
        elif cmd == "elements":
            _print(list_ui_elements())
        elif cmd == "click_text":
            _print(click_element(" ".join(args)))
        elif cmd == "frontmost":
            _print(frontmost_app())
        elif cmd == "open":
            _print(open_app(" ".join(args)))
        elif cmd == "applescript":
            _print(run_applescript(" ".join(args)))
        elif cmd == "permissions":
            _print({"accessibility": has_accessibility(),
                    "screen_recording": has_screen_recording()})
        elif cmd == "request_permissions":
            request_permissions(); _print({"requested": True})
        else:
            _print({"error": f"unknown command {cmd!r}"}); return 1
    except Exception as e:
        _print({"error": str(e), "type": type(e).__name__}); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
