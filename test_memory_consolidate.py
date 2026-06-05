"""
test_memory_consolidate.py — unit tests for the pure pieces of session-end memory
consolidation: parsing the brain's reply, dedupe against existing memory, and the
end-to-end consolidate() flow driven by a FAKE thinker (no network, no `claude` CLI).

Run:  python -m pytest test_memory_consolidate.py -q
  or: python test_memory_consolidate.py
"""

from __future__ import annotations

import memory_consolidate as mc


# --------------------------------------------------------------------------- parse
def test_parse_plain_array():
    assert mc.parse_facts('["Likes coffee.", "Runs a small business."]') == [
        "Likes coffee.", "Runs a small business."]


def test_parse_fenced_json():
    raw = '```json\n["Is learning guitar."]\n```'
    assert mc.parse_facts(raw) == ["Is learning guitar."]


def test_parse_array_buried_in_prose():
    raw = 'Here are the facts:\n["Wakes up early.", "Lives in Brazil."]\nThat is all.'
    assert mc.parse_facts(raw) == ["Wakes up early.", "Lives in Brazil."]


def test_parse_object_with_facts_key():
    assert mc.parse_facts('{"facts": ["Prefers dark mode."]}') == ["Prefers dark mode."]


def test_parse_list_of_objects():
    assert mc.parse_facts('[{"fact": "Has a dog named Rex."}]') == ["Has a dog named Rex."]


def test_parse_empty_and_garbage():
    assert mc.parse_facts("[]") == []
    assert mc.parse_facts("") == []
    assert mc.parse_facts(None) == []
    assert mc.parse_facts("totally not json") == []


def test_parse_clamps_to_five():
    raw = ('["Plays the violin.", "Speaks French.", "Loves spicy food.", '
           '"Wakes before dawn.", "Collects vinyl records.", "Hikes on Sundays."]')
    assert len(mc.parse_facts(raw)) == 5


def test_parse_drops_secrets_and_pii():
    raw = ('["Her password is hunter2.", "Email is pietro.ams18@gmail.com.", '
           '"Phone is +55 11 99999-8888.", "CPF is 123.456.789-09.", '
           '"Enjoys long-distance running."]')
    assert mc.parse_facts(raw) == ["Enjoys long-distance running."]


def test_parse_drops_overlong():
    long_fact = "x" * (mc.MAX_FACT_LEN + 1)
    assert mc.parse_facts(f'["{long_fact}", "Short fact here."]') == ["Short fact here."]


def test_parse_dedupes_within_reply():
    raw = '["Is learning to play guitar.", "She is learning the guitar."]'
    assert mc.parse_facts(raw) == ["Is learning to play guitar."]


# -------------------------------------------------------------------------- dedupe
EXISTING = """# What Jarvis knows about you

(a parenthetical note that should be ignored)

- Name: Pietro
- Location: Brazil
- Goal: building my own AI assistant ("Jarvis") and growing it over time
- Prefers temperatures in Celsius.  _(learned 2026-06-01)_
"""


def test_is_duplicate_exact():
    lines = mc._memory_lines(EXISTING)
    assert mc.is_duplicate("Location: Brazil", lines) is True


def test_is_duplicate_rephrased_keyword_overlap():
    lines = mc._memory_lines(EXISTING)
    # Same meaning, different words / accents / stamp irrelevant.
    assert mc.is_duplicate("She prefers temperatures shown in celsius", lines) is True


def test_is_duplicate_substring():
    lines = mc._memory_lines(EXISTING)
    assert mc.is_duplicate("Brazil", lines) is True


def test_not_duplicate_new_fact():
    lines = mc._memory_lines(EXISTING)
    assert mc.is_duplicate("Enjoys playing tennis on weekends.", lines) is False


def test_dedupe_filters_known_keeps_new():
    candidates = [
        "Lives in Brazil.",                 # known (Location: Brazil)
        "Prefers temperatures in Celsius.",  # known verbatim
        "Is building an AI assistant called Jarvis.",  # known (Goal ...)
        "Enjoys playing tennis on weekends.",          # NEW
        "Tennis is her favorite weekend sport.",       # dup of the new one
    ]
    assert mc.dedupe(candidates, EXISTING) == ["Enjoys playing tennis on weekends."]


def test_memory_lines_skips_headers_and_notes():
    lines = mc._memory_lines(EXISTING)
    assert all(not l.startswith("#") and not l.startswith("(") for l in lines)


# ----------------------------------------------------------------- transcript shapes
def test_worth_consolidating_skips_trivial():
    assert mc._worth_consolidating([("you", "en", "hi")]) is False
    assert mc._worth_consolidating([("you", "en", "what time is it")]) is False


def test_worth_consolidating_accepts_real_chat():
    turns = [("you", "en", "I just started learning the guitar this week."),
             ("jarvis", "en", "Nice! That's a great hobby."),
             ("you", "en", "Yeah, I practice every evening after work.")]
    assert mc._worth_consolidating(turns) is True


def test_format_transcript_labels_speakers():
    turns = [("you", "pt", "Bom dia"), ("jarvis", "pt", "Bom dia, Pietro!")]
    text = mc._format_transcript(turns)
    assert "Pietro: Bom dia" in text
    assert "Jarvis: Bom dia, Pietro!" in text


def test_iter_turns_parses_log_string():
    log = ("09:00:01 [pt] you: tenho um cachorro chamado Rex\n"
           "09:00:03 [pt] jarvis: Que legal!\n")
    roles = [r for r, _ in mc._iter_turns(log)]
    assert roles == ["you", "jarvis"]


# --------------------------------------------------------- end-to-end with fake brain
def test_consolidate_end_to_end(tmp_path):
    mem = tmp_path / "about_you.md"
    mem.write_text(EXISTING, encoding="utf-8")

    turns = [("you", "en", "I just adopted a dog named Rex and I love long runs."),
             ("jarvis", "en", "Congratulations on Rex!"),
             ("you", "en", "I live in Brazil, by the way.")]

    # Fake thinker returns one new fact + one already-known fact.
    fake = lambda prompt: '["Has a dog named Rex.", "Lives in Brazil."]'

    saved = mc.consolidate(turns, think=fake, memory_file=mem, today="2026-06-05")
    assert saved == ["Has a dog named Rex."]  # "Lives in Brazil" deduped out

    contents = mem.read_text(encoding="utf-8")
    assert "- Has a dog named Rex.  _(learned 2026-06-05)_" in contents


def test_consolidate_skips_trivial_without_calling_brain(tmp_path):
    mem = tmp_path / "about_you.md"
    mem.write_text(EXISTING, encoding="utf-8")
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return "[]"

    saved = mc.consolidate([("you", "en", "hi")], think=fake, memory_file=mem)
    assert saved == []
    assert calls == []  # fast path: brain never invoked on a trivial session


def test_consolidate_never_raises(tmp_path):
    mem = tmp_path / "about_you.md"
    mem.write_text(EXISTING, encoding="utf-8")

    def boom(prompt):
        raise RuntimeError("brain exploded")

    turns = [("you", "en", "I am learning to paint with watercolors lately."),
             ("you", "en", "It is my new hobby this year.")]
    assert mc.consolidate(turns, think=boom, memory_file=mem) == []


if __name__ == "__main__":
    import sys
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                import tempfile
                with tempfile.TemporaryDirectory() as d:
                    from pathlib import Path
                    fn(Path(d))
            else:
                fn()
            print(f"ok   {name}")
        except Exception:
            failures += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{'-' * 40}\n{'ALL PASSED' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
