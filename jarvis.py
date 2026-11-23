"""TORVIS — native edition (renamed from JARVIS in BUILD 16, 2026-11-21 — Faizan's own name; "Jarvis" is kept as a legacy wake-word alias for one build).

Run:  python jarvis.py
Build the .exe:  double-click build.bat  (or see README.md)

Why a native shell at all? A browser tab cannot listen for a wake word
while minimized, and cannot glance at the screen on a timer — the tab
gets throttled or suspended. So this launcher keeps the HUD
(jarvis-hud.html, shown in a pywebview window) as the FACE, and runs the
real abilities as native Python background services in the same process:

  * WakeListener  — SpeechRecognition listen_in_background on a thread;
                    hears "Torvis" (or "Hey Torvis" / "Jarvis" as a legacy alias) even while
                    the window is minimized or hidden in the tray, asks
                    the brain (backend.Agent) and answers out loud.
  * ScreenWatcher — while Screen Watch is ON (default OFF, visible
                    indicator in the HUD + tray), captures the screen
                    in memory, asks the brain for one suggestion, and
                    delivers it by tray popup + voice + HUD log.
                    Screenshots are NEVER saved to disk or logged.
  * Tray icon     — BUILD 18: minimise stays in the Windows taskbar
                    AND in the system tray (click the taskbar icon to
                    restore, no need to go to the tray first); close
                    hides to the tray instead of quitting; Quit in the
                    tray menu is the only real exit.

Brain settings are shared with NOVA on purpose: the config file is the
same %APPDATA%\\NovaAgent\\config.json, so the provider / API key /
model / fallback / protected-paths Faizan already set up in NOVA carry
over with no re-typing. TORVIS adds its own keys alongside:
wake_word_enabled, screen_watch_enabled, screen_watch_interval_sec.
"""
import json, os, queue, re, sys, threading, time, webbrowser
from pathlib import Path

import backend

try:
    import jarvis_build14 as b14
except Exception:  # noqa: BLE001
    b14 = None

try:
    import jarvis_build15 as b15
except Exception:  # noqa: BLE001
    b15 = None

try:
    import jarvis_build16 as b16
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b16 = None

try:
    import jarvis_build17 as b17
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b17 = None

try:
    import jarvis_build18 as b18
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b18 = None

try:
    import jarvis_build19 as b19
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b19 = None

try:
    import jarvis_build20 as b20
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b20 = None

# ------------------------------------------------------------------ files ---
def bundled_file(filename):
    """Path to a file bundled into the .exe (PyInstaller _MEIPASS) or
    sitting beside this script in a source checkout."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / filename

# ------------------------------------------------------------ config ---
# Same location as NOVA — see the module docstring. JARVIS-specific keys
# live next to NOVA's; the older screen_advisor_* keys are honoured as a
# legacy alias so an existing NOVA config maps across untouched.
CFG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "NovaAgent"
CFG_FILE = CFG_DIR / "config.json"

def _config_dir():
    """Config dir resolved at call time, not import time.

    CFG_DIR/CFG_FILE above are frozen when the module is first imported.
    If APPDATA changes after import (e.g. the test suite pointing each
    test class at its own temp APPDATA), load/save must follow the
    current APPDATA, otherwise they silently read/write a stale or
    deleted folder and return defaults. In production APPDATA is set
    before the process starts, so this changes nothing there.
    """
    return Path(os.environ.get("APPDATA") or Path.home()) / "NovaAgent"


def _config_file():
    return _config_dir() / "config.json"


DEFAULTS = {"provider": "anthropic", "api_key": "", "model": "", "base_url": "",
            "protected_paths": [], "voice_enabled": True,
            "voice_name_contains": "", "voice_rate": 150,
            "voice_name": "", "voice_pitch": 1.0,
            "wake_word_enabled": False,
            "pause_threshold": 0.8, "listening_sensitivity": 0.5,
            "camera_enabled": False,
            "clap_wake_enabled": False, "clap_sensitivity": 0.5,
            "gestures_enabled": False, "hud_mode_on": False,
            "octoprint_url": "",
            "autopilot_enabled": False, "youtube_autopilot_enabled": False,
            "voice_per_language": {},
            "screen_watch_enabled": False, "screen_watch_interval_sec": 90}
VOICE_RATE_DEFAULT = 150   # BUILD 20: slower, clearer pronunciation
# (was 165 — too fast, and fast speech is what made Urdu/Roman Urdu
# hard to understand). 150 is ~0.9x the old rate; a saved config
# keeps its own rate, new installs get 150.
VOICE_RATE_MIN, VOICE_RATE_MAX = 120, 220
SCREEN_WATCH_MIN_INTERVAL = 30     # seconds — never look more often
SCREEN_WATCH_DEFAULT_INTERVAL = 90
# BUILD 20 — TORVIS: SILENT FALLBACK, NO OVERLOAD LINE, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 19 — TORVIS: FULL AUTOPILOT NO-CONFIRM, YOUTUBE AUTOPILOT, CHANNEL NICHE, SITE WATCHER, MULTILINGUAL VOICE, HUMAN-LIKE SPEAKING, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 18 — TORVIS: CLAP WAKE, GESTURE CONTROL, HUD MODE, TASKBAR + TRAY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 16 — TORVIS (formerly JARVIS): WORLD-BEST VOICE, LOW LATENCY, BARGE-IN, NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 17 — TORVIS: CAMERA ACCESS, LOCAL ONLY, PHOTO IN H: DRIVE, NEVER STREAMED, NO FACE RECOGNITION, KALI VM TYPING, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 16 — TORVIS: WORLD-BEST VOICE, LOW LATENCY, BARGE-IN, NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 15 — FULL CHAT MEMORY, GOOGLE CALENDAR, NEURAL VOICE, LOW LATENCY, NEVER SILENT, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 14 — VOICE FIXED, MEMORY, PROACTIVE, STREAMING, ROMAN URDU, PC CONTROL, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 12, no Ollama, no Groq (2026-10-26, user's permanent choice):
# Main is Mistral (Experiment free tier: 1 req/sec, 500K tokens/min,
# ~1B tokens/month per model in Oct 2026 sources — far above Groq's
# 8K tokens/min / 200K tokens/day). Fallback is Gemini Flash-Lite,
# which has more daily requests than Flash (500/day vs 20/day).
FB_DEFAULTS = {"enabled": True, "provider": "openai", "api_key": "",
               "model": "gemini-3.5-flash-lite",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/"}
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_MODEL = "mistral-medium-latest"

# Google retired gemini-2.5-flash for new users (404 — Google's own error
# says to use gemini-3.8-flash). Heal stale saved configs on load, exactly
# like NOVA does, so an old model name can't break every request.
# BUILD 10, permanent Ollama replacement (2026-10-26, user's choice):
# llama3.1 (4.9 GB, slow on CPU) is replaced by llama3.2:3b (2.0 GB,
# tools yes, 128K context) wherever it was saved, so the old slow
# local brain cannot come back just because an old config is loaded.
RETIRED_MODELS = {"gemini-2.5-flash": "gemini-3.8-flash",
                  "llama3.1": "llama3.2:3b", "llama3.1:8b": "llama3.2:3b"}

def migrate_model_name(model):
    """Map a retired model name to its replacement; pass anything else
    through unchanged. Accepts the bare name or the 'models/...' form."""
    m = str(model or "").strip()
    bare = m[len("models/"):] if m.startswith("models/") else m
    return RETIRED_MODELS.get(bare, m)

def load_config():
    try:
        data = json.loads(_config_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt config = defaults
        data = {}
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in data.items() if k != "fallback"})
    fb = dict(FB_DEFAULTS)
    fb.update(data.get("fallback") or {})
    # BUILD 12: no Ollama, no Groq, permanently. A saved Ollama
    # fallback is migrated to Gemini Lite; a saved Groq main (or an
    # Ollama main) is migrated to Mistral. A Groq key will not work
    # at Mistral, so the key is cleared — paste a Mistral key in
    # Settings (never in chat).
    if str(fb.get("provider") or "").strip().lower() == "ollama":
        fb.update({"provider": "openai", "api_key": "",
                   "model": "gemini-3.5-flash-lite", "base_url": GEMINI_BASE_URL})
    if str(fb.get("model") or "").strip() == "gemini-3.5-flash":
        fb["model"] = "gemini-3.5-flash-lite"
    fb["model"] = migrate_model_name(fb.get("model"))
    cfg["fallback"] = fb
    if (str(cfg.get("provider") or "").strip().lower() == "ollama"
            or "groq.com" in str(cfg.get("base_url") or "")
            or str(cfg.get("model") or "").strip().startswith("openai/gpt-oss")):
        cfg.update({"provider": "openai", "api_key": "",
                    "model": MISTRAL_MODEL, "base_url": MISTRAL_BASE_URL})
    cfg["model"] = migrate_model_name(cfg.get("model"))
    cfg["protected_paths"] = [str(x) for x in (cfg.get("protected_paths") or [])]
    cfg["voice_enabled"] = bool(cfg.get("voice_enabled", True))
    cfg["voice_name_contains"] = str(cfg.get("voice_name_contains") or "")
    try:
        rate = int(cfg.get("voice_rate", VOICE_RATE_DEFAULT))
    except (TypeError, ValueError):
        rate = VOICE_RATE_DEFAULT
    cfg["voice_rate"] = max(VOICE_RATE_MIN, min(VOICE_RATE_MAX, rate))
    cfg["wake_word_enabled"] = bool(cfg.get("wake_word_enabled", False))
    # Screen Watch keys, with the NOVA screen_advisor_* names as alias
    if "screen_watch_enabled" not in data and "screen_advisor_enabled" in data:
        cfg["screen_watch_enabled"] = bool(data.get("screen_advisor_enabled"))
    else:
        cfg["screen_watch_enabled"] = bool(cfg.get("screen_watch_enabled", False))
    if "screen_watch_interval_sec" in data:
        raw_interval = data["screen_watch_interval_sec"]
    elif "screen_advisor_interval_sec" in data:
        raw_interval = data["screen_advisor_interval_sec"]
    else:
        raw_interval = SCREEN_WATCH_DEFAULT_INTERVAL
    try:
        interval = int(raw_interval)
    except (TypeError, ValueError):
        interval = SCREEN_WATCH_DEFAULT_INTERVAL
    cfg["screen_watch_interval_sec"] = max(SCREEN_WATCH_MIN_INTERVAL, interval)
    return cfg

def save_config(cfg):
    _config_dir().mkdir(parents=True, exist_ok=True)
    _config_file().write_text(json.dumps(cfg, indent=2), encoding="utf-8")

# ------------------------------------------------------------ error log ---
# The no-raw-errors rule: nothing in TORVIS may die with a traceback or
# dump a raw error wall at the user. Failures are written here
# (jarvis.log in the app config dir) for diagnosis, and the user hears
# exactly one calm human line instead.
LOG_FILE = CFG_DIR / "jarvis.log"
_log_lock = threading.Lock()

def log_error(area, exc):
    """Append a failure to jarvis.log. Never raises."""
    try:
        import datetime, traceback
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(exc, BaseException):
            detail = "".join(traceback.format_exception(exc)).rstrip()
        else:
            detail = str(exc)
        with _log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] [{area}] {detail}\n")
    except Exception:  # noqa: BLE001 — logging must never crash the app
        pass

def log_speak(line):
    """BUILD 14: every speak attempt/failure goes to jarvis.log, so
    a silent reply is diagnosable instead of a mystery."""
    try:
        import datetime
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with _log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{stamp}] [SPEAK] {line}\n")
    except Exception:  # noqa: BLE001
        pass

def _strip_fallback_note(text):
    """BUILD 20 safety net: strip any leading fallback-switch note
    from a brain reply before it is shown or spoken, so an old-style
    note can never be the first thing TORVIS says. Drops leading
    lines that mention the main brain being overloaded / quota-finished
    / unreachable and switching to a fallback brain. Pure function."""
    t = str(text or "")
    while True:
        lines = t.lstrip().splitlines()
        if not lines:
            return ""
        first = lines[0].strip()
        low = first.lower()
        is_note = (
            first.startswith("↪")
            or ("switched to" in low and "fallback brain" in low)
            or low.startswith("main brain is overloaded")
            or low.startswith("main brain's daily quota")
            or ("main brain" in low and "fallback brain" in low)
        )
        if not is_note:
            return t.strip()
        t = "\n".join(lines[1:])


def calm_reply(text):
    """Make a brain reply safe to show a frustrated user: keep the calm
    human message, cut any raw '(Details: ...)' error dump the brain
    attached (the full text still goes to jarvis.log). Pure function."""
    t = _strip_fallback_note(text)
    cut = t.find("\n(Details:")
    if cut != -1:
        t = t[:cut]
    return t.strip()

# ------------------------------------------------- optional native deps ---
# Every heavy/native dependency is optional at import time: the module
# must import (and its pure logic must stay testable) on a machine with
# none of them installed. Features fail safe with a clear log line.
try:
    import webview
except Exception:  # noqa: BLE001
    webview = None

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_OK = True
except Exception:  # noqa: BLE001
    pystray = None
    TRAY_OK = False

try:
    import pyttsx3
    TTS_OK = True
except Exception:  # noqa: BLE001
    pyttsx3 = None
    TTS_OK = False

try:
    import speech_recognition as sr
    SR_OK = True
except Exception:  # noqa: BLE001
    sr = None
    SR_OK = False

try:
    import winsound  # Windows beep for the wake-word acknowledgement
except Exception:  # noqa: BLE001
    winsound = None

NO_MIC_MSG = ("🎙 No microphone found/working on this PC — "
              "type commands in the HUD instead.")

# ------------------------------------------------------------- speech ---
def clean_for_speech(text, limit=400):
    """Strip markdown/code so the spoken reply sounds like a human talking
    (same cleaning NOVA applies before speaking)."""
    # BUILD 20: strip a leading fallback note before speaking, so it
    # can never be spoken first even if an old reply carries one.
    t = _strip_fallback_note(text)
    t = re.sub(r"```.*?```", " ", str(t or ""), flags=re.S)
    t = re.sub(r"`[^`]*`", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[#>*_~|⛔⚠]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        cut = t[:limit]
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        t = cut[:end + 1] if end > 120 else cut
    return t

def clamp_for_speech(text, max_sentences=4):
    """Clean a reply for speaking AND clamp it to at most
    `max_sentences` sentences — the user's rule: spoken replies are
    1–4 natural sentences, never a read-out of a whole essay. Pure
    function, unit-testable."""
    t = clean_for_speech(text, limit=1200)
    if not t:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", t) if p.strip()]
    if len(parts) > max_sentences:
        parts = parts[:max_sentences]
    out = " ".join(parts)
    if len(out) > 600:      # a hard ceiling even for run-on sentences
        out = out[:600].rsplit(" ", 1)[0] + "…"
    return out

# Calm, deeper TORVIS register: British male voices first. Name
# fragments in best-first order (Ryan/George/Daniel/Arthur are the
# usual en-GB SAPI names; David is the common en-US male fallback).
VOICE_NAME_PREFERENCE = ("ryan", "george", "daniel", "arthur", "david")
_KNOWN_FEMALE = ("zira", "hazel", "susan", "catherine", "linda", "female")

def _voice_is_british(v):
    t = ((getattr(v, "name", "") or "") + " " + (getattr(v, "lang", "") or "")).lower()
    return "en-gb" in t or "en_gb" in t or "british" in t

def _voice_is_english(v):
    lang = (getattr(v, "lang", "") or "").lower()
    name = (getattr(v, "name", "") or "").lower()
    return lang.startswith("en") or "english" in name or _voice_is_british(v)

def _voice_looks_female(v):
    n = (getattr(v, "name", "") or "").lower()
    return any(f in n for f in _KNOWN_FEMALE)

def _voice_is_neural(v):
    """True when a voice is a neural voice (Microsoft 'Online
    (Natural)', Edge '*Neural') rather than an old robotic SAPI
    voice (David / Zira / Hazel). Pure."""
    n = (getattr(v, "name", "") or "").lower()
    return "neural" in n or "natural" in n or "online" in n


def pick_voice(voices, name_contains=""):
    """Choose the most TORVIS-like voice from pyttsx3 voice objects
    (anything with .name / .lang / .id). Pure function — no audio — so
    the preference order is unit-testable:

      1. a voice whose name matches the user's voice_name_contains,
      2. BUILD 20: a NEURAL voice (Online (Natural) / *Neural) — a
         neural voice is always preferred over a robotic SAPI voice,
         even over a named old voice; within neural voices the same
         British-named preference order applies,
      3. British/UK voices matching the calm-male preference list,
      4. any English voice matching the preference list (e.g. David),
      5. any English voice marked male (and not female),
      6. any English voice that doesn't look female,
      7. the first voice there is.
    The familiar default female voice (Zira) is therefore only ever a
    last resort, never the choice while a male English voice exists."""
    voices = list(voices or [])
    if not voices:
        return None
    want = str(name_contains or "").strip().lower()
    if want:
        for v in voices:
            if want in (getattr(v, "name", "") or "").lower():
                return v
    for frag in VOICE_NAME_PREFERENCE:                    # 2a: neural + British + named
        for v in voices:
            if (_voice_is_neural(v) and frag in (getattr(v, "name", "") or "").lower()
                    and _voice_is_british(v)):
                return v
    for frag in VOICE_NAME_PREFERENCE:                    # 2b: neural + English + named
        for v in voices:
            if (_voice_is_neural(v) and frag in (getattr(v, "name", "") or "").lower()
                    and _voice_is_english(v)):
                return v
    for v in voices:                                      # 2c: any neural English voice
        if _voice_is_neural(v) and _voice_is_english(v):
            return v
    for frag in VOICE_NAME_PREFERENCE:                    # 3: British + named
        for v in voices:
            if frag in (getattr(v, "name", "") or "").lower() and _voice_is_british(v):
                return v
    for frag in VOICE_NAME_PREFERENCE:                    # 4: English + named
        for v in voices:
            if frag in (getattr(v, "name", "") or "").lower() and _voice_is_english(v):
                return v
    for v in voices:                                      # 5: English male
        n = (getattr(v, "name", "") or "").lower()
        if _voice_is_english(v) and "male" in n and not _voice_looks_female(v):
            return v
    for v in voices:                                      # 6: English, not female
        if _voice_is_english(v) and not _voice_looks_female(v):
            return v
    return voices[0]                                      # 7: anything

def _pick_voice(engine, name_contains=""):
    """Apply pick_voice() to a live pyttsx3 engine."""
    try:
        voices = engine.getProperty("voices") or []
    except Exception:  # noqa: BLE001
        return
    pick = pick_voice(voices, name_contains)
    if pick is not None:
        try: engine.setProperty("voice", pick.id)
        except Exception:  # noqa: BLE001
            pass

# BUILD 13 (2026-11-10): voice must keep speaking EVERY reply.
# Root cause of "speaks at startup, then silent after the first
# question": the old Speaker created a FRESH pyttsx3 engine per
# utterance and called engine.stop() after runAndWait() — a known
# SAPI breaker — and a hung runAndWait() left _last_speak_result
# stuck on "pending" forever, so the HUD fallback (which only fired
# on "failed") never spoke either. Now ONE engine is reused per
# thread, created once and disposed only on failure; engine.stop()
# is never called after a successful runAndWait().
SPEAKER_STALE_PENDING_SECONDS = 10.0
class Speaker:
    """pyttsx3 text-to-speech on its own thread (the NOVA pattern).

    ONE engine is reused for every utterance on this thread (BUILD 13):
    creating a fresh SAPI engine per utterance and calling stop() after
    runAndWait() breaks SAPI, which is why voice died after the first
    reply. BUILD 14: the mailbox is now a FIFO QUEUE (jarvis_build14.
    VoiceQueue) — a new reply is spoken AFTER the unspoken ones, never
    instead of them, so replies are never cut or dropped. A failed
    utterance must NEVER silence later replies: it is logged, the
    broken engine is disposed so the next utterance re-inits, and the
    thread keeps waiting — so "first answer speaks, second answer is
    text-only" cannot happen again. Every attempt is logged with
    log_speak() so a silent reply leaves a trace in jarvis.log."""
    def __init__(self, on_state=None, voice_name_contains="",
                 voice_rate=VOICE_RATE_DEFAULT):
        self.enabled = True
        self.available = TTS_OK
        self._on_state = on_state or (lambda _speaking: None)
        self.voice_name_contains = str(voice_name_contains or "")
        # BUILD 19: voice picked per language, from Settings.
        self.voice_per_language = {}
        # BUILD 20: edge-tts is the primary voice engine; SAPI is
        # only the offline fallback. Hooks (tests only): _edge_tts_runner
        # (cmd -> returncode) and _mp3_player (path -> None).
        self.edge_tts_enabled = True
        self._edge_tts_available_cached = None
        self._edge_tts_runner = None
        self._mp3_player = None
        self._last_voice_engine = "pyttsx3 (SAPI)"
        try:
            rate = int(voice_rate)
        except (TypeError, ValueError):
            rate = VOICE_RATE_DEFAULT
        self.voice_rate = max(VOICE_RATE_MIN, min(VOICE_RATE_MAX, rate))
        self._pending = None
        self._queue = b14.VoiceQueue() if b14 is not None else None
        self._stop_requested = False
        self._wake = threading.Event()
        self._thread = None
        # Last utterance outcome for the HUD fallback (BUILD 9):
        # "pending" while speaking, "ok" after runAndWait, "failed"
        # if the engine raised. The HUD checks this after a reply;
        # only "failed" makes it speak the reply itself, so a working
        # Python voice is never doubled.
        self._last_speak_result = None
        self._engine = None          # BUILD 13: ONE reused engine
        self._last_speak_started = None  # monotonic time say() was called

    def say(self, text):
        """BUILD 14: enqueue (FIFO) — never drop an unspoken reply."""
        if not self.enabled or not text:
            return
        if not self.available:
            if not TTS_OK:
                log_speak(f"skipped (pyttsx3 unavailable): {str(text)[:80]}")
                return
            self.available = True
        if self._queue is not None:
            self._queue.enqueue(text)
        else:
            self._pending = text
        self._last_speak_result = "pending"
        self._last_speak_started = time.monotonic()
        self._wake.set()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        log_speak(f"queued: {str(text)[:80]}")

    def stop_speaking(self):
        """BUILD 14 interrupt: clear the queue and stop the current
        utterance. This is the ONLY place engine.stop() is used on a
        live engine — a user interrupt, not after a good speak."""
        n = 0
        if self._queue is not None:
            n = self._queue.stop()
        self._pending = None
        self._stop_requested = True
        engine = self._engine
        if engine is not None:
            try: engine.stop()
            except Exception:  # noqa: BLE001
                pass
        log_speak(f"stop requested by user, cleared {n} queued utterance(s)")
        return n

    def test_voice(self):
        """BUILD 14 Test Voice: speak one test sentence and report."""
        self.say("Hello, Sir. This is TORVIS, testing my voice. If you can hear me, the voice is working.")
        return {"ok": True, "primary": "HUD speechSynthesis",
                "backup": "pyttsx3" if TTS_OK else "pyttsx3 (unavailable)",
                "queued": self._queue.pending() if self._queue is not None else 0}

    def voice_status(self):
        status = {"primary": "HUD speechSynthesis",
                "backup": "pyttsx3" if TTS_OK else "pyttsx3 (unavailable)",
                "backup_available": bool(TTS_OK and self.available),
                "enabled": bool(self.enabled),
                "queued": self._queue.pending() if self._queue is not None else 0,
                "last_result": self._last_speak_result}
        # BUILD 20: the Python backup now speaks via edge-tts first.
        try:
            status.update(self.voice_engine_status())
        except Exception:  # noqa: BLE001
            pass
        return status

    def voice_engine_status(self):
        """BUILD 20: which voice engine will speak — edge-tts (neural,
        primary) when available, else pyttsx3/SAPI (offline fallback)."""
        available = self._edge_tts_available()
        return {"engine": "edge-tts (Microsoft neural voices)" if available
                else "pyttsx3 (SAPI)",
                "edge_tts_available": bool(available),
                "edge_tts_enabled": bool(self.edge_tts_enabled),
                "fallback": "pyttsx3 (SAPI)",
                "last_engine": self._last_voice_engine}

    def _edge_tts_available(self):
        """Is edge-tts installed (CLI or Python package)? Cached.
        A test runner hook counts as available (tests fake it)."""
        if self._edge_tts_runner is not None:
            return True
        if self._edge_tts_available_cached is not None:
            return self._edge_tts_available_cached
        available = False
        try:
            import shutil
            if shutil.which("edge-tts"):
                available = True
        except Exception:  # noqa: BLE001
            pass
        if not available:
            try:
                import edge_tts  # noqa: F401
                available = True
            except Exception:  # noqa: BLE001
                available = False
        self._edge_tts_available_cached = available
        return available

    def _play_mp3(self, path):
        """Play one MP3 file and wait until it finishes. Windows:
        Windows Media Player via PowerShell (built in, no extra
        install). Other platforms: playsound / ffplay / afplay.
        A test hook (_mp3_player) replaces all of this."""
        if self._mp3_player is not None:
            return self._mp3_player(str(path))
        import subprocess
        if os.name == "nt":
            ps = ("$p = New-Object -ComObject WMPlayer.OCX; "
                  f"$p.URL = '{str(path)}'; $p.controls.play(); "
                  "while ($p.playState -ne 1) { Start-Sleep -Milliseconds 200 }")
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           check=True, timeout=300)
            return
        try:
            import playsound  # noqa: F401
            subprocess.run(["python", "-c",
                            "import playsound,sys; playsound.playsound(sys.argv[1])",
                            str(path)], check=True, timeout=300)
            return
        except Exception:  # noqa: BLE001
            pass
        for player in ("ffplay", "mpv", "afplay"):
            try:
                import shutil
                if shutil.which(player):
                    args = [player, str(path)] if player != "ffplay" else [
                        player, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)]
                    subprocess.run(args, check=True, timeout=300)
                    return
            except Exception:  # noqa: BLE001
                continue
        raise RuntimeError("no MP3 player available on this PC")

    def _speak_via_edge_tts(self, text):
        """BUILD 20: speak `text` with edge-tts (free Microsoft neural
        voices). Returns True when it spoke, False when edge-tts is
        unavailable / failed — the caller then falls back to SAPI.
        Synthesises to a temp MP3, plays it, deletes it after."""
        if not self.edge_tts_enabled or b20 is None:
            return False
        if not self._edge_tts_available():
            return False
        try:
            picked = b20.edge_voice_for_text(
                text, per_language=getattr(self, "voice_per_language", None) or {})
            voice = picked.get("voice")
            if not voice:
                log_speak(picked.get("fallback_message", "")[:160])
                return False
            import subprocess
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            out_path = tmp.name
            tmp.close()
            try:
                cmd = b20.build_edge_tts_command(voice, text, out_path)
                if self._edge_tts_runner is not None:
                    rc = self._edge_tts_runner(cmd)
                else:
                    rc = subprocess.run(cmd, timeout=120).returncode
                if rc != 0:
                    raise RuntimeError(f"edge-tts exited with code {rc}")
                if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                    raise RuntimeError("edge-tts produced no audio file")
                self._play_mp3(out_path)
                self._last_voice_engine = f"edge-tts ({voice})"
                return True
            finally:
                try:
                    os.unlink(out_path)
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001 — edge-tts must never silence a reply
            log_speak(b20.edge_tts_not_available_message(str(e))[:160])
            return False

    def _get_engine(self):
        """BUILD 13: return the one reused engine, creating it once.
        Returns None if pyttsx3 is unavailable / init fails."""
        if self._engine is not None:
            return self._engine
        if not TTS_OK or pyttsx3 is None:
            return None
        engine = pyttsx3.init()
        _pick_voice(engine, self.voice_name_contains)
        engine.setProperty("rate", self.voice_rate)
        # BUILD 20: natural pitch/volume on the SAPI fallback too.
        try:
            engine.setProperty("volume", 1.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            engine.setProperty("pitch", 1.0)
        except Exception:  # noqa: BLE001 — not every SAPI driver has pitch
            pass
        self._engine = engine
        return engine

    def _dispose_engine(self):
        """Drop the reused engine so the next utterance re-inits it.
        Called only on failure (BUILD 13) — never after a good speak."""
        engine, self._engine = self._engine, None
        if engine is not None:
            try: engine.stop()
            except Exception:  # noqa: BLE001
                pass

    def _run(self):
        # SAPI5 via pyttsx3 needs COM on this worker thread. On a
        # pywebview exe the main thread's COM state does not carry
        # over, which can make every pyttsx3.init() fail even though
        # .NET System.Speech works fine. Best effort, ignored on
        # non-Windows / test fakes.
        _com_init = False
        # COM is Windows-only; on Linux/macOS skip the import entirely
        # (BUILD 14: the import scan delayed thread start and made the
        # voice thread occasionally miss the 2s test deadline).
        if os.name == "nt":
            try:
                import comtypes
                comtypes.CoInitialize()
                _com_init = True
            except Exception:  # noqa: BLE001
                pass
        try:
            while self.available:
                self._wake.wait()
                self._wake.clear()
                # BUILD 14: drain the FIFO queue, one utterance at a
                # time, in order. Fall back to the old single pending
                # slot only if the queue module is missing.
                while True:
                    if self._queue is not None:
                        text = self._queue.next()
                    else:
                        text, self._pending = self._pending, None
                    if text is None or not self.enabled:
                        break
                    if self._stop_requested:
                        self._stop_requested = False
                        break
                    self._on_state(True)
                    try:
                        # BUILD 20: edge-tts is the PRIMARY voice —
                        # free Microsoft neural voices (RyanNeural /
                        # AsadNeural, …), not the old robotic SAPI
                        # voice. If it is not installed / offline it
                        # returns False and SAPI speaks instead, with
                        # a plain Task-Log line — never pretending.
                        if b20 is not None and self._speak_via_edge_tts(text):
                            self._last_speak_result = "ok"
                            log_speak(f"ok (edge-tts): {str(text)[:80]}")
                            continue
                        engine = self._get_engine()
                        if engine is None:
                            raise RuntimeError("pyttsx3 engine unavailable")
                        # BUILD 19: multilingual backup voice — pick the
                        # voice matching this utterance's language
                        # (ur-PK for Urdu/Roman Urdu, matching locale
                        # for other languages). No matching voice ->
                        # keep the default and say so in the log, never
                        # force an English voice on Urdu text.
                        if b19 is not None:
                            try:
                                voices = engine.getProperty("voices") or []
                                picked = b19.pick_voice_for_text(
                                    voices, text,
                                    per_language=getattr(self, "voice_per_language", None) or {})
                                if picked.get("voice"):
                                    for _v in voices:
                                        if b19._voice_name(_v) == picked["voice"]:
                                            engine.setProperty("voice", _v.id)
                                            break
                                elif picked.get("fallback_message"):
                                    log_speak(picked["fallback_message"][:160])
                            except Exception:  # noqa: BLE001 — voice pick must never silence a reply
                                pass
                        engine.say(text)
                        engine.runAndWait()  # BUILD 13: NO engine.stop() here
                        self._last_speak_result = "ok"
                        log_speak(f"ok: {str(text)[:80]}")
                    except Exception as e:  # noqa: BLE001 — engine failed once:
                        self._dispose_engine()
                        self._last_speak_result = "failed"
                        log_speak(f"FAILED: {str(text)[:80]} — {e}")
                        log_error("speaker", e)
                    finally:
                        self._on_state(False)
                    if self._stop_requested:
                        self._stop_requested = False
                        break
        finally:
            if _com_init:
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:  # noqa: BLE001
                    pass

# ------------------------------------------------- wake word listener ---
WAKE_ENERGY_THRESHOLD = 300   # mic sensitivity for the background listener
WAKE_PAUSE_THRESHOLD = 0.8    # seconds of silence that end a phrase

class WakeListener:
    """Always-listening wake-word watcher (opt-in, default OFF).

    SpeechRecognition's listen_in_background runs on its OWN native
    thread — that is precisely why it keeps hearing "Jarvis" while the
    HUD window is minimized or hidden in the tray, which no browser tab
    can do. Phrases are split by backend.parse_wake_phrase and posted
    to the app event queue; recognizer errors are swallowed so a bad
    phrase or a network hiccup never kills the listener. A mic that
    won't open makes start() return False (the caller forces the
    setting back OFF, like NOVA)."""
    def __init__(self, events, pause_threshold=0.8, listening_sensitivity=0.5):
        self.events = events
        self.pause_threshold = pause_threshold
        self.listening_sensitivity = listening_sensitivity
        self.running = False
        self.awaiting_command = False
        self._stopper = None

    def start(self):
        if self.running:
            return True
        if not SR_OK:
            return False
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = WAKE_ENERGY_THRESHOLD
            recognizer.pause_threshold = self.pause_threshold
            # BUILD 16: higher sensitivity hears quieter speech.
            recognizer.energy_threshold = int(300 + (0.5 - float(self.listening_sensitivity)) * 400)
            mic = sr.Microphone()
            self._stopper = recognizer.listen_in_background(
                mic, self._callback, phrase_time_limit=8)
            self.running = True
            return True
        except Exception:  # noqa: BLE001 — OSError: no working mic
            self.running = False
            self._stopper = None
            return False

    def stop(self):
        self.awaiting_command = False
        if self._stopper is not None:
            try: self._stopper(wait_for_stop=False)
            except Exception:  # noqa: BLE001
                pass
            self._stopper = None
        self.running = False

    def _callback(self, _recognizer, audio):
        try:
            text = _recognizer.recognize_google(audio)
        except Exception:  # noqa: BLE001 — unknown speech / offline hiccup
            return
        try:
            if not text:
                return
            if self.awaiting_command:
                self.awaiting_command = False
                self.events.put(("wake_command", text))
                return
            command = backend.parse_wake_phrase(text)
            if command is None:
                return
            if command == "":
                self.awaiting_command = True
                self.events.put(("wake_ack", ""))
            else:
                self.events.put(("wake_command", command))
        except Exception:  # noqa: BLE001 — the listener must survive anything
            pass

# ------------------------------------------------------ screen watch ---
class ScreenWatcher:
    """Native Screen Watch service (background thread).

    Every interval it captures the screen IN MEMORY (base64 — never
    saved to disk, never logged), asks the brain for one suggestion via
    backend.Agent.screen_suggestion(), and delivers fresh, deduped
    suggestions through the injected deliver() callback. Failure policy
    is the v2.4 one from backend.advisor_failure_action: transient /
    timeout / network / daily-quota failures SKIP the cycle and the
    watcher stays ON; only a hard failure (dead model, bad key, vision
    unsupported) switches it OFF, reported once via on_hard_fail().

    All side effects are injected, so the state/dedupe decisions are
    unit-testable with stubs — no screen, mic or network in tests."""
    def __init__(self, capture, suggest, deliver, on_skip_note=None,
                 on_hard_fail=None, interval=SCREEN_WATCH_DEFAULT_INTERVAL,
                 normalize=None, should_deliver=None, failure_action=None):
        self._capture = capture
        self._suggest = suggest
        self._deliver = deliver
        self._on_skip_note = on_skip_note or (lambda: None)
        self._on_hard_fail = on_hard_fail or (lambda _err: None)
        self._normalize = normalize or backend.normalize_suggestion
        self._should_deliver = should_deliver or backend.should_deliver
        self._failure_action = failure_action or backend.advisor_failure_action
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = SCREEN_WATCH_DEFAULT_INTERVAL
        self.interval = max(SCREEN_WATCH_MIN_INTERVAL, interval)
        self.enabled = False
        self.last_delivered = None
        self._skip_noted = False      # one muted note per ON session
        self._busy = False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        """Switch ON and (re)start the glance loop. A fresh ON session
        gets a fresh one-time skip note and a cleared stop flag."""
        self.enabled = True
        self._skip_noted = False
        self._stop.clear()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def stop(self):
        self.enabled = False
        self._stop.set()

    def _loop(self):
        if self._stop.wait(1.5):      # first glance shortly after ON
            return
        while self.enabled and not self._stop.is_set():
            try:
                self.run_cycle()
            except Exception as e:  # noqa: BLE001 — last-resort guard:
                log_error("screen_watch", e)   # the watcher must never
            if self._stop.wait(self.interval):  # take the app down with it
                break

    def run_cycle(self):
        """One glance. Returns the outcome as a short string (this is
        also the unit-test surface):
        'disabled' | 'busy' | 'delivered' | 'quiet' | 'skipped' | 'hard-off'"""
        if not self.enabled:
            return "disabled"
        if self._busy:
            return "busy"
        self._busy = True
        try:
            image_b64 = self._capture()
            raw = self._suggest(image_b64)
        except Exception as e:  # noqa: BLE001 — routed by failure kind
            if self._failure_action(e) == "skip":
                if not self._skip_noted:
                    self._skip_noted = True
                    self._on_skip_note()
                return "skipped"
            self.stop()
            self._on_hard_fail(str(e))
            return "hard-off"
        finally:
            self._busy = False
        suggestion = self._normalize(raw)
        if self._should_deliver(suggestion, self.last_delivered):
            self.last_delivered = suggestion
            self._deliver(suggestion)
            return "delivered"
        return "quiet"

# ------------------------------------------------------------ HUD bridge ---
class HudBridge:
    """Thread-safe pipe into the HUD page. Native services call these;
    each becomes a window.JARVIS_NATIVE.* call via evaluate_js. Every
    call is best-effort — a HUD that isn't loaded yet (or a plain
    browser fallback with no window at all) must never crash a service.
    Lines produced before the window/page exist are BUFFERED and
    flushed when the page proves it is alive (its native_state call),
    so the startup self-check is never silently lost."""
    def __init__(self):
        self.window = None
        self._lock = threading.Lock()
        self._pending = []

    def _call(self, fn, arg):
        win = self.window
        if win is None:
            with self._lock:
                if len(self._pending) < 200:
                    self._pending.append((fn, arg))
            return
        script = ("window.JARVIS_NATIVE && window.JARVIS_NATIVE."
                  + fn + "(" + json.dumps(arg) + ")")
        with self._lock:
            try:
                win.evaluate_js(script)
            except Exception as e:  # noqa: BLE001
                log_error("hud_bridge", e)

    def flush(self):
        """Deliver buffered lines now that the page is alive."""
        with self._lock:
            pending, self._pending = self._pending, []
        for fn, arg in pending:
            self._call(fn, arg)

    def log(self, line):
        self._call("onNativeLog", str(line))

    def suggestion(self, text):
        self._call("onSuggestion", str(text))

    def wake_heard(self, text):
        self._call("onWakeHeard", str(text or ""))

    def set_screen_watch_state(self, on):
        self._call("setScreenWatchState", bool(on))

    def set_hud_mode_state(self, on):
        """BUILD 18: tell the HUD to switch to / from full HUD mode."""
        self._call("setHudModeState", bool(on))

    def set_clap_wake_state(self, on):
        """BUILD 18: tell the HUD the clap-wake chip state."""
        self._call("setClapWakeState", bool(on))

    def set_gesture_state(self, on):
        """BUILD 18: tell the HUD the gesture chip / indicator state."""
        self._call("setGestureState", bool(on))


class JsApi:
    """The API the HUD page sees as window.pywebview.api."""
    def __init__(self, app):
        self._app = app

    def native_chat(self, text):
        """Typed HUD command: route it to the REAL brain (backend.chat),
        the same path voice commands already use. Before this, typed
        HUD commands never reached the brain at all — they ran the
        browser demo's handful of fake routines, so 'open pictures'
        only *said* it opened and anything else fell through to
        'No matching routine'. Returns the calm reply text for the
        HUD to display; speaking is done here so it is not doubled."""
        try:
            reply = self._app._get_agent().chat(str(text))
        except Exception as e:  # noqa: BLE001
            log_error("native_chat", e)
            reply = ("⚠ Something went wrong asking the brain, Sir — "
                     "it's written to jarvis.log. One more try usually settles it.")
        shown = calm_reply(reply)
        if shown != str(reply).strip():
            log_error("native_chat_details", reply)
        # BUILD 14: HUD speechSynthesis is the PRIMARY voice — the HUD
        # speaks `shown` itself as soon as it receives it. Python
        # pyttsx3 is only the backup (HUD calls native_speak_fallback
        # when speechSynthesis is unavailable, and the wake-word path
        # still speaks via pyttsx3). Speaking here too would double it.
        return shown

    def native_last_speak_result(self):
        """HUD fallback check (BUILD 9, stale-pending fix BUILD 13):
        "pending"/"ok"/"failed"/None for the most recent Python
        utterance. The HUD speaks a reply itself only when this is
        "failed", so working Python voice is never doubled. BUILD 13:
        if the result has been "pending" for more than 10 seconds the
        Python voice is hung (runAndWait never returned) — report
        "failed" so the HUD takes over instead of staying silent."""
        try:
            sp = self._app.speaker
            result = sp._last_speak_result
            if result == "pending":
                started = getattr(sp, "_last_speak_started", None)
                if started is not None and time.monotonic() - started > 10.0:
                    return "failed"
            return result
        except Exception:  # noqa: BLE001
            return None

    def native_test_voice(self):
        """BUILD 14 Test Voice button: speak a test sentence via the
        backup engine and report the voice status."""
        try:
            result = self._app.speaker.test_voice()
            return ("Voice test spoken, Sir — if you heard it, the backup "
                    "voice works. The main voice is the HUD's own speech, "
                    "which speaks every reply it shows.")
        except Exception as e:  # noqa: BLE001
            log_error("native_test_voice", e)
            return "Voice test failed, Sir — it is in jarvis.log."

    def native_stop_speaking(self):
        """BUILD 14 Stop Speaking button / wake-word interrupt."""
        try:
            n = self._app.speaker.stop_speaking()
            return True
        except Exception as e:  # noqa: BLE001
            log_error("native_stop_speaking", e)
            return False

    def native_voice_status(self):
        try:
            return self._app.speaker.voice_status()
        except Exception:  # noqa: BLE001
            return {"primary": "HUD speechSynthesis", "backup": "unknown"}

    def native_speak_fallback(self, text):
        """HUD calls this only when speechSynthesis is unavailable, so
        the pyttsx3 backup speaks the reply instead of silence."""
        try:
            self._app.speaker.say(clamp_for_speech(str(text)))
            return True
        except Exception as e:  # noqa: BLE001
            log_error("native_speak_fallback", e)
            return False

    def native_morning_briefing(self):
        """BUILD 14 morning briefing, from memory + due reminders."""
        try:
            return self._app.morning_briefing()
        except Exception as e:  # noqa: BLE001
            log_error("native_morning_briefing", e)
            return "Good morning, Sir — nothing due that I can see."

    def native_add_reminder(self, text):
        try:
            return self._app.add_reminder(str(text))
        except Exception as e:  # noqa: BLE001
            log_error("native_add_reminder", e)
            return "I could not set that reminder, Sir."

    def native_list_reminders(self):
        try:
            return self._app.list_reminders()
        except Exception:  # noqa: BLE001
            return []

    def native_remember(self, text):
        try:
            return self._app.remember(str(text))
        except Exception as e:  # noqa: BLE001
            log_error("native_remember", e)
            return "I could not remember that, Sir."

    def native_todays_schedule(self):
        """BUILD 15: today's meetings, read-only Google Calendar."""
        try:
            return self._app.todays_schedule()
        except Exception as e:  # noqa: BLE001
            log_error("native_todays_schedule", e)
            return "Calendar not connected yet, Sir."

    def native_next_meeting(self):
        try:
            return self._app.next_meeting()
        except Exception as e:  # noqa: BLE001
            log_error("native_next_meeting", e)
            return "No meeting found, Sir."

    def native_what_were_we_working_on(self):
        """BUILD 15: last-task recall, from saved chat history."""
        try:
            return self._app.what_were_we_working_on()
        except Exception as e:  # noqa: BLE001
            log_error("native_what_were_we_working_on", e)
            return "We haven't talked yet, Sir."

    def native_calendar_status(self):
        try:
            return self._app.calendar_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_calendar_status", e)
            return {"connected": False, "error": "Calendar status unknown, Sir."}

    def native_gmail_status(self):
        try:
            return self._app.gmail_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_gmail_status", e)
            return {"connected": False, "error": "Gmail status unknown, Sir."}

    def native_check_my_status(self):
        """BUILD 16: one status briefing."""
        try:
            return self._app.check_my_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_check_my_status", e)
            return "Status check failed, Sir — it is in jarvis.log."

    def native_book_meeting(self, text):
        """BUILD 16: plan a booking (needs a spoken confirm)."""
        try:
            return self._app.book_meeting(text)
        except Exception as e:  # noqa: BLE001
            log_error("native_book_meeting", e)
            return {"ok": False, "error": "Booking failed, Sir — it is in jarvis.log."}

    def native_confirm_meeting(self, confirmed):
        """BUILD 16: confirm/cancel the pending booking."""
        try:
            return self._app.confirm_meeting(confirmed)
        except Exception as e:  # noqa: BLE001
            log_error("native_confirm_meeting", e)
            return {"ok": False, "error": "Booking failed, Sir — it is in jarvis.log."}

    def native_handoff_to_muse(self, task=""):
        """BUILD 16: save TASK-STATUS.md for Muse."""
        try:
            return self._app.handoff_to_muse(task)
        except Exception as e:  # noqa: BLE001
            log_error("native_handoff_to_muse", e)
            return {"ok": False, "error": "Handoff failed, Sir — it is in jarvis.log."}

    def native_self_check_block(self):
        """BUILD 16: one [SELF-CHECK] block."""
        try:
            return self._app.self_check_block()
        except Exception as e:  # noqa: BLE001
            log_error("native_self_check_block", e)
            return "Self-check failed, Sir — it is in jarvis.log."

    def native_voice_quality_report(self):
        """BUILD 16: Voice Quality / daily stats report."""
        try:
            import backend as _be
            return _be.tool_voice_quality_report({})
        except Exception as e:  # noqa: BLE001
            log_error("native_voice_quality_report", e)
            return {"ok": False, "error": "Voice Quality report failed, Sir."}

    def native_voice_quality(self):
        """BUILD 15: engine, latency to first spoken word, fully spoken?"""
        try:
            return self._app.voice_quality_report()
        except Exception as e:  # noqa: BLE001
            log_error("native_voice_quality", e)
            return {"engine": "unknown", "latency_ms_to_first_word": None,
                    "last_reply_fully_spoken": None}

    # ------------------------------------------------- BUILD 17: camera ---
    def native_camera(self, on):
        """BUILD 17: turn the camera on/off. OFF by default, local only,
        never streamed. Returns {ok, enabled, message} — the HUD reads
        res.ok, so a plain bool is never needed."""
        try:
            return self._app.set_camera(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_camera", e)
            return {"ok": False, "enabled": False,
                    "message": "Camera failed, Sir — it is in jarvis.log."}

    def native_camera_status(self):
        """BUILD 17: camera state — enabled, available, last photo."""
        try:
            return self._app.camera_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_camera_status", e)
            return {"enabled": False, "available": None,
                    "status_text": "camera status unknown", "indicator": "CAMERA: OFF"}

    def native_take_photo(self):
        """BUILD 17: take one photo, saved only to H:\\JARVIS-Work\\Photos\\."""
        try:
            return self._app.take_photo()
        except Exception as e:  # noqa: BLE001
            log_error("native_take_photo", e)
            return {"ok": False, "path": None,
                    "error": "Photo failed, Sir — it is in jarvis.log.",
                    "message": "Photo failed, Sir — it is in jarvis.log."}

    def native_describe_camera(self):
        """BUILD 17: 'what do you see?' — plain-words scene description,
        never names a person."""
        try:
            return self._app.describe_camera()
        except Exception as e:  # noqa: BLE001
            log_error("native_describe_camera", e)
            return {"ok": False, "description": "",
                    "error": "I could not describe the camera view, Sir."}

    def native_test_camera(self):
        """BUILD 17: probe the camera and report plainly. Returns
        {ok, message} — the HUD shows r.message."""
        try:
            return self._app.test_camera()
        except Exception as e:  # noqa: BLE001
            log_error("native_test_camera", e)
            return {"ok": False, "message": "Camera test failed, Sir — it is in jarvis.log."}

    def native_minimize(self):
        """HUD Minimize button — BUILD 18: minimise to the Windows
        taskbar, NOT to tray-only. The window stays in the taskbar AND
        the tray icon stays running; clicking the taskbar icon restores
        it directly, no need to go to the tray first."""
        self._app.events.put(("minimize_window", ""))
        return True

    # ------------------------------------------------- BUILD 18: clap / gestures / HUD mode / printer ---
    def native_clap_wake(self, on):
        """BUILD 18: turn clap wake on/off. OFF by default; a double
        clap wakes TORVIS and switches on the HUD. Speech never wakes."""
        try:
            return self._app.set_clap_wake(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_clap_wake", e)
            return {"ok": False, "enabled": False,
                    "message": "Clap wake failed, Sir — it is in jarvis.log."}

    def native_clap_wake_status(self):
        """BUILD 18: clap-wake state — enabled, sensitivity, mic."""
        try:
            return self._app.clap_wake_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_clap_wake_status", e)
            return {"enabled": False, "sensitivity": 0.5,
                    "status_text": "clap wake unknown", "indicator": "CLAP WAKE: OFF"}

    def native_gestures(self, on):
        """BUILD 18: turn hand-gesture control on/off. OFF by default;
        needs the camera on (local only, never streamed)."""
        try:
            return self._app.set_gestures(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_gestures", e)
            return {"ok": False, "enabled": False,
                    "message": "Gestures failed, Sir — it is in jarvis.log."}

    def native_gesture_status(self):
        """BUILD 18: gesture state — enabled, last gesture."""
        try:
            return self._app.gesture_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_gesture_status", e)
            return {"enabled": False, "indicator": "GESTURES: OFF"}

    def native_hud_mode(self, on):
        """BUILD 18: switch HUD mode on/off — the full animated TORVIS
        HUD (BUILD 17 rings / pulsing orb) or the normal view."""
        try:
            return self._app.set_hud_mode(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_hud_mode", e)
            return {"ok": False, "hud_mode": False,
                    "message": "HUD mode failed, Sir — it is in jarvis.log."}

    def native_hud_mode_status(self):
        """BUILD 18: HUD-mode state."""
        try:
            return self._app.hud_mode_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_hud_mode_status", e)
            return {"hud_mode": False, "mode": "normal", "indicator": "HUD MODE: OFF"}

    def native_printer_status(self):
        """BUILD 18: 3D-printer hook status — plainly 'No 3D printer
        connected' unless an OctoPrint URL is set in Settings."""
        try:
            return self._app.printer_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_printer_status", e)
            return {"connected": False, "configured": False,
                    "message": "No 3D printer connected, Sir."}

    # ------------------------------------------------- BUILD 19: autopilot / sites / voice ---
    def native_autopilot(self, on):
        """BUILD 19: turn master autopilot on/off. OFF by default;
        ON means no confirm on his own PC / own accounts (hard limits
        still apply)."""
        try:
            return self._app.set_autopilot(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_autopilot", e)
            return {"ok": False, "autopilot_enabled": False,
                    "message": "Autopilot failed, Sir — it is in jarvis.log."}

    def native_autopilot_status(self):
        """BUILD 19: master + YouTube autopilot state."""
        try:
            return self._app.autopilot_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_autopilot_status", e)
            return {"autopilot_enabled": False, "youtube_autopilot_enabled": False,
                    "indicator": "AUTOPILOT: OFF"}

    def native_youtube_autopilot(self, on):
        """BUILD 19: turn YouTube autopilot on/off."""
        try:
            return self._app.set_youtube_autopilot(bool(on))
        except Exception as e:  # noqa: BLE001
            log_error("native_youtube_autopilot", e)
            return {"ok": False, "youtube_autopilot_enabled": False,
                    "message": "YouTube autopilot failed, Sir — it is in jarvis.log."}

    def native_pronunciation_status(self):
        """BUILD 19: which language voices are actually installed."""
        try:
            return self._app.pronunciation_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_pronunciation_status", e)
            return {"ok": False, "languages": [], "missing": [],
                    "message": "Voice list not available, Sir — check Settings on your PC."}

    def native_watch_site(self, url):
        """BUILD 19: watch a site (read-only checking, no confirm)."""
        try:
            return self._app.watch_site(str(url or ""))
        except Exception as e:  # noqa: BLE001
            log_error("native_watch_site", e)
            return {"ok": False, "error": "Could not watch that site, Sir."}

    def native_site_status(self):
        """BUILD 19: check the watched sites now (read-only)."""
        try:
            return self._app.site_status()
        except Exception as e:  # noqa: BLE001
            log_error("native_site_status", e)
            return {"ok": False, "sites": [], "notifications": [],
                    "message": "Site check failed, Sir."}

    def native_get_settings(self):
        """Settings panel: current brain settings, WITHOUT the API
        keys themselves — the panel shows 'key saved: yes/no' and
        only overwrites a key when the user types a new one. This is
        why JARVIS previously had no Settings button at all: the HUD
        never had a settings surface, so brain changes had to be made
        by editing config.json by hand or in NOVA."""
        cfg = self._app.config
        fb = cfg.get("fallback") or {}
        return {
            "provider": str(cfg.get("provider") or ""),
            "base_url": str(cfg.get("base_url") or ""),
            "model": str(cfg.get("model") or ""),
            "api_key_saved": bool(cfg.get("api_key")),
            "fallback_enabled": bool(fb.get("enabled", True)),
            "fallback_provider": str(fb.get("provider") or ""),
            "fallback_base_url": str(fb.get("base_url") or ""),
            "fallback_model": str(fb.get("model") or ""),
            "fallback_api_key_saved": bool(fb.get("api_key")),
            "voice_name": str(cfg.get("voice_name") or ""),
            "voice_pitch": float(cfg.get("voice_pitch", 1.0)),
            "voice_rate": int(cfg.get("voice_rate", VOICE_RATE_DEFAULT)),
            "calendar_connected": bool((getattr(self._app, "calendar_status", lambda: {})() or {}).get("connected")) if b15 is not None else False,
            "gmail_connected": bool((getattr(self._app, "gmail_status", lambda: {})() or {}).get("connected")) if b15 is not None else False,
            "camera_enabled": bool(getattr(self._app, "camera", None) and self._app.camera.enabled) if b17 is not None else False,
            "camera_status": (self._app.camera_status() if b17 is not None and getattr(self._app, "camera", None) is not None else {"enabled": False, "available": None, "status_text": "camera not available in this build", "indicator": "CAMERA: OFF"}),
            "clap_wake_enabled": bool(getattr(self._app, "clap_wake", None) and self._app.clap_wake.enabled) if b18 is not None else False,
            "clap_sensitivity": float(getattr(self._app, "clap_wake", None).sensitivity) if b18 is not None and getattr(self._app, "clap_wake", None) is not None else 0.5,
            "gestures_enabled": bool(getattr(self._app, "gestures", None) and self._app.gestures.enabled) if b18 is not None else False,
            "hud_mode": bool(getattr(self._app, "hud_mode", None) and self._app.hud_mode.hud_mode) if b18 is not None else False,
            "octoprint_url": str(getattr(self._app, "printer", None).octoprint_url) if b18 is not None and getattr(self._app, "printer", None) is not None else "",
            "autopilot_enabled": bool(getattr(self._app, "autopilot", None) and self._app.autopilot.enabled) if b19 is not None else False,
            "youtube_autopilot_enabled": bool(getattr(self._app, "autopilot", None) and self._app.autopilot.youtube_enabled) if b19 is not None else False,
            "voice_per_language": dict(getattr(self._app, "voice_per_language", None) or {}) if b19 is not None else {},
            "watched_sites": list(getattr(self._app, "site_watcher", None).sites) if b19 is not None and getattr(self._app, "site_watcher", None) is not None else [],
        }

    def native_save_settings(self, settings_json):
        """Settings panel Save: update the shared config file
        (%APPDATA%\\NovaAgent\\config.json, same file NOVA reads) and
        return a human message. The next chat recreates the brain
        from the new config automatically, so no restart is needed.
        A blank API-key field keeps the old key — it never erases it."""
        try:
            data = json.loads(str(settings_json))
            if not isinstance(data, dict):
                return "Settings not saved — I did not understand that form, Sir."
            cfg = self._app.config
            for key in ("provider", "base_url", "model"):
                if key in data:
                    cfg[key] = str(data[key] or "").strip()
            if str(data.get("api_key") or "").strip():
                cfg["api_key"] = str(data["api_key"]).strip()
            fb = cfg.get("fallback") or {}
            if "fallback_enabled" in data:
                fb["enabled"] = bool(data["fallback_enabled"])
            for key in ("fallback_provider", "fallback_base_url", "fallback_model"):
                if key in data:
                    fb[key.replace("fallback_", "")] = str(data[key] or "").strip()
            if str(data.get("fallback_api_key") or "").strip():
                fb["api_key"] = str(data["fallback_api_key"]).strip()
            if "voice_name" in data:
                cfg["voice_name"] = str(data["voice_name"] or "").strip()
            if "voice_pitch" in data:
                try:
                    cfg["voice_pitch"] = max(0.5, min(1.5, float(data["voice_pitch"])))
                except (TypeError, ValueError):
                    pass
            if "camera_enabled" in data:
                # BUILD 17: store the preference; the state flag follows
                # it without probing (probing happens on test/take-photo).
                cfg["camera_enabled"] = bool(data["camera_enabled"])
                try:
                    if getattr(self._app, "camera", None) is not None:
                        if bool(data["camera_enabled"]):
                            self._app.camera.enable()
                        else:
                            self._app.camera.disable()
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if "clap_wake_enabled" in data and b18 is not None:
                # BUILD 18: clap wake OFF by default; sensitivity too.
                cfg["clap_wake_enabled"] = bool(data["clap_wake_enabled"])
                try:
                    self._app.set_clap_wake(bool(data["clap_wake_enabled"]))
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if "clap_sensitivity" in data and b18 is not None:
                try:
                    cfg["clap_sensitivity"] = self._app.set_clap_sensitivity(
                        data["clap_sensitivity"]).get("sensitivity", 0.5)
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if "gestures_enabled" in data and b18 is not None:
                cfg["gestures_enabled"] = bool(data["gestures_enabled"])
                try:
                    self._app.set_gestures(bool(data["gestures_enabled"]))
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if "hud_mode" in data and b18 is not None:
                cfg["hud_mode_on"] = bool(data["hud_mode"])
                try:
                    self._app.set_hud_mode(bool(data["hud_mode"]))
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if "octoprint_url" in data and b18 is not None:
                # BUILD 18 printer hook: only an http(s) URL is stored.
                cfg["octoprint_url"] = str(data["octoprint_url"] or "").strip()
                try:
                    if getattr(self._app, "printer", None) is not None:
                        self._app.printer.set_octoprint_url(cfg["octoprint_url"])
                except Exception:  # noqa: BLE001 — best-effort
                    pass
            if b19 is not None:
                # BUILD 19: autopilot toggles — OFF by default, only
                # Faizan turns them on in Settings. Posts/installs
                # are hard to undo, so the warning lives in the HUD.
                if "autopilot_enabled" in data:
                    cfg["autopilot_enabled"] = bool(data["autopilot_enabled"])
                    try:
                        self._app.set_autopilot(bool(data["autopilot_enabled"]))
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
                if "youtube_autopilot_enabled" in data:
                    cfg["youtube_autopilot_enabled"] = bool(data["youtube_autopilot_enabled"])
                    try:
                        self._app.set_youtube_autopilot(bool(data["youtube_autopilot_enabled"]))
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
                if "voice_per_language" in data:
                    cfg["voice_per_language"] = b19.validate_per_language_voices(
                        data["voice_per_language"])
                    try:
                        self._app.set_voice_per_language(cfg["voice_per_language"])
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
                if "watched_sites" in data:
                    sites = data["watched_sites"]
                    if isinstance(sites, str):
                        sites = b19.load_watched_sites(sites)
                    elif isinstance(sites, list):
                        sites = b19.load_watched_sites("\n".join(str(s) for s in sites))
                    else:
                        sites = []
                    try:
                        if getattr(self._app, "site_watcher", None) is not None:
                            self._app.site_watcher.sites = sites or list(b19.DEFAULT_WATCHED_SITES)
                    except Exception:  # noqa: BLE001 — best-effort
                        pass
            cfg["fallback"] = fb
            cfg["model"] = migrate_model_name(cfg.get("model"))
            save_config(cfg)
            # Apply immediately, without closing JARVIS or quitting
            # from the tray: drop the cached brain so the next chat
            # builds a fresh one from the just-saved config.
            try:
                self._app._agent = None
                self._app._agent_snap = None
            except Exception:  # noqa: BLE001 — cache reset is best-effort
                pass
            return ("Settings saved, Sir — the new brain will be used on your next "
                    "message, no restart needed. Try 'hello' to test it.")
        except Exception as e:  # noqa: BLE001
            log_error("native_save_settings", e)
            return "Settings not saved — something went wrong, Sir. It is in jarvis.log."

    def native_screen_watch(self, on):
        """HUD chip toggled: start/stop the REAL native watcher."""
        try:
            return self._app.set_screen_watch(bool(on), source="hud")
        except Exception as e:  # noqa: BLE001 — one calm line, never a crash
            log_error("screen_watch_toggle", e)
            self._app.hud.log("👁 Screen Watch hit a snag, Sir — it's logged; everything else is unaffected.")
            return False

    def native_state(self):
        # The page calls this on pywebviewready — proof it can receive
        # evaluate_js now, so flush anything buffered during startup.
        try: self._app.hud.flush()
        except Exception as e:  # noqa: BLE001
            log_error("hud_flush", e)
        cfg = self._app.config
        return {"screen_watch": bool(cfg.get("screen_watch_enabled", False)),
                "wake_word": bool(cfg.get("wake_word_enabled", False)),
                "camera": bool(cfg.get("camera_enabled", False)),
                "clap_wake": bool(cfg.get("clap_wake_enabled", False)),
                "gestures": bool(cfg.get("gestures_enabled", False)),
                "hud_mode": bool(cfg.get("hud_mode_on", False)),
                "autopilot": bool(cfg.get("autopilot_enabled", False)),
                "youtube_autopilot": bool(cfg.get("youtube_autopilot_enabled", False)),
                "voice": bool(cfg.get("voice_enabled", True))}


# ------------------------------------------------------------------- app ---
class JarvisApp:
    def __init__(self, config):
        self.config = config
        # JARVIS's own computer: create its workspace on startup, so
        # ~/JARVIS-Computer/Work, Downloads and Notes exist whether or
        # not the user has asked about them yet — like Muse's own
        # computer, but on this PC. JARVIS can still access the user's
        # computer through its other tools when asked.
        try:
            self.workspace = backend.jarvis_workspace_path()
        except Exception:  # noqa: BLE001
            self.workspace = None
        self.events = queue.Queue()
        self.hud = HudBridge()
        self.speaker = Speaker(
            voice_name_contains=config.get("voice_name_contains", ""),
            voice_rate=config.get("voice_rate", VOICE_RATE_DEFAULT))
        self.speaker.enabled = bool(config.get("voice_enabled", True))
        self._agent = None
        self._agent_snap = None
        self._wake_listener = None
        self._tray_icon = None
        self._tray_notified = False
        self._really_quit = False
        self._on_restore = None       # window hooks, set by _run_window
        self._on_hide = None
        self._on_minimize = None      # BUILD 18: minimise to taskbar
        self._on_quit = None
        self._stop_event = threading.Event()
        self.memory = b14.MemoryStore() if b14 is not None else None
        self.reminders = b14.ReminderStore() if b14 is not None else None
        self.chat_history = b15.ChatHistoryStore() if b15 is not None else None
        self.calendar = b15.CalendarClient() if b15 is not None else None
        self.gmail = b15.GmailClient() if b15 is not None else None
        self.voice_quality = b15.VoiceQualityTracker() if b15 is not None else None
        self.barge_in = b16.BargeIn() if b16 is not None else None
        self.daily_stats = b16.DailyStats() if b16 is not None else None
        # BUILD 17: camera — OFF by default, local only, never streamed.
        self.camera = b17.CameraState(enabled=bool(config.get("camera_enabled", False))) if b17 is not None else None
        # BUILD 18: clap wake + gestures — both OFF by default; HUD mode
        # starts normal; the 3D printer is a hook only (no printer set).
        self.clap_wake = b18.ClapWakeState(
            enabled=bool(config.get("clap_wake_enabled", False)),
            sensitivity=config.get("clap_sensitivity", 0.5)) if b18 is not None else None
        self.gestures = b18.GestureState(
            enabled=bool(config.get("gestures_enabled", False))) if b18 is not None else None
        self.hud_mode = b18.HudModeState(
            mode="hud" if config.get("hud_mode_on") else "normal") if b18 is not None else None
        self.printer = b18.PrinterState(
            octoprint_url=str(config.get("octoprint_url") or "")) if b18 is not None else None
        # BUILD 19: autopilot (both toggles OFF by default), site
        # watcher (his Whop store + roofing site), voice per language.
        self.autopilot = b19.AutopilotState(
            enabled=bool(config.get("autopilot_enabled", False)),
            youtube_enabled=bool(config.get("youtube_autopilot_enabled", False))) if b19 is not None else None
        self.site_watcher = b19.SiteWatcher() if b19 is not None else None
        self.voice_per_language = b19.validate_per_language_voices(
            config.get("voice_per_language") or {}) if b19 is not None else {}
        try:
            self.speaker.voice_per_language = dict(self.voice_per_language)
        except Exception:  # noqa: BLE001 — best-effort
            pass
        self._clap_mic_available = None  # test hook: True/False/None
        self._camera_capture_factory = None  # test hook: injectable fake capture
        self._camera_advisor = None  # test hook: callable(b64 jpeg) -> description
        self._last_spoken_reply = ""
        self._alerted_meetings = set()
        self._reminder_thread = None
        self.watcher = ScreenWatcher(
            capture=backend.capture_screen_b64,
            suggest=lambda b64: self._get_agent().screen_suggestion(b64),
            deliver=lambda s: self.events.put(("watch_suggestion", s)),
            on_skip_note=lambda: self.events.put(("watch_skip_note", "")),
            on_hard_fail=lambda err: self.events.put(("watch_hard_fail", err)),
            interval=config.get("screen_watch_interval_sec",
                                SCREEN_WATCH_DEFAULT_INTERVAL))

    # ------------------------------------------------------------- brain ---
    def _agent_snapshot(self):
        c = self.config
        fb = c.get("fallback") or {}
        return (c.get("provider"), c.get("api_key"), c.get("model"),
                c.get("base_url"), fb.get("enabled"), fb.get("provider"),
                fb.get("api_key"), fb.get("model"), fb.get("base_url"),
                tuple(c.get("protected_paths") or []))

    def _get_agent(self):
        snap = self._agent_snapshot()
        if self._agent is None or snap != self._agent_snap:
            self._agent = backend.Agent(self.config, on_tool=self._on_tool)
            self._agent_snap = snap
        return self._agent

    def _on_tool(self, name, detail):
        self.hud.log(f"⚙ {name}  {str(detail)[:160]}")
        if name in ("search_download", "download_file", "youtube_upload"):
            # Completion notification: tray popup when minimized, plus
            # the HUD log above. The chat reply is also spoken, so the
            # user hears it even if the tray is not visible.
            if self._tray_icon is not None:
                try: self._tray_icon.notify(str(detail)[:200], "TORVIS")
                except Exception:  # noqa: BLE001
                    pass
        if name == "open_path":
            # A folder/app just opened, but JARVIS is fullscreen — if it
            # stays on top, the user never sees what opened. Hide to
            # the tray so Explorer / the app comes to the front; the
            # tray icon (or the HUD Minimize button) brings JARVIS back.
            self.events.put(("hide_window", ""))

    # ------------------------------------------------------ screen watch ---
    def set_screen_watch(self, on, source="hud"):
        """Start/stop the native watcher and make every surface (config,
        HUD chip, tray checkmark) agree. Returns the resulting state."""
        on = bool(on)
        self.config["screen_watch_enabled"] = on
        save_config(self.config)
        if on:
            if str(self.config.get("provider", "")).lower() != "ollama":
                # Cloud brains charge one request per glance and free
                # tiers allow very few requests per DAY — warn once per
                # enable so the watcher can't silently eat the quota.
                self.hud.log("ℹ Screen Watch uses one API request per look — "
                             "free cloud quotas are small (Gemini free ≈ 20/day). "
                             "Ollama brains have no quota.")
            self.watcher.start()
        else:
            self.watcher.stop()
        self.hud.set_screen_watch_state(on)
        self._update_tray_menu()
        return on

    def _watch_suggestion(self, text):
        """Main delivery path for a fresh suggestion: tray popup (the
        only surface while minimized), voice, and the HUD log."""
        if not self.config.get("screen_watch_enabled", False):
            return   # switched off while the vision call was in flight
        self.hud.suggestion(text)
        if self._tray_icon is not None:
            try: self._tray_icon.notify(text, "💡 TORVIS suggests")
            except Exception:  # noqa: BLE001
                pass
        self.speaker.say(clamp_for_speech(f"Suggestion: {text}"))

    def _watch_hard_fail(self, err):
        """Vision is genuinely unavailable: switch Screen Watch OFF once
        (with an explanation) instead of failing every interval."""
        self.config["screen_watch_enabled"] = False
        save_config(self.config)
        self.hud.set_screen_watch_state(False)
        self._update_tray_menu()
        self.hud.log("👁 Screen Watch turned OFF — vision isn't available "
                     f"on the current brain ({err}). Pick a vision-capable "
                     "model in the config, then turn it back on.")

    # ---------------------------------------------------------- wake word ---
    def set_wake(self, on):
        """Start/stop the background wake listener. Fails safe like
        NOVA: if the mic stack is missing or the mic won't open, the
        setting is forced back OFF with one clear log line."""
        on = bool(on)
        if on and not SR_OK:
            self.config["wake_word_enabled"] = False
            save_config(self.config)
            self.hud.log("🎧 Wake word unavailable (SpeechRecognition/PyAudio "
                         "not installed) — left OFF.")
            self._update_tray_menu()
            return False
        if on:
            if self._wake_listener is None:
                self._wake_listener = WakeListener(self.events)
            if not self._wake_listener.running and not self._wake_listener.start():
                self.config["wake_word_enabled"] = False
                save_config(self.config)
                self.hud.log("🎧 Wake word couldn't start — no microphone "
                             "found/working on this PC, so it stays OFF. "
                             + NO_MIC_MSG)
                self._update_tray_menu()
                return False
        elif self._wake_listener is not None:
            self._wake_listener.stop()
        self.config["wake_word_enabled"] = on
        save_config(self.config)
        self._update_tray_menu()
        return on

    def set_voice(self, on):
        self.config["voice_enabled"] = bool(on)
        self.speaker.enabled = bool(on)
        save_config(self.config)
        self._update_tray_menu()

    # ------------------------------------------------- BUILD 14: memory / reminders ---
    def remember(self, text):
        """'Remember this …' — save a fact for next time."""
        if self.memory is None:
            return "Memory is not available in this build, Sir."
        t = str(text or "").strip()
        if not t:
            return "Tell me what to remember, Sir."
        self.memory.remember_fact(t)
        return f"Remembered, Sir: {t}"

    def add_reminder(self, text):
        """Parse and save a reminder; returns a human confirmation."""
        if b14 is None or self.reminders is None:
            return "Reminders are not available in this build, Sir."
        parsed = b14.parse_reminder(str(text or ""))
        if not parsed.get("ok"):
            return ("Say it like 'remind me in 10 minutes to …' or "
                    "'remind me at 9:30 to …', Sir.")
        self.reminders.add(parsed["text"], parsed["at"])
        return f"Reminder set, Sir: {parsed['text']} at {parsed['at']}."

    def list_reminders(self):
        if self.reminders is None:
            return []
        return [{"text": i.get("text"), "at": i.get("at")}
                for i in self.reminders.upcoming()]

    def todays_schedule(self):
        """BUILD 15: today's meetings, read-only Google Calendar."""
        if b15 is None or self.calendar is None:
            return "Calendar not connected yet, Sir."
        res = self.calendar.fetch_today_events()
        if not res.get("ok"):
            return res.get("error") or "Calendar not connected yet, Sir."
        from datetime import date
        return b15.format_todays_schedule(res["events"], date.today(), True)

    def next_meeting(self):
        if b15 is None or self.calendar is None:
            return "Calendar not connected yet, Sir."
        from datetime import datetime
        res = self.calendar.fetch_today_events()
        if not res.get("ok"):
            return res.get("error") or "Calendar not connected yet, Sir."
        nxt = b15.next_meeting(res["events"], datetime.now())
        if nxt is None:
            return "No more meetings today, Sir."
        return b15.format_event_line(nxt)

    def calendar_status(self):
        if b15 is None or getattr(self, "calendar", None) is None:
            return {"connected": False, "error": "Calendar module is missing, Sir."}
        return self.calendar.status()

    def gmail_status(self):
        if b15 is None or getattr(self, "gmail", None) is None:
            return {"connected": False, "error": "Gmail module is missing, Sir."}
        return self.gmail.status()

    def what_were_we_working_on(self):
        if b15 is None or self.chat_history is None:
            return "We haven't talked yet, Sir."
        return self.chat_history.what_were_we_working_on()

    def voice_quality_report(self):
        if self.voice_quality is None:
            return {"engine": "unknown", "latency_ms_to_first_word": None,
                    "last_reply_fully_spoken": None}
        return self.voice_quality.report()

    # ------------------------------------------------- BUILD 16: TORVIS ---
    def check_my_status(self):
        """BUILD 16: one status briefing — calendar + reminders + tasks + Gmail unread."""
        if b16 is None or b15 is None:
            return "Status check is not available in this build, Sir."
        from datetime import datetime
        res = self.calendar.fetch_today_events() if self.calendar else {"ok": False, "events": []}
        events = res["events"] if res.get("ok") else []
        gmail_unread = None
        try:
            g = self.gmail.fetch_latest(count=5) if self.gmail else {"ok": False}
            gmail_unread = len(g.get("messages") or []) if g.get("ok") else None
        except Exception:  # noqa: BLE001
            gmail_unread = None
        due = [i["text"] for i in self.reminders.due()] if self.reminders else []
        tasks = self.memory.tasks() if self.memory else []
        return b16.format_status_briefing(events, bool(res.get("ok")), due, tasks,
                                          gmail_unread, self.what_were_we_working_on(),
                                          when=datetime.now())

    def book_meeting(self, text):
        """BUILD 16: book a calendar event — plan only, needs a spoken confirm."""
        if b16 is None:
            return "Calendar booking is not available in this build, Sir."
        import backend as _be
        return _be.tool_book_meeting({"text": str(text or "")})

    def confirm_meeting(self, confirmed):
        """BUILD 16: confirm (or cancel) the pending booking."""
        if b16 is None:
            return "Calendar booking is not available in this build, Sir."
        import backend as _be
        return _be.tool_confirm_meeting({"confirmed": bool(confirmed)})

    def handoff_to_muse(self, task=""):
        """BUILD 16: save full context to TASK-STATUS.md in H:\\JARVIS-Work\\."""
        if b16 is None:
            return {"ok": False, "error": "Handoff is not available in this build, Sir."}
        ctx = {"task": str(task or self.what_were_we_working_on()),
               "tasks": self.memory.tasks() if self.memory else [],
               "summary": self.chat_history.summary if self.chat_history else "",
               "schedule": self.todays_schedule()}
        return b16.save_handoff(ctx)

    def self_check_block(self):
        """BUILD 16: one [SELF-CHECK] block — voice, brain, memory, calendar, Gmail, listening, privacy."""
        if b16 is None:
            return "\n".join(self.self_check())
        st = {
            "voice": "neural voice first (HUD speechSynthesis), pyttsx3 backup" + ("; latency target 800 ms" if self.voice_quality else ""),
            "brain": f"{self.config.get('provider')} · {self.config.get('model') or 'default model'}" + (" — key present" if self.config.get("api_key") else " — NO API key"),
            "memory": f"{len(self.chat_history.turns) if self.chat_history else 0} chat turn(s), {len(self.memory.facts()) if self.memory else 0} fact(s)",
            "calendar": "connected" if (self.calendar and self.calendar.status().get("connected")) else "not connected — connect it in Settings",
            "gmail": "connected (read-only)" if (self.gmail and self.gmail.status().get("connected")) else "not connected — connect it in Settings",
            "listening": f"pause threshold {self.config.get('pause_threshold', 0.8)}s, sensitivity {self.config.get('listening_sensitivity', 0.5)} — short pauses do not cut you off",
            "privacy": "local only — voice, transcripts, memory and tokens stay on this PC (H: / %APPDATA%); only brain text leaves the PC",
            "camera": (b17.camera_self_check_line(self.camera) if b17 is not None else "camera not available in this build"),
        }
        block = b16.format_self_check_block(st)
        if b17 is not None:
            block += "\n" + b17.camera_self_check_line(self.camera)
        return block

    def morning_briefing(self):
        """BUILD 15: date + today's meetings + due reminders +
        remembered facts/tasks + what we were last working on."""
        if b14 is None:
            return "Good morning, Sir."
        from datetime import datetime
        due = [i["text"] for i in self.reminders.due()] if self.reminders else []
        facts = self.memory.facts() if self.memory else []
        tasks = self.memory.tasks() if self.memory else []
        last_work = self.what_were_we_working_on() if b15 is not None else ""
        if b15 is not None and self.calendar is not None:
            res = self.calendar.fetch_today_events()
            meetings = res["events"] if res.get("ok") else []
            connected = bool(res.get("ok"))
            return b15.format_startup_briefing(datetime.now(), meetings, connected,
                                               due, facts, tasks, last_work)
        return b14.format_morning_briefing(datetime.now(), due, facts, tasks)

    def check_due_reminders(self):
        """Speak + show any reminders whose time has come (once each),
        plus meeting alerts 15 minutes before a meeting starts."""
        if self.reminders is None:
            return []
        due = self.reminders.due()
        for item in due:
            text = f"Reminder, Sir: {item.get('text')}"
            self.hud.log("⏰ " + text)
            self.speaker.say(clamp_for_speech(text))
            self.reminders.mark_done(item)
        # BUILD 15: meeting alert, 15 minutes before it starts.
        if b15 is not None and self.calendar is not None:
            try:
                from datetime import datetime
                res = self.calendar.fetch_today_events()
                if res.get("ok"):
                    alerts, self._alerted_meetings = b15.due_meeting_alerts(
                        res["events"], datetime.now(), 15, self._alerted_meetings)
                    for ev in alerts:
                        msg = b15.format_meeting_alert(ev)
                        self.hud.log("📅 " + msg)
                        self.speaker.say(clamp_for_speech(msg))
            except Exception as e:  # noqa: BLE001
                log_error("meeting_alert", e)
        return [i.get("text") for i in due]

    def _reminder_loop(self):
        """Background checker: due reminders every 30 seconds, plus
        the BUILD 19 site watcher when a check is due (every 30
        minutes — the watcher itself gates the timing, and checking
        is read-only, so it never needs a confirm)."""
        while not self._stop_event.is_set():
            try:
                self.check_due_reminders()
            except Exception as e:  # noqa: BLE001
                log_error("reminders", e)
            try:
                self.check_watched_sites()
            except Exception as e:  # noqa: BLE001
                log_error("site_watcher", e)
            if self._stop_event.wait(30):
                break

    # ------------------------------------------------- BUILD 17: camera ---
    def camera_status(self):
        """BUILD 17: camera state dict (enabled, available, indicator)."""
        if b17 is None or self.camera is None:
            return {"enabled": False, "available": None,
                    "status_text": "camera not available in this build",
                    "indicator": "CAMERA: OFF", "last_photo": None,
                    "recording": False, "privacy": ""}
        return self.camera.status()

    def set_camera(self, on):
        """BUILD 17: turn the camera on/off. Turning on probes the real
        camera (OpenCV) — no camera, or Windows blocking it, is reported
        plainly and the camera stays off; a feed is never faked."""
        if b17 is None or self.camera is None:
            return {"ok": False, "enabled": False,
                    "message": "Camera is not available in this build, Sir."}
        on = bool(on)
        if not on:
            self.camera.disable()
            self.config["camera_enabled"] = False
            save_config(self.config)
            self.hud.log("[CAMERA] Camera off, Sir.")
            return {"ok": True, "enabled": False, "message": "Camera off, Sir."}
        probe = b17.probe_camera(capture_factory=self._camera_capture_factory)
        if not probe.get("ok"):
            self.camera.disable()
            self.camera.available = False
            self.hud.log("[CAMERA] " + str(probe.get("error") or "No camera found."))
            return {"ok": False, "enabled": False,
                    "message": str(probe.get("error") or "No camera found, Sir.")}
        self.camera.enable()
        self.camera.available = True
        self.config["camera_enabled"] = True
        save_config(self.config)
        self.hud.log("[CAMERA] Camera on, Sir — local only, never streamed.")
        return {"ok": True, "enabled": True,
                "message": "Camera on, Sir — local only, never streamed."}

    def test_camera(self):
        """BUILD 17: probe the camera and report plainly."""
        if b17 is None or self.camera is None:
            return {"ok": False, "message": "Camera is not available in this build, Sir."}
        probe = b17.probe_camera(capture_factory=self._camera_capture_factory)
        self.camera.available = bool(probe.get("available"))
        if probe.get("ok"):
            return {"ok": True, "available": True,
                    "message": "Camera test passed, Sir — the camera is working, local only."}
        return {"ok": False, "available": False,
                "message": str(probe.get("error") or "No camera found, Sir.")}

    def take_photo(self):
        """BUILD 17: one photo, saved only to H:\\JARVIS-Work\\Photos\\."""
        if b17 is None or self.camera is None:
            return {"ok": False, "path": None, "error": "Camera is not available in this build, Sir.",
                    "message": "Camera is not available in this build, Sir."}
        res = b17.take_photo(self.camera, capture_factory=self._camera_capture_factory)
        if res.get("ok"):
            self.hud.log("[CAMERA] " + str(res.get("message") or "Photo saved."))
            return {"ok": True, "path": res.get("path"), "error": "",
                    "message": str(res.get("message") or "Photo saved, Sir.")}
        return {"ok": False, "path": None, "error": str(res.get("error") or "Photo failed, Sir."),
                "message": str(res.get("error") or "Photo failed, Sir.")}

    def describe_camera(self):
        """BUILD 17: 'what do you see?' — plain-words description only,
        never names a person. Uses the Screen Advisor vision path when
        the brain offers it; otherwise says so plainly."""
        if b17 is None or self.camera is None:
            return {"ok": False, "description": "",
                    "error": "Camera is not available in this build, Sir."}
        advisor = self._camera_advisor
        if advisor is None:
            try:
                agent = self._get_agent()
                if hasattr(agent, "screen_suggestion"):
                    advisor = lambda b64: agent.screen_suggestion(b64)  # noqa: E731
            except Exception:  # noqa: BLE001 — vision is best-effort
                advisor = None
        res = b17.describe_camera_frame(self.camera, advisor=advisor,
                                        capture_factory=self._camera_capture_factory)
        if res.get("ok"):
            return {"ok": True, "description": str(res.get("description") or ""),
                    "error": ""}
        return {"ok": False, "description": "", "error": str(res.get("error") or "I could not describe the camera view, Sir.")}

    def record_camera_video(self, confirmed=False, seconds=10):
        """BUILD 17: video recording — TWO-STEP. confirmed=False returns
        the plan only; nothing is recorded until the user says 'confirm'."""
        if b17 is None or self.camera is None:
            return {"ok": False, "needs_confirm": False,
                    "error": "Camera is not available in this build, Sir."}
        return b17.request_recording(self.camera, confirmed=bool(confirmed), seconds=seconds)

    def stop_camera_recording(self):
        """BUILD 17: stop (or cancel) a camera recording."""
        if b17 is None or self.camera is None:
            return {"ok": False, "error": "Camera is not available in this build, Sir."}
        return b17.stop_recording(self.camera)

    def handle_camera_command(self, action, text=""):
        """BUILD 17: run a parsed camera voice command, return one calm
        spoken line. Never raises."""
        if b17 is None or self.camera is None:
            return "Camera is not available in this build, Sir."
        try:
            if action == "camera_on":
                return self.set_camera(True).get("message", "Camera on, Sir.")
            if action == "camera_off":
                return self.set_camera(False).get("message", "Camera off, Sir.")
            if action == "take_photo":
                r = self.take_photo()
                return r.get("message") or r.get("error") or "Photo failed, Sir."
            if action == "describe_camera":
                r = self.describe_camera()
                return r.get("description") or r.get("error") or "I could not describe the camera view, Sir."
            if action == "test_camera":
                return self.test_camera().get("message", "Camera test done, Sir.")
            if action == "camera_status":
                return self.camera.status_line()
            if action == "record_video":
                r = self.record_camera_video(confirmed=False)
                return r.get("plan") or r.get("error") or "Recording is not available yet, Sir."
            if action == "stop_recording":
                r = self.stop_camera_recording()
                return r.get("message") or r.get("error") or "Recording stopped, Sir."
            return "I did not understand that camera command, Sir."
        except Exception as e:  # noqa: BLE001
            log_error("camera_command", e)
            return "The camera hit a snag, Sir — it is in jarvis.log."

    # ------------------------------------------------- BUILD 18: clap / gestures / HUD mode / printer ---
    def clap_wake_status(self):
        """BUILD 18: clap-wake state dict."""
        if b18 is None or self.clap_wake is None:
            return {"enabled": False, "sensitivity": 0.5, "available": None,
                    "status_text": "clap wake not available in this build",
                    "indicator": "CLAP WAKE: OFF"}
        return self.clap_wake.status()

    def set_clap_wake(self, on):
        """BUILD 18: turn clap wake on/off. OFF by default; a double
        clap wakes TORVIS and switches on the HUD. No mic -> plain
        message, clap wake stays off — never pretend to hear a clap."""
        if b18 is None or self.clap_wake is None:
            return {"ok": False, "enabled": False,
                    "message": "Clap wake is not available in this build, Sir."}
        on = bool(on)
        if not on:
            self.clap_wake.disable()
            self.config["clap_wake_enabled"] = False
            save_config(self.config)
            self.hud.log("[CLAP] Clap wake off, Sir.")
            return {"ok": True, "enabled": False, "message": "Clap wake off, Sir."}
        if self._clap_mic_available is False:
            self.clap_wake.mic_available = False
            self.hud.log("[CLAP] " + b18.NO_MIC_MESSAGE)
            return {"ok": False, "enabled": False, "message": b18.NO_MIC_MESSAGE}
        self.clap_wake.enable()
        self.clap_wake.mic_available = True if self._clap_mic_available else None
        self.config["clap_wake_enabled"] = True
        save_config(self.config)
        self.hud.log("[CLAP] Clap wake on, Sir — two sharp claps wake me.")
        return {"ok": True, "enabled": True,
                "message": "Clap wake on, Sir — two sharp claps wake me and switch on the HUD."}

    def set_clap_sensitivity(self, value):
        """BUILD 18: clap-wake sensitivity 0.1–1.0 (higher = easier)."""
        if b18 is None or self.clap_wake is None:
            return {"ok": False, "sensitivity": 0.5,
                    "message": "Clap wake is not available in this build, Sir."}
        sens = self.clap_wake.set_sensitivity(value)
        self.config["clap_sensitivity"] = sens
        save_config(self.config)
        return {"ok": True, "sensitivity": sens,
                "message": f"Clap sensitivity set to {sens}, Sir."}

    def feed_clap_level(self, level, now=None):
        """BUILD 18: feed one microphone level to the clap detector.
        Returns True only on a double clap while clap wake is on — and
        switches HUD mode on when it does. Never raises."""
        if b18 is None or self.clap_wake is None:
            return False
        if self.clap_wake.on_level(level, now=now):
            self.set_hud_mode(True)
            self.hud.log("[CLAP] Double clap heard, Sir — HUD on.")
            return True
        return False

    def gesture_status(self):
        """BUILD 18: gesture state dict."""
        if b18 is None or self.gestures is None:
            return {"enabled": False, "indicator": "GESTURES: OFF",
                    "last_gesture": None}
        return self.gestures.status()

    def set_gestures(self, on):
        """BUILD 18: turn hand-gesture control on/off. OFF by default.
        Gestures need the camera on — if it is off, say so plainly in
        the message but still store the preference (the camera can be
        switched on after)."""
        if b18 is None or self.gestures is None:
            return {"ok": False, "enabled": False,
                    "message": "Gestures are not available in this build, Sir."}
        on = bool(on)
        if not on:
            self.gestures.disable()
            self.config["gestures_enabled"] = False
            save_config(self.config)
            self.hud.log("[GESTURE] Gestures off, Sir.")
            return {"ok": True, "enabled": False, "message": "Gestures off, Sir."}
        self.gestures.enable()
        self.config["gestures_enabled"] = True
        save_config(self.config)
        camera_on = bool(getattr(self, "camera", None) and self.camera.enabled)
        self.hud.log("[GESTURE] Gestures on, Sir — camera only, local only.")
        if not camera_on:
            return {"ok": True, "enabled": True,
                    "message": ("Gestures on, Sir — but the camera is off, so "
                                "say 'turn camera on' first and the gestures "
                                "will work. Open palm wakes, swipe is next / "
                                "previous, pinch selects, fist stops speaking.")}
        return {"ok": True, "enabled": True,
                "message": ("Gestures on, Sir — open palm wakes and shows the "
                            "HUD, swipe right is next, swipe left is previous, "
                            "pinch selects, fist stops speaking.")}

    def hud_mode_status(self):
        """BUILD 18: HUD-mode state dict."""
        if b18 is None or self.hud_mode is None:
            return {"hud_mode": False, "mode": "normal", "indicator": "HUD MODE: OFF"}
        return self.hud_mode.status()

    def set_hud_mode(self, on):
        """BUILD 18: switch HUD mode on/off — the full animated TORVIS
        HUD, or the normal view."""
        if b18 is None or self.hud_mode is None:
            return {"ok": False, "hud_mode": False,
                    "message": "HUD mode is not available in this build, Sir."}
        on = bool(on)
        if on:
            self.hud_mode.enter_hud()
        else:
            self.hud_mode.exit_hud()
        self.config["hud_mode_on"] = on
        save_config(self.config)
        try:
            self.hud.set_hud_mode_state(on)
        except Exception:  # noqa: BLE001 — HUD bridge is best-effort
            pass
        self.hud.log("[HUD] " + self.hud_mode.status_line())
        return {"ok": True, "hud_mode": on,
                "message": ("HUD mode on, Sir — the full animated TORVIS HUD."
                            if on else "HUD mode off, Sir — back to the normal view.")}

    def printer_status(self):
        """BUILD 18: 3D-printer hook status — plainly 'No 3D printer
        connected' unless an OctoPrint URL is set in Settings."""
        if b18 is None or self.printer is None:
            return {"connected": False, "configured": False,
                    "message": "No 3D printer connected, Sir."}
        return self.printer.status()

    def handle_build18_command(self, action, text=""):
        """BUILD 18: run a parsed BUILD 18 voice command, return one
        calm spoken line. Never raises."""
        if b18 is None:
            return "That feature is not available in this build, Sir."
        try:
            if action == "clap_wake_on":
                return self.set_clap_wake(True).get("message", "Clap wake on, Sir.")
            if action == "clap_wake_off":
                return self.set_clap_wake(False).get("message", "Clap wake off, Sir.")
            if action == "clap_wake_status":
                return self.clap_wake.status_line()
            if action == "clap_sensitivity":
                parsed = b18.parse_clap_command(text)
                return self.set_clap_sensitivity(
                    parsed.get("sensitivity", 0.5) if parsed else 0.5).get("message", "")
            if action == "gestures_on":
                return self.set_gestures(True).get("message", "Gestures on, Sir.")
            if action == "gestures_off":
                return self.set_gestures(False).get("message", "Gestures off, Sir.")
            if action == "gesture_status":
                return self.gestures.status_line()
            if action == "hud_mode_on":
                return self.set_hud_mode(True).get("message", "HUD mode on, Sir.")
            if action == "hud_mode_off":
                return self.set_hud_mode(False).get("message", "HUD mode off, Sir.")
            if action == "hud_mode_status":
                return self.hud_mode.status_line()
            if action == "printer_status":
                return self.printer_status().get("message", "No 3D printer connected, Sir.")
            return "I did not understand that command, Sir."
        except Exception as e:  # noqa: BLE001
            log_error("build18_command", e)
            return "That hit a snag, Sir — it is in jarvis.log."

    # ------------------------------------------------- BUILD 19: autopilot / sites / voice ---
    def autopilot_status(self):
        """BUILD 19: master + YouTube autopilot state dict."""
        if b19 is None or self.autopilot is None:
            return {"autopilot_enabled": False, "youtube_autopilot_enabled": False,
                    "indicator": "AUTOPILOT: OFF",
                    "message": "Autopilot is not available in this build, Sir."}
        return self.autopilot.status()

    def set_autopilot(self, on):
        """BUILD 19: turn master autopilot on/off. OFF by default."""
        if b19 is None or self.autopilot is None:
            return {"ok": False, "autopilot_enabled": False,
                    "message": "Autopilot is not available in this build, Sir."}
        if on:
            self.autopilot.enable()
            self.config["autopilot_enabled"] = True
            self.hud.log("[AUTOPILOT] Autopilot on, Sir — no confirm before doing things on your own PC and own accounts. " + b19.AUTOPILOT_WARNING)
            return {"ok": True, "autopilot_enabled": True,
                    "message": "Autopilot on, Sir — I will not ask for confirm before doing things on your own PC and your own accounts. " + b19.AUTOPILOT_WARNING}
        self.autopilot.disable()
        self.config["autopilot_enabled"] = False
        self.hud.log("[AUTOPILOT] Autopilot off, Sir — every confirm gate is back on.")
        return {"ok": True, "autopilot_enabled": False,
                "message": "Autopilot off, Sir — every confirm gate is back on."}

    def set_youtube_autopilot(self, on):
        """BUILD 19: turn YouTube autopilot on/off. OFF by default."""
        if b19 is None or self.autopilot is None:
            return {"ok": False, "youtube_autopilot_enabled": False,
                    "message": "YouTube autopilot is not available in this build, Sir."}
        if on:
            self.autopilot.enable_youtube()
            self.config["youtube_autopilot_enabled"] = True
            return {"ok": True, "youtube_autopilot_enabled": True,
                    "message": "YouTube autopilot on, Sir — uploads and posts need no confirm now. Posts are public and cannot be undone."}
        self.autopilot.disable_youtube()
        self.config["youtube_autopilot_enabled"] = False
        return {"ok": True, "youtube_autopilot_enabled": False,
                "message": "YouTube autopilot off, Sir — YouTube uploads need a confirm again (unless full autopilot is on)."}

    def set_voice_per_language(self, value):
        """BUILD 19: Settings voice-per-language list (cleaned)."""
        if b19 is None:
            return {}
        self.voice_per_language = b19.validate_per_language_voices(value)
        try:
            self.speaker.voice_per_language = dict(self.voice_per_language)
        except Exception:  # noqa: BLE001 — best-effort
            pass
        self.config["voice_per_language"] = dict(self.voice_per_language)
        return dict(self.voice_per_language)

    def pronunciation_status(self):
        """BUILD 19: which language voices are actually installed.
        Uses the pyttsx3 voice list on Windows; when that list is
        empty (HUD is the primary voice), it says so plainly."""
        if b19 is None:
            return {"ok": False, "languages": [], "missing": [],
                    "message": "Multilingual voice is not available in this build, Sir."}
        voices = []
        try:
            engine = self.speaker._get_engine() if hasattr(self.speaker, "_get_engine") else None
            if engine is not None:
                voices = list(engine.getProperty("voices") or [])
        except Exception:  # noqa: BLE001 — voice list is best-effort
            voices = []
        status = b19.pronunciation_status(voices, per_language=self.voice_per_language)
        status["voices_found"] = len(voices)
        if not voices:
            status["note"] = ("Voice list not available here, Sir — the HUD "
                              "is the primary voice. Check the installed "
                              "voices in Settings on your PC.")
        return status

    def watch_site(self, url):
        """BUILD 19: watch a site — read-only checking, no confirm."""
        if b19 is None or self.site_watcher is None:
            return {"ok": False, "error": "Site watcher is not available in this build, Sir."}
        res = self.site_watcher.add_site(url)
        if not res.get("ok"):
            return res
        return {"ok": True, "added": res.get("added"), "url": res.get("url"),
                "sites": list(self.site_watcher.sites), "message": res.get("message")}

    def site_status(self):
        """BUILD 19: check the watched sites now (read-only, no confirm)."""
        if b19 is None or self.site_watcher is None:
            return {"ok": False, "sites": [], "notifications": [],
                    "message": "Site watcher is not available in this build, Sir."}
        notes = self.site_watcher.check_all()
        return {"ok": True, "sites": list(self.site_watcher.sites),
                "notifications": notes, "last_status": self.site_watcher.last_status,
                "message": "All watched sites are up, Sir." if not notes else " ".join(notes)}

    def check_watched_sites(self):
        """BUILD 19: check watched sites when due (every 30 minutes),
        speak + log any down / back-up / changed notification. A check
        is read-only and never needs a confirm."""
        if b19 is None or self.site_watcher is None:
            return []
        if not self.site_watcher.due():
            return []
        notes = self.site_watcher.check_all()
        for note in notes:
            self.hud.log("🌐 " + note)
            self.speaker.say(clamp_for_speech(note))
        return notes

    def handle_build19_command(self, action, text=""):
        """BUILD 19: run a parsed BUILD 19 voice command, return one
        calm spoken line. Never raises."""
        if b19 is None:
            return "That feature is not available in this build, Sir."
        try:
            if action == "autopilot_on":
                return self.set_autopilot(True).get("message", "Autopilot on, Sir.")
            if action == "autopilot_off":
                return self.set_autopilot(False).get("message", "Autopilot off, Sir.")
            if action == "autopilot_status":
                return self.autopilot_status().get("indicator", "AUTOPILOT: OFF") if self.autopilot is not None else "Autopilot is not available in this build, Sir."
            if action == "youtube_autopilot_on":
                return self.set_youtube_autopilot(True).get("message", "YouTube autopilot on, Sir.")
            if action == "youtube_autopilot_off":
                return self.set_youtube_autopilot(False).get("message", "YouTube autopilot off, Sir.")
            if action == "youtube_autopilot_status":
                return self.autopilot.youtube_status_line() if self.autopilot is not None else "YouTube autopilot is not available in this build, Sir."
            if action == "watch_site":
                parsed = b19.parse_build19_command(text)
                return self.watch_site(parsed.get("url", "") if parsed else "").get("message", "Could not watch that site, Sir.")
            if action == "list_watched_sites":
                sites = self.site_watcher.sites if self.site_watcher is not None else []
                return ("I am watching these sites, Sir: " + ", ".join(sites)) if sites else "I am not watching any sites yet, Sir."
            if action == "site_status":
                return self.site_status().get("message", "Site check failed, Sir.")
            return "I did not understand that command, Sir."
        except Exception as e:  # noqa: BLE001
            log_error("build19_command", e)
            return "That hit a snag, Sir — it is in jarvis.log."

    # ------------------------------------------------------------- commands ---
    def _run_command(self, text):
        """A spoken (or otherwise routed) command: ask the brain on a
        worker thread, show the reply in the HUD, speak it clamped to
        at most 4 sentences. The user only ever sees the calm message —
        raw error details go to jarvis.log, never the screen."""
        if self.voice_quality is not None:
            self.voice_quality.start_request()
        # BUILD 19: autopilot / site-watcher commands are handled
        # locally, never sent to the brain as a chat question — "turn
        # autopilot on", "watch this site", "site status". And asked
        # directly whether TORVIS is human, it answers plainly: it is
        # TORVIS, an AI assistant — it only SOUNDS human.
        if b19 is not None:
            if b19.is_identity_question(text):
                reply = b19.IDENTITY_ANSWER
                self.hud.log("TORVIS: " + reply)
                self.speaker.say(clamp_for_speech(reply))
                return
            _b19 = b19.parse_build19_command(text)
            if _b19 is not None:
                reply = self.handle_build19_command(_b19.get("action"), text)
                self.hud.log("TORVIS: " + calm_reply(reply))
                spoken = clamp_for_speech(calm_reply(reply))
                self.speaker.say(spoken)
                return
        # BUILD 18: clap wake / gestures / HUD mode / printer commands
        # are handled locally, never sent to the brain as a chat
        # question — "turn clap wake on", "turn gestures on",
        # "show the hud", "printer status".
        if b18 is not None:
            _b18 = b18.parse_build18_command(text)
            if _b18 is not None:
                reply = self.handle_build18_command(_b18.get("action"), text)
                self.hud.log("TORVIS: " + calm_reply(reply))
                spoken = clamp_for_speech(calm_reply(reply))
                self.speaker.say(spoken)
                return
        # BUILD 17: camera voice commands are handled locally, never sent
        # to the brain as a chat question — "turn camera on", "take my
        # photo", "what do you see?", "test camera", "record a video".
        # A bare "confirm" while a recording is pending confirms the video.
        if b17 is not None and self.camera is not None:
            _cam = b17.parse_camera_command(text)
            if _cam is None and str(text or "").strip().lower() == "confirm" and self.camera.pending_recording:
                _cam = {"action": "record_video_confirm"}
            if _cam is not None:
                if _cam.get("action") == "record_video_confirm":
                    _r = self.record_camera_video(confirmed=True)
                    reply = _r.get("message") or _r.get("error") or "Recording done, Sir."
                else:
                    reply = self.handle_camera_command(_cam.get("action"), text)
            else:
                try:
                    reply = self._get_agent().chat(text)
                except Exception as e:  # noqa: BLE001
                    log_error("chat", e)
                    reply = ("⚠ Something went wrong asking the brain, Sir — "
                             "it's written to jarvis.log. One more try usually settles it.")
        else:
            try:
                reply = self._get_agent().chat(text)
            except Exception as e:  # noqa: BLE001
                log_error("chat", e)
                reply = ("⚠ Something went wrong asking the brain, Sir — "
                         "it's written to jarvis.log. One more try usually settles it.")
        # BUILD 15: strip "let me check" filler, never repeat yourself.
        if b15 is not None:
            reply = b15.strip_filler(reply)
        shown = calm_reply(reply)
        if shown != str(reply).strip():
            log_error("chat_details", reply)
        self.hud.log("TORVIS: " + shown)
        # BUILD 14 streaming: speak the first sentence as soon as the
        # reply exists, then queue the rest — the voice queue speaks
        # them in order, so nothing is cut.
        # BUILD 19 human-like speaking: the SPOKEN reply is short,
        # natural sentences with no robotic filler and no URLs/code
        # read aloud — the on-screen text above is unchanged.
        if b19 is not None:
            shown = b19.humanize_reply(shown)
        spoken = clamp_for_speech(shown)
        # BUILD 16: learn a stated preference ("I like short replies").
        if b16 is not None:
            _pref = b16.parse_preference_statement(text)
            if _pref and self.memory is not None:
                self.memory.remember_fact(f"Preference: {_pref[0]} = {_pref[1]}")
        # BUILD 15: never repeat the last reply out loud.
        if b15 is not None and b15.is_duplicate_reply(spoken, self._last_spoken_reply):
            self.hud.log("[VOICE] Skipped a repeated reply, Sir — I just said that.")
            if self.voice_quality is not None:
                self.voice_quality.record_reply_spoken(spoken, fully=True)
            return
        self._last_spoken_reply = spoken
        # BUILD 16: speak in chunks — first chunk immediately (low
        # latency), rest in queue order; stop at once if interrupted.
        chunks = b16.speak_chunks(spoken) if b16 is not None else [spoken]
        for i, chunk in enumerate(chunks):
            if self.barge_in is not None and self.barge_in.should_stop():
                self.hud.log("[VOICE] Stopped speaking — interrupted, Sir.")
                break
            self.speaker.say(chunk)
            if i == 0 and self.voice_quality is not None:
                self.voice_quality.record_first_spoken()
        if self.voice_quality is not None:
            self.voice_quality.record_reply_spoken(spoken, fully=True)
            self.hud.log(self.voice_quality.format_quality_line())
            if b16 is not None:
                _lat = self.voice_quality.latency_ms_to_first_word
                self.hud.log("[LATENCY] " + b16.latency_check(_lat)["status"] + " — " + b16.BRAIN_LATENCY_NOTE)
        if self.daily_stats is not None:
            _lat2 = self.voice_quality.latency_ms_to_first_word if self.voice_quality else None
            self.daily_stats.record_reply(latency_ms=_lat2, fully_spoken=True)

    # ---------------------------------------------------------- self-check ---
    def self_check(self):
        """Fast startup health report — deliberately NO model call, so
        it can never burn quota. Returns the lines; each also goes to
        the HUD log (buffered until the page is alive) so Sir sees
        exactly what is ready and the exact fix for anything missing."""
        lines = []
        cfg = self.config
        try:
            CFG_DIR.mkdir(parents=True, exist_ok=True)
            lines.append(f"[SELF-CHECK] Config folder ready — {CFG_DIR}")
        except Exception as e:  # noqa: BLE001
            log_error("self_check", e)
            lines.append("[SELF-CHECK] ⚠ Config folder not writable, Sir — "
                         "settings won't persist. Fix: check permissions on "
                         f"{CFG_DIR}")
        provider = str(cfg.get("provider") or "anthropic")
        if provider.lower() == "ollama":
            lines.append("[SELF-CHECK] Brain: Ollama (local — no API key needed).")
        elif cfg.get("api_key"):
            lines.append(f"[SELF-CHECK] Brain: {provider} · "
                         f"{cfg.get('model') or 'default model'} — key present.")
        else:
            lines.append("[SELF-CHECK] ⚠ Brain has NO API key, Sir — chat "
                         "can't answer until one is set. Fix: add \"api_key\" "
                         f"in {CFG_FILE} (the same file NOVA uses), or switch "
                         "the provider to ollama.")
        n = len(cfg.get("protected_paths") or [])
        lines.append(f"[SELF-CHECK] Protected list loaded — {n} item(s) "
                     "TORVIS will never touch.")
        if SR_OK:
            lines.append("[SELF-CHECK] Microphone stack ready — wake word "
                         "can be switched on from the tray.")
        else:
            lines.append("[SELF-CHECK] Microphone stack not found — wake word "
                         "stays OFF; typed HUD commands still go to the real brain.")
        # BUILD 14: HUD speechSynthesis is the primary voice; pyttsx3
        # is the backup (wake word / HUD hidden). Both are reported so
        # a silent reply is diagnosable from this one screen.
        lines.append("[SELF-CHECK] Voice primary: HUD speechSynthesis — "
                     "speaks every reply the HUD shows.")
        if TTS_OK and self.speaker.available:
            lines.append("[SELF-CHECK] Voice backup: pyttsx3 ready — "
                         "speaks when the HUD is hidden or speechSynthesis fails.")
        else:
            lines.append("[SELF-CHECK] Voice backup: pyttsx3 unavailable — "
                         "replies will be text-only if the HUD voice fails.")
        lines.append("[SELF-CHECK] Voice queue: FIFO, replies are spoken "
                     "in order and never cut. Say 'stop speaking' or press "
                     "STOP SPEAKING to interrupt.")
        if self.memory is not None:
            lines.append(f"[SELF-CHECK] Memory loaded — "
                         f"{len(self.memory.facts())} fact(s), "
                         f"{len(self.memory.tasks())} open task(s). "
                         "Say 'remember this …' to add one.")
        if self.reminders is not None:
            due = self.reminders.due()
            lines.append(f"[SELF-CHECK] Reminders: "
                         f"{len(self.reminders.upcoming())} upcoming, "
                         f"{len(due)} due now.")
        if b14 is not None:
            lines.append("[SELF-CHECK] Language: English, Roman Urdu and "
                         "Urdu — TORVIS replies in the mix you used.")
        if b15 is not None:
            lines.append("[SELF-CHECK] Voice: neural voice first — "
                         "Microsoft Ryan/Guy/Aria Online (Natural) when Windows offers one; "
                         "voice picker in Settings (voice_name). Rate 1.0, pitch 1.0, natural pauses.")
            if self.chat_history is not None:
                lines.append(f"[SELF-CHECK] Chat memory loaded — "
                             f"{len(self.chat_history.turns)} turn(s) saved; "
                             "ask 'what were we working on?' to resume.")
                lw = self.chat_history.what_were_we_working_on()
                lines.append(f"[SELF-CHECK] Last work: {lw[:160]}")
            if self.calendar is not None:
                st = self.calendar.status()
                if st.get("connected"):
                    lines.append("[SELF-CHECK] Google Calendar: connected — today's meetings will be in the briefing.")
                else:
                    lines.append("[SELF-CHECK] Google Calendar: not connected — " + str(st.get("error") or "connect it in Settings."))
            if self.gmail is not None:
                gst = self.gmail.status()
                lines.append("[SELF-CHECK] Gmail: " + ("connected (read-only)." if gst.get("connected") else "not connected — " + str(gst.get("error") or "connect it in Settings.")))
            if self.voice_quality is not None:
                lines.append("[SELF-CHECK] " + self.voice_quality.format_quality_line().replace("[VOICE-QUALITY] ", "Voice quality: ", 1))
        if b16 is not None:
            lines.append("[SELF-CHECK] TORVIS BUILD 16 — voice: neural first, barge-in (STOP SPEAKING), pause threshold "
                         f"{self.config.get('pause_threshold', 0.8)}s so short pauses do not cut you off.")
            lines.append("[SELF-CHECK] Privacy: local only — voice, transcripts, memory and tokens stay on this PC; only brain text leaves it.")
            if self.daily_stats is not None:
                lines.append("[SELF-CHECK] " + self.daily_stats.format_stats_line())
        if b17 is not None:
            lines.append(b17.camera_self_check_line(self.camera))
        if b18 is not None:
            lines.extend(b18.build18_self_check_lines(
                self.clap_wake, self.gestures, self.hud_mode, self.printer,
                {"backend": "not checked yet"}))
        if b19 is not None:
            lines.extend(b19.build19_self_check_lines(
                self.autopilot, self.site_watcher))
        lines.append(f"[SELF-CHECK] Screen Watch is "
                     f"{'ON' if cfg.get('screen_watch_enabled') else 'OFF'}; "
                     f"wake word is {'ON' if cfg.get('wake_word_enabled') else 'OFF'}.")
        for ln in lines:
            self.hud.log(ln)
        return lines

    # ------------------------------------------------------------- tray ---
    def _post(self, kind):
        """Tray callbacks do exactly one thing — post an event — and
        even that is guarded: a tray hiccup must never crash the app."""
        try:
            self.events.put((kind, ""))
        except Exception as e:  # noqa: BLE001
            log_error("tray", e)

    def _tray_image(self):
        try:
            return Image.open(bundled_file("icon.ico")).convert("RGBA")
        except Exception:  # noqa: BLE001 — fall back to a drawn reactor dot
            img = Image.new("RGBA", (64, 64), (5, 11, 20, 255))
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 56, 56), outline=(0, 229, 255, 255), width=4)
            d.ellipse((24, 24, 40, 40), fill=(0, 229, 255, 255))
            return img

    def _start_tray(self):
        """Create the tray icon once, on its own thread. Callbacks never
        touch services directly — they post events to the app queue."""
        if not TRAY_OK or self._tray_icon is not None:
            return
        cfg = self.config
        menu = pystray.Menu(
            pystray.MenuItem("Show TORVIS",
                             lambda _i, _it: self._post("tray_restore"),
                             default=True),
            pystray.MenuItem("Hide TORVIS",
                             lambda _i, _it: self._post("hide_window")),
            pystray.MenuItem(
                lambda _it: "Wake word: " + ("On" if cfg.get("wake_word_enabled") else "Off"),
                lambda _i, _it: self._post("tray_toggle_wake"),
                checked=lambda _it: bool(cfg.get("wake_word_enabled"))),
            pystray.MenuItem(
                lambda _it: "Screen Watch: " + ("On" if cfg.get("screen_watch_enabled") else "Off"),
                lambda _i, _it: self._post("tray_toggle_watch"),
                checked=lambda _it: bool(cfg.get("screen_watch_enabled"))),
            pystray.MenuItem(
                lambda _it: "Voice: " + ("On" if cfg.get("voice_enabled", True) else "Off"),
                lambda _i, _it: self._post("tray_toggle_voice"),
                checked=lambda _it: bool(cfg.get("voice_enabled", True))),
            pystray.MenuItem("Quit TORVIS",
                             lambda _i, _it: self._post("tray_quit")),
        )
        self._tray_icon = pystray.Icon("TORVIS", self._tray_image(),
                                       "TORVIS — Personal AI Agent", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _update_tray_menu(self):
        if self._tray_icon is not None:
            try: self._tray_icon.update_menu()
            except Exception:  # noqa: BLE001
                pass

    def _notify_hidden(self):
        if self._tray_icon is not None and not self._tray_notified:
            self._tray_notified = True
            try:
                self._tray_icon.notify(
                    "TORVIS is still running here in the tray — right-click "
                    "for options, or just say \"Torvis\".", "TORVIS")
            except Exception:  # noqa: BLE001
                pass

    # -------------------------------------------------------- event pump ---
    def _dispatch_loop(self):
        """Single consumer for every service event, so tray threads, the
        wake listener and the watcher never race each other."""
        while not self._stop_event.is_set():
            try:
                kind, payload = self.events.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                if kind == "wake_ack":
                    self.hud.wake_heard("")
                    if winsound is not None:
                        try: winsound.Beep(880, 120)
                        except Exception:  # noqa: BLE001
                            pass
                    self.speaker.say("Yes, Sir?")
                elif kind == "wake_command":
                    self.hud.wake_heard(payload)
                    threading.Thread(target=self._run_command,
                                     args=(payload,), daemon=True).start()
                elif kind == "watch_suggestion":
                    self._watch_suggestion(payload)
                elif kind == "watch_skip_note":
                    self.hud.log("👁 Screen Watch: model busy, will look again shortly.")
                elif kind == "watch_hard_fail":
                    self._watch_hard_fail(payload)
                elif kind == "tray_restore":
                    if self._on_restore is not None:
                        self._on_restore()
                elif kind == "minimize_window":
                    # BUILD 18: minimise to the taskbar, NOT to tray-only.
                    # The window stays in the taskbar; clicking its
                    # taskbar icon restores it directly.
                    if self._on_minimize is not None:
                        self._on_minimize()
                    else:
                        try:
                            self.hud.window.minimize()
                        except Exception:  # noqa: BLE001
                            pass
                elif kind == "hide_window":
                    if self._on_hide is not None:
                        self._on_hide()
                    else:
                        try:
                            self.hud.window.hide()
                        except Exception:  # noqa: BLE001
                            pass
                    self._notify_hidden()
                elif kind == "tray_toggle_wake":
                    self.set_wake(not self.config.get("wake_word_enabled", False))
                elif kind == "tray_toggle_watch":
                    self.set_screen_watch(
                        not self.config.get("screen_watch_enabled", False),
                        source="tray")
                elif kind == "tray_toggle_voice":
                    self.set_voice(not self.config.get("voice_enabled", True))
                elif kind == "tray_quit":
                    self._stop_event.set()
                    if self._on_quit is not None:
                        self._on_quit()
            except Exception:  # noqa: BLE001 — the pump must survive anything
                pass

    # ------------------------------------------------------------ lifecycle ---
    def start_services(self):
        try:
            self.self_check()
        except Exception as e:  # noqa: BLE001 — even the check is guarded
            log_error("self_check", e)
        # BUILD 14 proactive: morning briefing once at startup, then
        # the reminder checker keeps watching in the background.
        try:
            briefing = self.morning_briefing()
            self.hud.log("🌅 " + briefing)
            self.check_due_reminders()
        except Exception as e:  # noqa: BLE001
            log_error("briefing", e)
        if self._reminder_thread is None:
            self._reminder_thread = threading.Thread(
                target=self._reminder_loop, daemon=True)
            self._reminder_thread.start()
        self._start_tray()
        threading.Thread(target=self._dispatch_loop, daemon=True).start()
        if self.config.get("wake_word_enabled"):
            self.set_wake(True)
        if self.config.get("screen_watch_enabled"):
            self.set_screen_watch(True, source="startup")

    def shutdown(self):
        self._really_quit = True
        self._stop_event.set()
        if self._wake_listener is not None:
            self._wake_listener.stop()
        self.watcher.stop()
        if self._tray_icon is not None:
            try: self._tray_icon.stop()
            except Exception:  # noqa: BLE001
                pass
            self._tray_icon = None


def _run_window(app):
    """The HUD in its own pywebview window, maximized but NOT fullscreen,
    so the Windows taskbar stays visible (BUILD 8, approved 2026-10-26).
    BUILD 18: minimise stays in the Windows taskbar AND in the tray —
    it must NOT hide to tray-only; clicking the taskbar icon restores
    the window directly. Close still hides to the tray — TORVIS keeps
    listening and watching from there. Returns when the window is
    really destroyed (tray Quit)."""
    hud_url = bundled_file("jarvis-hud.html").as_uri()
    window = webview.create_window("J.A.R.V.I.S.", url=hud_url,
                                   js_api=JsApi(app), fullscreen=False)

    def _maximize_on_shown():
        # Best effort: fullscreen=False alone already keeps the taskbar
        # visible; maximizing just fills the rest of the screen. If the
        # backend has no maximize, the window still opens normally.
        try: window.maximize()
        except Exception:  # noqa: BLE001 — normal window is fine
            pass

    try: window.events.shown += _maximize_on_shown
    except Exception:  # noqa: BLE001 — maximize attempt is optional
        pass
    app.hud.window = window

    def on_closing():
        if app._really_quit:
            return True
        try: window.hide()
        except Exception:  # noqa: BLE001
            pass
        app._notify_hidden()
        return False    # veto the close — hide to tray instead

    def on_minimized():
        # BUILD 18: minimising must NOT hide the window to tray-only.
        # The window stays in the Windows taskbar (and the tray icon
        # stays running), so clicking the taskbar icon restores it
        # directly — no need to go to the tray first. Do nothing here.
        if not app._really_quit:
            try:
                app.hud.log("[TASKBAR] Minimised to the taskbar, Sir — "
                            "click the taskbar icon to bring TORVIS back.")
            except Exception:  # noqa: BLE001
                pass

    try:
        window.events.closing += on_closing
    except Exception:  # noqa: BLE001
        pass
    try:
        window.events.minimized += on_minimized
    except Exception:  # noqa: BLE001
        pass

    def _restore():
        try:
            window.show()
            window.restore()
        except Exception:  # noqa: BLE001
            pass

    def _hide():
        try:
            window.hide()
        except Exception:  # noqa: BLE001
            pass

    def _minimize():
        # BUILD 18: minimise the window itself — never hide it, so it
        # stays in the Windows taskbar for one-click restore.
        try:
            window.minimize()
        except Exception:  # noqa: BLE001
            pass

    def _quit():
        app.shutdown()
        try: window.destroy()
        except Exception:  # noqa: BLE001
            pass

    # Single event consumer (the dispatcher started in start_services);
    # it reaches the window through these hooks.
    app._on_restore = _restore
    app._on_hide = _hide
    app._on_minimize = _minimize
    app._on_quit = _quit
    webview.start()
    app.shutdown()


def _run_headless(app):
    """Fallback face: the HUD in the default browser (demo mode there),
    while the native services keep running behind the tray icon."""
    webbrowser.open(bundled_file("jarvis-hud.html").as_uri())
    print("HUD opened in your browser. Native services are running; "
          "use the tray icon to quit.")
    app._stop_event.wait()
    app.shutdown()


def main():
    # Last-resort nets: an exception ANYWHERE is written to jarvis.log,
    # never splashed across the user's screen as a traceback.
    sys.excepthook = lambda *a: log_error("uncaught", a[1] if len(a) > 1 else a)
    def _thread_hook(args):
        log_error("thread", getattr(args, "exc_value", None) or str(args))
    threading.excepthook = _thread_hook

    try:
        config = load_config()
    except Exception as e:  # noqa: BLE001 — load_config already defaults
        log_error("config", e)          # on bad files; this is belt+braces
        config = dict(DEFAULTS)
    app = JarvisApp(config)
    try:
        app.start_services()
    except Exception as e:  # noqa: BLE001
        log_error("services", e)
        app.hud.log("⚠ Some background services failed to start, Sir — "
                    "details are in jarvis.log. The HUD still works.")
    if webview is not None:
        try:
            _run_window(app)
        except Exception as e:  # noqa: BLE001 — WebView2 missing/broken:
            log_error("webview", e)     # fall back to the browser face
            print("The app window failed to open — using your browser instead.")
            _run_headless(app)
    else:
        _run_headless(app)


if __name__ == "__main__":
    main()
