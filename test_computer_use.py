"""
test_computer_use.py — prove Jarvis can really control your Mac.  python test_computer_use.py

Run this AFTER you've granted Accessibility + Screen Recording (see doctor.py). It does a
safe, self-cleaning demo in a throwaway TextEdit document: opens TextEdit, types a sentence,
reads it back through the Accessibility API, exercises key combos and a screenshot, then
closes the document WITHOUT saving. Each capability prints ✅ or ❌ so you know exactly what
works. It never touches your files.
"""

from __future__ import annotations

import time

import computer

SENTENCE = "Jarvis controla este Mac. Jarvis controls this Mac."


def _pause(s=0.8):
    time.sleep(s)


def main():
    print("🧪 Computer-control test (safe TextEdit scratch doc)\n")

    if not computer.has_accessibility():
        print("❌ Accessibility isn't granted yet — run `python doctor.py` first.")
        return 1
    if not computer.has_screen_recording():
        print("⚠️  Screen Recording isn't granted; the screenshot step will be skipped.")

    results = {}

    # 1) Open TextEdit with a fresh document
    print("→ opening TextEdit…")
    computer.run_applescript('tell application "TextEdit" to activate')
    _pause(1.0)
    computer.run_applescript('tell application "TextEdit" to make new document')
    _pause(0.8)
    computer.run_applescript('tell application "TextEdit" to activate')
    _pause(0.6)

    # 2) Type a sentence
    print("→ typing a sentence…")
    computer.type_text(SENTENCE)
    _pause(0.6)
    results["type_text"] = True

    # 3) Read it back via AppleScript (proves the text really landed)
    print("→ reading the document back…")
    r = computer.run_applescript('tell application "TextEdit" to get text of front document')
    got = (r.get("stdout") or "").strip()
    results["readback"] = SENTENCE.split(".")[0] in got
    print(f"   document says: {got!r}")

    # 4) Key combos: select all, then deselect with arrow
    print("→ exercising key combos (cmd+a, right arrow)…")
    try:
        computer.key("cmd+a"); _pause(0.3)
        computer.key("right"); _pause(0.2)
        results["key"] = True
    except Exception as e:
        results["key"] = False
        print("   key error:", e)

    # 5) Screenshot + AX element listing
    if computer.has_screen_recording():
        shot = computer.screenshot()
        results["screenshot"] = "error" not in shot
        print(f"   screenshot: {shot.get('width')}x{shot.get('height')}")
    els = computer.list_ui_elements()
    results["accessibility_tree"] = not els.get("error") and "elements" in els
    print(f"   accessibility elements found: {len(els.get('elements', []))} in {els.get('app')}")

    # 6) Clean up: close WITHOUT saving
    print("→ closing the scratch document without saving…")
    computer.run_applescript(
        'tell application "TextEdit" to close front document saving no')
    _pause(0.5)

    # Report
    print("\n" + "=" * 40)
    labels = {
        "type_text": "Type text",
        "readback": "Text actually landed (AppleScript readback)",
        "key": "Key combos (cmd+a, arrows)",
        "screenshot": "Screenshot",
        "accessibility_tree": "Read UI elements (Accessibility)",
    }
    ok = True
    for k, label in labels.items():
        if k in results:
            mark = "✅" if results[k] else "❌"
            ok = ok and results[k]
            print(f"  {mark} {label}")
    print("=" * 40)
    if ok:
        print("🎉 Jarvis can fully control your Mac. Try: python jarvis.py")
        return 0
    print("Some capabilities failed — check the ❌ items and re-run doctor.py.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
