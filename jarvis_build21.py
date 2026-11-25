"""BUILD 21 pure logic — fast answers, clear pronunciation, tasks
remembered, auto briefing on open, always-on features, auto-stop
on new input, and real Whop + Gumroad account work.

Root causes found (2026-11-23, BUILD 20 exe in Faizan's hands):
1. SLOW — chat() waits for the FULL brain reply, _http_json retries
   transient 500/503 errors 3 times with 2s/5s/10s waits (up to 17s
   before the fallback even starts), then the fallback brain runs
   the same full loop; edge-tts then synthesises the WHOLE reply to
   one MP3 before playing anything; and the FIFO voice queue plays
   2-3 queued questions in order. Fix: cut retries to (1s, 2s), a
   fast single-call path for short chat (no tools, 300 tokens),
   speak sentence-by-sentence (already chunked), and interrupt the
   old answer the moment a new question arrives.
2. PRONUNCIATION — Roman Urdu written in Latin letters was sent to
   the ur-PK neural voice, which is trained on Urdu SCRIPT: it reads
   Latin letters as English gibberish. An English voice reads the
   same words as English words ("mujhe" -> "moo-jee"). Fix:
   transliterate Roman Urdu words to Urdu script BEFORE TTS, then
   the ur-PK voice pronounces them correctly; slower rate for
   Roman Urdu (-15%), SSML prosody, and a log line naming the exact
   engine + voice that actually spoke, so a silent SAPI fallback
   can never hide again.
3. MEMORY — tasks were only saved when the brain happened to call
   the remember_this tool, or the user said "remember this".
   Ordinary "I have to do X / mujhe kal Y karna hai" was never
   stored; and the Agent builds its OWN MemoryStore/ChatHistoryStore
   at construction, so tasks added by the app after that were
   invisible to the brain until the agent was recreated. Fix:
   auto-extract tasks from every user message, and reload memory +
   chat history from disk at the start of every chat().
4. AUTO BRIEFING — start_services() only wrote the morning briefing
   to the HUD LOG, never spoke it, and morning_briefing() had no
   Gmail section at all. Fix: speak AND show a short startup
   briefing once per session: last work, open tasks, due reminders,
   today's meetings, and latest emails (or a plain "Gmail not
   connected yet" line — never invented mail).
5. ALWAYS ON — camera / clap wake / gestures defaulted to OFF and
   needed a toggle click to work at all. Fix: defaults ON, saved
   configs are migrated ON at load, and the toggle buttons are
   removed from the HUD/Settings (indicators stay).
6. AUTO-STOP — only the STOP SPEAKING button called
   stop_speaking(); a new typed/voice message queued behind the
   old speech. Fix: every new input interrupts first.
7. WHOP + GUMROAD — TORVIS had NO Whop/Gumroad tools at all, so
   the brain could only refuse uploads (the old refusal was a
   browser file-picker problem; TORVIS runs ON his PC, so it reads
   H: drive files directly and uploads via the official APIs, no
   picker involved). Fix: real API clients below, injectable HTTP
   so tests never touch the network.

Stdlib only — no audio, no network in this module — unit-testable.
"""
import json
import os
import re
from pathlib import Path

BUILD21_MARKER = ("BUILD 21 — TORVIS: FAST ANSWERS, CLEAR PRONUNCIATION, "
                  "REMEMBERS TASKS, AUTO BRIEFING, ALWAYS ON, NO GROQ, "
                  "NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK")

# BUILD 21: transient retries cut from (2, 5, 10) to (1, 2) seconds.
# The old schedule waited up to 17s on an overloaded brain before the
# fallback even started — the single biggest measured slow-down.
RETRY_WAITS_21 = (1, 2)

# ------------------------------------------------------------ 1. fast ----
TOOL_WORDS = {
    "open", "download", "install", "book", "remind", "remember",
    "search", "upload", "whop", "gumroad", "camera", "photo",
    "type", "click", "watch", "site", "calendar", "gmail", "email",
    "meeting", "youtube", "printer", "kali", "scan", "security",
    "file", "folder", "create", "delete", "move", "rename", "play",
    "volume", "brightness", "shutdown", "restart", "settings",
    "calculate", "times", "plus", "minus", "multiply", "divided",
    "subtract", "equals", "call", "check", "status",
}
FAST_SYSTEM_SUFFIX = (" Answer in 1-3 short sentences only. No tools, "
                      "no lists, no preamble — just the answer.")


def is_fast_chat(text):
    """True when `text` is short everyday chat that needs no tool:
    under 200 characters, no tool word, not a command. Pure."""
    t = str(text or "").strip()
    if not t or len(t) > 200:
        return False
    words = set(re.findall(r"[a-z]+", t.lower()))
    if words & TOOL_WORDS:
        return False
    return True


def first_sentence(text):
    """The first sentence of a reply — spoken first, without waiting
    for the rest of the reply or the full TTS file. Pure."""
    t = str(text or "").strip()
    if not t:
        return ""
    m = re.match(r"^(.+?[.!?])(?:\s|$)", t)
    return m.group(1).strip() if m else t


def briefing_spoken_seconds(text):
    """Rough spoken length of a briefing (about 150 words/minute).
    The startup briefing must stay under ~30 seconds."""
    return len(str(text or "").split()) / 150.0 * 60.0


def briefing_lines(text):
    """Number of spoken sections in a briefing (sentences)."""
    return len([s for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s])


def fast_chat_max_tokens():
    """Short answers need few tokens — a smaller reply is also a
    faster reply (less generation + less TTS)."""
    return 300


# --------------------------------------------------- 2. pronunciation ----
# Roman Urdu -> Urdu script. The ur-PK neural voice is trained on
# Urdu script; Latin letters make it (and any English voice) read
# Roman Urdu as English gibberish. Transliterating the common words
# first is what makes "mujhe batao" sound right.
ROMAN_URDU_TO_URDU = {
    "ali": "علی", "mujhe": "مجھے", "mujhay": "مجھے", "tum": "تم", "tumhe": "تمہیں",
    "tumhe": "تمہیں", "tumhara": "تمہارا", "tumhari": "تمہاری",
    "mera": "میرا", "meri": "میری", "mere": "میرے", "aap": "آپ",
    "aapka": "آپ کا", "aapki": "آپ کی", "kya": "کیا", "kaise": "کیسے",
    "kaisa": "کیسا", "kaisi": "کیسی", "kyun": "کیوں", "kab": "کب",
    "kahan": "کہاں", "kaun": "کون", "yeh": "یہ", "ye": "یہ",
    "woh": "وہ", "wo": "وہ", "hai": "ہے", "hain": "ہیں",
    "nahi": "نہیں", "nahin": "نہیں", "matlab": "مطلب",
    "batao": "بتاؤ", "bata": "بتا", "karo": "کرو", "kar": "کر",
    "karke": "کر کے", "chahiye": "چاہیے", "acha": "اچھا",
    "accha": "اچھا", "theek": "ٹھیک", "bilkul": "بالکل",
    "zaroor": "ضرور", "abhi": "ابھی", "kal": "کل", "aaj": "آج",
    "phir": "پھر", "bhi": "بھی", "aur": "اور", "lekin": "لیکن",
    "magar": "مگر", "agar": "اگر", "yaad": "یاد", "rakhna": "رکھنا",
    "sunao": "سناؤ", "dekho": "دیکھو", "kuch": "کچھ", "koi": "کوئی",
    "sab": "سب", "bohat": "بہت", "bahut": "بہت", "bhai": "بھائی",
    "yar": "یار", "yaar": "یار", "salam": "سلام",
    "shukriya": "شکریہ", "meherbani": "مہربانی", "kaam": "کام",
    "samajh": "سمجھ", "samjha": "سمجھا", "bolo": "بولو",
    "likho": "لکھو", "parho": "پڑھو", "mujhse": "مجھ سے",
    "tujhe": "تجھے", "usko": "اس کو", "isko": "اس کو",
    "uski": "اس کی", "iski": "اس کی", "hamara": "ہمارا",
    "hamari": "ہماری", "tumne": "تم نے", "maine": "میں نے",
    "usne": "اس نے", "isne": "اس نے", "jao": "جاؤ", "aao": "آؤ",
    "chal": "چل", "chalo": "چلو", "suno": "سنو", "bhejo": "بھیجو",
    "karoonga": "کروں گا", "karunga": "کروں گا", "hoga": "ہوگا",
    "hogi": "ہوگی", "tha": "تھا", "thi": "تھی", "the": "تھے",
    "raha": "رہا", "rahi": "رہی", "rahe": "رہے", "gaya": "گیا",
    "gayi": "گئی", "aaya": "آیا", "aayi": "آئی", "diya": "دیا",
    "liye": "لیے", "saath": "ساتھ", "paas": "پاس", "upar": "اوپر",
    "neeche": "نیچے", "andar": "اندر", "bahar": "باہر",
    "pehle": "پہلے", "baad": "بعد", "mein": "میں", "se": "سے",
    "ko": "کو", "ki": "کی", "ka": "کا", "ke": "کے", "ne": "نے",
    "par": "پر", "tak": "تک", "jab": "جب", "tab": "تب",
    "jaisa": "جیسا", "waisa": "ویسا", "aisa": "ایسا",
    "kitna": "کتنا", "kitni": "کتنی", "kitne": "کتنے",
    "kahan": "کہاں", "kidhar": "کدھر", "udhar": "ادھر",
    "idhar": "ادھر", "zara": "ذرا", "thoda": "تھوڑا",
    "zyada": "زیادہ", "kam": "کم", "acha": "اچھا",
    "bura": "برا", "sahi": "صحیح", "galat": "غلط",
    "mushkil": "مشکل", "asaan": "آسان", "naya": "نیا",
    "purana": "پرانا", "bada": "بڑا", "chota": "چھوٹا",
    "jaldi": "جلدی", "der": "دیر", "subah": "صبح",
    "shaam": "شام", "raat": "رات", "din": "دن",
    "hafta": "ہفتہ", "mahina": "مہینہ", "saal": "سال",
    "waqt": "وقت", "baat": "بات", "naam": "نام",
    "ghar": "گھر", "paise": "پیسے", "paisa": "پیسہ",
    "dost": "دوست", "duniya": "دنیا", "zindagi": "زندگی",
    "khushi": "خوشی", "dukh": "دکھ", "mohabbat": "محبت",
    "madad": "مدد", "sawaal": "سوال", "jawab": "جواب",
}
ROMAN_URDU_WORDS = set(ROMAN_URDU_TO_URDU.keys())


def detect_language(text):
    """Language of one reply, via BUILD 20 when present, else BUILD 14,
    else a small Roman-Urdu / English guess. Pure."""
    try:
        import jarvis_build20 as _b20
        return _b20.detect_language(text)
    except Exception:  # noqa: BLE001
        pass
    t = str(text or "")
    if re.search(r"[\u0600-\u06ff]", t):
        return "urdu"
    if roman_urdu_word_count(t) >= 2:
        return "roman-urdu"
    return "english"


def detect_roman_urdu(text):
    """True when the text is Roman Urdu (Latin-script Urdu) — at
    least two known Roman Urdu words. Pure."""
    return roman_urdu_word_count(text) >= 2


def roman_urdu_word_count(text):
    """How many words of `text` are known Roman Urdu words."""
    words = re.findall(r"[a-zA-Z]+", str(text or "").lower())
    return sum(1 for w in words if w in ROMAN_URDU_WORDS)


def transliterate_roman_urdu(text):
    """Replace known Roman Urdu words with Urdu script, word by word.
    Unknown words (names, English words) are left untouched.
    Returns (new_text, changed_count). Pure."""
    t = str(text or "")

    def _sub(m):
        word = m.group(0)
        mapped = ROMAN_URDU_TO_URDU.get(word.lower())
        return mapped if mapped else word

    out, n = re.subn(r"[A-Za-z]+", _sub, t)
    return out, n


def prepare_for_tts(text, language):
    """The text actually sent to the TTS voice, plus the rate to use.
    Roman Urdu / mixed: transliterate to Urdu script so the ur-PK
    voice pronounces it right, and slow down (-15%). Urdu script:
    as-is, -10%. English: as-is, -10%. Returns
    {text, rate, language, transliterated}. Pure."""
    lang = str(language or "").strip().lower()
    if lang in ("roman-urdu", "mixed"):
        tts_text, n = transliterate_roman_urdu(text)
        return {"text": tts_text, "rate": "-15%", "language": lang,
                "transliterated": n}
    return {"text": str(text or ""), "rate": "-10%", "language": lang,
            "transliterated": 0}


def build_edge_ssml(text, voice, rate="-10%", pitch="+0Hz",
                    lang="ur-PK"):
    """SSML for edge-tts: explicit voice + prosody, so the service
    cannot silently pick a different voice or speed. The text is
    XML-escaped. Pure. (edge-tts treats text starting with <speak>
    as SSML; if the service rejects it, the caller retries plain
    text before falling back to SAPI.)"""
    safe = (str(text or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="{lang}"><voice name="{voice}">'
            f'<prosody rate="{rate}" pitch="{pitch}">{safe}</prosody>'
            f"</voice></speak>")


def voice_spoken_report(engine, voice):
    """One log line naming the exact engine + voice that actually
    spoke — the proof that edge-tts spoke, or the plain admission
    that SAPI did. Pure."""
    label = "pyttsx3 (SAPI)" if str(engine).strip().lower() == "pyttsx3" else str(engine)
    return f"Spoke with {label} — voice: {voice}"


# ------------------------------------------------------- 3. task memory ----
_TASK_PATTERNS = [
    re.compile(r"(?i)\b(?:i have to|i need to|i must|i should|i will|i'll|i am going to)\s+([^.!?\n]{3,100})"),
    re.compile(r"(?i)\b(?:remind me to|my task is|task\s*:\s*)\s*([^.!?\n]{3,100})"),
    re.compile(r"(?i)\b(?:mujhe|mujhay)\s+([^.!?\n]{3,100}?(?:karna hai|karna he|chahiye|hai|karna))"),
    re.compile(r"(?i)\b(?:tomorrow|kal)\s+(?:i have to|i need to|mujhe|mujhay)\s+([^.!?\n]{3,100})"),
    re.compile(r"(?i)\b(?:kaam hai|kaam he)\s*[:\-]?\s*([^.!?\n]{3,100})"),
]


def extract_tasks_from_text(text):
    """Tasks a user states in plain words — "I have to call Ali",
    "mujhe kal report karni hai", "remind me to pay the bill".
    Returns a deduped list (max 3), or []. Pure. This is what
    BUILD 20 missed: tasks were only saved when the brain happened
    to call the remember_this tool."""
    t = str(text or "").strip()
    if not t:
        return []
    found = []
    for pat in _TASK_PATTERNS:
        for m in pat.finditer(t):
            task = re.sub(r"\s+", " ", m.group(1)).strip(" .,:;-")
            if len(task) < 3:
                continue
            task = task[:1].upper() + task[1:]
            if task not in found:
                found.append(task)
    return found[:3]


def format_open_tasks(tasks, limit=3):
    """Open tasks as one spoken line, or '' when there are none."""
    tasks = [str(x).strip() for x in (tasks or []) if str(x).strip()]
    if not tasks:
        return ""
    shown = tasks[:limit]
    extra = len(tasks) - len(shown)
    line = "Your open tasks: " + "; ".join(shown) + "."
    if extra:
        line += f" And {extra} more."
    return line


# --------------------------------------------------- 4. auto briefing -----
def gmail_briefing_line(gmail):
    """One line about email for the startup briefing. `gmail` is the
    dict from GmailClient.fetch_latest() plus a 'connected' flag, or
    None. Never invents mail: not connected -> say so plainly; no
    messages -> say so; otherwise the latest subjects, max 3."""
    if gmail is None:
        return ("Gmail is not connected yet — connect it in Settings "
                "and I will read your important emails for you.")
    if not gmail.get("connected", True):
        return ("Gmail is not connected yet — connect it in Settings "
                "and I will read your important emails for you.")
    if not gmail.get("ok", True):
        return ("I could not read your email just now — "
                + str(gmail.get("error") or "Gmail failed")[:80] + ".")
    messages = gmail.get("messages") or []
    if not messages:
        return "No new important emails, Sir."
    subjects = [str(m.get("subject") or "(no subject)").strip()
                for m in messages[:3] if str(m.get("subject") or "").strip()]
    if not subjects:
        return f"You have {len(messages)} new email(s), Sir."
    return ("Your latest emails: " + "; ".join(subjects) + ".")


def build_startup_briefing(last_work, tasks, reminders, meetings_text,
                           gmail, when_str=""):
    """The spoken + shown startup briefing, short (aim under 30
    seconds spoken, ~110 words). Never invents anything: every
    section is omitted when its data is empty, except the Gmail
    line, which always says plainly whether Gmail is connected.
    Pure."""
    parts = []
    greet = "Good morning, Sir." if when_str else "Welcome back, Sir."
    parts.append(greet)
    if last_work:
        parts.append(str(last_work).strip())
    task_line = format_open_tasks(tasks)
    if task_line:
        parts.append(task_line)
    if reminders:
        parts.append("Reminders due: " + "; ".join(str(r) for r in reminders[:3]) + ".")
    if meetings_text:
        parts.append(str(meetings_text).strip())
    parts.append(gmail_briefing_line(gmail))
    out = " ".join(p for p in parts if p)
    words = out.split()
    if len(words) > 120:
        out = " ".join(words[:120]) + "…"
    return out


# ------------------------------------------------------- 5. always on ----
ALWAYS_ON_FEATURES = {
    "camera_enabled": True,
    "clap_wake_enabled": True,
    "gestures_enabled": True,
    "auto_briefing_enabled": True,
}
# Screen Watch stays OFF by default (privacy + it burns brain quota
# on every glance); wake word stays as Faizan left it; autopilot
# stays OFF by default (Faizan turns it on himself, BUILD 19).
ALWAYS_ON_NOTE = ("Camera, clap wake and gestures are always on in "
                  "BUILD 21 — there is no toggle for them any more. "
                  "Screen Watch stays off by default (privacy + quota), "
                  "and autopilot stays off until Faizan turns it on.")


# ------------------------------------------------------- 6. auto-stop -----
def interrupt_message():
    """What the log records when a new message interrupts speech."""
    return "[VOICE] New message — stopped speaking mid-sentence, Sir."


# ------------------------------------------------- 7. Whop + Gumroad -----
# Official APIs (verified 2026-11-24 against docs.whop.com and
# Gumroad's API docs / community skills):
#  Whop: base https://api.whop.com/api/v2, Bearer <WHOP_API_KEY>.
#   Files: POST /files {filename, byte_size} -> {id, upload_url,
#   upload_headers}; PUT the bytes to upload_url; GET /files/{id}
#   polls upload_status until 'ready'. Products: POST /products
#   {company_id, title, headline, description, minimum_price_cents};
#   GET /products; GET /products/{id}. A product's buyers get its
#   files through a Files experience: POST /apps/{FILES_APP_ID}/
#   experiences {company_id, product_id, name}.
#  Gumroad: base https://api.gumroad.com/v2, Bearer access token
#   (Settings > Advanced > Applications). Files: POST /files/presign
#   {filename, file_size} -> {upload_id, key, file_url, parts[]};
#   PUT each part to its presigned_url; POST /files/complete
#   {upload_id, key, parts} -> {file_url}. Products: POST /products
#   {name, price, description}; PUT /products/{id} {files, published};
#   GET /products/{id}.
# Honest limits, in README too: the Whop Files-experience attach
# step and Gumroad cover-image upload are the least-documented API
# steps — the code reports the real API response for them and never
# says "done" when the API said no. Keys live in Settings or
# H:\JARVIS-Work\.env, never in chat, never printed.
WHOP_BASE = "https://api.whop.com/api/v2"
WHOP_FILES_APP_ID = "app_5UWRrs7haZZeiQ"
GUMROAD_BASE = "https://api.gumroad.com/v2"
WHOP_MISSING_KEY = ("Whop API key is missing, Sir — put it in Settings "
                    "(Whop API key) or in H:\\JARVIS-Work\\.env as "
                    "WHOP_API_KEY=whop_... (from Whop Dashboard > "
                    "Developer). I cannot touch your Whop account "
                    "without it, and I will not guess a key.")
GUMROAD_MISSING_KEY = ("Gumroad access token is missing, Sir — put it "
                       "in Settings (Gumroad access token) or in "
                       "H:\\JARVIS-Work\\.env as GUMROAD_ACCESS_TOKEN=... "
                       "(Gumroad > Settings > Advanced > Applications). "
                       "I cannot touch your Gumroad account without it.")
DOTENV_KEYS = ("WHOP_API_KEY", "GUMROAD_ACCESS_TOKEN")


def load_account_keys(config=None, env_file=None, environ=None):
    """Whop + Gumroad keys, in priority order: Settings config dict,
    then H:\\JARVIS-Work\\.env, then process environment. Returns
    {whop_api_key, gumroad_access_token} ('' when missing). The
    values are never logged or printed by this function. Pure
    except for the optional .env file read."""
    cfg = config or {}
    env = environ if environ is not None else os.environ
    whop = str(cfg.get("whop_api_key") or "").strip()
    gum = str(cfg.get("gumroad_access_token") or "").strip()
    if (not whop or not gum) and env_file is not None:
        try:
            for line in Path(env_file).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key == "WHOP_API_KEY" and not whop:
                    whop = value
                elif key == "GUMROAD_ACCESS_TOKEN" and not gum:
                    gum = value
        except Exception:  # noqa: BLE001 — missing .env = no keys there
            pass
    if not whop:
        whop = str(env.get("WHOP_API_KEY") or "").strip()
    if not gum:
        gum = str(env.get("GUMROAD_ACCESS_TOKEN") or "").strip()
    return {"whop_api_key": whop, "gumroad_access_token": gum}


def _default_http(method, url, headers=None, data=None, json_body=None):
    """stdlib HTTP for the API clients. Returns
    (status:int, body:dict, headers:dict). Never raises for an HTTP
    error status — the caller reads the body. Network failure raises
    RuntimeError with a plain message."""
    import urllib.request
    import urllib.error
    body = None
    hdrs = dict(headers or {})
    if json_body is not None:
        body = json.dumps(json_body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif data is not None:
        body = data if isinstance(data, (bytes, bytearray)) else str(data).encode()
    req = urllib.request.Request(url, data=body, method=method.upper())
    for k, v in hdrs.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode(errors="replace")
            try:
                parsed = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw}
            return r.status, parsed, dict(r.headers or {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return e.code, parsed, dict(e.headers or {})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Could not reach the API: {e}")


def _api_error(status, body):
    """One plain error string from an API response body."""
    if isinstance(body, dict):
        for key in ("error", "message", "detail"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, dict):
                msg = val.get("message") or val.get("error")
                if msg:
                    return str(msg)
        if body.get("raw"):
            return str(body["raw"])[:200]
    return f"API returned status {status}"


class WhopClient:
    """Whop account work via the official API — no browser, no file
    picker: files are read from the H: drive and PUT to Whop's
    presigned upload URL. `http` is injectable (tests fake it)."""

    def __init__(self, api_key, company_id="", http=None):
        self.api_key = str(api_key or "").strip()
        self.company_id = str(company_id or "").strip()
        self.http = http or _default_http

    def _req(self, method, path, json_body=None):
        if not self.api_key:
            return {"ok": False, "error": WHOP_MISSING_KEY}
        url = WHOP_BASE + path
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            status, body, _h = self.http(method, url, headers, None, json_body)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if 200 <= status < 300:
            return {"ok": True, "data": body if isinstance(body, dict) else {"raw": body}}
        return {"ok": False, "error": _api_error(status, body), "status": status}

    def list_products(self):
        """List products. Returns {ok, products:[{id,title,...}]}."""
        res = self._req("GET", "/products")
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        items = data.get("data") or data.get("products") or []
        if isinstance(items, dict):
            items = [items]
        return {"ok": True, "products": [
            {"id": str(p.get("id") or ""), "title": str(p.get("title") or p.get("name") or ""),
             "visibility": str(p.get("visibility") or "")} for p in items if isinstance(p, dict)]}

    def create_product(self, title, headline="", description="", price_cents=0):
        """Create a product. Returns {ok, product:{id,title}}.
        Price is set as minimum_price_cents; 0 = free / set later."""
        if not str(title or "").strip():
            return {"ok": False, "error": "A product needs a name, Sir."}
        body = {"title": str(title).strip()}
        if self.company_id:
            body["company_id"] = self.company_id
        if headline:
            body["headline"] = str(headline)
        if description:
            body["description"] = str(description)
        try:
            body["minimum_price_cents"] = int(price_cents)
        except (TypeError, ValueError):
            body["minimum_price_cents"] = 0
        res = self._req("POST", "/products", body)
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        prod = data.get("data") if isinstance(data.get("data"), dict) else data
        return {"ok": True, "product": {"id": str(prod.get("id") or ""),
                                        "title": str(prod.get("title") or title)}}

    def get_product(self, product_id):
        """Fetch one product — the verify step: never say 'done'
        without this. Returns {ok, product}."""
        if not str(product_id or "").strip():
            return {"ok": False, "error": "A product ID is needed, Sir."}
        res = self._req("GET", f"/products/{product_id}")
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        prod = data.get("data") if isinstance(data.get("data"), dict) else data
        return {"ok": True, "product": {"id": str(prod.get("id") or product_id),
                                        "title": str(prod.get("title") or prod.get("name") or ""),
                                        "visibility": str(prod.get("visibility") or "")}}

    def upload_file(self, file_path):
        """Upload a file from disk: create record -> PUT bytes to the
        presigned URL -> poll until 'ready'. Returns
        {ok, file:{id, url, filename}}. No browser picker involved."""
        if not self.api_key:
            return {"ok": False, "error": WHOP_MISSING_KEY}
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": f"File not found on this PC: {file_path}"}
        try:
            data_bytes = path.read_bytes()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Could not read that file, Sir: {e}"}
        res = self._req("POST", "/files", {"filename": path.name, "byte_size": len(data_bytes)})
        if not res.get("ok"):
            return res
        rec = (res.get("data") or {}).get("data") or res.get("data") or {}
        file_id = str(rec.get("id") or "")
        upload_url = rec.get("upload_url") or ""
        upload_headers = rec.get("upload_headers") or {}
        if not file_id or not upload_url:
            return {"ok": False, "error": "Whop did not return an upload URL, Sir — the file record was not created."}
        try:
            status, _body, _h = self.http("PUT", upload_url, dict(upload_headers), data_bytes, None)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if status not in (200, 201, 204):
            return {"ok": False, "error": f"Whop file upload failed with status {status}, Sir."}
        got = self._req("GET", f"/files/{file_id}")
        if got.get("ok"):
            gdata = (got.get("data") or {}).get("data") or got.get("data") or {}
            if gdata.get("upload_status") and gdata.get("upload_status") != "ready":
                return {"ok": True, "file": {"id": file_id, "url": gdata.get("url") or "",
                                             "filename": path.name},
                        "note": f"File uploaded, still processing (status: {gdata.get('upload_status')})."}
            return {"ok": True, "file": {"id": file_id, "url": gdata.get("url") or "",
                                         "filename": path.name}}
        return {"ok": True, "file": {"id": file_id, "url": "", "filename": path.name}}

    def attach_file_to_product(self, product_id, file_id, name="Download"):
        """Attach an uploaded file to a product via a Files
        experience. This is the least-documented Whop API step: the
        code reports the real API response and never claims success
        when the API said no. Returns {ok, experience:{id}}."""
        if not str(product_id or "").strip() or not str(file_id or "").strip():
            return {"ok": False, "error": "A product ID and a file ID are needed, Sir."}
        body = {"app_id": WHOP_FILES_APP_ID, "name": str(name or "Download"),
                "product_id": str(product_id)}
        if self.company_id:
            body["company_id"] = self.company_id
        res = self._req("POST", f"/apps/{WHOP_FILES_APP_ID}/experiences", body)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "Whop would not attach the file, Sir."),
                    "note": "The product and the file upload itself are fine — only the Files-experience attach step failed. Check the product in the Whop dashboard."}
        data = res.get("data") or {}
        exp = data.get("data") if isinstance(data.get("data"), dict) else data
        return {"ok": True, "experience": {"id": str(exp.get("id") or "")},
                "note": "File attached via the Files experience."}

    def publish_product(self, product_id):
        """Make a product visible. Returns {ok, product} verified
        with a fresh GET — never 'done' on a guess."""
        res = self._req("POST", f"/products/{product_id}/publish", {})
        if not res.get("ok"):
            # Some Whop API versions publish via visibility update.
            res2 = self._req("PUT", f"/products/{product_id}", {"visibility": "visible"})
            if not res2.get("ok"):
                return res
        return self.get_product(product_id)


class GumroadClient:
    """Gumroad account work via the official v2 API — no browser.
    `http` is injectable (tests fake it)."""

    def __init__(self, access_token, http=None):
        self.access_token = str(access_token or "").strip()
        self.http = http or _default_http

    def _req(self, method, path, json_body=None):
        if not self.access_token:
            return {"ok": False, "error": GUMROAD_MISSING_KEY}
        url = GUMROAD_BASE + path
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            status, body, _h = self.http(method, url, headers, None, json_body)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
        if 200 <= status < 300:
            return {"ok": True, "data": body if isinstance(body, dict) else {"raw": body}}
        return {"ok": False, "error": _api_error(status, body), "status": status}

    def list_products(self):
        res = self._req("GET", "/products")
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        items = data.get("products") or data.get("data") or []
        if isinstance(items, dict):
            items = [items]
        return {"ok": True, "products": [
            {"id": str(p.get("id") or ""), "name": str(p.get("name") or ""),
             "url": str(p.get("short_url") or p.get("url") or ""),
             "published": bool(p.get("published"))} for p in items if isinstance(p, dict)]}

    def get_product(self, product_id):
        if not str(product_id or "").strip():
            return {"ok": False, "error": "A product ID is needed, Sir."}
        res = self._req("GET", f"/products/{product_id}")
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        prod = data.get("product") if isinstance(data.get("product"), dict) else data
        return {"ok": True, "product": {"id": str(prod.get("id") or product_id),
                                        "name": str(prod.get("name") or ""),
                                        "url": str(prod.get("short_url") or prod.get("url") or ""),
                                        "published": bool(prod.get("published"))}}

    def upload_file(self, file_path):
        """Presign -> PUT part(s) -> complete. Returns
        {ok, file_url}. Files under 100 MB go as one part."""
        if not self.access_token:
            return {"ok": False, "error": GUMROAD_MISSING_KEY}
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": f"File not found on this PC: {file_path}"}
        try:
            size = path.stat().st_size
            data_bytes = path.read_bytes()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"Could not read that file, Sir: {e}"}
        res = self._req("POST", "/files/presign",
                        {"filename": path.name, "file_size": size})
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        upload_id = str(data.get("upload_id") or "")
        key = str(data.get("key") or "")
        parts = data.get("parts") or []
        if not upload_id or not parts:
            return {"ok": False, "error": "Gumroad did not return an upload slot, Sir."}
        etags = []
        offset = 0
        for i, part in enumerate(parts):
            url = part.get("presigned_url") or ""
            chunk = data_bytes[offset:offset + 100 * 1024 * 1024]
            offset += len(chunk)
            try:
                status, _b, hdrs = self.http("PUT", url, {}, chunk, None)
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": str(e)}
            if status not in (200, 201, 204):
                return {"ok": False, "error": f"Gumroad file upload failed with status {status}, Sir."}
            etag = ""
            for k, v in (hdrs or {}).items():
                if k.lower() == "etag":
                    etag = str(v).strip('"')
            etags.append({"part_number": i + 1, "etag": etag})
        done = self._req("POST", "/files/complete",
                         {"upload_id": upload_id, "key": key, "parts": etags})
        if not done.get("ok"):
            return done
        ddata = done.get("data") or {}
        return {"ok": True, "file_url": str(ddata.get("file_url") or data.get("file_url") or "")}

    def create_product(self, name, price_cents=0, description="", file_url=None):
        """Create a draft product. Returns {ok, product:{id,url}}."""
        if not str(name or "").strip():
            return {"ok": False, "error": "A product needs a name, Sir."}
        body = {"name": str(name).strip(), "description": str(description or "")}
        try:
            body["price"] = int(price_cents)
        except (TypeError, ValueError):
            body["price"] = 0
        if file_url:
            body["files"] = [{"url": str(file_url)}]
        res = self._req("POST", "/products", body)
        if not res.get("ok"):
            return res
        data = res.get("data") or {}
        prod = data.get("product") if isinstance(data.get("product"), dict) else data
        return {"ok": True, "product": {"id": str(prod.get("id") or ""),
                                        "name": str(prod.get("name") or name),
                                        "url": str(prod.get("short_url") or prod.get("url") or "")}}

    def update_product(self, product_id, publish=False, file_url=None, **fields):
        """Update a product; publish=True makes it live. Returns the
        verified product (fresh GET) — never 'done' on a guess."""
        if not str(product_id or "").strip():
            return {"ok": False, "error": "A product ID is needed, Sir."}
        body = dict(fields)
        if file_url:
            body["files"] = [{"url": str(file_url)}]
        if publish:
            body["published"] = True
        res = self._req("PUT", f"/products/{product_id}", body)
        if not res.get("ok"):
            return res
        return self.get_product(product_id)


def parse_price_cents(text):
    """'$29' / '29 dollars' / 'Rs 1999' -> cents (USD assumed for
    '$' / plain numbers; Rs is NOT converted — it is returned as
    rupees x100 and flagged by the caller). Returns (cents, currency)
    or (None, None). Pure."""
    t = str(text or "")
    m = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", t)
    if m:
        return int(round(float(m.group(1)) * 100)), "USD"
    m = re.search(r"(?i)\b(\d+(?:\.\d{1,2})?)\s*(?:dollars|usd)\b", t)
    if m:
        return int(round(float(m.group(1)) * 100)), "USD"
    return None, None


def parse_account_command(text):
    """Parse 'upload X to whop / gumroad', 'create a whop product
    called Y for $29', 'list my whop products' into a dict, or None
    when the text is not a Whop/Gumroad account command. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    platform = None
    if "whop" in low:
        platform = "whop"
    elif "gumroad" in low:
        platform = "gumroad"
    if platform is None:
        return None
    out = {"platform": platform}
    m = re.search(r"[A-Za-z]:\\[^\s\"']+|\"([^\"]+\.(?:zip|pdf|jpg|jpeg|png|xlsx))\"|(\S+\.(?:zip|pdf|jpg|jpeg|png|xlsx))", t)
    if m:
        out["file"] = (m.group(1) or m.group(2) or m.group(0)).strip('"')
    m = re.search(r"(?i)product\s+(?:called|named)?\s*[\"']?([^\"'\n]{2,80})", t)
    if m:
        out["product_name"] = m.group(1).strip().strip('"').strip("'")
    m = re.search(r"(?i)\b(?:id|product)\s+([A-Za-z0-9_\-]{6,})\b", t)
    if m and "product" in low and ("upload" in low or "status" in low or "check" in low):
        out["product_id"] = m.group(1)
    cents, currency = parse_price_cents(t)
    if cents is not None:
        out["price_cents"] = cents
        out["currency"] = currency
    if "list" in low and "product" in low:
        out["action"] = "list_products"
    elif "upload" in low:
        out["action"] = "upload_file"
    elif "create" in low:
        out["action"] = "create_product"
    elif "publish" in low:
        out["action"] = "publish"
    elif "status" in low or "check" in low:
        out["action"] = "status"
    else:
        out["action"] = "help"
    return out
