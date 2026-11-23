"""BUILD 19 pure logic — full autopilot (no-confirm, opt-in only),
YouTube autopilot, channel niche analysis, caption + hashtags,
site watcher, meeting alerts (no-confirm notifications).

BUILD 19 (2026-11-23) — TORVIS FULL AUTOPILOT.
Marker: "BUILD 19 — TORVIS: FULL AUTOPILOT NO-CONFIRM, YOUTUBE
AUTOPILOT, CHANNEL NICHE, SITE WATCHER, NO GROQ, NO OLLAMA,
MISTRAL MAIN, GEMINI LITE FALLBACK"

Faizan's explicit request, in his own words: TORVIS must not ask for
confirmation before doing things — not only YouTube, for ALL things.
This build implements that as an explicit opt-in, so the default
product is still safe, but when Faizan turns it on it really does
not ask:

* MASTER AUTOPILOT — a Settings toggle `autopilot_enabled`, default
  OFF, only Faizan can turn it on in Settings on his own PC. When ON,
  TORVIS does NOT ask for confirm before doing things on his own PC /
  his own accounts: installs from official sources only, YouTube and
  other account posts/uploads, Kali VM commands, file operations in
  the H: drive, site actions, and so on. When OFF, every old confirm
  gate stays exactly as before.
* YOUTUBE AUTOPILOT — a second Settings toggle
  `youtube_autopilot_enabled`, also default OFF. When ON, YouTube
  uploads/posts need no confirm. When OFF, the old two-step YouTube
  confirm stays — unless master autopilot is ON, which also covers
  YouTube. Either toggle ON is enough for YouTube; both OFF means
  confirm is asked.
* CHANNEL NICHE — `analyze_youtube_channel` reads HIS channel's
  videos/views/likes (official YouTube Data API v3, OAuth only, never
  a password) and recommends the best niche for HIS channel from that
  real data, with the numbers shown. Not connected -> plain
  "YouTube not connected yet" + OAuth setup steps, never invented data.
* CAPTION + HASHTAGS — `make_youtube_caption` builds a caption and
  hashtags from a video title/topic and his best-performing topics.
  No invented views.
* SITE WATCHER — `SiteWatcher` watches his sites (default: his Whop
  store and his roofing site) from H:\\JARVIS-Work\\watched-sites.txt,
  one URL per line, every 30 minutes while TORVIS runs, and notifies
  him (voice + Task Log) when a site goes down / comes back up, or
  when a watched page changes. Checking is read-only — no confirm
  is ever needed for checking.
* MEETING ALERTS — already existed (BUILD 15, 15 minutes before).
  An alert is a notification, not an action, so it NEVER needs a
  confirm, in autopilot or not. `meeting_alert_needs_confirm()`
  is False, always, and the README says so plainly.

HARD LIMITS — these stay in force even in autopilot mode, and
autopilot never overrides them:

* PROTECTED LIST: never touch protected files — skip only that item,
  say so plainly, continue. Autopilot does not override this.
* OWN STUFF ONLY: never scan / hack / access anyone else's system,
  network, account or website without their written permission.
  Autopilot does not override this.
* NEVER auto-pay for anything, and NEVER auto-delete files outside
  the H: drive without a separate explicit instruction in that
  moment. Autopilot does not override these either.
* Installs in autopilot: official sources only. In code that means
  an installer must come from TORVIS's own official-source download
  (a file TORVIS downloaded from an official site into
  H:\\JARVIS-Work\\) or be explicitly marked official_source — an
  unknown installer file still asks for confirm, even in autopilot.

Other confirm gates are untouched by autopilot's scope: Facebook /
TikTok posting still needs its own confirm unless master autopilot
is ON (it is Faizan's own account, so master autopilot covers it —
see `account_post_needs_confirm`), and deleting/paying are covered
by the hard limits above, not by autopilot.

* H: drive only: every file TORVIS downloads, unzips, builds or
  creates goes only in H:\\JARVIS-Work\\ — never the system drive.
* Camera local only, no face recognition. Ethical security: own PC
  and own accounts only.
* No Groq, no Ollama. Mistral mistral-medium-latest main, Gemini
  gemini-3.5-flash-lite fallback.

Everything in this file is unit-testable on Linux with the standard
library only. Network, YouTube API, the camera and Windows are all
injectable in tests, so no real account or site is needed here.
"""
import hashlib
import re
import time

BUILD19_MARKER = ("BUILD 19 — TORVIS: FULL AUTOPILOT NO-CONFIRM, YOUTUBE "
                  "AUTOPILOT, CHANNEL NICHE, SITE WATCHER, MULTILINGUAL "
                  "VOICE, HUMAN-LIKE SPEAKING, NO GROQ, "
                  "NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK")
BUILD18_MARKER = __import__("jarvis_build18").BUILD18_MARKER

AUTOPILOT_WARNING = (
    "Autopilot is Faizan's own choice, turned on by him in Settings. "
    "When it is on, TORVIS does not ask for confirm before acting on "
    "his own PC and his own accounts — posts and installs are hard to "
    "undo, so turn it off again if you want the confirm gates back. "
    "It never overrides the protected list, never touches anyone "
    "else's system or account, never pays for anything, and never "
    "deletes files outside the H: drive.")

AUTOPILOT_NOTE = (
    "Full autopilot — OFF by default. Turn it on in Settings or say "
    "'turn autopilot on'. When it is on, TORVIS does not ask for "
    "confirm before doing things on your own PC and your own accounts. "
    "When it is off, every confirm gate works as before.")

YOUTUBE_AUTOPILOT_NOTE = (
    "YouTube autopilot — OFF by default. Turn it on in Settings or say "
    "'turn youtube autopilot on'. When it is on, YouTube uploads and "
    "posts need no confirm. When it is off, the old two-step YouTube "
    "confirm stays — unless full autopilot is on, which also covers "
    "YouTube. Posts are public and cannot be undone.")

YOUTUBE_NOT_CONNECTED_MESSAGE = (
    "YouTube not connected yet, Sir — I have no channel data to read. "
    "Complete the one-time Google OAuth setup on your PC first: Google "
    "Cloud Console, enable YouTube Data API v3, create an OAuth client "
    "(Desktop app), sign in once in your own browser, and save the "
    "token file. I will never ask for your Google password, and I will "
    "never invent channel data.")

MEETING_ALERT_NOTE = (
    "Meeting alerts need no confirm, ever — an alert is a notification, "
    "not an action. TORVIS tells you 15 minutes before a meeting from "
    "your connected Google Calendar, in autopilot or not.")

DEFAULT_WATCHED_SITES = [
    "https://whop.com/zero-to-first-dollar-online-2d4f/",
    "https://summit-roofing-co-denver-2.whop.site",
]
WATCHED_SITES_FILE = "H:\\JARVIS-Work\\watched-sites.txt"
SITE_CHECK_INTERVAL_S = 30 * 60  # 30 minutes

# Actions autopilot NEVER skips a confirm for, whatever the toggles say.
NEVER_AUTOPILOT_ACTIONS = frozenset({
    "pay", "purchase", "payment",
    "delete_outside_h", "delete_protected",
    "scan_other", "hack_other", "access_other_account",
    "protected",
})

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "how", "to", "my", "your", "is", "are", "it", "this", "that", "i",
    "you", "we", "best", "new", "top", "free", "make", "made", "get",
    "vs", "by", "at", "from", "into", "over", "under", "part", "video",
})


def is_h_drive_path(path):
    """True when `path` is on the H: drive (Windows H:\\ or H:/).
    Pure — used to decide whether a delete/install may skip confirm."""
    p = str(path or "").strip()
    return bool(re.match(r"(?i)^h:[\\/]", p))


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


# ------------------------------------------------------------ autopilot ---
class AutopilotState:
    """Master autopilot + YouTube autopilot. Both OFF by default.
    Only Faizan turns either on, in Settings on his PC."""

    def __init__(self, enabled=False, youtube_enabled=False):
        self.enabled = bool(enabled)
        self.youtube_enabled = bool(youtube_enabled)

    # -- toggles -------------------------------------------------------
    def enable(self):
        self.enabled = True
        return True

    def disable(self):
        self.enabled = False
        return False

    def enable_youtube(self):
        self.youtube_enabled = True
        return True

    def disable_youtube(self):
        self.youtube_enabled = False
        return False

    # -- what needs a confirm? ----------------------------------------
    def youtube_no_confirm(self):
        """YouTube uploads/posts skip confirm when either toggle is on."""
        return bool(self.enabled or self.youtube_enabled)

    def needs_confirm(self, action="", **kw):
        """True when TORVIS must ask for confirm before `action`.
        False only when master autopilot is ON and the action is not
        one of the hard limits. Pure."""
        act = str(action or "").strip().lower()
        if act in NEVER_AUTOPILOT_ACTIONS:
            return True
        if kw.get("protected"):
            return True
        if kw.get("other_person") or kw.get("other_account"):
            return True
        if kw.get("pay"):
            return True
        if act in ("delete", "delete_path"):
            # Deletes skip confirm only inside the H: drive, and only
            # when the user gave a separate explicit instruction.
            if not is_h_drive_path(kw.get("path", "")):
                return True
            if not kw.get("explicit"):
                return True
        if act == "install":
            if not autopilot_install_allowed(kw.get("path", ""),
                                             kw.get("official_source", False)):
                return True
        return not self.enabled

    def account_post_needs_confirm(self, account="", own_account=True):
        """Posting to an account: no confirm in master autopilot, but
        only for Faizan's OWN account — anyone else's account always
        needs a confirm (and, per the own-stuff rule, is refused
        without written permission). Pure."""
        if not own_account:
            return True
        return not self.enabled

    def install_needs_confirm(self, path="", official_source=False):
        return self.needs_confirm("install", path=path,
                                  official_source=official_source)

    # -- status ---------------------------------------------------------
    def status(self):
        return {"autopilot_enabled": self.enabled,
                "youtube_autopilot_enabled": self.youtube_enabled,
                "youtube_no_confirm": self.youtube_no_confirm(),
                "indicator": self.indicator_text(),
                "youtube_indicator": self.youtube_indicator_text(),
                "note": AUTOPILOT_NOTE,
                "youtube_note": YOUTUBE_AUTOPILOT_NOTE,
                "warning": AUTOPILOT_WARNING}

    def indicator_text(self):
        return "AUTOPILOT: ON" if self.enabled else "AUTOPILOT: OFF"

    def youtube_indicator_text(self):
        return ("YOUTUBE AUTOPILOT: ON" if self.youtube_enabled
                else "YOUTUBE AUTOPILOT: OFF")

    def status_line(self):
        return (f"[AUTOPILOT] {self.indicator_text()} — "
                f"{self.youtube_indicator_text()} — "
                "confirm gates stay on when autopilot is off.")

    def youtube_status_line(self):
        return (f"[AUTOPILOT] {self.youtube_indicator_text()} — "
                "uploads need no confirm when on, two-step confirm when off.")


def autopilot_install_allowed(path="", official_source=False):
    """May an install skip its confirm in autopilot? Only when the
    installer is from an official source: either explicitly marked
    official_source (TORVIS downloaded it from an official site), or
    sitting in H:\\JARVIS-Work\\ where TORVIS puts official downloads.
    An unknown installer file is never autopiloted. Pure."""
    if official_source:
        return True
    return is_h_drive_path(path)


def meeting_alert_needs_confirm():
    """Meeting alerts are notifications, not actions — they NEVER need
    a confirm, in autopilot or not. Pure, always False."""
    return False


_AUTOPILOT_ON_RE = re.compile(
    r"\bturn\b.*\bautopilot\b.*\bon\b|\bautopilot\b.*\bon\b|\benable\b.*\bautopilot\b", re.I)
_AUTOPILOT_OFF_RE = re.compile(
    r"\bturn\b.*\bautopilot\b.*\boff\b|\bautopilot\b.*\boff\b|\bdisable\b.*\bautopilot\b", re.I)
_YT_AUTOPILOT_ON_RE = re.compile(r"\byoutube autopilot\b.*\bon\b|\bturn\b.*\byoutube autopilot\b.*\bon\b", re.I)
_YT_AUTOPILOT_OFF_RE = re.compile(r"\byoutube autopilot\b.*\boff\b", re.I)
_AUTOPILOT_STATUS_RE = re.compile(r"\bautopilot\b.*\b(status|state)\b", re.I)


def parse_autopilot_command(text):
    """'turn autopilot on/off', 'turn youtube autopilot on/off',
    'autopilot status' -> {action} or None. YouTube is checked first:
    'turn youtube autopilot on' contains 'autopilot on' too. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    if "autopilot" not in low:
        return None
    if "youtube" in low:
        if _YT_AUTOPILOT_OFF_RE.search(low):
            return {"action": "youtube_autopilot_off"}
        if _YT_AUTOPILOT_ON_RE.search(low):
            return {"action": "youtube_autopilot_on"}
        return {"action": "youtube_autopilot_status"}
    if _AUTOPILOT_STATUS_RE.search(low):
        return {"action": "autopilot_status"}
    if _AUTOPILOT_OFF_RE.search(low):
        return {"action": "autopilot_off"}
    if _AUTOPILOT_ON_RE.search(low):
        return {"action": "autopilot_on"}
    return {"action": "autopilot_status"}


def autopilot_self_check_line(state):
    """One [SELF-CHECK] autopilot line for the startup self-check."""
    if state is None:
        return "[SELF-CHECK] Autopilot: not available in this build, Sir."
    return (f"[SELF-CHECK] Autopilot: {state.indicator_text()} — "
            f"{state.youtube_indicator_text()} — OFF by default, "
            "protected list and own-stuff-only still apply when on.")


# ------------------------------------------------------------ YouTube: niche ---
def _topic_words(title):
    """Words in a video title that could be a topic: lowercased,
    letters only, 3+ letters, not a stopword. Pure."""
    words = re.findall(r"[a-zA-Z][a-zA-Z\-']{2,}", str(title or "").lower())
    return [w.strip("-'") for w in words if w not in STOPWORDS and len(w) >= 3]


def analyze_youtube_channel(videos, channel_name=""):
    """Recommend the best niche for HIS channel from real video data.
    `videos` is a list of {title, views, likes, topic?} (or None when
    YouTube is not connected — then the plain not-connected message).
    Topics come from each video's explicit `topic` when given, else
    from the words in its title. Ranked by total views, then average
    views. Never invents data: no videos -> no recommendation. Pure."""
    if videos is None:
        return {"ok": False, "connected": False,
                "error": YOUTUBE_NOT_CONNECTED_MESSAGE,
                "message": YOUTUBE_NOT_CONNECTED_MESSAGE}
    videos = list(videos or [])
    if not videos:
        return {"ok": False, "connected": True, "videos": 0, "topics": [],
                "best_niche": None,
                "message": ("Your channel has no videos I can read yet, "
                            "Sir — upload one first, then I will analyse "
                            "which topic performs best.")}
    totals = {}
    for v in videos:
        if not isinstance(v, dict):
            continue
        views = _to_int(v.get("views"), 0)
        likes = _to_int(v.get("likes"), 0)
        topic = str(v.get("topic") or "").strip().lower()
        words = [topic] if topic else _topic_words(v.get("title") or "")
        for w in set(words):
            row = totals.setdefault(w, {"topic": w, "videos": 0,
                                        "total_views": 0, "total_likes": 0})
            row["videos"] += 1
            row["total_views"] += views
            row["total_likes"] += likes
    topics = []
    for row in totals.values():
        row["avg_views"] = round(row["total_views"] / row["videos"]) if row["videos"] else 0
        topics.append(row)
    topics.sort(key=lambda r: (r["total_views"], r["avg_views"]), reverse=True)
    best = topics[0] if topics else None
    total_views = sum(_to_int(v.get("views"), 0) for v in videos if isinstance(v, dict))
    name = str(channel_name or "").strip()
    if best is None:
        return {"ok": False, "connected": True, "videos": len(videos),
                "topics": [], "best_niche": None,
                "message": ("I could not find a topic in your video "
                            "titles, Sir — give the videos clearer titles "
                            "and I will analyse them.")}
    return {"ok": True, "connected": True, "videos": len(videos),
            "total_views": total_views,
            "channel": name or None,
            "topics": topics,
            "best_niche": best["topic"],
            "best": best,
            "recommendation": (
                f"Best niche for your channel: '{best['topic']}' — "
                f"{best['videos']} video(s), {best['total_views']:,} total "
                f"views, {best['avg_views']:,} average views per video. "
                f"Make more videos about {best['topic']}, Sir."),
            "message": (
                f"Best niche for your channel: '{best['topic']}' — "
                f"{best['videos']} video(s), {best['total_views']:,} total "
                f"views, {best['avg_views']:,} average views per video.")}


def _hashtag(word):
    """One word -> a hashtag: letters/digits only, no spaces. Pure."""
    tag = re.sub(r"[^a-zA-Z0-9]", "", str(word or ""))
    return ("#" + tag) if tag else ""


def make_youtube_caption(title, topic="", best_topics=None):
    """Caption + hashtags for a video, from its title/topic and the
    channel's best-performing topics. No invented views. Pure."""
    title = str(title or "").strip() or "My new video"
    topic = str(topic or "").strip()
    tags = []
    for w in _topic_words(topic or title):
        tag = _hashtag(w)
        if tag and tag not in tags:
            tags.append(tag)
    for t in (best_topics or []):
        tag = _hashtag(t)
        if tag and tag not in tags:
            tags.append(tag)
    tags = tags[:8]
    if not tags:
        tags = ["#YouTube"]
    caption = (
        f"{title}\n\n"
        + (f"All about {topic} — " if topic else "")
        + "watch till the end, and tell me in the comments what you "
          "want next.\n\n"
        + " ".join(tags))
    return {"ok": True, "title": title, "topic": topic or None,
            "caption": caption, "hashtags": tags,
            "message": f"Caption ready for '{title}', Sir — hashtags: {' '.join(tags)}"}


def youtube_upload_needs_confirm(autopilot_state, confirmed=False):
    """YouTube upload confirm logic, shared by the tool and tests.
    Returns True when a confirm must still be asked: autopilot (master
    or YouTube) ON -> no confirm; OFF -> confirm unless the caller
    already passed confirmed=true. Pure."""
    if autopilot_state is not None and autopilot_state.youtube_no_confirm():
        return False
    return not bool(confirmed)


# ------------------------------------------------------------ site watcher ---
def load_watched_sites(text, use_defaults=False):
    """Parse watched-sites text: one URL per line, '#' comments and
    blank lines ignored. Returns a de-duplicated list, in order.
    With use_defaults=True and no URLs found, the default sites are
    returned. Pure."""
    sites = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith(("http://", "https://")) and line not in sites:
            sites.append(line)
    if not sites and use_defaults:
        return list(DEFAULT_WATCHED_SITES)
    return sites


def _content_hash(content):
    if content is None:
        return None
    if isinstance(content, bytes):
        raw = content
    else:
        raw = str(content).encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:16]


class SiteWatcher:
    """Watch a list of his sites, every 30 minutes while TORVIS runs.
    `fetcher(url)` is injectable in tests and returns
    (ok, status_code, content) — ok False means the site is down.
    Checking is read-only and never needs a confirm. Notifications
    are plain lines: site down, site back up, page changed."""

    def __init__(self, sites=None, interval_s=SITE_CHECK_INTERVAL_S,
                 fetcher=None):
        self.sites = list(sites) if sites else list(DEFAULT_WATCHED_SITES)
        self.interval_s = int(interval_s) if interval_s else SITE_CHECK_INTERVAL_S
        self.fetcher = fetcher
        self.last_status = {}   # url -> {"ok": bool, "status": int|None, "hash": str|None}
        self.last_checked_at = None

    def add_site(self, url):
        url = str(url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": f"That is not a website address, Sir: {url}"}
        if url in self.sites:
            return {"ok": True, "added": False, "url": url,
                    "message": f"I am already watching {url}, Sir."}
        self.sites.append(url)
        return {"ok": True, "added": True, "url": url,
                "message": f"Watching {url} now, Sir — I will tell you if it goes down or changes."}

    def remove_site(self, url):
        url = str(url or "").strip()
        if url in self.sites:
            self.sites.remove(url)
            self.last_status.pop(url, None)
            return {"ok": True, "removed": True, "url": url,
                    "message": f"Stopped watching {url}, Sir."}
        return {"ok": False, "error": f"I was not watching {url}, Sir."}

    def status(self):
        return {"sites": list(self.sites),
                "interval_minutes": round(self.interval_s / 60),
                "last_checked_at": self.last_checked_at,
                "last_status": {u: dict(v) for u, v in self.last_status.items()},
                "note": ("Checking is read-only and needs no confirm — "
                         "TORVIS tells you when a site goes down, comes "
                         "back up, or changes.")}

    def check_site(self, url, fetcher=None):
        """Check one site. Returns {url, ok, status, changed, notification}.
        First check never reports a 'change' (there is no before yet)."""
        fetch = fetcher or self.fetcher
        if fetch is None:
            return {"ok": False, "url": url,
                    "error": "No site checker available, Sir — the check needs the internet."}
        try:
            ok, status_code, content = fetch(url)
        except Exception as e:  # noqa: BLE001 — a failed check is "down", never a crash
            ok, status_code, content = False, None, None
            err = str(e)
        else:
            err = None
        content_hash = _content_hash(content) if ok else None
        prev = self.last_status.get(url)
        self.last_status[url] = {"ok": bool(ok), "status": status_code,
                                 "hash": content_hash}
        self.last_checked_at = time.time()
        notification = None
        changed = False
        if prev is None:
            if not ok:
                notification = f"Your site is down, Sir: {url}."
        elif prev.get("ok") and not ok:
            notification = (f"Your site just went down, Sir: {url} "
                            f"(was up, now not responding).")
        elif not prev.get("ok") and ok:
            notification = f"Your site is back up, Sir: {url}."
        elif ok and prev.get("hash") is not None and content_hash is not None \
                and prev.get("hash") != content_hash:
            changed = True
            notification = f"Your site changed, Sir: {url} — the page is different from last time I checked."
        result = {"ok": bool(ok), "url": url, "status": status_code,
                  "changed": changed, "notification": notification}
        if err:
            result["error"] = err
        return result

    def check_all(self, fetcher=None, now=None):
        """Check every watched site once. Returns a list of notification
        lines (empty when nothing changed). Never raises."""
        notes = []
        for url in list(self.sites):
            try:
                res = self.check_site(url, fetcher=fetcher)
            except Exception:  # noqa: BLE001 — one bad site never stops the rest
                continue
            if res.get("notification"):
                notes.append(res["notification"])
        return notes

    def due(self, now=None):
        """True when a check is due (30 minutes since the last one, or
        never checked). Pure-ish: `now` is injectable in tests."""
        if self.last_checked_at is None:
            return True
        now = float(now if now is not None else time.time())
        return (now - self.last_checked_at) >= self.interval_s


def site_watcher_self_check_line(watcher):
    """One [SELF-CHECK] site-watcher line for the startup self-check."""
    if watcher is None:
        return "[SELF-CHECK] Site watcher: not available in this build, Sir."
    return (f"[SELF-CHECK] Site watcher: watching {len(watcher.sites)} site(s) "
            f"every {round(watcher.interval_s / 60)} minutes — read-only, "
            "no confirm needed to check.")


# ------------------------------------------------------------ multilingual voice ---
# Pronunciation must be very good in Urdu and any other language, not
# just English. Rule: detect the language of EACH reply, pick the
# matching native neural voice when one is installed on Windows
# (ur-PK for Urdu / Roman Urdu, en-US / en-GB for English, and the
# matching locale for other languages when available), fall back
# plainly to the default voice when that locale is not installed, and
# NEVER mispronounce by forcing an English voice on Urdu text.
# Script detection is reliable (Urdu/Arabic script, Devanagari,
# Cyrillic, CJK, Greek); Latin-script languages use small distinctive
# word lists, and Roman Urdu uses BUILD 14's word list. When the
# language cannot be told apart, the reply is treated as English —
# and the status tool says so, instead of guessing a voice.
MULTILINGUAL_NOTE = (
    "Multilingual voice — detect the language of each reply and speak "
    "it with the matching native neural voice when one is installed: "
    "ur-PK for Urdu and Roman Urdu, en-GB / en-US for English, and the "
    "matching locale for other languages. If that locale is not "
    "installed on this PC, TORVIS falls back to the default voice and "
    "says so plainly — it never forces an English voice on Urdu text.")

# language -> speech locales, best first.
LANGUAGE_LOCALES = {
    "urdu": ["ur-PK"],
    "roman-urdu": ["ur-PK"],
    "mixed": ["ur-PK"],
    "english": ["en-GB", "en-US"],
    "hindi": ["hi-IN"],
    "punjabi": ["pa-IN", "pa-PK"],
    "arabic": ["ar-SA", "ar-EG"],
    "bengali": ["bn-IN", "bn-BD"],
    "french": ["fr-FR"],
    "spanish": ["es-ES", "es-MX"],
    "german": ["de-DE"],
    "turkish": ["tr-TR"],
    "russian": ["ru-RU"],
    "chinese": ["zh-CN"],
    "greek": ["el-GR"],
}
SUPPORTED_LANGUAGES = list(LANGUAGE_LOCALES.keys())

# Words a voice name may carry for a language (Windows names often
# say "Urdu (Pakistan)" or carry the locale tag instead).
VOICE_LANGUAGE_NAMES = {
    "urdu": ["urdu", "ur-pk"],
    "roman-urdu": ["urdu", "ur-pk"],
    "mixed": ["urdu", "ur-pk"],
    "english": ["english", "en-gb", "en-us"],
    "hindi": ["hindi", "hi-in"],
    "punjabi": ["punjabi", "pa-in", "pa-pk"],
    "arabic": ["arabic", "ar-sa", "ar-eg"],
    "bengali": ["bengali", "bn-in", "bn-bd"],
    "french": ["french", "fr-fr"],
    "spanish": ["spanish", "es-es", "es-mx"],
    "german": ["german", "de-de"],
    "turkish": ["turkish", "tr-tr"],
    "russian": ["russian", "ru-ru"],
    "chinese": ["chinese", "mandarin", "zh-cn"],
    "greek": ["greek", "el-gr"],
}

# Distinctive Latin-script words, per language. Two hits (or one
# distinctive greeting) is enough to call the language; one stray
# word is not.
_OTHER_LANGUAGE_WORDS = {
    "french": {"bonjour", "merci", "monsieur", "madame", "oui", "s'il",
               "vous", "avec", "pourquoi", "comment", "allez", "aussi"},
    "spanish": {"hola", "gracias", "buenos", "buenas", "por favor",
                "tambien", "también", "mucho", "quiero", "puedes"},
    "german": {"danke", "bitte", "guten", "morgen", "ich", "nicht",
               "und", "ist", "haben", "wieder", "schon"},
    "turkish": {"merhaba", "teşekkür", "tesekkur", "nasıl", "nasil",
                "günaydın", "gunaydin", "çok", "cok", "benim"},
    "punjabi": {"sat", "sri", "akal", "tussi", "tuhada", "ki", "haal"},
}
_URDU_SCRIPT_SPECIFIC = set("ٹڈڑںےھۃ")
_ARABIC_SCRIPT_RE = re.compile(r"[\u0600-\u06ff]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
_GURMUKHI_RE = re.compile(r"[\u0a00-\u0a7f]")
_BENGALI_RE = re.compile(r"[\u0980-\u09ff]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_GREEK_RE = re.compile(r"[\u0370-\u03ff]")


def _voice_text(voice):
    """A voice (string name, or an object with .name/.lang) -> one
    lowercase string to match against. Pure."""
    if voice is None:
        return ""
    if isinstance(voice, str):
        return voice.lower()
    name = getattr(voice, "name", "") or ""
    lang = getattr(voice, "lang", "") or ""
    # pyttsx3 voices carry .languages (a list of byte strings like
    # b'\x05en_GB') instead of .lang — decode those too.
    langs = getattr(voice, "languages", None) or []
    decoded = []
    for item in langs:
        try:
            decoded.append(item.decode("utf-8", "replace") if isinstance(item, bytes) else str(item))
        except Exception:  # noqa: BLE001
            pass
    return f"{name} {lang} {' '.join(decoded)}".lower()


def _voice_name(voice):
    if isinstance(voice, str):
        return voice
    return str(getattr(voice, "name", "") or getattr(voice, "id", "") or voice)


def detect_reply_language(text):
    """Detect the language of one reply. Returns a language key from
    SUPPORTED_LANGUAGES, or 'other' when it cannot be told apart.
    Script first (reliable), then distinctive Latin words, then
    BUILD 14's Roman Urdu / English detection. Pure."""
    t = str(text or "")
    if _GURMUKHI_RE.search(t):
        return "punjabi"
    if _DEVANAGARI_RE.search(t):
        return "hindi"
    if _BENGALI_RE.search(t):
        return "bengali"
    if _CYRILLIC_RE.search(t):
        return "russian"
    if _CJK_RE.search(t):
        return "chinese"
    if _GREEK_RE.search(t):
        return "greek"
    if _ARABIC_SCRIPT_RE.search(t):
        # Urdu-specific letters (ٹ ڈ ڑ ں ے) mean Urdu; Arabic script
        # without them is read as Arabic.
        return "urdu" if any(c in _URDU_SCRIPT_SPECIFIC for c in t) else "arabic"
    words = re.findall(r"[a-zA-Zçşğıüö']+", t.lower())
    if words:
        for lang, vocab in _OTHER_LANGUAGE_WORDS.items():
            hits = [w for w in words if w in vocab]
            if len(hits) >= 2:
                return lang
            if len(hits) == 1 and hits[0] in ("bonjour", "hola", "merhaba", "danke"):
                return lang
    try:
        import jarvis_build14 as _b14
        detected = _b14.detect_language(t)
    except Exception:  # noqa: BLE001 — BUILD 14 missing: English fallback
        detected = "english"
    if detected in ("urdu", "roman-urdu", "mixed", "english"):
        return detected
    return "other"


def locale_for_language(language):
    """Best speech locale for a language, or 'en-GB' as the plain
    fallback locale. Pure."""
    locales = LANGUAGE_LOCALES.get(str(language or "").strip().lower())
    return locales[0] if locales else "en-GB"


def pick_voice_for_language(available, language, per_language=None,
                            preferred_name=""):
    """Pick the installed voice for `language`. Order: (1) Faizan's
    per-language voice from Settings, (2) a voice whose name/lang
    matches the language's locale or language name, (3) None — the
    caller falls back to the default voice and says so plainly.
    Never forces an English voice on Urdu text: when the language is
    Urdu / Roman Urdu / mixed and no ur-PK voice is installed, this
    returns None (not an English voice). Pure."""
    lang = str(language or "").strip().lower()
    names = list(available or [])
    per_lang = per_language or {}
    chosen = per_lang.get(lang) if isinstance(per_lang, dict) else None
    if chosen:
        for v in names:
            if str(chosen).strip().lower() in _voice_text(v):
                return _voice_name(v)
    wanted = VOICE_LANGUAGE_NAMES.get(lang, [])
    for v in names:
        text = _voice_text(v)
        if any(w in text for w in wanted):
            return _voice_name(v)
    if lang in ("urdu", "roman-urdu", "mixed"):
        return None  # never mispronounce Urdu with an English voice
    if lang == "english":
        # Windows neural English voices are named, not tagged with a
        # locale (e.g. "Microsoft Ryan Online (Natural)") — a named
        # neural voice is the right English voice.
        for frag in ("ryan", "guy", "aria", "christopher", "sonia",
                     "jenny", "david"):
            for v in names:
                if frag in _voice_text(v):
                    return _voice_name(v)
    if preferred_name:
        for v in names:
            if str(preferred_name).strip().lower() in _voice_text(v):
                return _voice_name(v)
    return None


def pick_voice_for_text(available, text, per_language=None,
                        preferred_name=""):
    """Detect the language of `text` and pick its voice. Returns
    {language, locale, voice, installed, fallback_message}. When no
    matching voice is installed, voice is None and the message says
    so plainly — the caller uses the default voice. Pure."""
    language = detect_reply_language(text)
    locale = locale_for_language(language)
    voice = pick_voice_for_language(available, language,
                                    per_language=per_language,
                                    preferred_name=preferred_name)
    if voice:
        return {"language": language, "locale": locale, "voice": voice,
                "installed": True, "fallback_message": ""}
    return {"language": language, "locale": locale, "voice": None,
            "installed": False,
            "fallback_message": (
                f"No {locale} voice is installed on this PC, Sir — "
                "I will use the default voice for this reply, and it "
                "may not pronounce it perfectly. Install a "
                f"{locale} voice in Windows Settings > Time & language "
                "> Language, then I will use it.")}


def pronunciation_status(available, per_language=None):
    """Which language voices are actually installed? Returns
    {languages: [{language, locale, voice, installed}], missing: [...]}.
    `available` is voice names (strings) or voice objects. Pure."""
    rows = []
    for lang in SUPPORTED_LANGUAGES:
        voice = pick_voice_for_language(available, lang,
                                        per_language=per_language)
        rows.append({"language": lang,
                     "locale": LANGUAGE_LOCALES[lang][0],
                     "voice": voice, "installed": voice is not None})
    missing = [r["language"] for r in rows if not r["installed"]]
    return {"ok": True, "languages": rows, "missing": missing,
            "message": ("Installed voices: " +
                        ", ".join(f"{r['language']} ({r['voice']})"
                                  for r in rows if r["installed"])
                        if any(r["installed"] for r in rows)
                        else "No matching neural voices found yet, Sir — "
                             "the default voice will be used.")}


def validate_per_language_voices(value):
    """Clean a Settings voice-per-language dict: keep only known
    languages with a non-empty voice name. Pure."""
    cleaned = {}
    if not isinstance(value, dict):
        return cleaned
    for lang, name in value.items():
        lang = str(lang or "").strip().lower()
        name = str(name or "").strip()
        if lang in LANGUAGE_LOCALES and name:
            cleaned[lang] = name
    return cleaned


def multilingual_self_check_line(status=None):
    """One [SELF-CHECK] multilingual-voice line."""
    if status is None:
        return ("[SELF-CHECK] Multilingual voice: language is detected "
                "per reply — ur-PK for Urdu/Roman Urdu, matching locale "
                "for other languages, default voice when not installed.")
    installed = [r["language"] for r in status.get("languages", [])
                 if r.get("installed")]
    return (f"[SELF-CHECK] Multilingual voice: installed for "
            f"{', '.join(installed) if installed else 'no language yet'}"
            " — Urdu uses ur-PK, never an English voice.")


# ------------------------------------------------------------ human-like speaking ---
# Faizan's goal: the user should not even realise he is talking to an
# AI agent — he should think he is talking with a human. So TORVIS
# speaks like a person: natural pauses, short natural sentences, no
# robotic filler, no reading code or URLs aloud, a warm tone that
# matches the conversation, and speech that can be interrupted at
# any time (STOP SPEAKING / fist gesture / barge-in, BUILD 16).
# HARD RULE, kept in code and in the README: TORVIS must NOT claim
# to be a human, and must NOT hide that it is TORVIS when asked
# directly — it only SOUNDS human. Asked "are you human?" it answers
# plainly: it is TORVIS, an AI assistant.
HUMAN_STYLE_NOTE = (
    "Human-like speaking — sound like a person talking, not a robot: "
    "short natural sentences (1–3 at a time), natural pauses, no "
    "robotic filler, never read code or a URL aloud, warm tone that "
    "matches the conversation, and speech that can be interrupted at "
    "any time. Never claim to be human — if asked directly, say "
    "plainly you are TORVIS, an AI assistant.")

IDENTITY_ANSWER = (
    "No, Sir — I'm TORVIS, your AI assistant on your own PC. "
    "I just try to sound natural when I talk.")

_ROBOTIC_FILLER_RES = [
    re.compile(r"^(as an ai( language model)?|as a language model|i'?m an ai( assistant)?|i am an ai( assistant)?)[,.]?\s+", re.I),
    re.compile(r"^(let me check( that)?( for you)?|one moment( please)?|just a moment|hang on( a second)?|i'?ll check( that)?|checking( that)?|please wait( a moment)?)[,.]?\s+", re.I),
    re.compile(r"^(certainly|sure thing|of course|absolutely)[,.]?\s+(i (will|can|would)|let me)\b", re.I),
]
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_CODE_RE = re.compile(r"```.*?```|`[^`]*`", re.S)
_MARKDOWN_RE = re.compile(r"[#>*_~|]+")


def is_identity_question(text):
    """Is the user asking directly whether TORVIS is human / a real
    person / an AI? Pure — matched on the question, not the answer."""
    low = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    return bool(re.search(
        r"\bare you (a )?human\b|\bare you a real (person|human)\b"
        r"|\bare you (an )?ai\b|\bare you a robot\b"
        r"|\bare you really (a )?(human|person)\b", low))


def strip_robotic_filler(text):
    """Remove robotic filler from the START of a reply (and only the
    start — a direct identity answer is never stripped). Pure.
    Returns the cleaned text, or the original when nothing was filler."""
    t = str(text or "").strip()
    if not t:
        return t
    if is_identity_question(t):
        return t
    for pattern in _ROBOTIC_FILLER_RES:
        cleaned = pattern.sub("", t, count=1).strip()
        if cleaned and cleaned != t:
            t = cleaned
            break
    return t or text


def humanize_reply(text, max_sentences=3):
    """Make a reply sound like a person talking, for speaking.
    Strips robotic filler, never reads a URL or code aloud (URLs
    become 'that link', code blocks are dropped), keeps short natural
    sentences (at most `max_sentences`, long ones split at a natural
    pause), and keeps a warm, direct tone. Pure. The on-screen text
    is unchanged — this is for the spoken voice only."""
    t = str(text or "").strip()
    if not t:
        return ""
    if is_identity_question(t):
        return IDENTITY_ANSWER
    t = strip_robotic_filler(t)
    t = _CODE_RE.sub(" ", t)
    t = _URL_RE.sub("that link", t)
    t = _MARKDOWN_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    short = []
    for s in sentences:
        words = s.split()
        if len(words) > 30:
            # Split a long sentence at a natural pause (a comma).
            cut = s.find(",", 10)
            if cut > 10:
                short.append(s[:cut + 1].strip())
                short.append(s[cut + 1:].strip())
            else:
                short.append(s)
        else:
            short.append(s)
    short = [s for s in short if s][:max_sentences]
    out = " ".join(short).strip()
    if out and out[-1] not in ".!?":
        out += "."
    return out


def tone_for_reply(text):
    """Warm tone matching the conversation, as rate/pitch for the
    voice: questions lift slightly, good news brightens, an apology
    softens, everything else stays natural (1.0 / 1.0). Pure."""
    low = str(text or "").lower()
    if "?" in str(text or ""):
        return {"rate": 1.0, "pitch": 1.08, "tone": "question"}
    if "!" in str(text or "") or any(
            w in low for w in ("great", "done", "excellent", "wonderful", "amazing")):
        return {"rate": 1.05, "pitch": 1.1, "tone": "warm"}
    if any(w in low for w in ("sorry", "unfortunately", "failed", "sadly",
                              "couldn't", "could not")):
        return {"rate": 0.95, "pitch": 0.9, "tone": "gentle"}
    return {"rate": 1.0, "pitch": 1.0, "tone": "natural"}


def speaking_style_check(text):
    """Check one reply for human-like speaking problems. Returns
    {human_like, issues: [...]} — used by tests and by the self-check.
    Pure."""
    t = str(text or "")
    issues = []
    if strip_robotic_filler(t) != t.strip():
        issues.append("robotic filler at the start")
    if _URL_RE.search(t):
        issues.append("reads a URL aloud")
    if _CODE_RE.search(t):
        issues.append("reads code aloud")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]
    if len(sentences) > 3:
        issues.append(f"too many sentences ({len(sentences)} — speak 1–3)")
    if len(t.split()) > 60:
        issues.append("too long to speak naturally")
    if any(len(s.split()) > 30 for s in sentences):
        issues.append("a sentence is too long — split it at a pause")
    return {"human_like": not issues, "issues": issues,
            "sentences": len(sentences), "words": len(t.split())}


def human_style_self_check_line():
    """One [SELF-CHECK] human-like speaking line."""
    return ("[SELF-CHECK] Human-like speaking: short natural sentences, "
            "no robotic filler, never reads code or URLs aloud, warm "
            "tone, interruptible — and never claims to be human.")


# ------------------------------------------------------------ combined routing ---
def parse_build19_command(text):
    """Route one spoken/typed command to the BUILD 19 feature that owns
    it — autopilot, YouTube autopilot, watch a site, site status — or
    None. Pure. YouTube autopilot is checked inside the autopilot
    parser; site commands are checked after it."""
    result = parse_autopilot_command(text)
    if result is not None:
        return result
    low = str(text or "").strip().lower()
    if "watch" in low and ("site" in low or "http" in low):
        m = re.search(r"https?://\S+", str(text or "").strip())
        return {"action": "watch_site", "url": m.group(0) if m else ""}
    if "watched sites" in low or "list watched" in low:
        return {"action": "list_watched_sites"}
    if "site status" in low or "sites status" in low:
        return {"action": "site_status"}
    return None


def build19_self_check_lines(autopilot_state=None, watcher=None,
                             pronunciation=None):
    """All BUILD 19 [SELF-CHECK] lines, in order. Pure."""
    return [autopilot_self_check_line(autopilot_state),
            site_watcher_self_check_line(watcher),
            multilingual_self_check_line(pronunciation),
            human_style_self_check_line(),
            "[SELF-CHECK] Meeting alerts: 15 minutes before a meeting, "
            "no confirm ever — an alert is a notification, not an action."]
