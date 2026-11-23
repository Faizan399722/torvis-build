"""BUILD 20 pure logic — silent fallback (see backend.py / jarvis.py)
plus the voice fix: Microsoft Edge TTS (edge-tts) as the PRIMARY
voice engine, with pyttsx3 / Windows SAPI only as offline fallback.

Why: TORVIS spoke through pyttsx3 / SAPI — the old robotic voice,
which is why it sounded like an AI voice. The TikTok Jarvis builds
Faizan watched use cloud neural TTS (ElevenLabs / Azure neural
voices, paid / API key). edge-tts is the FREE equivalent: Microsoft
Edge's neural voices (en-GB-RyanNeural, ur-PK-AsadNeural, …), no API
key, no account — it streams an MP3 and plays it locally. It needs
internet; when it is not installed or offline, TORVIS falls back
plainly to SAPI and says so in the Task Log, never pretending.

Stdlib only — no audio, no network — so it is unit-testable on Linux.
The actual synthesis/playback lives in jarvis.py (Speaker), which
uses these pure helpers and injectable hooks.
"""
import re

BUILD20_MARKER = ("BUILD 20 — TORVIS: SILENT FALLBACK, NO OVERLOAD LINE, "
                  "NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK")

# Microsoft Edge neural voices, best first per language. These are
# the free edge-tts voices — no key, no account. Male first (TORVIS
# is a calm male voice), female second where it is the only neural
# voice for that locale.
EDGE_TTS_VOICES = {
    "english": ["en-GB-RyanNeural", "en-US-GuyNeural", "en-US-AriaNeural",
                "en-GB-SoniaNeural"],
    "urdu": ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"],
    "roman-urdu": ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"],
    "mixed": ["ur-PK-AsadNeural", "ur-PK-UzmaNeural"],
    "hindi": ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural"],
    "punjabi": ["pa-IN-GurleenNeural"],
    "arabic": ["ar-SA-HamedNeural", "ar-EG-SalmaNeural"],
    "bengali": ["bn-IN-BashkarNeural", "bn-BD-NabanitaNeural"],
    "french": ["fr-FR-HenriNeural", "fr-FR-DeniseNeural"],
    "spanish": ["es-ES-AlvaroNeural", "es-MX-JorgeNeural"],
    "german": ["de-DE-ConradNeural", "de-DE-KatjaNeural"],
    "turkish": ["tr-TR-AhmetNeural", "tr-TR-EmelNeural"],
    "russian": ["ru-RU-DmitryNeural", "ru-RU-SvetlanaNeural"],
    "chinese": ["zh-CN-YunyangNeural", "zh-CN-XiaoxiaoNeural"],
    "greek": ["el-GR-NestorasNeural", "el-GR-AthinaNeural"],
}
SUPPORTED_LANGUAGES = list(EDGE_TTS_VOICES.keys())

# Natural speech: a touch slower than default (~0.9x), natural pitch.
# edge-tts rate/pitch are relative strings: "-10%" is ~0.9x speed.
EDGE_TTS_RATE = "-10%"
EDGE_TTS_PITCH = "+0Hz"
EDGE_TTS_VOLUME = "+0%"
# pyttsx3 (SAPI) backup: 150 wpm instead of the old 165 — slower,
# clearer pronunciation. See jarvis.py VOICE_RATE_DEFAULT.
SAPI_RATE_DEFAULT = 150


def is_neural_voice_name(name):
    """True when a voice name is a neural voice: Microsoft 'Online
    (Natural)', Edge '*Neural', or the word 'natural'/'online'."""
    low = str(name or "").lower()
    return ("neural" in low or "natural" in low or "online" in low)


def _voice_text(voice):
    if voice is None:
        return ""
    if isinstance(voice, str):
        return voice.lower()
    name = getattr(voice, "name", "") or ""
    lang = getattr(voice, "lang", "") or ""
    return f"{name} {lang}".lower()


def prefer_neural_voices(voices):
    """Stable sort: neural voices first, everything else after, in
    the original order. Pure — used by the SAPI picker so a neural
    voice is never passed over for a robotic one."""
    voices = list(voices or [])
    return sorted(voices, key=lambda v: 0 if is_neural_voice_name(
        _voice_text(v) if not isinstance(v, str) else v) else 1)


def edge_voice_for_language(language, available=None, per_language=None):
    """Best edge-tts voice for `language`.

    `available`: None (unknown — return the default neural voice for
    the language, to be verified at runtime) or a list of voice names
    edge-tts actually offers on this PC. `per_language`: Faizan's
    Settings voice-per-language dict (voice names, e.g. Urdu ->
    "Microsoft Asad Online (Natural)" — matched loosely).
    Returns the edge-tts voice name, or None when a list was given
    and no matching neural voice is in it. Pure."""
    lang = str(language or "").strip().lower()
    wanted = EDGE_TTS_VOICES.get(lang) or EDGE_TTS_VOICES["english"]
    per_lang = per_language or {}
    chosen = per_lang.get(lang) if isinstance(per_lang, dict) else None
    if chosen:
        # A Settings name like "Microsoft Asad Online (Natural)" maps
        # to the edge voice with the same first name ("Asad").
        words = re.findall(r"[A-Za-z]+", str(chosen))
        for word in words:
            for voice in wanted:
                if word.lower() in voice.lower():
                    if available is None or any(
                            voice.lower() in str(a).lower()
                            for a in available):
                        return voice
    if available is None:
        return wanted[0]
    avail = [str(a) for a in available]
    for voice in wanted:
        for name in avail:
            if voice.lower() in name.lower():
                return voice
    return None


def detect_language(text):
    """Language of one reply, via BUILD 19 when present, else a small
    Roman-Urdu / English guess. Pure."""
    try:
        import jarvis_build19 as _b19
        return _b19.detect_reply_language(text)
    except Exception:  # noqa: BLE001
        pass
    t = str(text or "")
    if re.search(r"[\u0600-\u06ff]", t):
        return "urdu"
    if re.search(r"\b(mujhe|tumhara|mera|meri|kya|kaise|batao|chahiye|acha|theek|shukriya|aap|hai|hain|nahi)\b",
                 t, re.I):
        return "roman-urdu"
    return "english"


def edge_voice_for_text(text, available=None, per_language=None):
    """Detect the language of `text` and pick its edge-tts voice.
    Returns {language, voice, installed, fallback_message}. When no
    matching voice is known/installed, voice is None and the message
    says so plainly — the caller falls back to SAPI. Pure."""
    language = detect_language(text)
    voice = edge_voice_for_language(language, available=available,
                                    per_language=per_language)
    if voice:
        return {"language": language, "voice": voice, "installed": True,
                "fallback_message": ""}
    locale = {"urdu": "ur-PK", "roman-urdu": "ur-PK"}.get(language, "en-GB")
    return {"language": language, "voice": None, "installed": False,
            "fallback_message": (
                f"No {locale} neural voice is available for edge-tts, Sir — "
                "I will use the SAPI voice for this reply, and it may not "
                "pronounce it perfectly.")}


def build_edge_tts_command(voice, text, out_path, rate=EDGE_TTS_RATE,
                           pitch=EDGE_TTS_PITCH):
    """The `edge-tts` CLI command that synthesises `text` to `out_path`.
    Pure — the Speaker runs it, so it is testable without audio."""
    return ["edge-tts", "--voice", str(voice), "--rate", str(rate),
            "--pitch", str(pitch), "--file", str(out_path),
            "--text", str(text)]


def edge_tts_not_available_message(reason=""):
    """Plain Task-Log line when edge-tts cannot be used — never pretend
    the neural voice spoke. Pure."""
    detail = f" ({reason})" if reason else ""
    return ("Edge TTS is not available right now" + detail +
            " — using the SAPI voice for this reply instead.")


def pronunciation_install_note():
    """What Faizan installs on Windows for good pronunciation. Pure."""
    return (
        "For the best pronunciation, install these free voices in "
        "Windows Settings > Time & language > Language > Add a language "
        "(or Settings > Accessibility > Speech): English (United Kingdom) "
        "— Microsoft Ryan Online (Natural); English (United States) — "
        "Microsoft Guy Online (Natural); Urdu (Pakistan) — Microsoft Asad "
        "Online (Natural) / Uzma Online (Natural). edge-tts uses the "
        "same neural voices online with no install needed; SAPI needs "
        "them installed. The TikTok Jarvis voices are ElevenLabs / Azure "
        "neural TTS (paid, API key) — edge-tts is the free equivalent "
        "TORVIS now uses; ElevenLabs stays an optional hook if he ever "
        "wants that exact voice (his own API key in Settings, never in chat).")
