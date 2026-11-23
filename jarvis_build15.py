"""BUILD 15 pure logic — no mic, screen, network or Windows-only code.

BUILD 15 (2026-11-21) — FULL CHAT MEMORY, GOOGLE CALENDAR (READ-ONLY),
WORLD'S-BEST VOICE: NEURAL VOICE, LOW LATENCY, NEVER SILENT.
Marker: "BUILD 15 — FULL CHAT MEMORY, GOOGLE CALENDAR, NEURAL VOICE,
LOW LATENCY, NEVER SILENT, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI
LITE FALLBACK"

Best means best, not just good enough — Faizan's words. So BUILD 15
raises the bar on the voice itself, on top of the two features he
asked for (full chat memory + Google Calendar meetings):

* Voice: the best available Windows neural voice is primary —
  Microsoft Edge / Windows SAPI "Online (Natural)" voices (Ryan,
  Guy, Aria, Christopher, Sonia, Jenny) — picked by priority, with a
  voice picker in Settings (voice_name). Natural speed/pitch
  (rate 1.0, pitch 1.0 in the HUD; pyttsx3 backup stays at 165).
* Latency: first sentence spoken immediately, replies short and
  natural by default (1-3 sentences), no "let me check" filler,
  no long pauses.
* Never silent / never dropped / never repeated: FIFO queue (BUILD
  14) + a duplicate-reply guard + a VoiceQualityTracker that logs
  engine used, latency to first spoken word, and whether the last
  reply was fully spoken, in the Task Log.
* No paid APIs. Everything here is free: Windows neural voices are
  built into Windows/Edge, Google Calendar read is free, Mistral
  free tier + Gemini Lite fallback are unchanged.

Everything in this file is unit-testable on Linux with the standard
library only. Google API calls are lazy (imported only when the
calendar is actually used) and injectable in tests.
"""
import json, os, re, time
from datetime import datetime, timedelta, date
from pathlib import Path

import jarvis_build14 as b14

BUILD15_MARKER = "BUILD 15 — FULL CHAT MEMORY, GOOGLE CALENDAR, NEURAL VOICE, LOW LATENCY, NEVER SILENT, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK"
# The marker BUILD 14 tests look for must still be present in the
# shipped files; BUILD 15 supersedes it in the HUD/Settings line.
BUILD14_MARKER = b14.BUILD14_MARKER

MAX_HISTORY_TURNS = 200          # hard cap on stored turns
CONTEXT_TURNS = 12               # last N turns loaded into the brain
SUMMARY_AFTER_TURNS = 12         # summarise older turns once past this

# ------------------------------------------------------------ paths ---
def default_chat_history_path():
    """Chat history lives next to memory: %APPDATA%\\NovaAgent\\
    jarvis-chat-history.json when APPDATA exists, else the JARVIS
    work drive folder. Never on the system drive root, never C:."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "NovaAgent" / "jarvis-chat-history.json"
    return b14.work_drive_path() / "jarvis-chat-history.json"

def default_calendar_token_path():
    """Google Calendar OAuth token (created by the one-time sign-in
    in the user's own browser). Never in chat, never in the repo."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "NovaAgent" / "google-calendar-token.json"
    return b14.work_drive_path() / "google-calendar-token.json"

def default_calendar_credentials_path():
    """Google Cloud OAuth client secrets (credentials.json) — the
    user downloads this once from Google Cloud Console. Same folder
    as the token, never in chat, never in the repo."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "NovaAgent" / "google-calendar-credentials.json"
    return b14.work_drive_path() / "google-calendar-credentials.json"

GOOGLE_CALENDAR_PIP = "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
GOOGLE_CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# ------------------------------------------------------------ chat memory ---
def _topic_of(text, words=7):
    """A short topic phrase from a user turn: first few words, cleaned."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = re.sub(r"^(jarvis|hey jarvis|nova)[, ]+", "", t, flags=re.I)
    parts = t.split(" ")[:words]
    return " ".join(parts).strip(" .,?!") or "something"

def summarise_turns(turns, keep=CONTEXT_TURNS):
    """Rolling summary of the OLDER turns (everything before the last
    `keep` turns). Deterministic, no model call, so it costs nothing
    and works offline. Returns '' when there is nothing older."""
    older = list(turns or [])[:-keep] if len(turns or []) > keep else []
    if not older:
        return ""
    topics = []
    for turn in older:
        if turn.get("role") != "user":
            continue
        topic = _topic_of(turn.get("text") or "")
        if topic and topic not in topics:
            topics.append(topic)
    if not topics:
        return ""
    return "Earlier we talked about: " + "; ".join(topics[:6]) + "."

class ChatHistoryStore:
    """Persistent conversation history across restarts. JSON on disk:
    {"turns": [{"role", "text", "at"}], "summary": "..."}.
    Every user + JARVIS turn is saved with date/time. On startup the
    last CONTEXT_TURNS turns go into the brain; older turns collapse
    into the rolling summary, so context stays small."""
    def __init__(self, path=None):
        self.path = Path(path) if path else default_chat_history_path()
        self.turns = []
        self.summary = ""
        self.load()

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.turns = [dict(x) for x in (raw.get("turns") or [])
                              if isinstance(x, dict) and x.get("role") in ("user", "assistant")]
                self.summary = str(raw.get("summary") or "")
        except Exception:  # noqa: BLE001 — missing/corrupt = empty history
            self.turns, self.summary = [], ""
        return self.turns

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"turns": self.turns, "summary": self.summary},
                                      indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return True
        except Exception:  # noqa: BLE001
            return False

    def add(self, role, text, at=None):
        t = str(text or "").strip()
        if role not in ("user", "assistant") or not t:
            return False
        self.turns.append({"role": role, "text": t,
                           "at": (at or datetime.now()).isoformat(timespec="minutes")})
        self.turns = self.turns[-MAX_HISTORY_TURNS:]
        if len(self.turns) > SUMMARY_AFTER_TURNS:
            new_summary = summarise_turns(self.turns)
            if new_summary:
                self.summary = new_summary
        return self.save()

    def recent(self, n=CONTEXT_TURNS):
        return list(self.turns[-n:])

    def last_user_turn(self):
        for turn in reversed(self.turns):
            if turn.get("role") == "user":
                return turn
        return None

    def last_assistant_turn(self):
        for turn in reversed(self.turns):
            if turn.get("role") == "assistant":
                return turn
        return None

    def what_were_we_working_on(self):
        """What JARVIS says on startup / when asked 'what were we
        working on?' — no re-explaining needed from the user."""
        last_user = self.last_user_turn()
        if last_user is None:
            return "We haven't talked yet, Sir — a fresh start."
        last_ai = self.last_assistant_turn()
        reply = b14.first_sentence(last_ai.get("text") or "") if last_ai else ""
        out = f"Last we were working on: {last_user.get('text')}"
        if reply:
            out += f" — I replied: {reply}"
        if self.summary:
            out += f" {self.summary}"
        return out

    def as_prompt_lines(self):
        """History as system-prompt lines: rolling summary + recent turns."""
        lines = []
        if self.summary:
            lines.append(self.summary)
        for turn in self.recent():
            who = "User" if turn.get("role") == "user" else "JARVIS"
            lines.append(f"{who}: {turn.get('text')}")
        return lines

# ------------------------------------------------------------ calendar ---
def _parse_event_time(value):
    """Google event start/end: {'dateTime': '2026-11-21T09:30:00+05:00'}
    or {'date': '2026-11-21'} (all-day). Returns (datetime, all_day)."""
    if not isinstance(value, dict):
        return None, False
    if value.get("dateTime"):
        s = str(value["dateTime"]).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s), False
        except ValueError:
            return None, False
    if value.get("date"):
        try:
            d = date.fromisoformat(str(value["date"]))
            return datetime(d.year, d.month, d.day), True
        except ValueError:
            return None, False
    return None, False

def parse_event(raw):
    """One Google Calendar event dict -> a clean, testable dict.
    Pure function; no Google call."""
    raw = raw or {}
    start, all_day = _parse_event_time(raw.get("start") or {})
    end, _ = _parse_event_time(raw.get("end") or {})
    return {"title": str(raw.get("summary") or "(No title)"),
            "start": start, "end": end, "all_day": all_day,
            "location": str(raw.get("location") or ""),
            "description": str(raw.get("description") or "")}

def format_event_time(event):
    """'9:30 AM' for a timed event, 'All day' for an all-day one."""
    if event.get("all_day"):
        return "All day"
    start = event.get("start")
    if start is None:
        return "No time"
    return start.strftime("%I:%M %p").lstrip("0")

def format_event_line(event):
    line = f"{format_event_time(event)} — {event.get('title')}"
    if event.get("location"):
        line += f" ({event['location']})"
    return line

def events_on_day(events, day):
    """Events whose start falls on `day` (a date), sorted by time.
    All-day events sort first."""
    day = day if isinstance(day, date) else day.date()
    out = []
    for ev in events or []:
        start = ev.get("start")
        if start is None:
            continue
        ev_day = start.date() if isinstance(start, datetime) else start
        if ev_day == day:
            out.append(ev)
    out.sort(key=lambda e: (not e.get("all_day"), e.get("start") or datetime.min))
    return out

def next_meeting(events, now=None):
    """The next meeting at/after `now`, or None."""
    now = now or datetime.now()
    upcoming = []
    for ev in events or []:
        start = ev.get("start")
        if start is None:
            continue
        # All-day events have no useful "next" time; skip them here.
        if ev.get("all_day"):
            continue
        # Compare timezone-naive vs aware safely: drop tzinfo.
        s = start.replace(tzinfo=None) if start.tzinfo is not None else start
        n = now.replace(tzinfo=None) if now.tzinfo is not None else now
        if s >= n:
            upcoming.append((s, ev))
    if not upcoming:
        return None
    upcoming.sort(key=lambda x: x[0])
    return upcoming[0][1]

def format_todays_schedule(events, day=None, calendar_connected=True):
    """Today's meetings as one plain paragraph. If the calendar is
    NOT connected, say so plainly — never invent meetings."""
    day = day or date.today()
    if not calendar_connected:
        return ("Calendar not connected yet — connect it in Settings "
                "(Google Calendar, one-time sign-in), Sir, and I will "
                "read today's meetings for you.")
    todays = events_on_day(events, day)
    if not todays:
        return f"No meetings today ({day.strftime('%A %d %B')}), Sir — a clear day."
    lines = [format_event_line(ev) for ev in todays]
    return (f"Today, {day.strftime('%A %d %B')}, you have {len(todays)} "
            f"meeting(s): " + "; ".join(lines) + ".")

def format_startup_briefing(when, meetings, calendar_connected,
                            reminders, facts, tasks, last_work):
    """BUILD 15 startup briefing: date, today's meetings, due
    reminders, remembered facts/tasks, and what we were last working
    on. Pure function."""
    lines = [f"Good morning, Sir. Today is {when.strftime('%A %d %B %Y')}."]
    lines.append(format_todays_schedule(meetings, when.date(), calendar_connected))
    if reminders:
        lines.append("Reminders due: " + "; ".join(reminders) + ".")
    if tasks:
        lines.append(f"You have {len(tasks)} open task(s): " + "; ".join(tasks[:5]) + ".")
    if facts:
        lines.append("I remember: " + "; ".join(facts[:5]) + ".")
    if last_work:
        lines.append(last_work)
    return " ".join(lines)

class CalendarClient:
    """Read-only Google Calendar (official API, OAuth2 only — never a
    password, never Chrome-login automation). The Google libraries
    are imported lazily, only when the calendar is actually used, so
    JARVIS starts fine without them. `service` is injectable in
    tests (a fake with .events().list().execute())."""
    def __init__(self, token_path=None, credentials_path=None):
        self.token_path = Path(token_path) if token_path else default_calendar_token_path()
        self.credentials_path = (Path(credentials_path) if credentials_path
                                 else default_calendar_credentials_path())

    def status(self):
        """What the briefing/Settings shows: connected, or exactly
        what is missing (token? credentials file? libraries?)."""
        missing_libs = []
        for mod in ("googleapiclient", "google.oauth2.credentials",
                    "google_auth_oauthlib.flow"):
            try:
                __import__(mod)
            except Exception:  # noqa: BLE001
                missing_libs.append(mod)
        if missing_libs:
            return {"connected": False, "missing_libs": missing_libs,
                    "error": f"Calendar not connected yet — Google Calendar libraries are not installed, Sir. Run: {GOOGLE_CALENDAR_PIP}",
                    "token_found": self.token_path.exists(),
                    "credentials_found": self.credentials_path.exists()}
        if not self.token_path.exists():
            return {"connected": False, "missing_libs": [],
                    "error": ("Calendar not connected yet — connect it in Settings "
                              "(Google Calendar, one-time sign-in in your own browser)."),
                    "token_found": False,
                    "credentials_found": self.credentials_path.exists()}
        return {"connected": True, "missing_libs": [], "error": "",
                "token_found": True,
                "credentials_found": self.credentials_path.exists()}

    def fetch_today_events(self, service=None, day=None):
        """Today's events as parsed dicts. Returns {"ok": bool,
        "events": [...], "error": "..."}. Never raises, never invents
        meetings: not-connected / no-libraries / API failure all come
        back as ok=False with a plain message."""
        day = day or date.today()
        if service is None:
            st = self.status()
            if not st["connected"]:
                return {"ok": False, "events": [], "error": st["error"],
                        "connected": False}
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), GOOGLE_CALENDAR_SCOPES)
                service = build("calendar", "v3", credentials=creds)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "events": [],
                        "error": f"Google Calendar failed, Sir: {e}",
                        "connected": True}
        try:
            start = datetime(day.year, day.month, day.day).isoformat() + "Z"
            end = (datetime(day.year, day.month, day.day)
                   + timedelta(days=1)).isoformat() + "Z"
            result = (service.events().list(calendarId="primary",
                                            timeMin=start, timeMax=end,
                                            singleEvents=True,
                                            orderBy="startTime").execute())
            raw = result.get("items") or []
            return {"ok": True, "events": [parse_event(r) for r in raw],
                    "error": "", "connected": True}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "events": [],
                    "error": f"Google Calendar failed, Sir: {e}",
                    "connected": True}

    def create_event(self, parsed, service=None):
        """BUILD 16: book a calendar event (confirm-gated by the caller
        — this method never runs without a spoken 'confirm'). Needs a
        token with the calendar.events scope; a read-only token will
        fail plainly and JARVIS must ask Faizan to sign in again."""
        if service is None:
            st = self.status()
            if not st["connected"]:
                return {"ok": False, "error": st["error"]}
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path),
                    ["https://www.googleapis.com/auth/calendar.readonly",
                     "https://www.googleapis.com/auth/calendar.events"])
                service = build("calendar", "v3", credentials=creds)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"Google Calendar booking failed, Sir: {e}"}
        try:
            import jarvis_build16 as b16
            body = b16.build_event_body(parsed)
        except Exception:  # noqa: BLE001
            body = {"summary": parsed.get("title"),
                    "start": {"dateTime": parsed["start"].isoformat(), "timeZone": "Asia/Karachi"},
                    "end": {"dateTime": parsed["end"].isoformat(), "timeZone": "Asia/Karachi"}}
        try:
            result = service.events().insert(calendarId="primary", body=body).execute()
            return {"ok": True, "event_id": result.get("id"), "title": parsed.get("title"),
                    "start": parsed.get("start"), "end": parsed.get("end")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Google Calendar booking failed, Sir: {e}. If your token is read-only, sign in again in Settings so it gets booking permission."}

    def setup_instructions(self):
        """Exact one-time OAuth setup steps (also in README.md)."""
        return ("Google Calendar setup (one time, free): 1) Go to Google "
                "Cloud Console, create a project, enable the Google Calendar "
                "API, create OAuth client ID credentials (Desktop app), and "
                "download the credentials JSON. 2) Save it as "
                f"{self.credentials_path} 3) In JARVIS Settings, press "
                "'Connect Google Calendar' — it opens Google sign-in in your "
                "own browser; sign in once, allow read-only calendar access. "
                "4) The token is saved locally and never leaves this PC. "
                "No password is ever typed into JARVIS.")

# ------------------------------------------------------------ voice: best ---
# Windows neural voices, in priority order. These are the "Online
# (Natural)" voices built into Windows 11 / Edge — free, no API key,
# no paid service. A plain SAPI voice (e.g. "Microsoft David") is
# the fallback; a robotic voice is never preferred.
NEURAL_VOICE_PRIORITY = [
    "Microsoft Ryan Online (Natural)",
    "Microsoft Guy Online (Natural)",
    "Microsoft Aria Online (Natural)",
    "Microsoft Christopher Online (Natural)",
    "Microsoft Sonia Online (Natural)",
    "Microsoft Jenny Online (Natural)",
    "Microsoft Ryan Online",
    "Microsoft Guy Online",
    "Microsoft Aria Online",
    "Google UK English Male",
    "Microsoft David",
    "Ryan", "Guy", "Aria", "Christopher", "Sonia", "Jenny",
]
# Natural speech: rate 1.0, pitch 1.0 — BUILD 14 used 0.95 / 0.85,
# which is slower and deeper than a natural voice.
NATURAL_RATE = 1.0
NATURAL_PITCH = 1.0

def pick_neural_voice(available_names):
    """Best neural voice from the names Windows/Edge actually offers.
    Pure function. Returns the full name, or None when none match
    (then the caller falls back to any English voice)."""
    names = [str(n) for n in (available_names or [])]
    for wanted in NEURAL_VOICE_PRIORITY:
        for name in names:
            if wanted.lower() in name.lower():
                return name
    for name in names:
        if "natural" in name.lower() and ("en-gb" in name.lower() or "english" in name.lower()):
            return name
    return None

def pick_voice_for_text(available_names, text, preferred_name=""):
    """Voice picker: the user's chosen voice (Settings) first, then
    the best neural voice for the language. Urdu -> ur-PK voice."""
    if preferred_name:
        for name in (available_names or []):
            if preferred_name.lower() in str(name).lower():
                return name
    if b14.URDU_RE.search(str(text or "")):
        for name in (available_names or []):
            if "ur" in str(name).lower() and "pk" in str(name).lower():
                return name
    return pick_neural_voice(available_names)

# Filler that makes JARVIS sound slow / robotic. Strip it from the
# start of a spoken reply; the full text still shows on screen.
_FILLER_RE = re.compile(
    r"^(let me check( that)?( for you)?[,.]?\s+|"
    r"one moment( please)?[,.]?\s+|"
    r"just a moment[,.]?\s+|"
    r"hang on[,.]?\s+|"
    r"i'?ll check( that)?[,.]?\s+|"
    r"checking( that)?[,.]?\s+)", re.I)

def strip_filler(text):
    """Remove leading 'let me check' filler from a reply. Pure."""
    t = str(text or "")
    return _FILLER_RE.sub("", t, count=1).strip() or t

def _norm(text):
    return re.sub(r"[^a-z0-9 ]+", "", str(text or "").lower()).strip()

def is_duplicate_reply(text, last_text):
    """True when this reply is the same as the last one spoken —
    JARVIS must never repeat itself. Pure function."""
    a, b = _norm(text), _norm(last_text)
    return bool(a) and a == b

class VoiceQualityTracker:
    """Quality self-check for the Task Log: which engine spoke, how
    long to the first spoken word, and whether the last reply was
    fully spoken. No audio is analysed — this is timing + queue
    bookkeeping, so it works on any PC."""
    def __init__(self):
        self.engine = "HUD speechSynthesis (neural)"
        self.latency_ms_to_first_word = None
        self.last_reply_fully_spoken = None
        self.last_reply = ""
        self.failures = []
        self._request_started = None

    def start_request(self):
        self._request_started = time.monotonic()
        return self._request_started

    def record_first_spoken(self, engine=None):
        if engine:
            self.engine = engine
        if self._request_started is not None:
            self.latency_ms_to_first_word = round(
                (time.monotonic() - self._request_started) * 1000)
        return self.latency_ms_to_first_word

    def record_reply_spoken(self, text, fully=True):
        self.last_reply = str(text or "")
        self.last_reply_fully_spoken = bool(fully)
        return self.last_reply_fully_spoken

    def record_failed(self, reason):
        self.failures.append(str(reason))
        self.last_reply_fully_spoken = False
        return self.failures

    def report(self):
        return {"engine": self.engine,
                "latency_ms_to_first_word": self.latency_ms_to_first_word,
                "last_reply_fully_spoken": self.last_reply_fully_spoken,
                "last_reply": self.last_reply[:120],
                "failures": list(self.failures[-5:])}

    def format_quality_line(self):
        lat = self.latency_ms_to_first_word
        lat_s = f"{lat} ms" if lat is not None else "not measured yet"
        spoken = self.last_reply_fully_spoken
        spoken_s = ("yes" if spoken is True else
                    "no" if spoken is False else "not yet")
        return (f"[VOICE-QUALITY] Engine: {self.engine}; latency to first "
                f"spoken word: {lat_s}; last reply fully spoken: {spoken_s}.")

# ------------------------------------------------------------ voice tone ---
# Emotion in tone (free, on-device): the HUD varies rate/pitch a
# little by what the sentence IS — a question lifts, good news is a
# touch brighter, an apology is a touch slower/softer. Small shifts
# only (never a cartoon voice), and the words themselves stay the
# same. Pure function, so it is testable.
def tone_for(text):
    """(rate, pitch) for one sentence. Default is natural 1.0 / 1.0."""
    t = str(text or "").strip()
    if not t:
        return (NATURAL_RATE, NATURAL_PITCH)
    low = t.lower()
    if "?" in t:
        return (1.0, 1.08)
    if "!" in t or any(w in low for w in ("great", "done", "excellent", "wonderful", "amazing")):
        return (1.05, 1.1)
    if any(w in low for w in ("sorry", "unfortunately", "failed", "sadly", "couldn't", "could not")):
        return (0.95, 0.9)
    return (NATURAL_RATE, NATURAL_PITCH)

# ------------------------------------------------------------ meetings: alerts + daily summary ---
def due_meeting_alerts(events, now=None, window_minutes=15, already_alerted=None):
    """Meetings starting within the next `window_minutes` minutes
    that have NOT been alerted yet. Returns (alerts, new_alerted_set).
    Pure function — the app calls this from its reminder loop."""
    now = now or datetime.now()
    already = set(already_alerted or [])
    alerts, new_alerted = [], set(already)
    for ev in events or []:
        start = ev.get("start")
        if start is None or ev.get("all_day"):
            continue
        s = start.replace(tzinfo=None) if start.tzinfo is not None else start
        n = now.replace(tzinfo=None) if now.tzinfo is not None else now
        minutes = (s - n).total_seconds() / 60.0
        key = f"{ev.get('title')}|{s.isoformat()}"
        if 0 <= minutes <= window_minutes and key not in already:
            alerts.append(ev)
            new_alerted.add(key)
    return alerts, new_alerted

def format_meeting_alert(event):
    return (f"You have a meeting at {format_event_time(event)} — "
            f"{event.get('title')}. Starting in about 15 minutes, Sir.")

def daily_summary(turns, tasks, meetings, day=None):
    """One short end-of-day summary: what we talked about, open
    tasks, today's meetings. Pure function."""
    day = day or date.today()
    talked = [t.get("text") for t in (turns or []) if t.get("role") == "user"]
    lines = [f"Today, {day.strftime('%A %d %B')}, Sir."]
    if talked:
        lines.append("We talked about: " + "; ".join(_topic_of(t) for t in talked[-5:]) + ".")
    if tasks:
        lines.append(f"Open tasks: {len(tasks)} — " + "; ".join(tasks[:5]) + ".")
    if meetings:
        lines.append("Today's meetings: " + "; ".join(format_event_line(e) for e in meetings) + ".")
    if len(lines) == 1:
        lines.append("Nothing much today — a quiet day.")
    return " ".join(lines)

# ------------------------------------------------------------ H: drive only ---
def is_in_h_drive(path):
    """True only for paths inside H:\\JARVIS-Work\\. The H: rule is
    Faizan's: JARVIS's own files go only in H:, never C:."""
    try:
        p = Path(str(path or "")).resolve()
    except Exception:  # noqa: BLE001
        return False
    h = Path("H:/JARVIS-Work").resolve()
    try:
        return p == h or h in p.parents
    except Exception:  # noqa: BLE001
        return False

def search_h_drive(query, root=None):
    """Search file names under H:\\JARVIS-Work\\ only. `root` is
    injectable in tests (a fake H: folder). Returns a list of
    matching file paths (max 20). Never searches C:."""
    root = Path(root) if root else Path("H:/JARVIS-Work")
    q = str(query or "").lower().strip()
    if not q:
        return []
    out = []
    try:
        for p in root.rglob("*"):
            if p.is_file() and q in p.name.lower():
                out.append(str(p))
            if len(out) >= 20:
                break
    except Exception:  # noqa: BLE001 — missing drive = no results
        return []
    return out

# ------------------------------------------------------------ volume (hook) ---
VOLUME_ACTIONS = {"mute": "volumemute", "unmute": "volumemute",
                  "volume_up": "volumeup", "volume_down": "volumedown"}

def volume_control(action, presser=None):
    """Volume up/down/mute via the keyboard media keys (pyautogui on
    Windows). Hook-only when pyautogui is missing: a plain message
    saying what is needed, never a crash, never a silent failure."""
    key = VOLUME_ACTIONS.get(str(action or "").lower())
    if key is None:
        return {"ok": False, "error": "Volume actions are mute, volume_up or volume_down, Sir."}
    if presser is not None:
        return presser(key)
    try:
        import pyautogui  # type: ignore
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "Volume control needs pyautogui, Sir — it is not installed on this PC. Run: pip install pyautogui"}
    try:
        pyautogui.press(key)
        return {"ok": True, "action": str(action)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Volume control failed: {e}"}

# ------------------------------------------------------------ Gmail (hook) ---
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def default_gmail_token_path():
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "NovaAgent" / "google-gmail-token.json"
    return b14.work_drive_path() / "google-gmail-token.json"

class GmailClient:
    """Gmail READ-ONLY, official Google API, OAuth2 only — never a
    password, never Chrome-login automation. HOOK-ONLY until Faizan
    does the one-time Google sign-in: status() says exactly what is
    missing, fetch_latest() returns a plain message instead of
    inventing mail. `service` is injectable in tests."""
    def __init__(self, token_path=None, credentials_path=None):
        self.token_path = Path(token_path) if token_path else default_gmail_token_path()
        self.credentials_path = (Path(credentials_path) if credentials_path
                                 else default_calendar_credentials_path())

    def status(self):
        missing_libs = []
        for mod in ("googleapiclient", "google.oauth2.credentials",
                    "google_auth_oauthlib.flow"):
            try:
                __import__(mod)
            except Exception:  # noqa: BLE001
                missing_libs.append(mod)
        if missing_libs:
            return {"connected": False, "missing_libs": missing_libs,
                    "error": f"Gmail not connected yet — Gmail libraries are not installed, Sir. Run: {GOOGLE_CALENDAR_PIP}",
                    "token_found": self.token_path.exists()}
        if not self.token_path.exists():
            return {"connected": False, "missing_libs": [],
                    "error": ("Gmail is not connected yet — connect it in Settings "
                              "(Google, one-time sign-in in your own browser, read-only)."),
                    "token_found": False}
        return {"connected": True, "missing_libs": [], "error": "",
                "token_found": True}

    def fetch_latest(self, service=None, count=5):
        """Latest inbox mail, newest first. Returns {"ok", "messages",
        "error"}. Never raises, never invents mail."""
        if service is None:
            st = self.status()
            if not st["connected"]:
                return {"ok": False, "messages": [], "error": st["error"]}
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds = Credentials.from_authorized_user_file(
                    str(self.token_path), GMAIL_SCOPES)
                service = build("gmail", "v1", credentials=creds)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "messages": [],
                        "error": f"Gmail failed, Sir: {e}"}
        try:
            result = (service.users().messages().list(
                userId="me", maxResults=int(count)).execute())
            msgs = result.get("messages") or []
            out = []
            for m in msgs:
                detail = (service.users().messages().get(
                    userId="me", id=m.get("id"),
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"]).execute())
                headers = {h.get("name"): h.get("value")
                           for h in (detail.get("payload") or {}).get("headers") or []}
                out.append({"id": m.get("id"), "subject": headers.get("Subject", ""),
                            "from": headers.get("From", ""),
                            "date": headers.get("Date", ""),
                            "snippet": detail.get("snippet", "")})
            return {"ok": True, "messages": out, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "messages": [],
                    "error": f"Gmail failed, Sir: {e}"}
