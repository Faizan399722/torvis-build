"""BUILD 17 pure logic — camera access, LOCAL ONLY.

BUILD 17 (2026-11-21) — TORVIS CAMERA ACCESS.
Marker: "BUILD 17 — TORVIS: CAMERA ACCESS, LOCAL ONLY, PHOTO IN H:
DRIVE, NEVER STREAMED, NO FACE RECOGNITION, NO GROQ, NO OLLAMA,
MISTRAL MAIN, GEMINI LITE FALLBACK"

Faizan asked TORVIS to access the camera too, if available.

Hard rules, in code and in the README — never silently broken:

* The camera is OFF by default. It only turns on when Faizan turns
  it on in Settings or says "turn camera on". A clear indicator
  (HUD chip + Task Log line) shows when it is on.
* LOCAL ONLY. The camera feed is never streamed anywhere, never
  sent to any server. A photo is a single still frame, saved only in
  H:\\JARVIS-Work\\Photos\\. Video is NEVER recorded without a spoken
  "confirm" first (two-step, like installs and calendar bookings).
* NO face recognition, NO identifying people. "What do you see?"
  describes the scene in plain words only (through the Screen
  Advisor vision path when available); it never names a person.
* If no camera is found, say "No camera found" plainly — never fake
  a feed. If Windows blocks the camera, say so and tell him how to
  allow it in Windows Settings (Privacy & security -> Camera).
* The only thing that ever leaves the PC is still the text of a
  question sent to the brain he chose (Mistral / Gemini fallback).
  A camera frame sent to the vision model is a still image the user
  asked TORVIS to look at, on his own PC — it is never sent
  anywhere else, never stored in the cloud, never logged.

How it works on Windows (honest, Linux-tested only):
* Live preview in the HUD uses the browser's own camera API
  (getUserMedia) — local only, no server, permission asked by
  Windows/WebView2 the first time.
* Taking a photo / describing what the camera sees uses OpenCV
  (cv2.VideoCapture(0)) on Windows — free, already in
  requirements.txt, so the GitHub build includes it. If OpenCV is
  missing, TORVIS says so plainly instead of faking a photo.
* Everything in this file is unit-testable on Linux with the
  standard library only. Camera hardware is injectable in tests
  (capture_factory / frame bytes), so no real camera is needed here.
"""
import base64
import re
from datetime import datetime
from pathlib import Path

import jarvis_build14 as b14
import jarvis_build15 as b15

BUILD17_MARKER = ("BUILD 17 — TORVIS: CAMERA ACCESS, LOCAL ONLY, PHOTO IN "
                  "H: DRIVE, NEVER STREAMED, NO FACE RECOGNITION, KALI VM "
                  "TYPING, NO GROQ, NO OLLAMA, MISTRAL MAIN, "
                  "GEMINI LITE FALLBACK")
BUILD16_MARKER = __import__("jarvis_build16").BUILD16_MARKER

CAMERA_PRIVACY_RULE = (
    "Camera privacy rule: the camera is OFF by default and only on "
    "when Faizan turns it on. The feed is local only — never streamed, "
    "never sent to any server. A photo is one still frame, saved only "
    "in H:\\JARVIS-Work\\Photos\\. Video is never recorded without a "
    "spoken 'confirm' first. No face recognition, no identifying "
    "people — 'what do you see?' describes the scene in plain words "
    "only. If no camera is found, say so plainly and never fake a feed.")

CAMERA_NOTE = (
    "Camera — local only, on this PC. It is OFF by default; turn it on "
    "in Settings or say 'turn camera on'. When it is on, a red "
    "'CAMERA: ON' chip shows in the HUD and the Task Log says so. "
    "Photos save only to H:\\JARVIS-Work\\Photos\\. Video is never "
    "recorded without you saying 'confirm' first. No face recognition. "
    "If no camera is found, TORVIS says 'No camera found' — it never "
    "fakes a feed. If Windows blocks the camera, allow it in Windows "
    "Settings -> Privacy & security -> Camera.")

NO_CAMERA_MESSAGE = (
    "No camera found, Sir — or Windows is blocking it. Check Windows "
    "Settings -> Privacy & security -> Camera, and make sure TORVIS is "
    "allowed, then say 'turn camera on' again. I will never fake a feed.")

CAMERA_OFF_MESSAGE = (
    "The camera is off, Sir — it is off by default. Say 'turn camera "
    "on' or turn it on in Settings, and I will switch it on for you.")

WINDOWS_CAMERA_SETTINGS = (
    "Windows Settings -> Privacy & security -> Camera -> let TORVIS "
    "use the camera.")

# ------------------------------------------------------------ paths ---
def default_photos_path():
    """Photos live only in H:\\JARVIS-Work\\Photos\\ (or the
    ~/JARVIS-Computer fallback on a PC with no H: drive). Never on
    the system drive, never C:. Injectable root in tests."""
    return b14.work_drive_path() / "Photos"

def photo_filename(when=None):
    """torvis-photo-20261121-093000.jpg — one name per second."""
    when = when or datetime.now()
    return when.strftime("torvis-photo-%Y%m%d-%H%M%S.jpg")

def photo_path(when=None, root=None):
    return (Path(root) if root else default_photos_path()) / photo_filename(when)

def is_valid_photo_path(path, root=None):
    """True only for a .jpg under the Photos folder (H: drive).
    Rejects C:, traversal (..), and any other extension. Pure."""
    try:
        root_p = Path(root) if root else default_photos_path()
        s = str(path or "").replace("\\", "/")
        root_s = str(root_p).replace("\\", "/").rstrip("/")
        if ".." in s.split("/"):
            return False
        # Windows-style absolute (H:/... or another drive) or POSIX
        # absolute: compare directly against the Photos root. A bare
        # filename is taken to live under the Photos root. (On Linux a
        # backslash is not a separator, so a drive-letter path must not
        # slip through as a bare filename — the drive-letter check
        # catches it.)
        if re.match(r"^[A-Za-z]:/", s) or s.startswith("/"):
            resolved = s
        else:
            resolved = root_s + "/" + s.rsplit("/", 1)[-1]
        if not resolved.startswith(root_s + "/"):
            return False
        if Path(resolved).suffix.lower() not in (".jpg", ".jpeg"):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False

# ------------------------------------------------------------ camera state ---
class CameraState:
    """One camera state, shared by the HUD toggle and the voice tools.
    OFF by default. `available` is None until probed (unknown), True
    when a camera opened, False when none was found / blocked."""
    def __init__(self, enabled=False):
        self.enabled = bool(enabled)
        self.available = None
        self.last_photo = None
        self.recording = False
        self.pending_recording = None

    def enable(self):
        self.enabled = True
        return True

    def disable(self):
        self.enabled = False
        self.recording = False
        self.pending_recording = None
        return False

    def indicator_text(self):
        return "CAMERA: ON" if self.enabled else "CAMERA: OFF"

    def status(self):
        avail = self.available
        if avail is None:
            avail_text = "not checked yet"
        elif avail:
            avail_text = "camera found"
        else:
            avail_text = "no camera found"
        return {"enabled": self.enabled,
                "available": avail,
                "status_text": avail_text,
                "indicator": self.indicator_text(),
                "last_photo": self.last_photo,
                "recording": self.recording,
                "privacy": CAMERA_NOTE}

    def status_line(self):
        s = self.status()
        return (f"[CAMERA] {s['indicator']} — {s['status_text']}"
                + (f" — last photo: {s['last_photo']}" if s["last_photo"] else ""))

# ------------------------------------------------------------ voice commands ---
_ON_RE = re.compile(r"\b(turn|switch)\b.*\bcamera\b.*\b(on|off)\b", re.I)
_TAKE_RE = re.compile(r"\b(take|snap|capture)\b.*\b(photo|picture|pic|selfie)\b", re.I)
_SEE_RE = re.compile(r"\bwhat do you see\b|\bdescribe\b.*\bcamera\b|\bcan you see me\b", re.I)
_TEST_RE = re.compile(r"\btest\b.*\bcamera\b|\bcamera\b.*\btest\b", re.I)
_RECORD_RE = re.compile(r"\b(record|film)\b.*\b(video|me)\b", re.I)
_STOP_RECORD_RE = re.compile(r"\bstop\b.*\brecording\b", re.I)

def parse_camera_command(text):
    """'turn camera on' / 'take my photo' / 'what do you see?' ->
    {action} or None. Pure — the caller does the work."""
    t = str(text or "").strip()
    low = t.lower()
    if _STOP_RECORD_RE.search(low):
        return {"action": "stop_recording"}
    if _RECORD_RE.search(low):
        return {"action": "record_video"}
    m = _ON_RE.search(low)
    if m:
        return {"action": "camera_on" if m.group(2) == "on" else "camera_off"}
    if _TAKE_RE.search(low):
        return {"action": "take_photo"}
    if _SEE_RE.search(low):
        return {"action": "describe_camera"}
    if _TEST_RE.search(low):
        return {"action": "test_camera"}
    if "camera" in low:
        return {"action": "camera_status"}
    return None

# ------------------------------------------------------------ capture ---
def probe_camera(capture_factory=None):
    """Is there a camera, and can it open? Returns
    {ok, available, error}. `capture_factory` is injectable in tests:
    a callable returning an object with isOpened()/read()/release(),
    or raising. With no factory, OpenCV is tried on Windows; if it
    is missing, that is reported plainly — never faked."""
    if capture_factory is not None:
        try:
            cap = capture_factory()
            opened = cap.isOpened() if hasattr(cap, "isOpened") else True
            if not opened:
                return {"ok": False, "available": False, "error": NO_CAMERA_MESSAGE}
            ok, _frame = cap.read() if hasattr(cap, "read") else (True, None)
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
            if not ok:
                return {"ok": False, "available": False, "error": NO_CAMERA_MESSAGE}
            return {"ok": True, "available": True, "error": ""}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "available": False,
                    "error": f"No camera found, Sir — {e}"}
    try:
        import cv2  # noqa: PLC0415 — Windows only, lazy import
    except Exception:  # noqa: BLE001
        return {"ok": False, "available": False,
                "error": ("Camera is not available yet, Sir — OpenCV is not "
                          "installed. It is in requirements.txt, so rebuild "
                          "the exe from GitHub and it will be included. "
                          "I will never fake a feed.")}
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap.release()
            return {"ok": False, "available": False, "error": NO_CAMERA_MESSAGE}
        ok, _frame = cap.read()
        cap.release()
        if not ok:
            return {"ok": False, "available": False, "error": NO_CAMERA_MESSAGE}
        return {"ok": True, "available": True, "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "available": False,
                "error": f"No camera found, Sir — {e}"}

def capture_frame_bytes(capture_factory=None):
    """One still frame as JPEG bytes, or {ok: False, error}.
    Injectable factory in tests; OpenCV on Windows otherwise."""
    if capture_factory is not None:
        try:
            cap = capture_factory()
            ok, frame = cap.read()
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
            if not ok or frame is None:
                return {"ok": False, "error": NO_CAMERA_MESSAGE, "bytes": None}
            if isinstance(frame, (bytes, bytearray)):
                return {"ok": True, "error": "", "bytes": bytes(frame)}
            # A numpy frame: encode it if cv2 is available.
            try:
                import cv2  # noqa: PLC0415
                ok2, buf = cv2.imencode(".jpg", frame)
                if not ok2:
                    return {"ok": False, "error": NO_CAMERA_MESSAGE, "bytes": None}
                return {"ok": True, "error": "", "bytes": buf.tobytes()}
            except Exception:  # noqa: BLE001
                return {"ok": False, "error": NO_CAMERA_MESSAGE, "bytes": None}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"No camera found, Sir — {e}", "bytes": None}
    try:
        import cv2  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {"ok": False, "bytes": None,
                "error": ("Camera is not available yet, Sir — OpenCV is not "
                          "installed. Rebuild the exe from GitHub (it is in "
                          "requirements.txt) and try again.")}
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap.release()
            return {"ok": False, "bytes": None, "error": NO_CAMERA_MESSAGE}
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return {"ok": False, "bytes": None, "error": NO_CAMERA_MESSAGE}
        ok2, buf = cv2.imencode(".jpg", frame)
        if not ok2:
            return {"ok": False, "bytes": None, "error": NO_CAMERA_MESSAGE}
        return {"ok": True, "error": "", "bytes": buf.tobytes()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "bytes": None, "error": f"No camera found, Sir — {e}"}

def take_photo(state, root=None, when=None, capture_factory=None, frame_bytes=None):
    """Take ONE photo. Camera must be ON first; the frame is saved
    only under Photos (H: drive). Never raises. Returns
    {ok, path, error}."""
    if state is None or not getattr(state, "enabled", False):
        return {"ok": False, "path": None, "error": CAMERA_OFF_MESSAGE}
    if frame_bytes is not None:
        data = bytes(frame_bytes)
    else:
        cap = capture_frame_bytes(capture_factory=capture_factory)
        if not cap.get("ok"):
            return {"ok": False, "path": None, "error": cap.get("error") or NO_CAMERA_MESSAGE}
        data = cap["bytes"]
    # A JPEG must start with the JPEG magic bytes — never save junk.
    if not data or data[:2] != b"\xff\xd8":
        return {"ok": False, "path": None,
                "error": "The camera gave me a bad frame, Sir — no photo saved. Try again."}
    path = photo_path(when=when, root=root)
    if not is_valid_photo_path(path, root=root):
        return {"ok": False, "path": None,
                "error": "I will only save photos in H:\\JARVIS-Work\\Photos\\, Sir — nowhere else."}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "path": None, "error": f"Could not save the photo, Sir: {e}"}
    if state is not None:
        state.last_photo = str(path)
    return {"ok": True, "path": str(path), "error": "",
            "message": f"Photo saved, Sir — {path}"}

def describe_camera_frame(state, advisor=None, capture_factory=None, frame_bytes=None):
    """'What do you see?' — describe the scene in plain words only.
    `advisor` is a callable taking base64 JPEG and returning text
    (the Screen Advisor vision path). No advisor -> say plainly it
    cannot describe it yet. Never names a person, never guesses."""
    if state is None or not getattr(state, "enabled", False):
        return {"ok": False, "description": "", "error": CAMERA_OFF_MESSAGE}
    if frame_bytes is not None:
        data = bytes(frame_bytes)
    else:
        cap = capture_frame_bytes(capture_factory=capture_factory)
        if not cap.get("ok"):
            return {"ok": False, "description": "", "error": cap.get("error") or NO_CAMERA_MESSAGE}
        data = cap["bytes"]
    if advisor is None:
        return {"ok": False, "description": "",
                "error": ("The camera is on, Sir, and I can see the feed — "
                          "but I cannot describe what I see yet, because "
                          "vision for the camera is not connected on this "
                          "brain. The photo itself is still saved locally "
                          "if you ask me to take one.")}
    try:
        b64 = base64.b64encode(data).decode()
        text = advisor(b64)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "description": "",
                "error": f"I could not describe the camera view, Sir — {e}"}
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "description": "",
                "error": "I looked at the camera, Sir, but I could not make out anything to describe."}
    return {"ok": True, "description": text, "error": ""}

# ------------------------------------------------------------ recording (two-step) ---
def request_recording(state, confirmed=False, seconds=10, recorder=None, root=None, when=None):
    """Video recording — TWO-STEP, like installs. confirmed=False ->
    plan only, nothing recorded. confirmed=True -> the injected
    `recorder` (Windows/OpenCV) runs; with no recorder, say plainly
    recording is not available yet. Never raises."""
    if state is None or not getattr(state, "enabled", False):
        return {"ok": False, "needs_confirm": False, "error": CAMERA_OFF_MESSAGE}
    try:
        secs = int(seconds or 10)
    except Exception:  # noqa: BLE001
        secs = 10
    secs = min(max(secs, 1), 60)
    if not confirmed:
        state.pending_recording = {"seconds": secs}
        return {"ok": False, "needs_confirm": True,
                "plan": (f"I will record {secs} seconds of video from your camera, "
                         "saved only in H:\\JARVIS-Work\\Photos\\. Say 'confirm' "
                         "to record it — nothing is recorded until you say so."),
                "error": ""}
    state.pending_recording = None
    if recorder is None:
        return {"ok": False, "needs_confirm": False,
                "error": ("Recording is not available on this PC yet, Sir — "
                          "the video recorder needs OpenCV on Windows. A photo "
                          "works now ('take my photo'); recording will be added "
                          "once the recorder is connected. Nothing was recorded.")}
    try:
        result = recorder(secs, root=root, when=when)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "needs_confirm": False, "error": f"Recording failed, Sir: {e}"}
    if isinstance(result, dict):
        return result
    return {"ok": True, "path": str(result), "error": ""}

def stop_recording(state):
    """Stop a recording in progress (or cancel a pending one)."""
    if state is None:
        return {"ok": False, "error": "Camera is not available, Sir."}
    state.recording = False
    state.pending_recording = None
    return {"ok": True, "error": "", "message": "Recording stopped, Sir — nothing more is being recorded."}

# ------------------------------------------------------------ self-check ---
def camera_self_check_line(state):
    """One [SELF-CHECK] camera line for the startup self-check. Pure.
    It starts with [SELF-CHECK] like every other self-check line."""
    if state is None:
        return "[SELF-CHECK] Camera: not available in this build, Sir."
    s = state.status()
    return (f"[SELF-CHECK] Camera: {s['indicator']} — {s['status_text']} — "
            "local only, never streamed, no face recognition. "
            "Photos save only to H:\\JARVIS-Work\\Photos\\.")

def local_only_camera_check(path, root=None):
    """True only for a path under the Photos folder (H: drive)."""
    return is_valid_photo_path(path, root=root)


# ------------------------------------------------------------ Kali VM ---
# BUILD 17 — type commands while Faizan is using Kali in a VM
# (VirtualBox / VMware). TORVIS types into the Kali VM window only —
# never into any other window — and only after the user says "confirm".
#
# Safety, in code and in the README — never silently broken:
# * Only type into the Kali VM window TORVIS just focused. If the Kali
#   window is not found / not running, say so plainly — never type
#   blindly into whatever window happens to be focused.
# * Never run a command against any target except his own PC/network
#   (localhost, 127.0.0.1, private LAN ranges) or a target he has
#   written authorisation for (one per line in
#   H:\\JARVIS-Work\\authorised-targets.txt). Anything else is refused
#   plainly, with no partial result — no scan, no login, no exploit
#   against someone else's system, ever.
# * Every typed command is logged with a [KALI] prefix (jarvis.log, via
#   the caller's logger) so there is always a record of what was typed.
# * If pyautogui is missing, say so plainly instead of pretending.

KALI_VM_RULE = (
    "Kali VM rule: only type into the Kali VM window TORVIS just "
    "focused — never into any other window. Never run a command "
    "against any target except your own PC/network or a target you "
    "have written authorisation for; unauthorised targets are refused "
    "plainly. Every typed command is logged with [KALI].")

KALI_NOT_FOUND_MESSAGE = (
    "I could not find your Kali VM window, Sir — is Kali running in "
    "VirtualBox or VMware? Open the Kali VM, click its terminal once, "
    "and try again. I will never type into another window.")

AUTHORISED_TARGETS_FILE = "authorised-targets.txt"

_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HOST_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")


def is_kali_vm_title(title):
    """True for a VirtualBox / VMware window running Kali."""
    t = str(title or "").lower()
    return "kali" in t


def find_kali_vm_window(window_finder=None):
    """Find the Kali VM window. `window_finder` is injectable in tests:
    a callable returning a list of objects with a `.title` (and an
    `.activate()` method). With no finder, pyautogui's window list is
    used on Windows. Returns {ok, title, window, error}."""
    if window_finder is not None:
        try:
            windows = list(window_finder() or [])
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "title": None, "window": None,
                    "error": f"I could not list the open windows, Sir — {e}"}
    else:
        try:
            import pyautogui  # noqa: PLC0415 — Windows only, lazy import
        except Exception:  # noqa: BLE001
            return {"ok": False, "title": None, "window": None,
                    "error": ("Typing needs pyautogui, Sir — it is not "
                              "installed on this PC. It is in "
                              "requirements.txt, so rebuild the exe from "
                              "GitHub and it will be included.")}
        try:
            windows = pyautogui.getWindowsWithTitle("Kali")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "title": None, "window": None,
                    "error": f"I could not list the open windows, Sir — {e}"}
    for w in windows or []:
        title = getattr(w, "title", "") or str(w)
        if is_kali_vm_title(title):
            return {"ok": True, "title": str(title), "window": w, "error": ""}
    return {"ok": False, "title": None, "window": None, "error": KALI_NOT_FOUND_MESSAGE}


def focus_kali_vm(window_finder=None):
    """Bring the Kali VM window to the front. Returns {ok, title, error}."""
    found = find_kali_vm_window(window_finder=window_finder)
    if not found.get("ok"):
        return {"ok": False, "title": None, "error": found.get("error") or KALI_NOT_FOUND_MESSAGE}
    try:
        win = found.get("window")
        if win is not None and hasattr(win, "activate"):
            win.activate()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "title": found.get("title"),
                "error": f"I found your Kali VM, Sir, but I could not bring it to the front — {e}"}
    return {"ok": True, "title": found.get("title"), "error": ""}


def _is_private_or_local_ip(ip):
    """True for localhost and private LAN ranges — his own network."""
    parts = str(ip or "").split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    if nums[0] == 127 or nums[0] == 10:
        return True
    if nums[0] == 192 and nums[1] == 168:
        return True
    if nums[0] == 172 and 16 <= nums[1] <= 31:
        return True
    return False


def extract_targets(command):
    """IPs and hostnames mentioned in a command (for the authorisation
    check). Pure."""
    cmd = str(command or "")
    targets = set(_IP_RE.findall(cmd))
    for host in _HOST_RE.findall(cmd):
        low = host.lower()
        # Skip file extensions and tool names that look like domains.
        if low.endswith((".txt", ".log", ".py", ".sh", ".jpg", ".png", ".pdf")):
            continue
        targets.add(low)
    return sorted(targets)


def load_authorised_targets(root=None):
    """Targets Faizan has written authorisation for — one per line in
    H:\\JARVIS-Work\\authorised-targets.txt. Empty set when the file
    does not exist yet. Pure-ish (reads one file)."""
    try:
        base = Path(root) if root else b14.work_drive_path()
        path = base / AUTHORISED_TARGETS_FILE
        if not path.exists():
            return set()
        return {ln.strip().lower() for ln in path.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")}
    except Exception:  # noqa: BLE001
        return set()


def check_kali_command(command, authorised=None):
    """Authorisation check for a Kali command. Returns {ok, error,
    targets}. OK when the command names no outside target at all, or
    only his own PC/network, or only targets in `authorised`."""
    cmd = str(command or "").strip()
    if not cmd:
        return {"ok": False, "error": "There is no command to type, Sir — tell me the command first.",
                "targets": []}
    if authorised is None:
        authorised = load_authorised_targets()
    authorised = {str(t).strip().lower() for t in (authorised or set())}
    targets = extract_targets(cmd)
    bad = []
    for t in targets:
        low = t.lower()
        if _IP_RE.match(t) and _is_private_or_local_ip(t):
            continue
        if low in ("localhost", "kali", "localhost.localdomain"):
            continue
        if low in authorised:
            continue
        bad.append(t)
    if bad:
        return {"ok": False,
                "error": ("I will not run that, Sir — it targets "
                          + ", ".join(bad)
                          + ", which is not your own PC/network and is not "
                            "on your written authorisation list. Add it to "
                            "H:\\JARVIS-Work\\authorised-targets.txt first, "
                            "one per line, if you have written permission "
                            "for it."),
                "targets": targets}
    return {"ok": True, "error": "", "targets": targets}


def parse_kali_command(text):
    """'run this in Kali: nmap -sn 192.168.1.0/24' / 'Torvis, type
    nmap -sV localhost in Kali' -> the bare command. Pure."""
    t = str(text or "").strip()
    low = t.lower()
    for prefix in ("run this in kali:", "run this in kali", "run in kali:",
                   "in kali:", "in kali", "type this in kali:", "type in kali:"):
        if low.startswith(prefix):
            t = t[len(prefix):].strip()
            low = t.lower()
            break
    # Trailing "in kali" / "in the kali vm".
    for suffix in (" in the kali vm", " in kali vm", " in kali"):
        if low.endswith(suffix):
            t = t[: -len(suffix)].strip()
            break
    return t


def kali_log_line(command):
    """One [KALI] log line for jarvis.log — every typed command."""
    return f"[KALI] typed into Kali VM: {command}"


def type_in_kali(command, confirmed=False, window_finder=None, typer=None,
                 press_enter=None, logger=None, authorised=None):
    """Type a command into the focused Kali VM terminal, then press
    Enter. TWO-STEP: confirmed=False returns the plan only (and the
    authorisation verdict) — nothing is typed. confirmed=True focuses
    the Kali VM, types the command, presses Enter, and logs it with
    [KALI]. `typer` / `press_enter` / `logger` are injectable in tests;
    with no typer, b14.type_text (pyautogui) is used. Never raises."""
    cmd = parse_kali_command(command)
    if not cmd:
        return {"ok": False, "needs_confirm": False,
                "error": "There is no command to type, Sir — tell me the command first."}
    check = check_kali_command(cmd, authorised=authorised)
    if not check.get("ok"):
        return {"ok": False, "needs_confirm": False, "error": check.get("error")}
    if not confirmed:
        return {"ok": False, "needs_confirm": True,
                "command": cmd, "targets": check.get("targets", []),
                "plan": (f"I will type this in your Kali VM terminal: {cmd} — "
                         "say 'confirm' and I will focus the Kali window, "
                         "type it, and press Enter. Nothing is typed until "
                         "you say so."),
                "error": ""}
    focused = focus_kali_vm(window_finder=window_finder)
    if not focused.get("ok"):
        return {"ok": False, "needs_confirm": False, "error": focused.get("error")}
    if typer is not None:
        try:
            typed = typer(cmd)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "needs_confirm": False, "error": f"Typing failed, Sir: {e}"}
        if isinstance(typed, dict) and not typed.get("ok", True):
            return {"ok": False, "needs_confirm": False,
                    "error": typed.get("error") or "Typing failed, Sir."}
    else:
        typed = b14.type_text(cmd)
        if isinstance(typed, dict) and not typed.get("ok"):
            return {"ok": False, "needs_confirm": False,
                    "error": typed.get("error") or "Typing failed, Sir."}
    if press_enter is not None:
        try:
            press_enter()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "needs_confirm": False,
                    "error": f"I typed the command, Sir, but Enter did not work — {e}"}
    else:
        try:
            import pyautogui  # noqa: PLC0415 — Windows only, lazy import
            pyautogui.press("enter")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "needs_confirm": False,
                    "error": ("Typing needs pyautogui, Sir — it is not "
                              f"installed on this PC. ({e})")}
    line = kali_log_line(cmd)
    if logger is not None:
        try:
            logger(line)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "needs_confirm": False, "command": cmd,
            "title": focused.get("title"), "error": "",
            "log_line": line,
            "message": f"Typed in your Kali VM, Sir: {cmd}"}
