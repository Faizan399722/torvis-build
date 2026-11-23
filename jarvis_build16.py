"""BUILD 16 pure logic — no mic, screen, network or Windows-only code.

BUILD 16 (2026-11-21) — WORLD-BEST VOICE AGENT CHECKLIST.
Marker: "BUILD 16 — WORLD-BEST VOICE: LOW LATENCY, BARGE-IN, NEURAL
TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS,
PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN,
GEMINI LITE FALLBACK"

Personal assistant for Faizan on his own Windows PC — NOT customer
support or sales. Audited against the world-best voice-agent
checklist Faizan pasted (Retell / Stream / Mastra / Rasa):

1. Ultra-low latency — speak the first chunk immediately. Honest
   limit, stated in code and README: the Mistral free API itself
   takes seconds, so sub-second *brain* latency is impossible free.
   What IS free: first-chunk speaking (first sentence/clause spoken
   as soon as the reply exists), short replies, no filler, and a
   latency target check on the TTS first chunk (<=800 ms after the
   reply is ready). Do NOT claim sub-second brain latency anywhere.
2. Barge-in / turn-taking — interrupt mid-sentence, stop at once,
   do not cut the user off on a short pause (pause threshold).
3. Expressive speech — warmth, urgency, apology, excitement, calm.
4. Accurate listening — accents, noise, fast speech, Roman Urdu +
   English code-switching. Windows built-in recognition where
   available; NO paid STT. If speech is not understood, say so and
   ask to repeat once — never guess.
5. Context/memory — BUILD 15 kept, plus preference learning.
6. Tool execution — calendar booking WITH a spoken confirm gate
   (deferred in BUILD 15, now added), plus one "check my status"
   briefing (calendar + reminders + last tasks + Gmail unread).
7. Guardrails/handoffs — no hallucination on sensitive facts:
   "I don't know" + check the source, never guess. Clean handoff:
   save full context to TASK-STATUS.md in H:\\JARVIS-Work\\ so Muse
   (or a later JARVIS) can pick it up.
8. Production stability — every voice/speech failure falls back
   and logs, never crashes. One [SELF-CHECK] block at startup.
9. Privacy — voice data, transcripts, memory, tokens stay LOCAL
   (H: drive / %APPDATA%); only the brain API he chose
   (Mistral/Gemini) ever receives text. No cloud recording.
10. Observability — transcripts, latency, task completion,
    failures in jarvis.log + a daily stats view + a "Voice Quality"
    report command.

Everything here is unit-testable on Linux with the standard library
only. Google API calls stay lazy / injectable (BUILD 15).
"""
import json, os, re
from datetime import datetime, timedelta, date
from pathlib import Path

import jarvis_build14 as b14
import jarvis_build15 as b15

BUILD16_MARKER = ("BUILD 16 — TORVIS: WORLD-BEST VOICE, LOW LATENCY, BARGE-IN, "
                  "NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR "
                  "BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, "
                  "ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK")
BUILD15_MARKER = b15.BUILD15_MARKER

# Latency targets (honest): TTS first chunk after the reply is ready.
# The free Mistral brain itself takes seconds — that is NOT counted
# here, and no code may claim otherwise.
FIRST_CHUNK_TARGET_MS = 800
FIRST_CHUNK_WARN_MS = 2000
BRAIN_LATENCY_NOTE = ("The free Mistral brain itself takes seconds, Sir — "
                      "sub-second brain latency is not possible on the free "
                      "tier. What is instant here is the first spoken chunk "
                      "once the reply is ready.")

def latency_check(latency_ms):
    """Check a first-chunk TTS latency against the target. Pure."""
    if latency_ms is None:
        return {"ok": None, "status": "not measured yet",
                "target_ms": FIRST_CHUNK_TARGET_MS,
                "note": BRAIN_LATENCY_NOTE}
    ms = int(latency_ms)
    if ms <= FIRST_CHUNK_TARGET_MS:
        return {"ok": True, "status": f"on target ({ms} ms <= {FIRST_CHUNK_TARGET_MS} ms)",
                "target_ms": FIRST_CHUNK_TARGET_MS, "note": BRAIN_LATENCY_NOTE}
    if ms <= FIRST_CHUNK_WARN_MS:
        return {"ok": True, "status": f"acceptable ({ms} ms, target {FIRST_CHUNK_TARGET_MS} ms)",
                "target_ms": FIRST_CHUNK_TARGET_MS, "note": BRAIN_LATENCY_NOTE}
    return {"ok": False, "status": f"slow ({ms} ms > {FIRST_CHUNK_WARN_MS} ms) — check the voice engine",
            "target_ms": FIRST_CHUNK_TARGET_MS, "note": BRAIN_LATENCY_NOTE}

# ------------------------------------------------------------ streaming chunks ---
_CHUNK_RE = re.compile(r"(?<=[.!?])\s+|(?<=,)\s+")

def speak_chunks(text):
    """Split a reply into speakable chunks: sentences first, long
    sentences split on commas, so the first chunk can be spoken
    immediately (streaming TTS, first-chunk first). Pure."""
    out = []
    for sent in b14.split_sentences(text):
        if len(sent) <= 90:
            out.append(sent)
        else:
            parts = [p.strip() for p in _CHUNK_RE.split(sent) if p.strip()]
            out.extend(parts if parts else [sent])
    return out

def first_chunk(text):
    chunks = speak_chunks(text)
    return chunks[0] if chunks else ""

# ------------------------------------------------------------ barge-in / turn-taking ---
DEFAULT_PAUSE_THRESHOLD = 0.8   # seconds of silence before a phrase ends
DEFAULT_LISTENING_SENSITIVITY = 0.5  # 0.0-1.0; higher = hears quieter speech

class BargeIn:
    """Interrupt handling: one flag, set by the user (button, wake
    word, 'stop speaking'), read by the speaker. stop() must be
    immediate — the speaker checks it between chunks."""
    def __init__(self):
        self.interrupted = False
        self.interrupt_count = 0

    def interrupt(self):
        self.interrupted = True
        self.interrupt_count += 1
        return True

    def clear(self):
        self.interrupted = False

    def should_stop(self):
        return self.interrupted

def should_end_phrase_on_pause(pause_seconds, threshold=DEFAULT_PAUSE_THRESHOLD):
    """Turn-taking: a short pause (thinking) does NOT end the phrase;
    only a pause at/over the threshold does. Pure."""
    try:
        return float(pause_seconds) >= float(threshold)
    except Exception:  # noqa: BLE001
        return False

def validate_listening_settings(pause_threshold=None, sensitivity=None):
    """Clamp listening settings to safe ranges; defaults when missing."""
    try:
        pause = float(pause_threshold) if pause_threshold is not None else DEFAULT_PAUSE_THRESHOLD
    except Exception:  # noqa: BLE001
        pause = DEFAULT_PAUSE_THRESHOLD
    pause = min(max(pause, 0.4), 2.0)
    try:
        sens = float(sensitivity) if sensitivity is not None else DEFAULT_LISTENING_SENSITIVITY
    except Exception:  # noqa: BLE001
        sens = DEFAULT_LISTENING_SENSITIVITY
    sens = min(max(sens, 0.0), 1.0)
    return {"pause_threshold": pause, "listening_sensitivity": sens}

# ------------------------------------------------------------ expressive tone ---
# BUILD 15 tone_for covered question / good-news / apology. BUILD 16
# adds warmth, urgency, excitement, calm — small rate/pitch shifts
# only, never a cartoon voice. Returns (rate, pitch, mood).
def tone16_for(text):
    """(rate, pitch, mood) for one sentence. Natural is 1.0 / 1.0."""
    t = str(text or "").strip()
    if not t:
        return (1.0, 1.0, "calm")
    low = t.lower()
    if any(w in low for w in ("urgent", "urgently", "right now", "immediately", "emergency", "hurry")):
        return (1.08, 1.05, "urgent")
    if any(w in low for w in ("sorry", "unfortunately", "failed", "sadly", "couldn't", "could not", "my apologies")):
        return (0.95, 0.9, "apologetic")
    if "?" in t:
        return (1.0, 1.08, "question")
    if "!" in t or any(w in low for w in ("amazing", "wonderful", "brilliant", "fantastic", "great news")):
        return (1.06, 1.12, "excited")
    if any(w in low for w in ("welcome", "good morning", "good evening", "thank you", "shukriya", "lovely", "happy")):
        return (1.0, 1.05, "warm")
    if any(w in low for w in ("take your time", "no rush", "relax", "calm", "slowly")):
        return (0.92, 0.95, "calm")
    return (1.0, 1.0, "calm")

# ------------------------------------------------------------ listening / STT fallback ---
def interpret_heard(text, confidence=None):
    """What to do with a recognised phrase. Low/empty recognition is
    NEVER guessed at: say so and ask to repeat once. Pure."""
    t = str(text or "").strip()
    if not t:
        return {"ok": False, "action": "ask_repeat",
                "reply": "Sorry, Sir — I didn't catch that. Could you say it once more, please?"}
    if confidence is not None:
        try:
            if float(confidence) < 0.4:
                return {"ok": False, "action": "ask_repeat",
                        "reply": "Sorry, Sir — that came through unclear. Could you say it once more, please?"}
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "action": "use", "reply": "", "text": t}

# ------------------------------------------------------------ preference learning ---
# Explicit statements ("I like short replies", "reply in Roman Urdu")
# plus the reply-length the user actually prefers.
_PREF_RE = re.compile(
    r"(?:i like|i prefer|i want|please (?:always )?)(?:\s+my)?(?:\s*reply in)?\s*"
    r"(short|long|detailed|brief|roman urdu|urdu|english|warm|calm|fast|slow)"
    r"(?:\s+replies|\s+answers)?", re.I)
_PREF_MAP = {"short": ("reply_length", "short"), "brief": ("reply_length", "short"),
             "long": ("reply_length", "long"), "detailed": ("reply_length", "long"),
             "roman urdu": ("language", "roman-urdu"), "urdu": ("language", "urdu"),
             "english": ("language", "english"), "warm": ("tone", "warm"),
             "calm": ("tone", "calm"), "fast": ("speed", "fast"), "slow": ("speed", "slow")}

def parse_preference_statement(text):
    """'I like short replies' -> ('reply_length', 'short'), else None. Pure."""
    m = _PREF_RE.search(str(text or ""))
    if not m:
        return None
    return _PREF_MAP.get(m.group(1).lower())

def apply_preferences(preferences, reply_length_default="short"):
    """Preferences as one system-prompt line. Pure."""
    prefs = dict(preferences or {})
    parts = []
    if prefs.get("reply_length") == "long":
        parts.append("Give detailed replies")
    elif prefs.get("reply_length") == "short":
        parts.append("Keep replies short (1-3 sentences)")
    if prefs.get("language"):
        parts.append(f"Reply in {prefs['language']}")
    if prefs.get("tone"):
        parts.append(f"Use a {prefs['tone']} tone")
    if prefs.get("speed") == "fast":
        parts.append("Answer quickly, no preamble")
    return "; ".join(parts) + "." if parts else ""

# ------------------------------------------------------------ calendar booking (confirm-gated) ---
# BUILD 15 was read-only on purpose. BUILD 16 adds booking, but ONLY
# with a spoken confirm first — two steps, like installs.
BOOK_EVENT_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_CREATE_RE = re.compile(
    r"(?:book|schedule|add|create)(?:\s+(?:a|an|a new))?\s+(?:meeting|event|call)?\s*"
    r"(?P<title>.+?)\s+(?:on\s+)?(?P<when>tomorrow|today|"
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
    r"(?:\s+\d{4})?)\s+at\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?"
    r"(?:\s+for\s+(?P<dur>\d+)\s*(?P<unit>min|mins|minutes|hour|hours))?", re.I)

def parse_create_event(text, now=None):
    """'Book a meeting with Ali tomorrow at 3pm for 30 minutes' ->
    {ok, title, start, end, duration_minutes} or {ok: False, error}.
    Pure; no Google call. Past times roll to tomorrow."""
    now = now or datetime.now()
    m = _CREATE_RE.search(str(text or ""))
    if not m:
        return {"ok": False, "error": "Say it like 'book a meeting with Ali tomorrow at 3pm for 30 minutes', Sir."}
    title = (m.group("title") or "Meeting").strip(" .")
    if title.lower().startswith(("with ", "to ", "for ")):
        title = "Meeting " + title
    hour = int(m.group("hour")); minute = int(m.group("minute") or 0)
    ampm = (m.group("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    when = (m.group("when") or "today").lower()
    day = now.date()
    if when == "tomorrow":
        day += timedelta(days=1)
    elif when in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        target = names.index(when)
        delta = (target - day.weekday()) % 7
        day += timedelta(days=delta if delta else 7)
    else:
        try:
            day = datetime.strptime(when, "%d %B %Y").date() if len(when.split()) == 3 else datetime.strptime(when + f" {now.year}", "%d %B %Y").date()
        except Exception:  # noqa: BLE001
            pass
    dur = int(m.group("dur") or 30)
    if (m.group("unit") or "").lower().startswith("hour"):
        dur *= 60
    start = datetime(day.year, day.month, day.day, hour, minute)
    if start <= now:
        start += timedelta(days=1)
    return {"ok": True, "title": title, "start": start,
            "end": start + timedelta(minutes=dur), "duration_minutes": dur}

def build_event_body(parsed):
    """Google Calendar event body from a parsed booking. Pure."""
    return {"summary": parsed["title"],
            "start": {"dateTime": parsed["start"].isoformat(), "timeZone": "Asia/Karachi"},
            "end": {"dateTime": parsed["end"].isoformat(), "timeZone": "Asia/Karachi"}}

def confirm_booking_text(parsed):
    return (f"I will book '{parsed['title']}' on "
            f"{parsed['start'].strftime('%A %d %B at %I:%M %p')} for "
            f"{parsed['duration_minutes']} minutes, Sir. Say 'confirm' to book it.")

def create_event_with_confirm(parsed, confirmed, service=None, client=None):
    """Two-step booking. confirmed=False -> plan only, nothing booked.
    confirmed=True -> insert via the injected/real service. Pure
    apart from the optional service call."""
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error", "I could not understand that booking, Sir.")}
    if not confirmed:
        return {"ok": False, "needs_confirm": True, "pending": parsed,
                "plan": confirm_booking_text(parsed)}
    if service is not None:
        try:
            result = service.events().insert(calendarId="primary", body=build_event_body(parsed)).execute()
            return {"ok": True, "event_id": result.get("id"), "title": parsed["title"],
                    "start": parsed["start"], "end": parsed["end"]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Booking failed, Sir: {e}"}
    if client is not None:
        return client.create_event(parsed, service=None)
    return {"ok": False, "error": "Calendar not connected yet, Sir — connect Google Calendar in Settings first."}

# ------------------------------------------------------------ check my status ---
def format_status_briefing(calendar_events, calendar_connected, reminders,
                           tasks, gmail_unread, last_work, when=None):
    """One 'check my status' briefing: calendar + reminders + last
    tasks + Gmail unread count, in one go. Pure."""
    when = when or datetime.now()
    lines = [f"Here is your status, Sir — {when.strftime('%A %d %B %Y')}."]
    lines.append(b15.format_todays_schedule(calendar_events, when.date(), calendar_connected))
    if reminders:
        lines.append("Reminders due: " + "; ".join(reminders) + ".")
    if tasks:
        lines.append(f"Open tasks ({len(tasks)}): " + "; ".join(tasks[:5]) + ".")
    if gmail_unread is None:
        lines.append("Gmail: not connected yet, Sir.")
    elif gmail_unread == 0:
        lines.append("Gmail: no unread mail, Sir.")
    else:
        lines.append(f"Gmail: {gmail_unread} unread message(s), Sir.")
    if last_work:
        lines.append(last_work)
    return " ".join(lines)

# ------------------------------------------------------------ guardrails: no hallucination ---
SENSITIVE_FACT_WORDS = {"price", "cost", "date", "time", "meeting", "when",
                        "how much", "deadline", "address", "phone", "email"}

def unknown_fact_reply(topic):
    """What JARVIS says when it does not know a fact: 'I don't know'
    + check the source, never guess. Pure."""
    t = str(topic or "that").strip()
    return (f"I don't know {t}, Sir — I won't guess. Let me check the "
            f"source for you, or you can tell me and I will remember it.")

def should_not_guess(text):
    """True when the user asks for a sensitive fact JARVIS must not
    invent (price/date/meeting/time). The brain must check a source
    (search / calendar / memory) first. Pure heuristic."""
    low = str(text or "").lower()
    return any(w in low for w in SENSITIVE_FACT_WORDS)

# ------------------------------------------------------------ handoff to Muse ---
def default_handoff_path():
    """TASK-STATUS.md lives in H:\\JARVIS-Work\\ — never C:. Injectable
    path in tests via save_handoff(path=...)."""
    return b14.work_drive_path() / "TASK-STATUS.md"

def format_handoff_md(context, when=None):
    """Full context for Muse / a later JARVIS, as TASK-STATUS.md. Pure."""
    when = when or datetime.now()
    ctx = dict(context or {})
    lines = ["# TASK-STATUS — handoff from JARVIS",
             f"Updated: {when.strftime('%Y-%m-%d %H:%M')}",
             "",
             f"## What we were doing",
             str(ctx.get("task") or ctx.get("last_work") or "Not recorded."),
             "",
             "## Open tasks"]
    for t in (ctx.get("tasks") or []):
        lines.append(f"- [ ] {t}")
    lines += ["", "## Last chat summary",
              str(ctx.get("summary") or ctx.get("last_chat") or "Not recorded."),
              "", "## Meetings / reminders",
              str(ctx.get("schedule") or "Not recorded."),
              "", "## Notes for Muse",
              str(ctx.get("notes") or "Pick this up where JARVIS left off — ask Faizan before changing anything already agreed.")]
    return "\n".join(lines) + "\n"

def save_handoff(context, path=None):
    """Save the handoff file. Returns {ok, path, error}. Never raises."""
    p = Path(path) if path else default_handoff_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(format_handoff_md(context), encoding="utf-8")
        return {"ok": True, "path": str(p), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": str(p), "error": f"Could not save the handoff, Sir: {e}"}

# ------------------------------------------------------------ privacy: local-only ---
PRIVACY_NOTE = (
    "Privacy — what leaves this PC and what does not: "
    "your voice, transcripts, chat history, memory, reminders and "
    "Google tokens stay LOCAL on this PC only — in H:\\JARVIS-Work\\ "
    "and %APPDATA%\\NovaAgent\\. Nothing is recorded to the cloud. No cloud recording. "
    "The ONLY thing that ever leaves this PC is the text of a question "
    "you ask, sent to the brain you chose (Mistral, or Gemini as "
    "fallback) so it can answer — no audio, no files, no tokens. "
    "Google Calendar / Gmail are read through Google's official API "
    "with your own one-time sign-in; Google sees only those API calls. "
    "Screen Watch screenshots exist in memory only for one glance, "
    "are never saved to disk or logged.")

def local_only_check(path):
    """True when a data path is local (APPDATA or H: drive) — never a
    cloud URL or a system-drive root. Pure."""
    s = str(path or "").strip()
    if not s:
        return False
    if s.lower().startswith(("http://", "https://", "ftp://")):
        return False
    p = Path(s)
    try:
        appdata = os.environ.get("APPDATA", "")
        if appdata and str(p).lower().startswith(appdata.lower()):
            return True
    except Exception:  # noqa: BLE001
        pass
    return b15.is_in_h_drive(s) or str(p).lower().startswith("h:\\") or str(p).lower().startswith("h:/")

# ------------------------------------------------------------ observability ---
class DailyStats:
    """Observability: transcripts, latency, task completion, failures.
    Stored as JSON next to memory; reported in the HUD/Task Log and
    by the 'Voice Quality' report command. Pure stdlib."""
    def __init__(self, path=None):
        self.path = Path(path) if path else b14.work_drive_path() / "jarvis-daily-stats.json"
        self.data = {"replies": 0, "fully_spoken": 0, "failed_speaks": 0,
                     "latencies_ms": [], "tasks_completed": 0,
                     "tasks_failed": 0, "failures": []}
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data.update(raw)
        except Exception:  # noqa: BLE001
            pass
        return self.data

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            return True
        except Exception:  # noqa: BLE001
            return False

    def record_reply(self, latency_ms=None, fully_spoken=True):
        self.data["replies"] += 1
        if fully_spoken:
            self.data["fully_spoken"] += 1
        else:
            self.data["failed_speaks"] += 1
        if latency_ms is not None:
            self.data["latencies_ms"].append(int(latency_ms))
            self.data["latencies_ms"] = self.data["latencies_ms"][-100:]
        return self.save()

    def record_task(self, completed=True):
        self.data["tasks_completed" if completed else "tasks_failed"] += 1
        return self.save()

    def record_failure(self, reason):
        self.data["failures"].append(str(reason)[:200])
        self.data["failures"] = self.data["failures"][-10:]
        return self.save()

    def average_latency_ms(self):
        lat = self.data.get("latencies_ms") or []
        return round(sum(lat) / len(lat)) if lat else None

    def stats(self):
        return {"replies": self.data["replies"],
                "fully_spoken": self.data["fully_spoken"],
                "failed_speaks": self.data["failed_speaks"],
                "average_latency_ms": self.average_latency_ms(),
                "latency_target_ms": FIRST_CHUNK_TARGET_MS,
                "tasks_completed": self.data["tasks_completed"],
                "tasks_failed": self.data["tasks_failed"],
                "recent_failures": list(self.data.get("failures") or [])[-5:]}

    def format_stats_line(self):
        s = self.stats()
        avg = s["average_latency_ms"]
        avg_s = f"{avg} ms" if avg is not None else "not measured yet"
        return (f"[DAILY-STATS] Replies spoken: {s['fully_spoken']}/{s['replies']} fully; "
                f"failed speaks: {s['failed_speaks']}; average latency to first spoken word: "
                f"{avg_s} (target {FIRST_CHUNK_TARGET_MS} ms); tasks done: "
                f"{s['tasks_completed']}, failed: {s['tasks_failed']}.")

# ------------------------------------------------------------ startup self-check ---
def format_self_check_block(status):
    """One [SELF-CHECK] block: voice, brain, memory, calendar, Gmail,
    privacy, listening. Pure — `status` is a dict of plain strings."""
    st = dict(status or {})
    lines = ["[SELF-CHECK] JARVIS startup — all systems:"]
    for key in ("voice", "brain", "memory", "calendar", "gmail", "listening", "privacy"):
        if key in st:
            lines.append(f"[SELF-CHECK] {key.capitalize()}: {st[key]}")
    return "\n".join(lines)

# ------------------------------------------------------------ ethical security mode ---
# BUILD 16 — ETHICAL SECURITY MODE. Safe, authorised-only security
# checks on YOUR OWN PC/network only. The rule, in code and README:
# TORVIS never scans, accesses, or attacks anyone else's system
# without their written permission, and refuses unauthorised hacking.
# Allowed targets only: this PC (localhost / 127.0.0.1 / ::1 / "my pc"
# / "this pc") and files under H:\\JARVIS-Work\\. Anything else is
# refused, plainly, with no partial result.
ETHICAL_SECURITY_RULE = (
    "Ethical security rule: TORVIS only checks YOUR OWN PC and YOUR OWN "
    "files — never anyone else's system, network, account or website "
    "without their written permission. Unauthorised scanning, hacking, "
    "password cracking, or accessing someone else's system is refused, "
    "plainly, every time.")

AUTHORISED_HOSTS = {"localhost", "127.0.0.1", "::1", "my pc", "this pc", "my computer", "this computer"}
WEAK_PASSWORDS = {"123456", "password", "123456789", "12345678", "12345",
                  "qwerty", "abc123", "password1", "admin", "letmein",
                  "welcome", "123123", "111111", "iloveyou", "monkey"}
COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
                993, 995, 1723, 3306, 3389, 5432, 5900, 8080]

def is_authorised_target(target):
    """True only for this PC / localhost / H: drive paths. Pure."""
    t = str(target or "").strip().lower()
    if not t:
        return False
    if t in AUTHORISED_HOSTS:
        return True
    if t.startswith("h:/") or t.startswith("h:\\"):
        return True
    return False

def refuse_unauthorised(target):
    return {"ok": False, "refused": True,
            "error": ("I can't do that, Sir — I only check your own PC and your own "
                      f"files. '{target}' is not your own system, and I never scan, "
                      "access, or attack someone else's system without their written "
                      "permission.")}

def check_open_ports(host="localhost", ports=None, connector=None):
    """Check which common ports are open on YOUR OWN PC only.
    `connector(host, port)` is injectable in tests (returns True if open).
    Refuses any other host. Never raises."""
    if not is_authorised_target(host):
        return refuse_unauthorised(host)
    ports = list(ports or COMMON_PORTS)
    open_ports, closed = [], []
    for port in ports:
        try:
            if connector is not None:
                is_open = bool(connector(host, int(port)))
            else:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                is_open = sock.connect_ex(("127.0.0.1", int(port))) == 0
                sock.close()
        except Exception:  # noqa: BLE001
            is_open = False
        (open_ports if is_open else closed).append(int(port))
    return {"ok": True, "host": "this PC (localhost)", "open_ports": open_ports,
            "closed_ports": closed,
            "advice": ("Open ports are normal for services you use, Sir. "
                       "If a port you do not recognise is open, tell me and I will explain what it is — "
                       "I will not close anything without your confirm.") if open_ports else
                      "No common ports are open on this PC, Sir — a good, quiet result."}

def _password_strength(value):
    """Weak / okay / strong, without ever returning the password. Pure."""
    v = str(value or "")
    if v.lower() in WEAK_PASSWORDS or len(v) < 8:
        return "weak"
    score = sum([len(v) >= 12, any(c.isdigit() for c in v),
                 any(c.isupper() for c in v), any(c in "!@#$%^&*_-+" for c in v)])
    return "strong" if score >= 3 else "okay"

def check_weak_passwords_in_file(path, confirmed=False):
    """Check passwords written in YOUR OWN file (H: drive only) for
    weakness — TWO-STEP, needs confirmed=True. NEVER returns the actual
    passwords: only line numbers, masked hints and strength. Refuses
    files outside H: and refuses without a confirm."""
    if not b15.is_in_h_drive(str(path or "")):
        return {"ok": False, "refused": True,
                "error": "I only check your own files in H:\\JARVIS-Work\\, Sir — never files elsewhere."}
    if not confirmed:
        return {"ok": False, "needs_confirm": True,
                "plan": (f"I will check the passwords written in {path} for weakness — "
                         "I will only report line numbers and strength, never the passwords themselves. "
                         "Say 'confirm' to check it.")}
    try:
        text = Path(str(path)).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not read that file, Sir: {e}"}
    found = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.search(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*(\S+)", line)
        if m:
            found.append({"line": i, "strength": _password_strength(m.group(1)),
                          "hint": f"{m.group(1)[:2]}*** ({len(m.group(1))} chars)"})
    weak = [f for f in found if f["strength"] == "weak"]
    return {"ok": True, "checked_lines": len(text.splitlines()),
            "passwords_found": len(found), "weak_count": len(weak),
            "findings": found,
            "advice": (f"{len(weak)} weak password(s) found, Sir — change those to long, unique passwords "
                       "and never reuse one. I have not shown any password itself.")
                      if weak else "No weak passwords found in that file, Sir."}

def scan_h_drive_files(root=None, max_files=200):
    """Scan YOUR OWN H: drive files: count by type, flag sensitive
    file names (.key / .pem / .env / passwords file) WITHOUT opening
    their contents, flag executables/scripts. H: only, never C:. Pure
    apart from the directory walk."""
    root = Path(root) if root else Path("H:/JARVIS-Work")
    if not b15.is_in_h_drive(str(root)):
        return {"ok": False, "refused": True,
                "error": "I only scan your own files in H:\\JARVIS-Work\\, Sir."}
    counts, sensitive, executables = {}, [], []
    total = 0
    try:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            total += 1
            ext = p.suffix.lower() or "(no extension)"
            counts[ext] = counts.get(ext, 0) + 1
            low = p.name.lower()
            if low.endswith((".key", ".pem", ".env")) or "password" in low:
                sensitive.append(str(p))
            if p.suffix.lower() in (".exe", ".msi", ".bat", ".ps1", ".vbs"):
                executables.append(str(p))
            if total >= max_files:
                break
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not scan that folder, Sir: {e}"}
    return {"ok": True, "total_files": total, "by_type": counts,
            "sensitive_files": sensitive, "executables": executables,
            "advice": ("Sensitive files found — keep .key/.pem/.env files in your Protected List "
                       "and never share them, Sir.") if sensitive else
                      "No sensitive file names found in your H: drive, Sir."}

def explain_security_risk(topic):
    """Explain a security risk in plain words — education only, never
    exploit instructions. Pure."""
    t = str(topic or "security").strip()
    return (f"Security risk — {t}: the risk is that someone who gets that "
            "information can pretend to be you or get into your accounts. "
            "The safe fix is: use long unique passwords, turn on two-factor "
            "sign-in where it is offered, keep your software updated, and "
            "never share passwords or secret files. I can check your own PC "
            "and your own H: drive files for these risks — I will never "
            "attack or scan anyone else's system.")
