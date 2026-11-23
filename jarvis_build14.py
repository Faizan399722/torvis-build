"""BUILD 14 pure logic — no mic, screen, network or Windows-only code.

Everything in here is unit-testable on Linux with the standard library
only. The native shell (jarvis.py) and the brain (backend.py) import
from this module; the HUD (jarvis-hud.html) mirrors the same rules in
JavaScript for its speech queue.

BUILD 14 (2026-11-21) — VOICE FIXED, MEMORY, PROACTIVE, STREAMING,
ROMAN URDU, PC CONTROL, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI
LITE FALLBACK.

Voice rule, BUILD 14: the HUD's speechSynthesis is the PRIMARY voice
(it is the one that actually works on Faizan's PC — Windows SAPI via
pyttsx3 spoke on Q1 then went silent on Q2, and BUILD 13's engine
reuse did not fix that). pyttsx3 stays as the BACKUP voice, used when
the HUD is hidden/minimised (wake word) or speechSynthesis is
unavailable. Replies are spoken through a FIFO queue, never
latest-wins, so a new reply can never cut an unspoken one off.
"""
import json, os, re
from datetime import datetime, timedelta
from pathlib import Path

BUILD14_MARKER = "BUILD 14 — VOICE FIXED, MEMORY, PROACTIVE, STREAMING, ROMAN URDU, PC CONTROL, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK"

# ------------------------------------------------------------ language ---
# Roman Urdu words Faizan actually uses, plus common Urdu words written
# in Latin letters. Urdu script is U+0600–U+06FF.
ROMAN_URDU_WORDS = {
    "mujhe", "tum", "tumhe", "tumhara", "tumhari", "mera", "meri", "mere",
    "aap", "aapka", "aapki", "kya", "kaise", "kaisa", "kaisi", "kyun",
    "kab", "kahan", "kaun", "yeh", "ye", "woh", "wo", "hai", "hain",
    "nahi", "nahin", "matlab", "batao", "bata", "karo", "kar", "karke",
    "chahiye", "acha", "accha", "theek", "bilkul", "zaroor", "abhi",
    "kal", "aaj", "phir", "bhi", "aur", "lekin", "magar", "agar",
    "yaad", "rakhna", "sunao", "dekho", "kuch", "koi", "sab", "bohat",
    "bahut", "bhai", "yar", "yaar", "salam", "shukriya", "meherbani",
    "kaam", "batao", "samajh", "samjha", "bolo", "likho", "parho",
    "mujhse", "tujhe", "usko", "isko", "uski", "iski", "hamara",
    "hamari", "tumne", "maine", "usne", "isne", "karke", "jao",
    "aao", "chal", "chalo", "dekho", "suno", "bolo", "karo", "bhejo",
}
URDU_RE = re.compile(r"[\u0600-\u06ff]")

def detect_language(text):
    """Return 'urdu' | 'roman-urdu' | 'mixed' | 'english'.

    Urdu script -> 'urdu'. Two or more Roman Urdu words -> 'roman-urdu'
    (or 'mixed' when the sentence is mostly English words too).
    One Roman Urdu word in an otherwise English sentence -> 'mixed'.
    Everything else -> 'english'. Pure function."""
    t = str(text or "")
    if URDU_RE.search(t):
        return "urdu"
    words = re.findall(r"[a-zA-Z]+", t.lower())
    if not words:
        return "english"
    hits = [w for w in words if w in ROMAN_URDU_WORDS]
    if len(hits) >= 2:
        return "roman-urdu" if len(hits) / len(words) >= 0.4 else "mixed"
    if len(hits) == 1:
        return "mixed"
    return "english"

def speak_lang_for(language):
    """SpeechSynthesis / SAPI language tag for a detected language."""
    return "ur-PK" if language in ("urdu", "roman-urdu", "mixed") else "en-GB"

def reply_language_note(language):
    """One line for the system prompt: answer in the user's own mix."""
    if language == "urdu":
        return "Reply in Urdu (Urdu script)."
    if language == "roman-urdu":
        return "Reply in Roman Urdu, the same mix the user used."
    if language == "mixed":
        return "Reply in the same English + Roman Urdu mix the user used."
    return "Reply in English."

# ------------------------------------------------------------ sentences ---
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

def split_sentences(text):
    """Split cleaned text into sentences. Pure function."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return []
    return [p.strip() for p in _SENTENCE_RE.split(t) if p.strip()]

def first_sentence(text):
    """The first sentence of a reply — spoken as soon as it is ready,
    so JARVIS talks while the rest of the reply is still queued
    (BUILD 14 streaming)."""
    parts = split_sentences(text)
    return parts[0] if parts else ""

def rest_after_first(text):
    """Everything after the first sentence."""
    parts = split_sentences(text)
    return " ".join(parts[1:]) if len(parts) > 1 else ""

# ------------------------------------------------------------ reminders ---
_REMIND_IN_RE = re.compile(
    r"remind me in\s+(\d+)\s*(second|seconds|minute|minutes|hour|hours)\b",
    re.I)
_REMIND_AT_RE = re.compile(
    r"remind me (?:tomorrow )?at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
    re.I)
_REMIND_TOMORROW_RE = re.compile(r"remind me tomorrow at\s+", re.I)

def _reminder_text(text):
    """The reminder itself, with the 'remind me …' instruction stripped."""
    t = str(text or "")
    t = re.sub(r"^\s*remind me\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:in\s+\d+\s*(?:second|seconds|minute|minutes|hour|hours)\s+"
               r"(?:to\s+)?)", "", t, flags=re.I)
    t = re.sub(r"^(?:tomorrow\s+)?at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*"
               r"(?:to\s+)?", "", t, flags=re.I)
    t = re.sub(r"^(?:to\s+)", "", t, flags=re.I)
    return t.strip(" .") or "reminder"

def parse_reminder(text, now=None):
    """Parse 'remind me in 10 minutes to …' / 'remind me at 9:30 …' /
    'remind me tomorrow at 8 am to …' into a reminder dict, or
    {"ok": False} when the text is not a reminder. Pure function.
    `now` is a datetime, for tests; defaults to datetime.now()."""
    now = now or datetime.now()
    t = str(text or "")
    m = _REMIND_IN_RE.search(t)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        minutes = n / 60.0 if "second" in unit else n * 60.0 if "hour" in unit else float(n)
        at = now + timedelta(minutes=minutes)
        return {"ok": True, "at": at.isoformat(timespec="minutes"),
                "in_minutes": minutes, "text": _reminder_text(t)}
    m = _REMIND_AT_RE.search(t)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = (m.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if _REMIND_TOMORROW_RE.search(t) or at <= now:
            at = at + timedelta(days=1)
        return {"ok": True, "at": at.isoformat(timespec="minutes"),
                "in_minutes": round((at - now).total_seconds() / 60.0, 1),
                "text": _reminder_text(t)}
    return {"ok": False, "error": "not a reminder"}

def format_morning_briefing(when, reminders, facts, tasks):
    """One short briefing text: date, due reminders, remembered facts
    and open tasks. Pure function."""
    lines = [f"Good morning, Sir. Today is {when.strftime('%A %d %B %Y')}."]
    if reminders:
        lines.append("Reminders due: " + "; ".join(reminders) + ".")
    if tasks:
        lines.append(f"You have {len(tasks)} open task(s): " + "; ".join(tasks[:5]) + ".")
    if facts:
        lines.append("I remember: " + "; ".join(facts[:5]) + ".")
    if len(lines) == 1:
        lines.append("Nothing due this morning — a clean start.")
    return " ".join(lines)

# ------------------------------------------------------------ memory ---
def default_memory_path():
    """Memory lives in %APPDATA%\\NovaAgent\\jarvis-memory.json when
    APPDATA exists (same folder as config.json); otherwise in the
    JARVIS work drive folder. Never on the system drive root."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "NovaAgent" / "jarvis-memory.json"
    return work_drive_path() / "jarvis-memory.json"

def default_reminder_path():
    return default_memory_path().with_name("jarvis-reminders.json")

def work_drive_path():
    """JARVIS's own work folder. On Faizan's PC this is the H: drive
    (H:\\JARVIS-Work\\) when it exists — his rule: JARVIS files go
    only in H:, never the C: drive. On a PC with no H: drive it falls
    back to ~/JARVIS-Computer. No C: path is ever written in code."""
    h_drive = Path("H:/JARVIS-Work")
    try:
        if h_drive.exists():
            return h_drive
    except Exception:  # noqa: BLE001
        pass
    return Path.home() / "JARVIS-Computer"

class MemoryStore:
    """Persistent memory across restarts: facts, tasks, preferences.
    JSON on disk; every write is atomic enough for one user (write to
    a temp file, then replace)."""
    def __init__(self, path=None):
        self.path = Path(path) if path else default_memory_path()
        self.data = {"facts": [], "tasks": [], "preferences": {}}
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data["facts"] = [str(x) for x in raw.get("facts") or []]
                self.data["tasks"] = [str(x) for x in raw.get("tasks") or []]
                prefs = raw.get("preferences") or {}
                self.data["preferences"] = dict(prefs) if isinstance(prefs, dict) else {}
        except Exception:  # noqa: BLE001 — missing/corrupt = empty memory
            pass
        return self.data

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except Exception:  # noqa: BLE001
            return False

    def remember_fact(self, text):
        t = str(text or "").strip()
        if not t:
            return False
        if t not in self.data["facts"]:
            self.data["facts"].append(t)
        return self.save()

    def remember_task(self, text):
        t = str(text or "").strip()
        if not t:
            return False
        if t not in self.data["tasks"]:
            self.data["tasks"].append(t)
        return self.save()

    def complete_task(self, text):
        t = str(text or "").strip()
        if t in self.data["tasks"]:
            self.data["tasks"].remove(t)
            return self.save()
        return False

    def facts(self):
        return list(self.data["facts"])

    def tasks(self):
        return list(self.data["tasks"])

    def as_prompt_lines(self):
        """Memory as system-prompt lines, so the brain actually uses it."""
        lines = []
        for f in self.data["facts"]:
            lines.append(f"Remembered about the user: {f}")
        for t in self.data["tasks"]:
            lines.append(f"Open task: {t}")
        return lines

class ReminderStore:
    """Reminders on disk (same folder as memory)."""
    def __init__(self, path=None):
        self.path = Path(path) if path else default_reminder_path()
        self.items = []
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.items = [dict(x) for x in raw if isinstance(x, dict)]
        except Exception:  # noqa: BLE001
            self.items = []
        return self.items

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.items, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except Exception:  # noqa: BLE001
            return False

    def add(self, text, at_iso):
        item = {"text": str(text), "at": str(at_iso), "done": False}
        self.items.append(item)
        self.save()
        return item

    def due(self, now=None):
        """Reminders whose time has come and are not done yet."""
        now = now or datetime.now()
        out = []
        for item in self.items:
            if item.get("done"):
                continue
            try:
                at = datetime.fromisoformat(str(item.get("at")))
            except ValueError:
                continue
            if at <= now:
                out.append(item)
        return out

    def mark_done(self, item):
        item["done"] = True
        return self.save()

    def upcoming(self):
        return [i for i in self.items if not i.get("done")]

# ------------------------------------------------------------ voice queue ---
class VoiceQueue:
    """FIFO voice queue (BUILD 14). The old Speaker used latest-wins:
    a new reply dropped the unspoken one. Now every utterance is
    spoken in order, and stop() is the only thing that clears it
    (the user pressing Stop, or the wake word interrupting)."""
    def __init__(self):
        self._items = []
        self._log = []

    def enqueue(self, text):
        t = str(text or "").strip()
        if not t:
            return False
        self._items.append(t)
        self._log.append(f"queued: {t[:80]}")
        return True

    def next(self):
        if not self._items:
            return None
        text = self._items.pop(0)
        self._log.append(f"speaking: {text[:80]}")
        return text

    def stop(self):
        n = len(self._items)
        self._items = []
        self._log.append(f"stopped, cleared {n} queued utterance(s)")
        return n

    def pending(self):
        return len(self._items)

    def log(self):
        return list(self._log)

# ------------------------------------------------------------ PC control ---
# Apps by name only — no drive paths in code, so no C: drive is ever
# touched. Windows resolves these from PATH / the shell.
APP_MAP = {
    "notepad": "notepad.exe", "calculator": "calc.exe",
    "chrome": "chrome.exe", "edge": "msedge.exe",
    "file explorer": "explorer.exe", "explorer": "explorer.exe",
    "word": "winword.exe", "excel": "excel.exe",
    "powerpoint": "powerpnt.exe", "paint": "mspaint.exe",
    "settings": "ms-settings:", "terminal": "cmd.exe",
    "command prompt": "cmd.exe", "powershell": "powershell.exe",
    "spotify": "spotify.exe", "vs code": "code.exe",
    "vscode": "code.exe", "discord": "discord.exe",
    "whatsapp": "whatsapp.exe", "telegram": "telegram.exe",
}

def resolve_app(name):
    """App name -> executable/shell target, or None. Pure function."""
    key = re.sub(r"\s+", " ", str(name or "").strip().lower())
    key = key.replace("open ", "", 1).strip()
    return APP_MAP.get(key)

def open_app(name, runner=None):
    """Open an app by name. `runner` is injected in tests (a fake that
    records the command); on real Windows it launches the exe. Only
    names in APP_MAP are allowed — arbitrary paths/commands are
    refused, so this can never be used to run something off a
    protected path."""
    target = resolve_app(name)
    if target is None:
        return {"ok": False, "error": f"I don't know how to open '{name}' yet, Sir."}
    if runner is not None:
        return runner(target)
    if os.name != "nt":
        return {"ok": False, "error": "Opening apps by name works on Windows, Sir."}
    try:
        import subprocess
        if target.endswith(":"):
            os.startfile(target)  # noqa: S606 — allow-listed shell target only
        else:
            subprocess.Popen([target])  # noqa: S603 — allow-listed exe only
        return {"ok": True, "app": str(name), "opened": target}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not open '{name}': {e}"}

def type_text(text, typer=None):
    """Type text into the focused window. Needs pyautogui on Windows;
    without it, say so plainly instead of pretending. `typer` is
    injected in tests."""
    if typer is not None:
        return typer(str(text or ""))
    try:
        import pyautogui  # type: ignore
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "Typing needs pyautogui, Sir — it is not installed on this PC."}
    try:
        pyautogui.typewrite(str(text or ""), interval=0.02)
        return {"ok": True, "typed_chars": len(str(text or ""))}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Typing failed: {e}"}

def click_at(x, y, clicker=None):
    """Click at screen coordinates the user gave. Coordinates must be
    non-negative integers; anything else is refused."""
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Click needs whole-number X and Y coordinates, Sir."}
    if x < 0 or y < 0:
        return {"ok": False, "error": "Click coordinates cannot be negative, Sir."}
    if clicker is not None:
        return clicker(x, y)
    try:
        import pyautogui  # type: ignore
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "Clicking needs pyautogui, Sir — it is not installed on this PC."}
    try:
        pyautogui.click(x, y)
        return {"ok": True, "x": x, "y": y}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Click failed: {e}"}
