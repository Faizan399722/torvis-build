"""BUILD 18 pure logic — clap wake, hand-gesture control, HUD mode,
taskbar + tray minimise, 3D-printer hook (stub only).

BUILD 18 (2026-11-23) — TORVIS CLAP WAKE, GESTURE CONTROL, HUD MODE,
TASKBAR + TRAY.
Marker: "BUILD 18 — TORVIS: CLAP WAKE, GESTURE CONTROL, HUD MODE,
TASKBAR + TRAY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK"

Faizan watched a Fatih Makes (@fatihmakes) TikTok demo and asked for
the same kind of features in TORVIS. This is an ORIGINAL build — no
Fatih Makes code exists here, and none was copied: his Mark 59 / Mark
58 are paid releases. Everything below is written from scratch.

Hard rules, in code and in the README — never silently broken:

* CLAP WAKE is OFF by default. It only wakes TORVIS when Faizan turns
  it on in Settings or says "turn clap wake on". It listens for a sharp
  DOUBLE clap — two short, loud spikes close together — and must NOT
  trigger on normal speech: a single spike never wakes, sustained loud
  sound (speech / music) never wakes, and the sensitivity setting only
  moves the spike threshold. If no microphone is available, TORVIS says
  so plainly — it never pretends to hear a clap.
* GESTURES are OFF by default and need the camera on (BUILD 17, local
  only, never streamed, no face recognition). Open palm = wake / show
  the HUD, swipe right = next, swipe left = previous, pinch = select /
  confirm, fist = stop speaking. MediaPipe is used when it is
  installed; otherwise a simple OpenCV hand-contour fallback counts
  raised fingers. If there is no camera, no MediaPipe and no OpenCV,
  TORVIS says so plainly and never guesses a gesture.
* HUD MODE switches the normal view to the full animated TORVIS HUD
  (the BUILD 17 rotating rings / pulsing orb) when a clap, a gesture,
  or a wake word happens, and back to normal on command. The existing
  HUD is kept — HUD mode is a switch, not a new face.
* MINIMISE — Faizan's explicit request: when minimised, TORVIS stays
  in the Windows taskbar AND in the system tray. Minimising must NOT
  hide it to tray-only. Clicking the taskbar icon restores the window
  directly — no need to go to the tray first. The tray icon is still
  there, and its right-click menu still works (Show / Hide / Quit).
  Closing the window still hides to the tray (Quit in the tray menu
  is the only real exit) — only minimise changes.
* 3D PRINTER is a HOOK ONLY. Faizan has not confirmed he has a
  printer. `printer_status` says plainly "No 3D printer connected"
  unless an OctoPrint URL is set in Settings, and `printer_control`
  refuses plainly without a configured printer. No full printer
  driver is built here, and no printer is ever invented.
* H: drive only: every file TORVIS downloads, unzips, builds or
  creates goes only in H:\\JARVIS-Work\\ — never the system drive.
* Ethical security: own PC only, never anyone else's system, network,
  account or website without their written permission.
* No Groq, no Ollama. Mistral mistral-medium-latest main, Gemini
  gemini-3.5-flash-lite fallback.

Everything in this file is unit-testable on Linux with the standard
library only. Microphone levels, camera frames, hand landmarks and
windows are all injectable in tests, so no real mic / camera / MediaPipe
is needed here.
"""
import re
import time

BUILD18_MARKER = ("BUILD 18 — TORVIS: CLAP WAKE, GESTURE CONTROL, HUD MODE, "
                  "TASKBAR + TRAY, NO GROQ, NO OLLAMA, MISTRAL MAIN, "
                  "GEMINI LITE FALLBACK")
BUILD17_MARKER = __import__("jarvis_build17").BUILD17_MARKER

CLAP_WAKE_NOTE = (
    "Clap wake — OFF by default. Turn it on in Settings or say 'turn "
    "clap wake on'. Two sharp claps close together wake TORVIS and "
    "switch on the HUD. One clap never wakes, and normal speech never "
    "wakes — only a double clap does. If no microphone is available, "
    "TORVIS says so plainly and never pretends to hear a clap.")

NO_MIC_MESSAGE = (
    "No microphone available, Sir — clap wake cannot listen. Check the "
    "microphone in Windows Settings, then turn clap wake on again. "
    "Typed commands still work.")

GESTURE_NOTE = (
    "Gestures — OFF by default, and they need the camera on (local "
    "only, never streamed, no face recognition). Open palm wakes and "
    "shows the HUD, swipe right is next, swipe left is previous, "
    "pinch selects, fist stops speaking. If no camera is found, or "
    "neither MediaPipe nor OpenCV is installed, TORVIS says so plainly "
    "and never guesses a gesture.")

NO_GESTURE_BACKEND_MESSAGE = (
    "Gestures are not available yet, Sir — the camera is on, but "
    "neither MediaPipe nor OpenCV is installed on this PC. Install one "
    "of them (MediaPipe is in requirements.txt) and try again. I will "
    "never guess a gesture.")

NO_PRINTER_MESSAGE = (
    "No 3D printer connected, Sir — I have no printer set up. If you "
    "have a 3D printer with OctoPrint, add its address in Settings "
    "(OctoPrint URL) and I will check it. I will not invent a printer.")

# ------------------------------------------------------------ clap wake ---
# A clap is a sharp spike: loud, and much louder than the level just
# before it. Normal speech is loud too, but it stays loud — it does not
# spike twice, briefly, from quiet. So a wake needs TWO spikes, each
# short and sharp, 0.25–1.0 seconds apart, with no sustained loud sound
# in between. One spike, or a long loud stretch, never wakes.

DEFAULT_SENSITIVITY = 0.5
MIN_SENSITIVITY = 0.1
MAX_SENSITIVITY = 1.0
# Higher sensitivity = lower threshold (easier to hear a clap).
# sensitivity 0.5 -> threshold 0.60; 1.0 -> 0.35; 0.1 -> 0.80.
MIN_SPIKE_RISE = 0.20
DOUBLE_CLAP_MIN_GAP_S = 0.25
DOUBLE_CLAP_MAX_GAP_S = 1.0
SPEECH_SUSTAINED_COUNT = 4  # this many loud levels in a row = speech/music


def clamp_sensitivity(value):
    """Clamp a sensitivity setting to 0.1–1.0. Pure."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SENSITIVITY
    return min(MAX_SENSITIVITY, max(MIN_SENSITIVITY, v))


def clap_threshold(sensitivity):
    """Spike loudness needed at this sensitivity. Pure."""
    return round(0.85 - clamp_sensitivity(sensitivity) * 0.5, 3)


class ClapDetector:
    """Double-clap detector over microphone levels (0.0–1.0).

    Feed one level at a time with `feed(level, now=None)`; it returns
    True only on the second sharp spike of a double clap. A single
    spike, a slow rise, or sustained loud sound returns False. The
    detector holds no audio — only spike times and the last level.
    `now` is injectable in tests (seconds, monotonic)."""

    def __init__(self, sensitivity=DEFAULT_SENSITIVITY):
        self.sensitivity = clamp_sensitivity(sensitivity)
        self._prev_level = 0.0
        self._spike_times = []
        self._loud_run = 0

    @property
    def threshold(self):
        return clap_threshold(self.sensitivity)

    def set_sensitivity(self, value):
        self.sensitivity = clamp_sensitivity(value)
        return self.sensitivity

    def reset(self):
        self._prev_level = 0.0
        self._spike_times = []
        self._loud_run = 0

    def feed(self, level, now=None):
        """One mic level (0.0–1.0). True only on a double clap."""
        try:
            level = float(level)
        except (TypeError, ValueError):
            return False
        level = min(1.0, max(0.0, level))
        now = float(now if now is not None else time.monotonic())
        threshold = self.threshold
        # Sustained loud sound (speech / music) is not a clap: count
        # consecutive loud levels, and if there are too many, drop all
        # spikes so a loud stretch can never become a double clap.
        if level >= threshold:
            self._loud_run += 1
        else:
            self._loud_run = 0
        if self._loud_run >= SPEECH_SUSTAINED_COUNT:
            self._spike_times = []
            self._prev_level = level
            return False
        is_spike = level >= threshold and (level - self._prev_level) >= MIN_SPIKE_RISE
        self._prev_level = level
        if not is_spike:
            return False
        self._spike_times.append(now)
        # Keep only recent spikes.
        self._spike_times = [t for t in self._spike_times
                             if now - t <= DOUBLE_CLAP_MAX_GAP_S]
        if len(self._spike_times) >= 2:
            gap = self._spike_times[-1] - self._spike_times[-2]
            if DOUBLE_CLAP_MIN_GAP_S <= gap <= DOUBLE_CLAP_MAX_GAP_S:
                self._spike_times = []
                self._loud_run = 0
                return True
        return False


def detect_double_clap(levels, sensitivity=DEFAULT_SENSITIVITY, step_s=0.05):
    """Convenience pure helper: does this list of levels (one per
    `step_s` seconds, starting at t=0) contain a double clap?"""
    detector = ClapDetector(sensitivity=sensitivity)
    for i, level in enumerate(levels or []):
        if detector.feed(level, now=i * step_s):
            return True
    return False


class ClapWakeState:
    """Clap-wake on/off + sensitivity. OFF by default. `mic_available`
    is None until probed (unknown), True when a mic opened, False when
    none was found."""

    def __init__(self, enabled=False, sensitivity=DEFAULT_SENSITIVITY):
        self.enabled = bool(enabled)
        self.detector = ClapDetector(sensitivity=sensitivity)
        self.mic_available = None
        self.last_wake_at = None

    @property
    def sensitivity(self):
        return self.detector.sensitivity

    def enable(self):
        self.enabled = True
        return True

    def disable(self):
        self.enabled = False
        self.detector.reset()
        return False

    def set_sensitivity(self, value):
        return self.detector.set_sensitivity(value)

    def indicator_text(self):
        return "CLAP WAKE: ON" if self.enabled else "CLAP WAKE: OFF"

    def status(self):
        avail = self.mic_available
        if avail is None:
            avail_text = "microphone not checked yet"
        elif avail:
            avail_text = "microphone available"
        else:
            avail_text = "no microphone available"
        return {"enabled": self.enabled,
                "sensitivity": self.sensitivity,
                "threshold": self.detector.threshold,
                "available": avail,
                "status_text": avail_text,
                "indicator": self.indicator_text(),
                "note": CLAP_WAKE_NOTE}

    def status_line(self):
        s = self.status()
        return (f"[CLAP] {s['indicator']} — {s['status_text']} — "
                f"sensitivity {s['sensitivity']}, threshold {s['threshold']}")

    def on_level(self, level, now=None):
        """Feed one mic level; returns True only on a double clap while
        clap wake is on. Never raises."""
        if not self.enabled:
            return False
        if self.detector.feed(level, now=now):
            self.last_wake_at = now if now is not None else time.monotonic()
            return True
        return False


_CLAP_ON_RE = re.compile(r"\bclap\b.*\b(wake|on)\b|\bturn\b.*\bclap\b.*\bon\b", re.I)
_CLAP_OFF_RE = re.compile(r"\bturn\b.*\bclap\b.*\boff\b|\bclap\b.*\boff\b", re.I)
_CLAP_SENS_RE = re.compile(r"clap\s+(?:wake\s+)?sensitivity\s*(?:to|=|is)?\s*([0-9]*\.?[0-9]+)", re.I)
_CLAP_STATUS_RE = re.compile(r"\bclap\b.*\b(status|state)\b", re.I)


def parse_clap_command(text):
    """'turn clap wake on' / 'clap sensitivity 0.7' / 'clap wake
    status' -> {action, ...} or None. Pure — the caller does the work."""
    t = str(text or "").strip()
    low = t.lower()
    if "clap" not in low:
        return None
    m = _CLAP_SENS_RE.search(low)
    if m:
        return {"action": "clap_sensitivity", "sensitivity": float(m.group(1))}
    # Status first: "clap wake status" contains "wake", which the
    # on-pattern would also match — check status before on/off.
    if _CLAP_STATUS_RE.search(low):
        return {"action": "clap_wake_status"}
    if _CLAP_OFF_RE.search(low):
        return {"action": "clap_wake_off"}
    if _CLAP_ON_RE.search(low):
        return {"action": "clap_wake_on"}
    return {"action": "clap_wake_status"}


def clap_self_check_line(state):
    """One [SELF-CHECK] clap-wake line for the startup self-check."""
    if state is None:
        return "[SELF-CHECK] Clap wake: not available in this build, Sir."
    s = state.status()
    return (f"[SELF-CHECK] Clap wake: {s['indicator']} — {s['status_text']} — "
            "double clap only, never speech, OFF by default.")

# ------------------------------------------------------------ gestures ---
# Gesture meanings (Fatih Makes style, our own code):
#   open palm (all fingers up)  -> wake / show HUD
#   swipe right (hand moves right) -> next
#   swipe left  (hand moves left)  -> previous
#   pinch (thumb tip close to index tip) -> select / confirm
#   fist (no fingers up) -> stop speaking
# A gesture only fires once per cooldown (0.8s) so holding a hand up
# does not repeat it endlessly.

GESTURE_COOLDOWN_S = 0.8
SWIPE_MIN_DX = 0.18
PINCH_MAX_DISTANCE = 0.05

GESTURE_ACTIONS = {
    "open_palm": "wake",
    "swipe_right": "next",
    "swipe_left": "previous",
    "pinch": "select",
    "fist": "stop_speaking",
}

GESTURE_DESCRIPTIONS = {
    "wake": "Open palm — wake TORVIS and show the HUD, Sir.",
    "next": "Swipe right — next, Sir.",
    "previous": "Swipe left — previous, Sir.",
    "select": "Pinch — selected, Sir.",
    "stop_speaking": "Fist — stopping speaking, Sir.",
}


def fingers_up_from_landmarks(landmarks):
    """21 hand landmarks [(x, y), ...] (MediaPipe order) -> a list of
    5 bools [thumb, index, middle, ring, little]. A finger is up when
    its tip is above (smaller y than) its middle joint. Pure. Returns
    None when the landmarks are not usable."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in landmarks]
    except (TypeError, ValueError, IndexError):
        return None
    if len(pts) != 21:
        return None
    # Tip / pip pairs: index 8/6, middle 12/10, ring 16/14, little 20/18.
    # Thumb: tip 4 is left/right of joint 3 (x), not up/down.
    fingers = [pts[4][0] < pts[3][0] if pts[0][0] > pts[9][0] else pts[4][0] > pts[3][0]]
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        fingers.append(pts[tip][1] < pts[pip][1])
    return fingers


def pinch_distance_from_landmarks(landmarks):
    """Distance between thumb tip (4) and index tip (8), 0.0–~1.0.
    Under PINCH_MAX_DISTANCE counts as a pinch. Pure."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in landmarks]
        if len(pts) != 21:
            return None
        dx = pts[4][0] - pts[8][0]
        dy = pts[4][1] - pts[8][1]
        return round((dx * dx + dy * dy) ** 0.5, 4)
    except (TypeError, ValueError, IndexError):
        return None


def classify_gesture(fingers_up=None, pinch_distance=None, hand_x=None,
                     prev_hand_x=None):
    """Classify one hand frame -> gesture action or None. Pure.
    `fingers_up` is [thumb, index, middle, ring, little]; `hand_x` /
    `prev_hand_x` are normalised palm x positions (0.0–1.0) for swipes.
    Pinch wins over open palm / fist; a swipe wins over a held pose
    only when the hand actually moved."""
    if hand_x is not None and prev_hand_x is not None:
        try:
            dx = float(hand_x) - float(prev_hand_x)
        except (TypeError, ValueError):
            dx = 0.0
        if dx >= SWIPE_MIN_DX:
            return "next"
        if dx <= -SWIPE_MIN_DX:
            return "previous"
    if pinch_distance is not None:
        try:
            if float(pinch_distance) <= PINCH_MAX_DISTANCE:
                return "select"
        except (TypeError, ValueError):
            pass
    if fingers_up is not None:
        try:
            ups = [bool(f) for f in fingers_up]
        except (TypeError, ValueError):
            return None
        if len(ups) != 5:
            return None
        if all(ups):
            return "wake"
        if not any(ups):
            return "stop_speaking"
    return None


def classify_from_landmarks(landmarks, prev_hand_x=None):
    """Classify from 21 MediaPipe landmarks. Pure. Hand x is the wrist
    (landmark 0) x, used for swipe detection against the previous frame."""
    fingers = fingers_up_from_landmarks(landmarks)
    pinch = pinch_distance_from_landmarks(landmarks)
    hand_x = None
    try:
        hand_x = float(landmarks[0][0])
    except (TypeError, ValueError, IndexError):
        hand_x = None
    return classify_gesture(fingers_up=fingers, pinch_distance=pinch,
                            hand_x=hand_x, prev_hand_x=prev_hand_x)


def classify_from_finger_count(count):
    """OpenCV hand-contour fallback: a raised-finger count -> gesture.
    5 = open palm (wake), 0 = fist (stop speaking). Counts 1–4 are not
    a gesture on their own — return None, never guess. Pure."""
    try:
        n = int(count)
    except (TypeError, ValueError):
        return None
    if n >= 5:
        return "wake"
    if n <= 0:
        return "stop_speaking"
    return None


def gesture_backend_available(mediapipe_module=None, cv2_module=None,
                              mediapipe_present=None, cv2_present=None):
    """Which gesture backend is available? Returns {mediapipe, opencv,
    backend, message}. `mediapipe_module` / `cv2_module` are injectable
    in tests (an object, or None); the *_present flags override the
    import check. Never raises, never imports anything by itself when
    a flag is given."""
    if mediapipe_present is None:
        if mediapipe_module is not None:
            mediapipe_present = True
        else:
            try:
                __import__("mediapipe")
                mediapipe_present = True
            except Exception:  # noqa: BLE001
                mediapipe_present = False
    if cv2_present is None:
        if cv2_module is not None:
            cv2_present = True
        else:
            try:
                __import__("cv2")
                cv2_present = True
            except Exception:  # noqa: BLE001
                cv2_present = False
    if mediapipe_present:
        backend_name = "mediapipe"
        message = "Gestures use MediaPipe hand tracking, Sir — local only."
    elif cv2_present:
        backend_name = "opencv-contour"
        message = ("Gestures use the OpenCV hand-contour fallback, Sir — "
                   "open palm and fist only, local only.")
    else:
        backend_name = "none"
        message = NO_GESTURE_BACKEND_MESSAGE
    return {"mediapipe": bool(mediapipe_present), "opencv": bool(cv2_present),
            "backend": backend_name, "message": message}


class GestureState:
    """Gesture control on/off. OFF by default. `last_gesture` is the
    last action fired; `last_fired_at` enforces the cooldown."""

    def __init__(self, enabled=False):
        self.enabled = bool(enabled)
        self.last_gesture = None
        self.last_fired_at = None
        self._prev_hand_x = None

    def enable(self):
        self.enabled = True
        return True

    def disable(self):
        self.enabled = False
        self._prev_hand_x = None
        return False

    def indicator_text(self):
        return "GESTURES: ON" if self.enabled else "GESTURES: OFF"

    def status(self):
        return {"enabled": self.enabled,
                "indicator": self.indicator_text(),
                "last_gesture": self.last_gesture,
                "note": GESTURE_NOTE}

    def status_line(self):
        s = self.status()
        return (f"[GESTURE] {s['indicator']}"
                + (f" — last gesture: {s['last_gesture']}" if s["last_gesture"] else ""))

    def update(self, action, now=None):
        """Record a classified gesture action. Returns the action when
        it fires, or None when gestures are off, the action is None, or
        the same action is still inside its cooldown. Never raises."""
        if not self.enabled or not action:
            return None
        now = float(now if now is not None else time.monotonic())
        if (self.last_gesture == action and self.last_fired_at is not None
                and now - self.last_fired_at < GESTURE_COOLDOWN_S):
            return None
        self.last_gesture = action
        self.last_fired_at = now
        return action

    def update_from_landmarks(self, landmarks, now=None):
        """Classify one frame of landmarks and fire it (cooldown-aware).
        Returns the fired action or None."""
        if not self.enabled:
            return None
        action = classify_from_landmarks(landmarks, prev_hand_x=self._prev_hand_x)
        try:
            self._prev_hand_x = float(landmarks[0][0])
        except (TypeError, ValueError, IndexError):
            pass
        return self.update(action, now=now)

    def update_from_finger_count(self, count, now=None):
        """Classify from the OpenCV fallback finger count and fire it."""
        if not self.enabled:
            return None
        return self.update(classify_from_finger_count(count), now=now)


_GESTURE_ON_RE = re.compile(r"\b(gesture|gestures)\b.*\b(on|enable|start)\b|\benable\b.*\bgesture", re.I)
_GESTURE_OFF_RE = re.compile(r"\b(gesture|gestures)\b.*\b(off|disable|stop)\b|\bdisable\b.*\bgesture", re.I)
_GESTURE_STATUS_RE = re.compile(r"\bgesture\b.*\b(status|state)\b", re.I)


def parse_gesture_command(text):
    """'turn gestures on' / 'gestures off' / 'gesture status' ->
    {action} or None. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    if "gesture" not in low:
        return None
    if _GESTURE_OFF_RE.search(low):
        return {"action": "gestures_off"}
    if _GESTURE_ON_RE.search(low):
        return {"action": "gestures_on"}
    if _GESTURE_STATUS_RE.search(low):
        return {"action": "gesture_status"}
    return {"action": "gesture_status"}


def gesture_self_check_line(state, backend_info=None):
    """One [SELF-CHECK] gesture line for the startup self-check."""
    if state is None:
        return "[SELF-CHECK] Gestures: not available in this build, Sir."
    backend_name = (backend_info or {}).get("backend", "not checked yet")
    return (f"[SELF-CHECK] Gestures: {state.indicator_text()} — backend: "
            f"{backend_name} — camera only, local only, no face recognition.")

# ------------------------------------------------------------ HUD mode ---
HUD_MODE_NORMAL = "normal"
HUD_MODE_FULL = "hud"


class HudModeState:
    """HUD mode switch: 'normal' (the usual view) or 'hud' (the full
    animated TORVIS HUD — BUILD 17 rotating rings / pulsing orb).
    Starts in 'normal'; a clap, a gesture or a wake word switches it
    to 'hud', and 'hud mode off' / 'normal mode' switches it back."""

    def __init__(self, mode=HUD_MODE_NORMAL):
        self.mode = mode if mode in (HUD_MODE_NORMAL, HUD_MODE_FULL) else HUD_MODE_NORMAL

    @property
    def hud_mode(self):
        return self.mode == HUD_MODE_FULL

    def enter_hud(self):
        self.mode = HUD_MODE_FULL
        return True

    def exit_hud(self):
        self.mode = HUD_MODE_NORMAL
        return False

    def toggle(self):
        if self.hud_mode:
            return self.exit_hud()
        return self.enter_hud()

    def indicator_text(self):
        return "HUD MODE: ON" if self.hud_mode else "HUD MODE: OFF"

    def status(self):
        return {"hud_mode": self.hud_mode, "mode": self.mode,
                "indicator": self.indicator_text()}

    def status_line(self):
        return f"[HUD] {self.indicator_text()} — full animated TORVIS HUD." if self.hud_mode else \
            f"[HUD] {self.indicator_text()} — normal view."


_HUD_ON_RE = re.compile(r"\b(hud mode|hud)\b.*\b(on|show|switch|open)\b|\bswitch to hud\b|\bshow (the )?hud\b", re.I)
_HUD_OFF_RE = re.compile(r"\b(hud mode|hud)\b.*\b(off|hide|close)\b|\bnormal mode\b|\bexit hud\b", re.I)


def parse_hud_mode_command(text):
    """'hud mode on' / 'show the hud' / 'normal mode' -> {action} or
    None. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    if "hud" not in low and "normal mode" not in low:
        return None
    if _HUD_OFF_RE.search(low):
        return {"action": "hud_mode_off"}
    if _HUD_ON_RE.search(low):
        return {"action": "hud_mode_on"}
    return {"action": "hud_mode_status"}


def hud_mode_self_check_line(state):
    """One [SELF-CHECK] HUD-mode line for the startup self-check."""
    if state is None:
        return "[SELF-CHECK] HUD mode: not available in this build, Sir."
    return f"[SELF-CHECK] HUD mode: {state.indicator_text()} — BUILD 17 animated HUD on wake."

# ------------------------------------------------------------ taskbar + tray ---
# BUILD 18 — Faizan's explicit request: minimising must NOT hide TORVIS
# to tray-only. The window stays in the Windows taskbar AND the tray
# icon stays in the system tray. Clicking the taskbar icon restores the
# window directly. The tray right-click menu still offers Show / Hide /
# Quit. Closing the window still hides to the tray (Quit is the only
# real exit) — only minimise changes.
MINIMIZE_TO_TASKBAR = True
TRAY_MENU_ITEMS = ["Show", "Hide", "Quit"]


def minimize_action():
    """What happens on minimise (BUILD 18). Pure — the window code in
    jarvis.py applies it: minimise the window, do NOT hide it, keep
    the tray icon running."""
    return {"action": "minimize_to_taskbar",
            "hide_to_tray": False,
            "stay_in_taskbar": True,
            "tray_icon": True,
            "restore_via": "taskbar",
            "message": ("Minimised to the taskbar, Sir — TORVIS is still "
                        "in the taskbar and in the tray. Click the taskbar "
                        "icon to bring it back, no need to go to the tray.")}


def close_action():
    """What happens on close (unchanged from BUILD 17): hide to the
    tray, keep listening — Quit in the tray menu is the only real exit.
    Pure."""
    return {"action": "hide_to_tray",
            "hide_to_tray": True,
            "stay_in_taskbar": False,
            "tray_icon": True,
            "restore_via": "tray",
            "message": ("TORVIS is still running in the tray, Sir — "
                        "right-click the tray icon to open it, or say "
                        "\"Torvis\". Quit in the tray menu is the only "
                        "way to close it.")}


def restore_action():
    """Restoring the window — from the taskbar icon or the tray Show
    item. Pure."""
    return {"action": "restore_window",
            "show": True, "restore": True,
            "message": "TORVIS is back, Sir."}


def tray_menu_items():
    """The tray right-click menu items, in order. Pure."""
    return list(TRAY_MENU_ITEMS)


def window_behaviour():
    """The full BUILD 18 window behaviour, for the self-check and for
    tests. Pure."""
    return {"minimize": minimize_action(),
            "close": close_action(),
            "restore": restore_action(),
            "tray_menu": tray_menu_items(),
            "minimize_to_taskbar": MINIMIZE_TO_TASKBAR}


def taskbar_self_check_line():
    """One [SELF-CHECK] taskbar/tray line for the startup self-check."""
    return ("[SELF-CHECK] Taskbar + tray: minimise stays in the taskbar "
            "AND the tray — click the taskbar icon to restore, no need "
            "to go to the tray first. Tray menu: Show / Hide / Quit.")

# ------------------------------------------------------------ 3D printer (hook only) ---
# Faizan has NOT confirmed he has a 3D printer. This is a hook only:
# status says plainly there is no printer unless an OctoPrint URL is
# set in Settings; control refuses plainly without one. No driver, no
# invented printer, no print is ever started here.

PRINTER_NOTE = (
    "3D printer — hook only. No printer is connected yet. If you have "
    "a 3D printer with OctoPrint, add its address in Settings "
    "(OctoPrint URL) and TORVIS will check it. Until then, printer "
    "commands are refused plainly — nothing is ever invented.")


class PrinterState:
    """3D-printer hook state. `octoprint_url` is empty until Faizan
    sets it in Settings; `connected` is False until a real check
    against that URL succeeds (that check lives on Windows, not here)."""

    def __init__(self, octoprint_url=""):
        self.octoprint_url = str(octoprint_url or "").strip()
        self.connected = False

    def set_octoprint_url(self, url):
        """Set the OctoPrint URL. Only http(s) URLs are accepted; a
        blank clears it. Returns the stored URL ('' when cleared)."""
        url = str(url or "").strip()
        if not url:
            self.octoprint_url = ""
            self.connected = False
            return ""
        if not re.match(r"^https?://", url, re.I):
            return self.octoprint_url
        self.octoprint_url = url
        self.connected = False
        return self.octoprint_url

    def status(self):
        if not self.octoprint_url:
            return {"connected": False, "configured": False,
                    "octoprint_url": "",
                    "message": NO_PRINTER_MESSAGE,
                    "note": PRINTER_NOTE}
        return {"connected": self.connected, "configured": True,
                "octoprint_url": self.octoprint_url,
                "message": ("A 3D printer is set up at "
                            f"{self.octoprint_url}, Sir — but I have not "
                            "checked it yet. Say 'printer status' again "
                            "after I have checked it."),
                "note": PRINTER_NOTE}

    def status_line(self):
        return f"[PRINTER] {self.status()['message']}"


def printer_control(state, action="", confirmed=False):
    """Printer control — STUB ONLY. Refuses plainly when no printer is
    configured, and refuses to start a print without a configured
    printer even when confirmed. Never raises, never invents a printer."""
    if state is None or not getattr(state, "octoprint_url", ""):
        return {"ok": False, "error": NO_PRINTER_MESSAGE}
    if not getattr(state, "connected", False):
        return {"ok": False,
                "error": ("The 3D printer at "
                          f"{state.octoprint_url} is not connected yet, "
                          "Sir — I cannot control it until the connection "
                          "is checked. Nothing was sent to any printer.")}
    return {"ok": False,
            "error": ("Printer control is a hook only in BUILD 18, Sir — "
                      "the printer is set up, but full print control is "
                      "not built yet. Nothing was sent to the printer.")}


_PRINTER_STATUS_RE = re.compile(r"\bprinter\b.*\b(status|state|connected)\b|\b3d printer\b", re.I)


def parse_printer_command(text):
    """'printer status' / 'is the 3d printer connected?' -> {action}
    or None. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    if "printer" not in low:
        return None
    if _PRINTER_STATUS_RE.search(low):
        return {"action": "printer_status"}
    return {"action": "printer_status"}


def printer_self_check_line(state):
    """One [SELF-CHECK] printer line for the startup self-check."""
    if state is None:
        return "[SELF-CHECK] 3D printer: hook only — no printer connected, Sir."
    if not state.octoprint_url:
        return "[SELF-CHECK] 3D printer: no printer connected — hook only, set an OctoPrint URL in Settings if you have one."
    return f"[SELF-CHECK] 3D printer: OctoPrint URL set ({state.octoprint_url}) — not checked yet."

# ------------------------------------------------------------ combined routing ---
def parse_build18_command(text):
    """Route one spoken/typed command to the BUILD 18 feature that owns
    it — clap wake, gestures, HUD mode, or the printer hook — or None.
    Pure. Order matters: clap first, then gestures, then HUD, then
    printer (a 'printer status' sentence never matches the others)."""
    for parser in (parse_clap_command, parse_gesture_command,
                   parse_hud_mode_command, parse_printer_command):
        result = parser(text)
        if result is not None:
            return result
    return None


def build18_self_check_lines(clap_state=None, gesture_state=None,
                             hud_state=None, printer_state=None,
                             gesture_backend=None):
    """All four BUILD 18 [SELF-CHECK] lines, in order. Pure."""
    return [clap_self_check_line(clap_state),
            gesture_self_check_line(gesture_state, gesture_backend),
            hud_mode_self_check_line(hud_state),
            printer_self_check_line(printer_state),
            taskbar_self_check_line()]
