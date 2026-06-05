"""
memory_consolidate.py — session-end memory consolidation for Jarvis.

When a session ends (Pietro says goodbye, or presses Ctrl+C), Jarvis reflects on the
whole conversation ONCE and saves a few durable facts about Pietro to
memory/about_you.md, so it grows smarter over time.

Design (research-backed):
- Quality is decided at WRITE time: the model is asked for 0-5 *durable* facts only.
- Store concise, self-contained facts — never secrets / PII / one-off requests.
- Dedupe against what's already in about_you.md (normalized substring + keyword overlap).
- Append with a date stamp, in the SAME format the `remember` tool already uses, so the
  memory file stays consistent: ``- <fact>  _(learned YYYY-MM-DD)_``.

The brain (brain.py) has NO python-side history list (it shells out to the `claude`
CLI and resumes by session_id). So the transcript is taken, in order of preference:
  1. an in-memory buffer passed in by jarvis.py (a list of (role, lang, text) turns) —
     this is exactly the current session and needs no log parsing;
  2. a raw transcript string, or any object exposing a non-empty ``.history`` list;
  3. as a fallback, today's logs/conversation-YYYY-MM-DD.log that jarvis.py writes.

Everything here is best-effort and SILENT on failure: consolidate() never raises, so it
can be called on shutdown without risk. The pure helpers (parse_facts, dedupe,
is_duplicate) take no I/O and are unit-tested in test_memory_consolidate.py.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
MEMORY_FILE = HERE / "memory" / "about_you.md"
LOG_DIR = HERE / "logs"

# How much conversation is worth reflecting on. Tiny "what time is it?" sessions are
# skipped entirely (no brain call) so shutdown stays fast.
MIN_USER_TURNS = 2
MIN_USER_CHARS = 40
MAX_FACTS = 5
MAX_FACT_LEN = 200

# Roles, across the buffer/log/history shapes, that mean "Pietro said this".
_USER_ROLES = {"you", "user", "pietro"}
_ASSISTANT_ROLES = {"jarvis", "assistant", "bot"}


# ----------------------------------------------------------------------------------
# Extraction prompt — the exact instruction sent to the brain.
# ----------------------------------------------------------------------------------
EXTRACTION_SYSTEM = (
    "You are the memory-extraction component of a personal assistant named Jarvis. "
    "Your ONLY job is to read a conversation transcript between Jarvis and its user, "
    "Pietro, and decide which NEW, durable facts about Pietro are worth saving to "
    "long-term memory. You output ONLY machine-readable JSON — never prose, never "
    "commentary, never markdown. You never speak."
)


def _build_prompt(transcript_text: str, existing_facts: str) -> str:
    """The precise user message sent to the brain for fact extraction."""
    existing = existing_facts.strip() or "(nothing saved yet)"
    return (
        "Read this conversation transcript and extract durable facts worth remembering "
        "about Pietro for future sessions.\n\n"
        "RULES:\n"
        "- Return ONLY a JSON array of strings. No prose, no markdown, no code fences. "
        'Example: ["fact one", "fact two"]\n'
        "- Return between 0 and 5 facts. Prefer fewer. If nothing is worth saving, "
        "return exactly [].\n"
        "- Save ONLY durable, reusable facts: stable preferences, who he is, ongoing "
        "projects/goals, how he likes things done, recurring people, places or tools "
        "he uses.\n"
        "- DO NOT save: one-off requests or tasks (\"open Safari\", \"what time is "
        "it\"), transient state, things true only today, small talk, or anything Jarvis "
        "said about itself.\n"
        "- DO NOT save secrets or sensitive PII: passwords, API keys, tokens, full card "
        "numbers, government IDs (CPF/CNPJ), home address, phone numbers, or exact "
        "financial figures.\n"
        "- Write each fact as ONE short, self-contained sentence in English, in the "
        'third person about Pietro (e.g. "Prefers temperatures in Celsius.", "Is '
        'learning to play the guitar.").\n'
        "- Do NOT repeat or merely rephrase anything already in CURRENT MEMORY below.\n\n"
        "CURRENT MEMORY (already known — do not repeat any of this):\n"
        f"{existing}\n\n"
        "TRANSCRIPT:\n"
        f"{transcript_text}\n\n"
        "JSON array:"
    )


# ----------------------------------------------------------------------------------
# Parsing the model's reply into a clean list of candidate facts (pure, testable).
# ----------------------------------------------------------------------------------
# Sensitive content we refuse to persist even if the model returns it (defense in depth).
_SECRET_PATTERNS = [
    # keyword secrets — but only the unambiguous ones bare; "pin"/"token" only when
    # they accompany an actual value (so "pin apps to the Dock" / "a token of thanks" survive).
    re.compile(r"(?i)\b(password|passwd|senha|api[\s_-]?key|secret\s*key|"
               r"access[\s_-]?token|cvv|otp)\b"),
    re.compile(r"(?i)\bpin\s*(?:code|number)?\s*(?:is|:)?\s*\d"),
    re.compile(r"(?i)\btoken\s*(?:is|:)\s*\S"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),           # CPF
    re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),     # CNPJ
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),                 # card-number-ish
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),            # email address
    re.compile(r"(?<!\d)\+?\d[\d ()\-]{8,}\d(?!\d)"),       # phone-number-ish
]


def _looks_like_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


def _try_json(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def parse_facts(raw, *, max_facts: int = MAX_FACTS, max_len: int = MAX_FACT_LEN) -> list:
    """Turn the brain's raw reply into a clean list of fact strings.

    Robust to: a bare JSON array, an array wrapped in ```json fences, an array buried
    in surrounding prose, an object like {"facts": [...]}, or list items that are
    objects ({"fact": "..."}). Drops empties, over-long items, and anything that looks
    like a secret/PII, and clamps to ``max_facts``.
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []

    # Strip a leading/trailing markdown code fence if present.
    text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    data = _try_json(text)
    if data is None:
        # Pull the first bracketed array out of surrounding prose.
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            data = _try_json(match.group(0))

    if isinstance(data, dict):
        for key in ("facts", "memories", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = None

    if not isinstance(data, list):
        return []

    out: list = []
    seen_norm: list = []
    for item in data:
        if isinstance(item, dict):
            item = item.get("fact") or item.get("text") or item.get("value") or ""
        fact = str(item).strip().strip('"').strip()
        if not fact or len(fact) > max_len:
            continue
        if _looks_like_secret(fact):
            continue
        # Drop near-identical repeats inside the same reply.
        if is_duplicate(fact, seen_norm):
            continue
        out.append(fact)
        seen_norm.append(fact)
        if len(out) >= max_facts:
            break
    return out


# ----------------------------------------------------------------------------------
# Dedupe against what's already saved (pure, testable).
# ----------------------------------------------------------------------------------
_STAMP_RE = re.compile(r"_\(\s*learned[^)]*\)_", re.IGNORECASE)

# Small bilingual stop-list so dedupe keys on the meaningful words of a fact, not glue.
# Includes common action verbs so two DISTINCT facts that merely share one verb
# ("Plays tennis" vs "Plays the guitar") aren't collapsed as duplicates.
_STOPWORDS = set(
    "the and or of to in on at for with is are was were be been being has have had "
    "do does did her she hers herself him his himself he pietro likes like prefers prefer "
    "enjoys enjoy wants want uses use using a an this that these those as by from their "
    "name named called about into out very really just also too when while "
    "live lives living lived play plays playing played work works working worked "
    "read reads reading run runs running study studies studying studied build builds "
    "building built make makes making go goes going watch watches watching "
    "o a os as um uma de da do das dos no na nos nas e ou para com que ela sua seu "
    "seus suas gosta gostar prefere usa usar tem ter esta este isso isto chamado "
    "chamada sobre".split()
)


def _stem(word: str) -> str:
    """Crude plural fold so 'weekends'/'weekend' and 'runs'/'run' compare equal."""
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Lowercase, accent-fold, drop the date stamp/bullet, and squash to bare words."""
    text = text or ""
    text = _STAMP_RE.sub(" ", text)
    text = text.lstrip("-*•").strip()
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(normalized: str) -> set:
    return {_stem(w) for w in normalized.split()
            if len(w) > 2 and w not in _STOPWORDS}


def is_duplicate(candidate: str, existing: list, *, overlap: float = 0.5) -> bool:
    """True if ``candidate`` says ~the same thing as any line in ``existing``.

    Heuristic: a duplicate if the normalized candidate is a substring of an existing
    line (or vice-versa), or if at least ``overlap`` of the candidate's significant
    words already appear together in some existing line.
    """
    cand_norm = _normalize(candidate)
    if not cand_norm:
        return True  # empty/degenerate → don't save
    cand_tokens = _tokens(cand_norm)
    for line in existing or []:
        ex_norm = _normalize(line)
        if not ex_norm:
            continue
        if cand_norm == ex_norm or cand_norm in ex_norm or ex_norm in cand_norm:
            return True
        ex_tokens = _tokens(ex_norm)
        if cand_tokens and ex_tokens:
            shared = len(cand_tokens & ex_tokens) / len(cand_tokens)
            if shared >= overlap:
                return True
    return False


def _memory_lines(memory_text: str) -> list:
    """The fact-bearing lines of about_you.md. Real facts are bullets ('- ...'); skip
    everything else (headers, and parenthetical notes that may wrap across lines)."""
    lines = []
    for raw in (memory_text or "").splitlines():
        line = raw.strip()
        if not line or line[:1] not in "-*•":
            continue
        lines.append(line)
    return lines


def dedupe(candidates: list, memory_text: str) -> list:
    """Keep only candidate facts not already represented in ``memory_text``."""
    existing = _memory_lines(memory_text)
    kept: list = []
    for cand in candidates:
        if is_duplicate(cand, existing):
            continue
        if is_duplicate(cand, kept):  # also guard against dup candidates
            continue
        kept.append(cand)
    return kept


# ----------------------------------------------------------------------------------
# Transcript handling (accepts buffer / string / .history / falls back to the log).
# ----------------------------------------------------------------------------------
_LOG_LINE_RE = re.compile(r"^\d{1,2}:\d{2}:\d{2}\s+\[[^\]]*\]\s+(\w+):\s*(.*)$")


def _iter_turns(transcript):
    """Yield (role_lower, text) from a buffer list, a log string, or history dicts."""
    if isinstance(transcript, str):
        for line in transcript.splitlines():
            m = _LOG_LINE_RE.match(line)
            if m:
                yield m.group(1).lower(), m.group(2)
            elif line.strip():
                yield "", line.strip()
        return
    for turn in transcript or []:
        if isinstance(turn, (list, tuple)):
            if len(turn) >= 3:       # (role, lang, text) — jarvis.py buffer shape
                yield str(turn[0]).lower(), str(turn[2])
            elif len(turn) == 2:     # (role, text)
                yield str(turn[0]).lower(), str(turn[1])
        elif isinstance(turn, dict):  # {"role": ..., "content"/"text": ...}
            role = str(turn.get("role", "")).lower()
            yield role, str(turn.get("content") or turn.get("text") or "")


def _format_transcript(transcript) -> str:
    out = []
    for role, text in _iter_turns(transcript):
        text = (text or "").strip()
        if not text:
            continue
        if role in _USER_ROLES:
            speaker = "Pietro"
        elif role in _ASSISTANT_ROLES:
            speaker = "Jarvis"
        else:
            speaker = (role or "?").capitalize()
        out.append(f"{speaker}: {text}")
    return "\n".join(out)


def _worth_consolidating(transcript) -> bool:
    turns = chars = 0
    for role, text in _iter_turns(transcript):
        if role in _USER_ROLES:
            t = (text or "").strip()
            if t:
                turns += 1
                chars += len(t)
    return turns >= MIN_USER_TURNS or chars >= MIN_USER_CHARS


def _read_log(log_dir: Path, today: str) -> str:
    path = Path(log_dir) / f"conversation-{today}.log"
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except Exception:
        return ""


def _resolve_transcript(src, log_dir: Path, today: str):
    if isinstance(src, (list, tuple)):
        return list(src)
    if isinstance(src, str) and src.strip():
        return src
    history = getattr(src, "history", None)  # e.g. a LocalBrain (Brain has none)
    if isinstance(history, list) and history:
        return history
    return _read_log(log_dir, today)  # fallback: today's conversation log


# ----------------------------------------------------------------------------------
# The LLM call (kept separate so consolidate() can be unit-tested with a fake thinker).
# ----------------------------------------------------------------------------------
def _default_thinker():
    """Build a one-shot extractor on top of brain.py, with a CLEAN system prompt and
    NO computer tools and NO --resume — so it never disturbs the live conversation."""
    try:
        from brain import Brain
        brain = Brain(enable_computer_use=False)
        brain.computer_use = False
        brain.session_id = None
        brain.persona = EXTRACTION_SYSTEM
        return lambda prompt: brain.think(prompt)
    except Exception:
        return None


def _append_facts(facts: list, memory_file: Path, stamp: str) -> None:
    if not facts:
        return
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    # One single write of the whole block → effectively atomic for this small append,
    # so a killed daemon thread can't leave a half-written line.
    block = "".join(f"- {fact}  _(learned {stamp})_\n" for fact in facts)
    with open(memory_file, "a", encoding="utf-8") as f:
        f.write(block)


def consolidate(brain_or_transcript=None, *, think=None,
                memory_file=None, log_dir=None, today=None) -> list:
    """Reflect on a finished session and append new durable facts to about_you.md.

    ``brain_or_transcript`` may be the in-memory turn buffer (list of (role, lang, text)
    tuples), a raw transcript string, an object with a ``.history`` list, a Brain (which
    has no history → falls back to today's log), or None (read today's log).

    Returns the list of facts actually saved (possibly empty). NEVER raises — safe to
    call on shutdown.
    """
    try:
        memory_path = Path(memory_file) if memory_file else MEMORY_FILE
        logs = Path(log_dir) if log_dir else LOG_DIR
        stamp = today or datetime.now().strftime("%Y-%m-%d")

        transcript = _resolve_transcript(brain_or_transcript, logs, stamp)
        if not _worth_consolidating(transcript):
            return []  # trivial session → skip the brain entirely (fast path)

        transcript_text = _format_transcript(transcript)
        if not transcript_text.strip():
            return []

        existing_text = ""
        if memory_path.exists():
            try:
                existing_text = memory_path.read_text(encoding="utf-8")
            except Exception:
                existing_text = ""
        existing_facts = "\n".join(_memory_lines(existing_text))

        thinker = think or _default_thinker()
        if thinker is None:
            return []

        raw = thinker(_build_prompt(transcript_text, existing_facts))
        candidates = parse_facts(raw)
        new_facts = dedupe(candidates, existing_text)
        _append_facts(new_facts, memory_path, stamp)
        return new_facts
    except Exception:
        # Memory consolidation must never break shutdown.
        return []


if __name__ == "__main__":
    # Manual run: reflect on today's conversation log and print what would be saved.
    saved = consolidate()
    if saved:
        print("Saved to memory:")
        for f in saved:
            print("  -", f)
    else:
        print("Nothing new worth saving.")
