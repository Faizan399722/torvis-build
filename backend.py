"""JARVIS — agent brain (native edition).

This is the NOVA agent brain, carried over unchanged except for the name
and the wake words: it talks to an AI model (Anthropic Claude, OpenAI,
or any OpenAI-compatible endpoint such as Google Gemini or a local
Ollama) and gives it full access to this computer through tools. Per the
owner's explicit choice there are NO approval prompts: tools execute
immediately, even risky ones. The one and only restriction is the owner's
protected-paths list (config → protected_paths): any file or folder on
that list is completely off-limits to every tool, including commands
that merely mention it. No third-party packages are needed here: only
the stdlib.

Auto-fallback: if the main brain can't be reached (e.g. the internet is
down), its free daily quota is finished, or it stays overloaded (429 /
500 / 503) after every retry, chat() automatically retries the message
once on a fallback brain (default: local Ollama), then switches back
so recovery is automatic.
"""
import base64, fnmatch, io, json, os, platform, re, shutil, socket, subprocess, sys, time, urllib.request, urllib.error, urllib.parse, webbrowser
from pathlib import Path

try:
    import jarvis_build14 as b14
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
    b14 = None

try:
    import jarvis_build15 as b15
except Exception:  # noqa: BLE001 — pure-logic module, always present in the zip
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
# BUILD 17 — TORVIS: CAMERA ACCESS, LOCAL ONLY, PHOTO IN H: DRIVE, NEVER STREAMED, NO FACE RECOGNITION, KALI VM TYPING, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 18 — TORVIS: CLAP WAKE, GESTURE CONTROL, HUD MODE, TASKBAR + TRAY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 19 — TORVIS: FULL AUTOPILOT NO-CONFIRM, YOUTUBE AUTOPILOT, CHANNEL NICHE, SITE WATCHER, MULTILINGUAL VOICE, HUMAN-LIKE SPEAKING, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 16: pending calendar booking awaiting a spoken "confirm".
# One at a time; confirming books it, anything else cancels it.
PENDING_BOOKING = None
# Test hooks: when set (a list), these are used instead of a real Google
# call. Never set in production code.
TEST_CALENDAR_EVENTS = None
TEST_GMAIL_MESSAGES = None
# BUILD 17: the brain's own camera state (OFF by default, local only) and
# an injectable capture factory for tests. Never set in production code.
_CAMERA_STATE = None
_CAMERA_CAPTURE_FACTORY = None
# BUILD 18: the brain's own clap-wake / gesture / HUD-mode / printer
# states (all OFF / normal / no printer by default). Never set in
# production code except by the tests below.
_CLAP_STATE = None
_GESTURE_STATE = None
_HUD_STATE = None
_PRINTER_STATE = None
# BUILD 19: the brain's own autopilot + site-watcher states (both
# autopilot toggles OFF by default). Never set in production code
# except by the tests below. TEST_YOUTUBE_VIDEOS, when set to a list
# (or None), is used instead of a real YouTube API call.
_AUTOPILOT_STATE = None
_SITE_WATCHER = None
TEST_YOUTUBE_VIDEOS = "unset"


def _clap_state():
    global _CLAP_STATE
    if _CLAP_STATE is None:
        _CLAP_STATE = b18.ClapWakeState() if b18 is not None else None
    return _CLAP_STATE


def _gesture_state():
    global _GESTURE_STATE
    if _GESTURE_STATE is None:
        _GESTURE_STATE = b18.GestureState() if b18 is not None else None
    return _GESTURE_STATE


def _hud_state():
    global _HUD_STATE
    if _HUD_STATE is None:
        _HUD_STATE = b18.HudModeState() if b18 is not None else None
    return _HUD_STATE


def _printer_state():
    global _PRINTER_STATE
    if _PRINTER_STATE is None:
        _PRINTER_STATE = b18.PrinterState() if b18 is not None else None
    return _PRINTER_STATE


def _autopilot_state():
    """Module-level autopilot state for the brain tools (jarvis.py
    owns its own AutopilotState for the HUD/native side)."""
    global _AUTOPILOT_STATE
    if _AUTOPILOT_STATE is None:
        _AUTOPILOT_STATE = b19.AutopilotState() if b19 is not None else None
    return _AUTOPILOT_STATE


def _site_watcher():
    """Module-level site watcher for the brain tools."""
    global _SITE_WATCHER
    if _SITE_WATCHER is None:
        _SITE_WATCHER = b19.SiteWatcher() if b19 is not None else None
    return _SITE_WATCHER


def _camera_state():
    """Module-level camera state for the brain tools (jarvis.py owns its
    own CameraState for the HUD/native side)."""
    global _CAMERA_STATE
    if _CAMERA_STATE is None:
        _CAMERA_STATE = b17.CameraState() if b17 is not None else None
    return _CAMERA_STATE

# ------------------------------------------- protected paths (the rule) ---
# The ONLY restriction in NOVA. Entries may be:
#   * an exact file/folder path        "C:\\Users\\me\\Secrets\\id.txt"
#   * a folder (everything under it)   "C:\\Users\\me\\Secrets"
#   * a simple glob pattern            "*.key"  /  "private_*"
#   * a bare file/folder name          "vault"  (matches anywhere)
PROTECTED_PATHS = []

def set_protected_paths(entries):
    """Replace the protected list (called by Agent from config)."""
    global PROTECTED_PATHS
    PROTECTED_PATHS = [str(e).strip() for e in (entries or []) if str(e).strip()]

def _norm_path(p):
    return os.path.normcase(os.path.abspath(
        os.path.expandvars(os.path.expanduser(str(p)))))

def _is_glob(entry):
    return any(ch in entry for ch in "*?[")

def protected_match(path):
    """Return the protected entry that covers `path`, or None."""
    if not PROTECTED_PATHS:
        return None
    target = _norm_path(path)
    name = Path(target).name.lower()
    parts = [c.lower() for c in Path(target).parts]
    for entry in PROTECTED_PATHS:
        if _is_glob(entry):
            pat = entry.lower()
            if fnmatch.fnmatch(target.lower(), pat) or fnmatch.fnmatch(name, pat):
                return entry
            continue
        e = _norm_path(entry)
        if target == e or target.startswith(e + os.sep):
            return entry
        bare = entry.strip("/\\")
        if "/" not in bare and "\\" not in bare and bare.lower() in parts:
            return entry
    return None

def command_mentions_protected(command):
    """Return the protected entry mentioned in a shell command, or None."""
    if not PROTECTED_PATHS:
        return None
    cmd = str(command).replace("\\", "/").lower()
    tokens = [t.strip("\"'") for t in cmd.replace('"', " ").replace("'", " ").split()]
    for entry in PROTECTED_PATHS:
        if _is_glob(entry):
            pat = entry.lower()
            core = pat.strip("*")
            if core and core in cmd:
                return entry
            if any(fnmatch.fnmatch(t, pat) or fnmatch.fnmatch(t.rsplit("/", 1)[-1], pat)
                   for t in tokens):
                return entry
            continue
        e = _norm_path(entry).replace("\\", "/").lower()
        if e in cmd:
            return entry
        bare = entry.strip("/\\")
        if "/" not in bare and "\\" not in bare and bare.lower() in cmd:
            return entry
    return None

# ---------------------------------------------------------- wake word ---
# JARVIS is the primary name now; "nova" keeps working so phrases learned
# on the older build don't suddenly stop being heard.
WAKE_WORDS = ("hey torvis", "torvis", "hey jarvis", "jarvis", "hey nova", "nova")  # BUILD 16: Torvis is primary; Jarvis is a legacy alias for one build

def parse_wake_phrase(text, wake_words=WAKE_WORDS):
    """Split a recognized phrase into (wake word + optional command).

    Pure function (no audio / GUI) so it can be unit-tested anywhere.
    Returns:
      * None  — the phrase doesn't address NOVA; ignore it.
      * ""    — wake word only ("Nova", "Hey Nova!"): acknowledge and
                treat the NEXT utterance as the command.
      * str   — the command that followed the wake word, e.g.
                "hey nova open downloads" -> "open downloads".
    Matching is case-insensitive on whole words, so "supernova" does not
    trigger it. When several wake words match, the earliest (then longest)
    wins; anything before the wake word is discarded.
    """
    if not text:
        return None
    lowered = str(text).lower()
    best = None  # (start, end) of the winning wake-word match
    for w in wake_words:
        m = re.search(r"\b" + re.escape(str(w).lower()) + r"\b", lowered)
        if m and (best is None or m.start() < best[0]
                  or (m.start() == best[0] and m.end() > best[1])):
            best = (m.start(), m.end())
    if best is None:
        return None
    return str(text)[best[1]:].strip(" \t\r\n,.:;!?-")

def _protected_refusal(path):
    return {"ok": False,
            "error": f"⛔ Protected by your rule — I don't touch {path}."}

# ---------------------------------------------------------------- tools ---

def _ok(**kw):
    out = {"ok": True}; out.update(kw); return out

def tool_system_info(_a):
    import socket
    disk = shutil.disk_usage(str(Path.home().anchor))
    return _ok(system=f"{platform.system()} {platform.release()} ({platform.version()})",
               machine=platform.machine(), processor=platform.processor() or "n/a",
               hostname=socket.gethostname(), user=os.environ.get("USERNAME") or os.environ.get("USER", ""),
               home=str(Path.home()), cwd=os.getcwd(),
               disk_free_gb=round(disk.free / 1e9, 1), disk_total_gb=round(disk.total / 1e9, 1),
               python=sys.version.split()[0])

def tool_list_files(a):
    p = Path(os.path.expandvars(os.path.expanduser(a.get("path") or str(Path.home()))))
    if protected_match(p): return _protected_refusal(p)
    if not p.exists(): return {"ok": False, "error": f"Path not found: {p}"}
    items = []
    for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))[:300]:
        try: size = e.stat().st_size if e.is_file() else None
        except OSError: size = None
        items.append({"name": e.name, "type": "folder" if e.is_dir() else "file", "size": size})
    return _ok(path=str(p), items=items)

def tool_read_file(a):
    p = Path(os.path.expandvars(os.path.expanduser(a["path"])))
    if protected_match(p): return _protected_refusal(p)
    if not p.is_file(): return {"ok": False, "error": f"Not a file: {p}"}
    if p.stat().st_size > 2_000_000: return {"ok": False, "error": "File is larger than 2 MB; read a smaller part or another file."}
    try: text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e: return {"ok": False, "error": str(e)}
    return _ok(path=str(p), content=text[:20000], truncated=len(text) > 20000)

def tool_write_file(a):
    p = Path(os.path.expandvars(os.path.expanduser(a["path"])))
    if protected_match(p): return _protected_refusal(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a.get("content", ""), encoding="utf-8")
    return _ok(path=str(p), bytes=p.stat().st_size)

def tool_delete_path(a):
    p = Path(os.path.expandvars(os.path.expanduser(a["path"])))
    if protected_match(p): return _protected_refusal(p)
    # BUILD 19 hard limit: autopilot never auto-deletes files outside
    # the H: drive without a separate explicit instruction in that
    # moment. The brain must pass explicit_delete=true only when the
    # user named that exact file in this moment; otherwise, in
    # autopilot, an outside-H: delete still asks for confirm first.
    # (Autopilot OFF: the old behaviour — the user's own delete ask
    # in this moment is the instruction — is unchanged.)
    if b19 is not None and _autopilot_state() is not None \
            and _autopilot_state().enabled \
            and not b19.is_h_drive_path(str(p)) \
            and not str(a.get("explicit_delete", "")).strip().lower() in ("true", "yes", "1"):
        return {"ok": False, "needs_confirm": True, "path": str(p),
                "error": "Not deleted yet, Sir — that file is outside the H: drive, and autopilot never deletes outside H: without you naming that exact file in this moment. Say 'confirm' and name the file again, and I will delete it."}
    if not p.exists(): return {"ok": False, "error": f"Not found: {p}"}
    if p.is_dir(): shutil.rmtree(p)
    else: p.unlink()
    return _ok(deleted=str(p))

def tool_run_command(a):
    cmd = a["command"]
    hit = command_mentions_protected(cmd)
    if hit: return _protected_refusal(hit)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        return _ok(exit_code=r.returncode, stdout=(r.stdout or "")[-8000:], stderr=(r.stderr or "")[-3000:])
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out after 120 seconds."}

def tool_open_path(a):
    target = os.path.expandvars(os.path.expanduser(a["path"]))
    if target.startswith(("http://", "https://")):
        webbrowser.open(target); return _ok(opened=target)
    if protected_match(target): return _protected_refusal(target)
    p = Path(target)
    if not p.exists(): return {"ok": False, "error": f"Not found: {target}"}
    if sys.platform.startswith("win"): os.startfile(str(p))          # noqa: S606
    elif sys.platform == "darwin": subprocess.Popen(["open", str(p)])
    else: subprocess.Popen(["xdg-open", str(p)])
    return _ok(opened=str(p))

def tool_search_files(a):
    root = Path(os.path.expandvars(os.path.expanduser(a.get("root") or str(Path.home()))))
    if protected_match(root): return _protected_refusal(root)
    needle = a["name_contains"].lower(); found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ("node_modules", ".git", "__pycache__", "AppData")
                       and not protected_match(os.path.join(dirpath, d))]
        for n in filenames:
            full = os.path.join(dirpath, n)
            if needle in n.lower() and not protected_match(full):
                found.append(full)
        if len(found) >= 100: break
    return _ok(matches=found, truncated=len(found) >= 100)

# ------------------------------------------------- downloads & installs ---
# Voice-driven software fetching, the native way (no browser, no clicking):
# download_file streams a URL straight to ~/Downloads (or a named folder);
# install_software runs an already-downloaded installer silently. Per the
# owner's INSTALLS rule, installs are two-step: the first call (without
# confirmed=true) changes nothing and returns the plan; only after the
# user says "confirm" does the caller pass confirmed=true and it runs.

def _open_url(req):
    """Indirection over urllib.request.urlopen (60s timeout) so tests can
    stub the network without touching real sockets."""
    return urllib.request.urlopen(req, timeout=60)

def derive_filename(url, content_disposition=None):
    """Best file name for a download: Content-Disposition wins, then the
    URL's last path segment, then a generic name. Sanitized for Windows.
    Pure function."""
    name = ""
    if content_disposition:
        m = re.search(r"filename\*\s*=\s*(?:[^']*'[^']*')?\"?([^\";]+)\"?",
                      content_disposition)
        if not m:
            m = re.search(r"filename\s*=\s*\"?([^\";]+)\"?", content_disposition)
        if m:
            name = urllib.parse.unquote(m.group(1).strip())
    if not name:
        path = urllib.parse.urlparse(str(url)).path
        name = urllib.parse.unquote(path.rsplit("/", 1)[-1])
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")
    if not name:
        name = "download.bin"
    return name[:150]

def _unique_dest(folder, name):
    dest = folder / name
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 1
    while True:
        cand = folder / f"{stem} ({n}){suffix}"
        if not cand.exists():
            return cand
        n += 1

def tool_download_file(a):
    url = str(a.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "Only http(s) URLs can be downloaded."}
    folder = Path(os.path.expandvars(os.path.expanduser(
        a.get("folder") or str((b14.work_drive_path() / "Downloads") if b14 is not None else Path.home() / "Downloads"))))
    if protected_match(folder): return _protected_refusal(folder)
    tmp = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        resp = _open_url(req)
        try:
            headers = getattr(resp, "headers", None)
            cd = headers.get("Content-Disposition") if headers else None
            final_url = resp.geturl() if hasattr(resp, "geturl") else url
            dest = _unique_dest(folder, derive_filename(final_url, cd))
            if protected_match(dest): return _protected_refusal(dest)
            tmp = dest.with_name(dest.name + ".part")
            total = 0
            with open(tmp, "wb") as f:
                while True:                      # streamed in chunks —
                    chunk = resp.read(262144)    # never all in memory
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
        finally:
            try: resp.close()
            except Exception:  # noqa: BLE001
                pass
        tmp.replace(dest)
        return _ok(path=str(dest), bytes=total,
                   size_mb=round(total / 1e6, 2), url=url)
    except Exception as e:  # noqa: BLE001 — honest failure, no half file
        try:
            if tmp is not None and tmp.exists(): tmp.unlink()
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"Download failed: {type(e).__name__}: {e}"}

def pick_install_command(path, installer_type="auto"):
    """Silent-install command line for an installer file. Returns
    (argv, kind) or (None, reason). Pure function.

    .msi is deterministic (msiexec /qn). For .exe there is no way to be
    sure of the packaging technology from outside, so the choice is:
    explicit type > name hints (inno/nsis) > NSIS /S, the most common
    silent switch for Windows utilities. A wrong guess is not fatal —
    most installers ignore unknown switches and open their GUI instead,
    which the caller reports honestly."""
    p = str(path)
    low = p.lower()
    t = str(installer_type or "auto").lower()
    if low.endswith(".msi") or t == "msi":
        return (["msiexec", "/i", p, "/qn", "/norestart"], "msi")
    if not low.endswith(".exe"):
        return (None, f"Not an .msi or .exe installer: {p}")
    if t == "inno" or (t == "auto" and ("inno" in low or "innosetup" in low)):
        return ([p, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"], "inno")
    if t == "quiet":
        return ([p, "/quiet", "/norestart"], "generic-quiet")
    # "nsis" explicit, or the auto default for unknown .exe files
    return ([p, "/S"], "nsis")

_INSTALL_EXIT_NOTES = {
    0: "Installed successfully.",
    3010: "Installed successfully — a restart is required to finish.",
    1641: "Installed successfully — the installer started a restart.",
    1603: "Installer failed (1603) — commonly a permissions/admin problem.",
    1619: "Installer failed (1619) — the package could not be opened.",
    1620: "Installer failed (1620) — the package could not be opened.",
    1223: "Cancelled (1223) — the admin (UAC) prompt was declined. "
          "UAC prompts appear on Windows' secure desktop and cannot be "
          "clicked by the agent; approve it by hand and ask again.",
}

def _exec_install(argv):
    """Indirection over subprocess.run so tests never install anything."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=900,
                          encoding="utf-8", errors="replace")

def tool_install_software(a):
    p = Path(os.path.expandvars(os.path.expanduser(a.get("path") or "")))
    if protected_match(p): return _protected_refusal(p)
    if not p.is_file():
        return {"ok": False, "error": f"Installer not found: {p}"}
    argv, kind = pick_install_command(str(p), a.get("installer_type", "auto"))
    if argv is None:
        return {"ok": False, "error": kind}
    plan = (f"Run {p.name} silently ({kind}: {' '.join(argv[1:]) or 'no extra flags'}). "
            "This can change system files, settings and installed programs, "
            "and may need admin rights.")
    confirmed = str(a.get("confirmed", "")).strip().lower() in ("true", "yes", "1")
    # BUILD 19: master autopilot skips the install confirm — but only
    # for an official-source installer (a file TORVIS downloaded from
    # an official site into H:\JARVIS-Work\, or explicitly marked
    # official_source). An unknown installer still asks, even on
    # autopilot. Autopilot OFF: the old two-step confirm stays.
    _ap = _autopilot_state() if b19 is not None else None
    _autopilot_install = bool(_ap is not None and _ap.enabled
                              and b19.autopilot_install_allowed(
                                  str(p), bool(a.get("official_source"))))
    if not confirmed and not _autopilot_install:
        # The owner's INSTALLS rule: state what will change and WAIT for
        # a spoken "confirm" — the first call never installs anything.
        return {"ok": False, "needs_confirm": True, "plan": plan,
                "error": "Not installed yet. " + plan +
                         " Say 'confirm' and I will run it."}
    try:
        r = _exec_install(argv)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Installer timed out after 15 minutes "
                                      "(it may be waiting on a window I cannot see)."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not start the installer: {e}"}
    note = _INSTALL_EXIT_NOTES.get(
        r.returncode,
        "Installer finished." if r.returncode == 0 else
        f"Installer exited with code {r.returncode} — that usually means "
        "it did not complete; it may have opened a window needing the user.")
    return _ok(path=str(p), exit_code=r.returncode, installer=kind, note=note,
               output=((r.stdout or "") + (r.stderr or ""))[-1500:])

def parse_search_html(html_text):
    """Parse DuckDuckGo html results into [{title, url, snippet}].
    Pure function — testable without network. DuckDuckGo result links
    look like <a class="result__a" href="https://example.com">Title</a>
    followed by <a class="result__snippet">Snippet</a>."""
    from html import unescape
    def clean(s):
        s = re.sub(r"<[^>]+>", "", s or "")
        return unescape(s).strip()
    results = []
    # Split on result links; each chunk may contain its snippet.
    parts = re.split(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                     html_text or "", flags=re.S)
    # parts: [pre, url1, title1, between1, url2, title2, between2, ...]
    for i in range(1, len(parts) - 1, 3):
        url, title = parts[i], clean(parts[i + 1])
        rest = parts[i + 2] if i + 2 < len(parts) else ""
        m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', rest, flags=re.S)
        snippet = clean(m.group(1)) if m else ""
        # DuckDuckGo wraps some links as /l/?uddg=<encoded real url>
        if url.startswith("//"):
            url = "https:" + url
        elif "/l/?uddg=" in url:
            try:
                url = urllib.parse.unquote(url.split("uddg=", 1)[1].split("&", 1)[0])
            except Exception:  # noqa: BLE001
                pass
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= 8:
            break
    return results

def tool_search_web(a):
    """Built-in web search (DuckDuckGo html, no API key, no download).
    Use this when the user asks something you don't know, says 'search
    for it', or says yes to a search offer — never answer 'I don't
    have that in my local data' without searching first."""
    q = str(a.get("query") or "").strip()
    if not q:
        return {"ok": False, "error": "No search query given."}
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        resp = _open_url(req)
        try:
            html_text = resp.read().decode("utf-8", errors="replace")
        finally:
            try: resp.close()
            except Exception:  # noqa: BLE001
                pass
        results = parse_search_html(html_text)[:5]
        if not results:
            return {"ok": False, "error": "Search returned no results. Try different words, or open a browser search."}
        return _ok(query=q, results=results)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Web search failed: {type(e).__name__}: {e}"}

_FILE_EXTS = (".exe", ".msi", ".zip", ".iso", ".pdf", ".mp4", ".mp3",
              ".apk", ".dmg", ".tar.gz", ".tgz", ".doc", ".docx", ".xls")

def pick_direct_file_url(results):
    """First search result whose URL looks like a direct file download.
    Pure function. Returns None when no result is a file — then the
    honest fallback is to open the search page in the browser, not to
    guess a download link or click through logins/CAPTCHAs."""
    for r in results or []:
        url = str(r.get("url") or "").lower().split("?", 1)[0]
        if url.endswith(_FILE_EXTS):
            return r.get("url")
    return None

def tool_search_download(a):
    """Full download workflow the user asked for, in one tool:
    search the web for the file, download the first direct file link,
    open the downloaded file, and report it so JARVIS can notify the
    user. If the user gave a direct URL, download that instead of
    searching. If no direct file link is found, open the search page
    in the browser and say so plainly — JARVIS does NOT automate
    Chrome clicks, logins, or CAPTCHAs to force a download."""
    q = str(a.get("query") or a.get("file") or "").strip()
    if not q:
        return {"ok": False, "error": "No file name or link given. Tell me what to download."}
    if q.startswith(("http://", "https://")):
        dl = tool_download_file({"url": q, "folder": a.get("folder")})
        if not dl.get("ok"):
            return dl
        opened = tool_open_path({"path": dl["path"]})
        return _ok(query=q, found_url=q, downloaded_path=dl["path"],
                   size_mb=dl.get("size_mb"), opened=bool(opened.get("ok")),
                   notification=f"Downloaded and opened: {dl['path']}")
    search = tool_search_web({"query": q + " download"})
    if not search.get("ok"):
        return search
    direct = pick_direct_file_url(search.get("results"))
    if not direct:
        # No direct file: open the search page so the user can click
        # the right download button themselves (login/CAPTCHA may apply).
        tool_open_path({"path": "https://duckduckgo.com/?q=" + urllib.parse.quote(q + " download")})
        return _ok(query=q, direct_file_found=False, browser_opened=True,
                   results=search.get("results"),
                   notification="No direct download link found — I opened the search page in your browser, Sir. Click the official download button there, and tell me if you want me to open the file after it downloads.")
    dl = tool_download_file({"url": direct, "folder": a.get("folder")})
    if not dl.get("ok"):
        return dl
    opened = tool_open_path({"path": dl["path"]})
    return _ok(query=q, found_url=direct, downloaded_path=dl["path"],
               size_mb=dl.get("size_mb"), opened=bool(opened.get("ok")),
               notification=f"Downloaded and opened: {dl['path']}")

def tool_youtube_upload(a):
    """Upload a video to the user's YouTube channel — OFFICIAL API ONLY.
    Never a password, never automating a Chrome login to the user's
    account (Google blocks that, and it would expose the account).
    The user must have completed the one-time Google OAuth setup on
    their own PC (a token file, not a password in chat), and must say
    'confirm' before anything is posted — posting is a public action.
    JARVIS does NOT create a video from nothing: video_path must be
    an existing video file the user made or gave it, and thumbnail_path
    must be an existing image file if a thumbnail is wanted. Privacy
    defaults to private unless the user explicitly says unlisted/public."""
    video = str(a.get("video_path") or "").strip()
    title = str(a.get("title") or "").strip()
    if not video or not title:
        return {"ok": False, "error": "I need both a video file and a title to upload. Give me the video file path and the title, description and thumbnail if you want them."}
    p = Path(os.path.expandvars(os.path.expanduser(video)))
    if protected_match(p): return _protected_refusal(p)
    if not p.is_file():
        return {"ok": False, "error": f"Video file not found: {p}. I cannot invent a video — give me the file you want uploaded, or tell me what video to make from what material."}
    thumb = str(a.get("thumbnail_path") or "").strip()
    if thumb:
        tp = Path(os.path.expandvars(os.path.expanduser(thumb)))
        if protected_match(tp): return _protected_refusal(tp)
        if not tp.is_file():
            return {"ok": False, "error": f"Thumbnail file not found: {tp}"}
    privacy = str(a.get("privacy") or "private").strip().lower()
    if privacy not in ("private", "unlisted", "public"):
        privacy = "private"
    plan = (f"Upload '{p.name}' to YouTube as '{title}' ({privacy}), "
            f"description: {(a.get('description') or '')[:200]}, "
            f"thumbnail: {thumb or 'none'}. This will post to your channel.")
    confirmed = str(a.get("confirmed", "")).strip().lower() in ("true", "yes", "1")
    # BUILD 19: YouTube autopilot (master autopilot OR YouTube
    # autopilot, either toggle ON) skips the confirm — Faizan's own
    # choice for his own channel, turned on by him in Settings.
    # Both toggles OFF: the old two-step confirm stays exactly.
    _ap19 = _autopilot_state() if b19 is not None else None
    if b19 is not None and b19.youtube_upload_needs_confirm(_ap19, confirmed):
        return {"ok": False, "needs_confirm": True, "plan": plan,
                "error": "Not uploaded yet. " + plan + " Say 'confirm' and I will upload it."}
    # Confirmed (or autopilot): now try the official API, or explain setup honestly.
    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2.credentials import Credentials  # type: ignore
    except ImportError:
        return {"ok": False, "error": "YouTube upload needs the Google API client, which is not installed. On your PC run: pip install google-api-python-client google-auth-oauthlib — then complete the one-time Google OAuth setup (Google Cloud Console → YouTube Data API v3 → OAuth client) and save the token file, and try again. I will never ask for your Google password."}
    token_path = Path(os.path.expandvars(os.path.expanduser(
        a.get("token_path") or str(Path.home() / "NovaAgent" / "youtube_token.json"))))
    # Also accept the JARVIS/NOVA config-dir location on Windows.
    alt = None
    if os.environ.get("APPDATA"):
        alt = Path(os.environ["APPDATA"]) / "NovaAgent" / "youtube_token.json"
    if not token_path.is_file() and alt is not None and alt.is_file():
        token_path = alt
    if not token_path.is_file():
        return {"ok": False, "error": f"YouTube is not connected yet — no OAuth token file found at {token_path}. Complete the one-time Google OAuth setup on your PC first (sign in with Google in your browser, approve YouTube upload access, save the token file), then say confirm again. I will never ask for your Google password."}
    try:
        creds = Credentials.from_authorized_user_file(str(token_path), ["https://www.googleapis.com/auth/youtube.upload"])
        yt = build("youtube", "v3", credentials=creds)
        from googleapiclient.http import MediaFileUpload  # type: ignore
        body = {"snippet": {"title": title, "description": str(a.get("description") or ""), "categoryId": "22"},
                "status": {"privacyStatus": privacy}}
        media = MediaFileUpload(str(p), resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        vid = resp.get("id", "")
        if thumb:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(tp))).execute()
        return _ok(video_id=vid, url=f"https://www.youtube.com/watch?v={vid}",
                   title=title, privacy=privacy,
                   notification=f"Uploaded to YouTube: {title} — https://www.youtube.com/watch?v={vid}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"YouTube upload failed: {type(e).__name__}: {e}. If the token expired, redo the OAuth setup on your PC and try again."}

def jarvis_workspace_path():
    """JARVIS's own computer workspace: a dedicated folder on this PC
    where JARVIS keeps its own work (notes, files it creates, things
    it downloads for itself), separate from the user's own folders.
    JARVIS can still access the user's computer through the other
    tools when the user asks — this workspace is its own home base,
    not a wall around it. Pure except for creating the folders."""
    base = Path.home() / "JARVIS-Computer"
    for sub in ("Work", "Downloads", "Notes"):
        try:
            (base / sub).mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
    return base

def tool_jarvis_computer(a):
    """JARVIS's own computer: its dedicated workspace, what is in it,
    and how much disk is free. Use this when the user asks what
    JARVIS's own computer is, or where JARVIS keeps its own files."""
    base = jarvis_workspace_path()
    try:
        items = sorted(p.name for p in base.iterdir()) if base.exists() else []
    except Exception:  # noqa: BLE001
        items = []
    try:
        usage = shutil.disk_usage(str(base))
        free_gb = round(usage.free / 1e9, 1)
    except Exception:  # noqa: BLE001
        free_gb = None
    return _ok(path=str(base), folders=["Work", "Downloads", "Notes"],
               contents=items, free_disk_gb=free_gb,
               note="This is JARVIS's own workspace on this PC. JARVIS can also access the user's computer through its other tools when asked, subject to the protected list.")

def tool_screenshot(a):
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"ok": False, "error": "Pillow is not installed, screenshots unavailable."}
    out = Path(os.path.expandvars(os.path.expanduser(a.get("path") or str(Path.home() / "Pictures" / "nova-screenshot.png"))))
    out.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab().save(str(out))
    return _ok(path=str(out))

def tool_remember_this(a):
    """BUILD 14: 'remember this …' — save a fact/task for next time."""
    if b14 is None:
        return {"ok": False, "error": "Memory module is missing, Sir."}
    store = b14.MemoryStore()
    text = str(a.get("text") or a.get("fact") or "").strip()
    if not text:
        return {"ok": False, "error": "Tell me what to remember, Sir."}
    if str(a.get("kind") or "").lower() == "task":
        store.remember_task(text)
        return _ok(remembered=text, kind="task")
    store.remember_fact(text)
    return _ok(remembered=text, kind="fact")

def tool_recall_memory(a):
    if b14 is None:
        return {"ok": False, "error": "Memory module is missing, Sir."}
    store = b14.MemoryStore()
    return _ok(facts=store.facts(), tasks=store.tasks())

def tool_add_reminder(a):
    if b14 is None:
        return {"ok": False, "error": "Reminder module is missing, Sir."}
    parsed = b14.parse_reminder(str(a.get("text") or ""))
    if not parsed.get("ok"):
        return {"ok": False, "error": "Say it like 'remind me in 10 minutes to …' or 'remind me at 9:30 to …', Sir."}
    store = b14.ReminderStore()
    item = store.add(parsed["text"], parsed["at"])
    return _ok(reminder=item["text"], at=item["at"], in_minutes=parsed["in_minutes"])

def tool_list_reminders(a):
    if b14 is None:
        return {"ok": False, "error": "Reminder module is missing, Sir."}
    store = b14.ReminderStore()
    return _ok(upcoming=store.upcoming(), due=[i["text"] for i in store.due()])

def tool_morning_briefing(a):
    if b14 is None:
        return {"ok": False, "error": "Briefing module is missing, Sir."}
    from datetime import datetime
    mem = b14.MemoryStore(); rem = b14.ReminderStore()
    due = [i["text"] for i in rem.due()]
    return _ok(briefing=b14.format_morning_briefing(datetime.now(), due, mem.facts(), mem.tasks()))


def tool_recall_last_chat(a):
    if b15 is None:
        return {"ok": False, "error": "Chat memory module is missing, Sir."}
    store = b15.ChatHistoryStore()
    return _ok(last_work=store.what_were_we_working_on(), recent=store.recent(5), summary=store.summary)

def tool_what_were_we_working_on(a):
    if b15 is None:
        return {"ok": False, "error": "Chat memory module is missing, Sir."}
    return _ok(answer=b15.ChatHistoryStore().what_were_we_working_on())

def tool_calendar_status(a):
    if b15 is None:
        return {"ok": False, "error": "Calendar module is missing, Sir."}
    return _ok(**b15.CalendarClient().status())

def _todays_events():
    """Today's calendar events: test hook, else the real read-only client."""
    if TEST_CALENDAR_EVENTS is not None:
        return {"ok": True, "events": [b15.parse_event(e) if isinstance(e, dict) and "start" in e and isinstance(e.get("start"), dict) else e for e in TEST_CALENDAR_EVENTS], "error": "", "connected": True}
    if b15 is None:
        return {"ok": False, "events": [], "error": "Calendar module is missing, Sir.", "connected": False}
    return b15.CalendarClient().fetch_today_events()

def tool_todays_schedule(a):
    if b15 is None:
        return {"ok": False, "error": "Calendar module is missing, Sir."}
    from datetime import date
    res = _todays_events()
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "Calendar not connected, Sir."), "connected": res.get("connected", False)}
    return _ok(schedule=b15.format_todays_schedule(res["events"], date.today(), True), events=[b15.format_event_line(e) for e in res["events"]])

def tool_list_meetings_today(a):
    return tool_todays_schedule(a)

def tool_next_meeting(a):
    if b15 is None:
        return {"ok": False, "error": "Calendar module is missing, Sir."}
    from datetime import datetime
    res = _todays_events()
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error", "Calendar not connected, Sir."), "connected": res.get("connected", False)}
    nxt = b15.next_meeting(res["events"], datetime.now())
    if nxt is None:
        return _ok(next_meeting=None, message="No more meetings today, Sir.")
    return _ok(next_meeting=b15.format_event_line(nxt))

def tool_daily_summary(a):
    if b15 is None:
        return {"ok": False, "error": "Summary module is missing, Sir."}
    from datetime import date
    store = b15.ChatHistoryStore()
    mem = b14.MemoryStore() if b14 is not None else None
    tasks = mem.tasks() if mem else []
    res = _todays_events()
    meetings = res["events"] if res.get("ok") else []
    return _ok(summary=b15.daily_summary(store.turns, tasks, meetings, date.today()))

def tool_learn_preference(a):
    if b14 is None:
        return {"ok": False, "error": "Memory module is missing, Sir."}
    store = b14.MemoryStore()
    key = str(a.get("key") or a.get("name") or "").strip()
    value = str(a.get("value") or "").strip()
    if not key or not value:
        return {"ok": False, "error": "Tell me the preference and its value, Sir — e.g. key 'voice' value 'Ryan'."}
    store.data.setdefault("preferences", {})[key] = value
    store.save()
    return _ok(learned={key: value})

def tool_search_h_drive(a):
    if b15 is None:
        return {"ok": False, "error": "H: drive module is missing, Sir."}
    return _ok(results=b15.search_h_drive(str(a.get("query") or a.get("name") or "")), folder="H:\\JARVIS-Work")

def tool_set_volume(a):
    if b15 is None:
        return {"ok": False, "error": "Volume module is missing, Sir."}
    return b15.volume_control(str(a.get("action") or ""))

def tool_read_gmail(a):
    if b15 is None:
        return {"ok": False, "error": "Gmail module is missing, Sir."}
    if TEST_GMAIL_MESSAGES is not None:
        return _ok(messages=TEST_GMAIL_MESSAGES, connected=True)
    return b15.GmailClient().fetch_latest(count=int(a.get("count") or 5))

def tool_gmail_status(a):
    if b15 is None:
        return {"ok": False, "error": "Gmail module is missing, Sir."}
    return _ok(**b15.GmailClient().status())


def tool_book_meeting(a):
    """BUILD 16: book a calendar event — TWO-STEP. First call returns
    the plan only; nothing is booked until tool_confirm_meeting is
    called with confirmed=true after the user says 'confirm'."""
    global PENDING_BOOKING
    if b16 is None:
        return {"ok": False, "error": "Calendar booking module is missing, Sir."}
    parsed = b16.parse_create_event(str(a.get("text") or a.get("title") or ""))
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed["error"]}
    PENDING_BOOKING = parsed
    return {"ok": False, "needs_confirm": True, "pending": {k: str(v) for k, v in parsed.items()},
            "plan": b16.confirm_booking_text(parsed)}

def tool_confirm_meeting(a):
    """BUILD 16: confirm (or cancel) the pending booking."""
    global PENDING_BOOKING
    if b16 is None:
        return {"ok": False, "error": "Calendar booking module is missing, Sir."}
    if PENDING_BOOKING is None:
        return {"ok": False, "error": "There is no booking waiting for confirmation, Sir — say 'book a meeting …' first."}
    if not a.get("confirmed"):
        PENDING_BOOKING = None
        return {"ok": False, "error": "Booking cancelled, Sir — nothing was booked."}
    parsed = PENDING_BOOKING
    PENDING_BOOKING = None
    if b15 is None:
        return {"ok": False, "error": "Calendar not connected yet, Sir."}
    return b15.CalendarClient().create_event(parsed)

def tool_check_my_status(a):
    """BUILD 16: one status briefing — calendar + reminders + tasks + Gmail unread."""
    if b16 is None or b15 is None:
        return {"ok": False, "error": "Status check is not available in this build, Sir."}
    from datetime import datetime, date
    cal = b15.CalendarClient()
    res = cal.fetch_today_events()
    events = res["events"] if res.get("ok") else []
    gmail_unread = None
    try:
        g = b15.GmailClient().fetch_latest(count=1)
        gmail_unread = len(g.get("messages") or []) if g.get("ok") else None
    except Exception:
        gmail_unread = None
    return {"ok": True, "status": b16.format_status_briefing(
        events, bool(res.get("ok")), [], [], gmail_unread, "", when=datetime.now())}

def tool_voice_quality_report(a):
    """BUILD 16: Voice Quality report — latency, fully-spoken rate, tasks, failures."""
    if b16 is None:
        return {"ok": False, "error": "Voice quality reporting is not available in this build, Sir."}
    return {"ok": True, **b16.DailyStats().stats(),
            "line": b16.DailyStats().format_stats_line(),
            "latency_note": b16.BRAIN_LATENCY_NOTE}

def tool_handoff_to_muse(a):
    r"""BUILD 16: save the full context to TASK-STATUS.md in H:\JARVIS-Work\ so Muse can pick it up."""
    if b16 is None:
        return {"ok": False, "error": "Handoff is not available in this build, Sir."}
    ctx = {"task": str(a.get("task") or a.get("text") or ""),
           "tasks": [str(x) for x in (a.get("tasks") or [])],
           "summary": str(a.get("summary") or ""),
           "schedule": str(a.get("schedule") or ""),
           "notes": str(a.get("notes") or "")}
    return b16.save_handoff(ctx)


def tool_security_check_ports(a):
    """BUILD 16 ethical security: check open ports on YOUR OWN PC only."""
    if b16 is None:
        return {"ok": False, "error": "Security checks are not available in this build, Sir."}
    return b16.check_open_ports(str(a.get("host") or "localhost"),
                                a.get("ports") or None)

def tool_security_check_passwords(a):
    """BUILD 16 ethical security: check weak passwords in YOUR OWN H: file — TWO-STEP, needs confirmed=true."""
    if b16 is None:
        return {"ok": False, "error": "Security checks are not available in this build, Sir."}
    return b16.check_weak_passwords_in_file(str(a.get("path") or ""), confirmed=bool(a.get("confirmed")))

def tool_security_scan_h_drive(a):
    """BUILD 16 ethical security: scan YOUR OWN H: drive files (types, sensitive names, executables) — contents of sensitive files are never opened."""
    if b16 is None:
        return {"ok": False, "error": "Security checks are not available in this build, Sir."}
    return b16.scan_h_drive_files()

def tool_explain_security_risk(a):
    """BUILD 16 ethical security: explain a security risk in plain words — education only, never exploit instructions."""
    if b16 is None:
        return {"ok": False, "error": "Security checks are not available in this build, Sir."}
    return {"ok": True, "explanation": b16.explain_security_risk(str(a.get("topic") or "security"))}


def tool_camera_status(a):
    """BUILD 17: camera state — OFF by default, local only, never streamed."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    return _ok(**_camera_state().status())


def tool_camera_on(a):
    """BUILD 17: turn the camera on (probes the real camera; no camera, or
    Windows blocking it, is reported plainly — a feed is never faked)."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    state = _camera_state()
    probe = b17.probe_camera(capture_factory=_CAMERA_CAPTURE_FACTORY)
    if not probe.get("ok"):
        state.disable()
        state.available = False
        return {"ok": False, "enabled": False, "error": probe.get("error") or "No camera found, Sir."}
    state.enable()
    state.available = True
    return {"ok": True, "enabled": True,
            "message": "Camera on, Sir — local only, never streamed."}


def tool_camera_off(a):
    """BUILD 17: turn the camera off."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    _camera_state().disable()
    return {"ok": True, "enabled": False, "message": "Camera off, Sir."}


def tool_test_camera(a):
    """BUILD 17: probe the camera and report plainly."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    state = _camera_state()
    probe = b17.probe_camera(capture_factory=_CAMERA_CAPTURE_FACTORY)
    state.available = bool(probe.get("available"))
    if probe.get("ok"):
        return {"ok": True, "available": True,
                "message": "Camera test passed, Sir — the camera is working, local only."}
    return {"ok": False, "available": False, "error": probe.get("error") or "No camera found, Sir."}


def tool_take_photo(a):
    """BUILD 17: take one photo, saved only to H:\\JARVIS-Work\\Photos\\.
    The camera must be on first."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    return b17.take_photo(_camera_state(), capture_factory=_CAMERA_CAPTURE_FACTORY)


def tool_describe_camera(a):
    """BUILD 17: 'what do you see?' — plain-words scene description only,
    never names a person. No vision advisor in the brain tools, so it says
    plainly it cannot describe it yet unless a frame is supplied."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    return b17.describe_camera_frame(_camera_state(), advisor=None,
                                     capture_factory=_CAMERA_CAPTURE_FACTORY)


def tool_record_camera_video(a):
    """BUILD 17: record video — TWO-STEP. First call (no confirmed) returns
    the plan only; call again with confirmed=true ONLY after the user says
    'confirm'. Nothing is recorded until then."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    return b17.request_recording(_camera_state(), confirmed=bool(a.get("confirmed")),
                                 seconds=a.get("seconds") or 10)


def tool_stop_camera_recording(a):
    """BUILD 17: stop (or cancel) a camera recording."""
    if b17 is None:
        return {"ok": False, "error": "Camera is not available in this build, Sir."}
    return b17.stop_recording(_camera_state())


# BUILD 17: Kali VM — pending command awaiting a spoken "confirm".
PENDING_KALI_COMMAND = None
# Test hook: when set, [KALI] log lines go to this callable instead of
# jarvis.log. Never set in production code.
_KALI_LOG_SINK = None


def _kali_log(line):
    """Append one [KALI] line to jarvis.log (%APPDATA%\\NovaAgent)."""
    if _KALI_LOG_SINK is not None:
        try:
            _KALI_LOG_SINK(line)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        log_dir = Path(os.environ.get("APPDATA") or Path.home()) / "NovaAgent"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "jarvis.log", "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — logging never breaks the task
        pass


def tool_focus_kali_vm(a):
    """BUILD 17: find and focus the Kali VM window (VirtualBox/VMware).
    Plain message if Kali is not running — never type blindly."""
    if b17 is None:
        return {"ok": False, "error": "Kali VM typing is not available in this build, Sir."}
    return b17.focus_kali_vm()


def tool_type_in_kali(a):
    """BUILD 17: type a command into the focused Kali VM terminal and
    press Enter — TWO-STEP. First call WITHOUT confirmed to show the
    plan; only call again with confirmed=true after the user says
    'confirm'. Refuses unauthorised targets plainly."""
    if b17 is None:
        return {"ok": False, "error": "Kali VM typing is not available in this build, Sir."}
    return b17.type_in_kali(str(a.get("command") or a.get("text") or ""),
                            confirmed=bool(a.get("confirmed")),
                            logger=_kali_log)


def tool_run_kali_command(a):
    """BUILD 17: run a command in Kali — TWO-STEP. First call returns
    the exact command and the authorisation verdict; nothing is typed
    until tool_confirm_kali_command is called with confirmed=true
    after the user says 'confirm'."""
    global PENDING_KALI_COMMAND
    if b17 is None:
        return {"ok": False, "error": "Kali VM typing is not available in this build, Sir."}
    cmd = b17.parse_kali_command(str(a.get("command") or a.get("text") or ""))
    if not cmd:
        return {"ok": False, "error": "There is no command to type, Sir — tell me the command first."}
    check = b17.check_kali_command(cmd)
    if not check.get("ok"):
        return {"ok": False, "error": check.get("error")}
    PENDING_KALI_COMMAND = cmd
    return {"ok": False, "needs_confirm": True, "command": cmd,
            "targets": check.get("targets", []),
            "plan": (f"I will type this in your Kali VM terminal: {cmd} — "
                     "say 'confirm' and I will focus the Kali window, type "
                     "it, and press Enter. Nothing is typed until you say so."),
            "error": ""}


def tool_confirm_kali_command(a):
    """BUILD 17: confirm (or cancel) the pending Kali command."""
    global PENDING_KALI_COMMAND
    if b17 is None:
        return {"ok": False, "error": "Kali VM typing is not available in this build, Sir."}
    if PENDING_KALI_COMMAND is None:
        return {"ok": False, "error": "There is no Kali command waiting for confirmation, Sir — say 'run this in Kali: …' first."}
    if not a.get("confirmed"):
        PENDING_KALI_COMMAND = None
        return {"ok": False, "error": "Kali command cancelled, Sir — nothing was typed."}
    cmd = PENDING_KALI_COMMAND
    PENDING_KALI_COMMAND = None
    return b17.type_in_kali(cmd, confirmed=True, logger=_kali_log)

def tool_clap_wake_status(a):
    """BUILD 18: clap-wake state — OFF by default, double clap only."""
    if b18 is None:
        return {"ok": False, "error": "Clap wake is not available in this build, Sir."}
    return _ok(**_clap_state().status())


def tool_enable_clap_wake(a):
    """BUILD 18: turn clap wake on/off (enabled=true/false). A double
    clap wakes TORVIS and switches on the HUD; speech never wakes."""
    if b18 is None:
        return {"ok": False, "error": "Clap wake is not available in this build, Sir."}
    state = _clap_state()
    if "sensitivity" in a:
        state.set_sensitivity(a.get("sensitivity"))
    if a.get("enabled"):
        state.enable()
        return _ok(enabled=True, sensitivity=state.sensitivity,
                   message="Clap wake on, Sir — two sharp claps wake me and switch on the HUD.")
    state.disable()
    return _ok(enabled=False, sensitivity=state.sensitivity,
               message="Clap wake off, Sir.")


def tool_gesture_status(a):
    """BUILD 18: gesture state — OFF by default, camera only, local only."""
    if b18 is None:
        return {"ok": False, "error": "Gestures are not available in this build, Sir."}
    return _ok(**_gesture_state().status())


def tool_enable_gestures(a):
    """BUILD 18: turn hand-gesture control on/off (enabled=true/false).
    Gestures need the camera on; the tool still stores the preference
    and says so plainly when the camera is off."""
    if b18 is None:
        return {"ok": False, "error": "Gestures are not available in this build, Sir."}
    state = _gesture_state()
    camera_on = bool(_camera_state() is not None and _camera_state().enabled)
    if a.get("enabled"):
        state.enable()
        return _ok(enabled=True, camera_on=camera_on,
                   message=("Gestures on, Sir — open palm wakes, swipe is next / "
                            "previous, pinch selects, fist stops speaking."
                            if camera_on else
                            "Gestures on, Sir — but the camera is off, so say "
                            "'turn camera on' first and the gestures will work."))
    state.disable()
    return _ok(enabled=False, camera_on=camera_on, message="Gestures off, Sir.")


def tool_hud_mode_on(a):
    """BUILD 18: switch HUD mode on — the full animated TORVIS HUD."""
    if b18 is None:
        return {"ok": False, "error": "HUD mode is not available in this build, Sir."}
    _hud_state().enter_hud()
    return _ok(hud_mode=True, mode="hud",
               message="HUD mode on, Sir — the full animated TORVIS HUD.")


def tool_hud_mode_off(a):
    """BUILD 18: switch HUD mode off — back to the normal view."""
    if b18 is None:
        return {"ok": False, "error": "HUD mode is not available in this build, Sir."}
    _hud_state().exit_hud()
    return _ok(hud_mode=False, mode="normal",
               message="HUD mode off, Sir — back to the normal view.")


def tool_printer_status(a):
    """BUILD 18: 3D-printer hook status — plainly 'No 3D printer
    connected' unless an OctoPrint URL is set in Settings. No printer
    is ever invented."""
    if b18 is None:
        return {"ok": False, "error": "No 3D printer connected, Sir."}
    return _ok(**_printer_state().status())


def tool_autopilot_status(a):
    """BUILD 19: master + YouTube autopilot state — both OFF by default."""
    if b19 is None:
        return {"ok": False, "error": "Autopilot is not available in this build, Sir."}
    return _ok(**_autopilot_state().status())


def tool_enable_autopilot(a):
    """BUILD 19: turn master autopilot on/off (enabled=true/false).
    ON means TORVIS does not ask for confirm on his own PC / own
    accounts. The protected list, own-stuff-only, no-pay and
    no-delete-outside-H: limits still apply — autopilot never
    overrides them."""
    if b19 is None:
        return {"ok": False, "error": "Autopilot is not available in this build, Sir."}
    state = _autopilot_state()
    if a.get("enabled"):
        state.enable()
        return _ok(enabled=True, **state.status(),
                   message="Autopilot on, Sir — I will not ask for confirm before doing things on your own PC and your own accounts. " + b19.AUTOPILOT_WARNING)
    state.disable()
    return _ok(enabled=False, **state.status(),
               message="Autopilot off, Sir — every confirm gate is back on.")


def tool_enable_youtube_autopilot(a):
    """BUILD 19: turn YouTube autopilot on/off (enabled=true/false).
    ON means YouTube uploads/posts need no confirm."""
    if b19 is None:
        return {"ok": False, "error": "YouTube autopilot is not available in this build, Sir."}
    state = _autopilot_state()
    if a.get("enabled"):
        state.enable_youtube()
        return _ok(**state.status(),
                   message="YouTube autopilot on, Sir — uploads and posts need no confirm now. Posts are public and cannot be undone.")
    state.disable_youtube()
    return _ok(**state.status(),
               message="YouTube autopilot off, Sir — YouTube uploads need a confirm again (unless full autopilot is on).")


def _youtube_token_path(a):
    token_path = Path(os.path.expandvars(os.path.expanduser(
        a.get("token_path") or str(Path.home() / "NovaAgent" / "youtube_token.json"))))
    alt = None
    if os.environ.get("APPDATA"):
        alt = Path(os.environ["APPDATA"]) / "NovaAgent" / "youtube_token.json"
    if not token_path.is_file() and alt is not None and alt.is_file():
        token_path = alt
    return token_path


def _fetch_youtube_channel_videos(a):
    """Read HIS channel's videos via the official YouTube Data API v3
    (OAuth token file only, never a password). Returns (videos, error):
    videos is a list of {title, views, likes, topic} or None when
    YouTube is not connected. TEST_YOUTUBE_VIDEOS, when set by tests,
    is used instead of a real API call."""
    if TEST_YOUTUBE_VIDEOS != "unset":
        return TEST_YOUTUBE_VIDEOS, None
    try:
        from googleapiclient.discovery import build  # type: ignore
        from google.oauth2.credentials import Credentials  # type: ignore
    except ImportError:
        return None, ("YouTube needs the Google API client, which is not installed. "
                      "On your PC run: pip install google-api-python-client google-auth-oauthlib — "
                      "then complete the one-time Google OAuth setup and try again. "
                      "I will never ask for your Google password.")
    token_path = _youtube_token_path(a)
    if not token_path.is_file():
        return None, b19.YOUTUBE_NOT_CONNECTED_MESSAGE
    try:
        creds = Credentials.from_authorized_user_file(
            str(token_path), ["https://www.googleapis.com/auth/youtube.readonly"])
        yt = build("youtube", "v3", credentials=creds)
        ch = yt.channels().list(part="contentDetails,snippet", mine=True).execute()
        items = ch.get("items") or []
        if not items:
            return [], None
        channel_name = (items[0].get("snippet") or {}).get("title", "")
        uploads = ((items[0].get("contentDetails") or {})
                   .get("relatedPlaylists") or {}).get("uploads", "")
        videos = []
        page_token = None
        for _ in range(5):  # up to ~250 videos, newest first
            pl = yt.playlistItems().list(
                part="snippet", playlistId=uploads, maxResults=50,
                pageToken=page_token).execute()
            ids = [ (it.get("snippet") or {}).get("resourceId", {}).get("videoId")
                    for it in pl.get("items") or [] ]
            ids = [i for i in ids if i]
            if ids:
                stats = yt.videos().list(
                    part="snippet,statistics", id=",".join(ids)).execute()
                for v in stats.get("items") or []:
                    sn, st = v.get("snippet") or {}, v.get("statistics") or {}
                    videos.append({"title": sn.get("title", ""),
                                   "views": int(st.get("viewCount") or 0),
                                   "likes": int(st.get("likeCount") or 0),
                                   "topic": ""})
            page_token = pl.get("nextPageToken")
            if not page_token:
                break
        return videos, channel_name
    except Exception as e:  # noqa: BLE001
        return None, (f"YouTube channel read failed: {type(e).__name__}: {e}. "
                      "If the token expired, redo the OAuth setup on your PC and try again.")


def tool_analyze_youtube_channel(a):
    """BUILD 19: analyse HIS YouTube channel — best niche from real
    video views/likes. Not connected -> plain message, never invented data."""
    if b19 is None:
        return {"ok": False, "error": "YouTube channel analysis is not available in this build, Sir."}
    videos, extra = _fetch_youtube_channel_videos(a)
    if videos is None:
        return {"ok": False, "error": extra or b19.YOUTUBE_NOT_CONNECTED_MESSAGE}
    channel_name = extra if isinstance(extra, str) else ""
    res = b19.analyze_youtube_channel(videos, channel_name=channel_name)
    if not res.get("ok"):
        return {"ok": False, "error": res.get("message", res.get("error", "No channel data, Sir."))}
    return _ok(**{k: v for k, v in res.items() if k != "message"},
               notification=res.get("recommendation"))


def tool_make_youtube_caption(a):
    """BUILD 19: caption + hashtags for a video, from its title/topic
    and (when given) the channel's best topics. No invented views."""
    if b19 is None:
        return {"ok": False, "error": "Caption maker is not available in this build, Sir."}
    topics = a.get("best_topics") or []
    if isinstance(topics, str):
        topics = [t.strip() for t in topics.split(",") if t.strip()]
    return _ok(**b19.make_youtube_caption(str(a.get("title") or ""),
                                          str(a.get("topic") or ""),
                                          list(topics)))


def tool_youtube_autopilot_post(a):
    """BUILD 19: caption/hashtags + upload in one go. No confirm when
    YouTube autopilot (or master autopilot) is ON; two-step confirm
    when both are OFF — the upload tool enforces that. Video file
    must exist and be on the H: drive."""
    if b19 is None:
        return {"ok": False, "error": "YouTube autopilot is not available in this build, Sir."}
    video = str(a.get("video_path") or "").strip()
    title = str(a.get("title") or "").strip()
    if not video or not title:
        return {"ok": False, "error": "I need both a video file and a title to post. Give me the video file path and the title."}
    if not b19.is_h_drive_path(video):
        return {"ok": False, "error": f"Video file must be on the H: drive, Sir — {video} is not. Move it to H:\\JARVIS-Work\\ first and I will post it."}
    caption = b19.make_youtube_caption(title, str(a.get("topic") or ""),
                                       a.get("best_topics") or [])
    desc = str(a.get("description") or caption["caption"])
    up = tool_youtube_upload({"video_path": video, "title": title,
                              "description": desc,
                              "thumbnail_path": str(a.get("thumbnail_path") or ""),
                              "privacy": str(a.get("privacy") or "private"),
                              "confirmed": a.get("confirmed", False)})
    if not up.get("ok"):
        return up
    up["caption"] = caption["caption"]
    up["hashtags"] = caption["hashtags"]
    return up


def tool_watch_site(a):
    """BUILD 19: watch a site — add a URL to the watched list.
    Checking is read-only and never needs a confirm."""
    if b19 is None:
        return {"ok": False, "error": "Site watcher is not available in this build, Sir."}
    res = _site_watcher().add_site(str(a.get("url") or ""))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error")}
    return _ok(**res, sites=_site_watcher().sites)


def tool_list_watched_sites(a):
    """BUILD 19: list the watched sites and their last status."""
    if b19 is None:
        return {"ok": False, "error": "Site watcher is not available in this build, Sir."}
    return _ok(**_site_watcher().status())


def tool_site_status(a):
    """BUILD 19: check the watched sites now (read-only, no confirm)
    and report down / up / changed notifications."""
    if b19 is None:
        return {"ok": False, "error": "Site watcher is not available in this build, Sir."}
    watcher = _site_watcher()
    notes = watcher.check_all()
    return _ok(sites=watcher.sites, notifications=notes,
               last_status=watcher.last_status,
               message=("All watched sites are up, Sir." if not notes
                        else " ".join(notes)))


def _available_voices(a):
    """Voices installed on this PC, for pronunciation_status. The
    brain accepts an injected list in tests; on Windows it asks
    pyttsx3; otherwise it reports that the list needs the HUD /
    Settings on the PC. Never raises."""
    if isinstance(a, dict) and "available_voices" in a:
        return list(a.get("available_voices") or [])
    try:
        import pyttsx3  # type: ignore
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        return [{"name": getattr(v, "name", ""), "lang": "",
                 "languages": [x.decode("utf-8", "replace") if isinstance(x, bytes) else str(x)
                               for x in (getattr(v, "languages", None) or [])]}
                for v in voices]
    except Exception:  # noqa: BLE001
        return []


def tool_pronunciation_status(a):
    """BUILD 19: which language voices are actually installed on this
    PC — ur-PK for Urdu/Roman Urdu, matching locale for other
    languages. Plain fallback when a locale is not installed; never
    forces an English voice on Urdu text."""
    if b19 is None:
        return {"ok": False, "error": "Multilingual voice is not available in this build, Sir."}
    per_lang = {}
    if isinstance(a, dict) and isinstance(a.get("voice_per_language"), dict):
        per_lang = b19.validate_per_language_voices(a.get("voice_per_language"))
    voices = _available_voices(a)
    # pyttsx3 dicts need .name/.lang shape for the picker: rebuild
    # them as simple objects the picker understands.
    class _V:
        def __init__(self, name, languages):
            self.name = name
            self.lang = ""
            self.languages = languages
    objs = [_V(v.get("name", ""), v.get("languages", [])) if isinstance(v, dict) else v
            for v in voices]
    status = b19.pronunciation_status(objs, per_language=per_lang)
    status["voices_found"] = len(objs)
    if not objs:
        status["note"] = ("Voice list not available here, Sir — check it in "
                          "Settings on your PC, where the HUD lists the "
                          "installed voices.")
    return _ok(**status)


def tool_open_app(a):
    if b14 is None:
        return {"ok": False, "error": "PC control module is missing, Sir."}
    return b14.open_app(str(a.get("name") or a.get("app") or ""))

def tool_type_text(a):
    if b14 is None:
        return {"ok": False, "error": "PC control module is missing, Sir."}
    return b14.type_text(str(a.get("text") or ""))

def tool_click_at(a):
    if b14 is None:
        return {"ok": False, "error": "PC control module is missing, Sir."}
    return b14.click_at(a.get("x"), a.get("y"))

TOOLS = {
    "system_info":  (tool_system_info,  "Get information about this computer: OS, user, home folder, disk space.", {}),
    "list_files":   (tool_list_files,   "List files and folders in a directory.", {"path": "Directory path (optional, defaults to home)"}),
    "read_file":    (tool_read_file,    "Read a text file's contents.", {"path": "File path"}),
    "write_file":   (tool_write_file,   "Create or overwrite a text file with the given content.", {"path": "File path", "content": "Full file content"}),
    "delete_path":  (tool_delete_path,  "Delete a file or folder permanently.", {"path": "Path to delete"}),
    "run_command":  (tool_run_command,  "Run a shell command on this computer and return its output.", {"command": "The command to run"}),
    "open_path":    (tool_open_path,    "Open a file, folder, application path or web URL for the user.", {"path": "Path or URL to open"}),
    "search_files": (tool_search_files, "Search for files by part of their name under a folder.", {"name_contains": "Text to match in file names", "root": "Folder to search under (optional)"}),
    "screenshot":   (tool_screenshot,   "Take a screenshot and save it as an image file.", {"path": "Where to save it (optional)"}),
    "search_web":   (tool_search_web,   "Search the web (DuckDuckGo, no API key needed) and return the top results with titles, links and snippets. Use this whenever the user asks something you do not know, asks you to search, or says yes to a search offer — search first, then answer from the results, instead of saying you do not have it in local data.", {"query": "What to search for"}),
    "search_download": (tool_search_download, "Full download workflow: search for a file the user named, download the first direct file link, open the downloaded file, and report it so the user can be notified. If no direct file link exists, open the search page in the browser and say so — never automate Chrome clicks, logins, or CAPTCHAs.", {"query": "File name to search for, or a direct http(s) URL", "folder": "Destination folder (optional)"}),
    "youtube_upload": (tool_youtube_upload, "Upload an existing video file to the user's YouTube channel via the OFFICIAL YouTube API only (OAuth token file, never a password, never Chrome-login automation). TWO-STEP: first call WITHOUT confirmed to show the plan, only call again with confirmed=true after the user says 'confirm'. Privacy defaults to private. JARVIS cannot invent a video — video_path must exist.", {"video_path": "Existing video file to upload", "title": "Video title", "description": "Video description (optional)", "thumbnail_path": "Existing thumbnail image (optional)", "privacy": "private, unlisted or public (optional, default private)", "confirmed": "Set to true ONLY after the user said confirm (optional)"}),
    "jarvis_computer": (tool_jarvis_computer, "JARVIS's own computer workspace: its dedicated folders on this PC for its own work, plus how much disk is free. JARVIS can also access the user's computer through the other tools when asked.", {}),
    "remember_this": (tool_remember_this, "BUILD 14: remember a fact or task about the user for next time.", {"text": "What to remember", "kind": "fact or task (optional)"}),
    "recall_memory": (tool_recall_memory, "BUILD 14: list what JARVIS remembers about the user — facts and open tasks.", {}),
    "add_reminder": (tool_add_reminder, "BUILD 14: set a reminder — 'remind me in 10 minutes to …' or 'remind me at 9:30 to …'.", {"text": "The full reminder sentence"}),
    "list_reminders": (tool_list_reminders, "BUILD 14: list upcoming and due reminders.", {}),
    "morning_briefing": (tool_morning_briefing, "BUILD 14: a short morning briefing — date, due reminders, remembered facts and open tasks.", {}),
    "open_app": (tool_open_app, "BUILD 14: open an app by name on Windows (notepad, calculator, chrome, edge, word, excel, settings, terminal, powershell, spotify, vs code). Only allow-listed apps — never a path.", {"name": "App name"}),
    "recall_last_chat": (tool_recall_last_chat, "BUILD 15: recall the last chat — what we were working on, recent turns, rolling summary.", {}),
    "what_were_we_working_on": (tool_what_were_we_working_on, "BUILD 15: what were we working on last? Answers from saved chat history, no re-explaining needed.", {}),
    "todays_schedule": (tool_todays_schedule, "BUILD 15: today's schedule from Google Calendar (read-only, OAuth). Says plainly if the calendar is not connected.", {}),
    "list_meetings_today": (tool_list_meetings_today, "BUILD 15: list today's meetings from Google Calendar (read-only).", {}),
    "next_meeting": (tool_next_meeting, "BUILD 15: the next meeting today from Google Calendar (read-only).", {}),
    "calendar_status": (tool_calendar_status, "BUILD 15: is Google Calendar connected? What is missing (token, credentials, libraries)?", {}),
    "daily_summary": (tool_daily_summary, "BUILD 15: a short daily summary — what we talked about, open tasks, today's meetings.", {}),
    "learn_preference": (tool_learn_preference, "BUILD 15: learn a preference about the user (e.g. voice, language) and remember it.", {"key": "Preference name", "value": "Preference value"}),
    "search_h_drive": (tool_search_h_drive, "BUILD 15: search file names in H:\\JARVIS-Work only — never C: drive.", {"query": "File name to search for"}),
    "set_volume": (tool_set_volume, "BUILD 15: volume control — mute, volume_up or volume_down (needs pyautogui on Windows; says so plainly if missing).", {"action": "mute / volume_up / volume_down"}),
    "read_gmail": (tool_read_gmail, "BUILD 15: read the latest Gmail (read-only, official Google API, OAuth only — never a password). Says plainly if Gmail is not connected.", {"count": "How many, default 5"}),
    "gmail_status": (tool_gmail_status, "BUILD 15: is Gmail connected? What is missing?", {}),
    "book_meeting": (tool_book_meeting, "BUILD 16: book a calendar event — TWO-STEP: first call returns the plan only, call confirm_meeting with confirmed=true ONLY after the user says 'confirm'.", {"text": "e.g. 'Book a meeting with Ali tomorrow at 3pm for 30 minutes'"}),
    "confirm_meeting": (tool_confirm_meeting, "BUILD 16: confirm (confirmed=true) or cancel the pending calendar booking.", {"confirmed": "Set to true ONLY after the user said confirm"}),
    "check_my_status": (tool_check_my_status, "BUILD 16: one status briefing — today's calendar, reminders, open tasks, Gmail unread count, last work.", {}),
    "voice_quality_report": (tool_voice_quality_report, "BUILD 16: Voice Quality report — replies spoken fully, average latency to first spoken word, tasks done/failed, recent failures.", {}),
    "handoff_to_muse": (tool_handoff_to_muse, "BUILD 16: hand this task to Muse — save the full context to TASK-STATUS.md in H:\\JARVIS-Work\\ so it can be picked up elsewhere.", {"task": "What we were doing", "summary": "Last chat summary (optional)"}),
    "security_check_ports": (tool_security_check_ports, "BUILD 16 ethical security: check open ports on YOUR OWN PC only (localhost). Refuses any other host.", {"host": "localhost (only your own PC)"}),
    "security_check_passwords": (tool_security_check_passwords, "BUILD 16 ethical security: check weak passwords in YOUR OWN H: drive file — TWO-STEP, call with confirmed=true ONLY after the user says 'confirm'. Never shows the passwords themselves.", {"path": "H:\\JARVIS-Work\\ file path", "confirmed": "Set to true ONLY after the user said confirm"}),
    "security_scan_h_drive": (tool_security_scan_h_drive, "BUILD 16 ethical security: scan YOUR OWN H: drive files — counts by type, flags sensitive names and executables, never opens sensitive contents.", {}),
    "explain_security_risk": (tool_explain_security_risk, "BUILD 16 ethical security: explain a security risk in plain words — education only, never exploit instructions.", {"topic": "e.g. weak passwords, open ports"}),
    "camera_status": (tool_camera_status, "BUILD 17: camera state — OFF by default, local only, never streamed, no face recognition.", {}),
    "camera_on": (tool_camera_on, "BUILD 17: turn the camera on (probes the real camera; says plainly if none is found — never fakes a feed).", {}),
    "camera_off": (tool_camera_off, "BUILD 17: turn the camera off.", {}),
    "test_camera": (tool_test_camera, "BUILD 17: test the camera and report plainly if it works.", {}),
    "take_photo": (tool_take_photo, "BUILD 17: take one photo, saved only to H:\\JARVIS-Work\\Photos\\. The camera must be on first.", {}),
    "describe_camera": (tool_describe_camera, "BUILD 17: 'what do you see?' — describe the camera view in plain words, never name a person.", {}),
    "record_camera_video": (tool_record_camera_video, "BUILD 17: record video — TWO-STEP: first call WITHOUT confirmed to show the plan, only call again with confirmed=true after the user says 'confirm'.", {"seconds": "How many seconds, 1-60 (optional)", "confirmed": "Set to true ONLY after the user said confirm (optional)"}),
    "stop_camera_recording": (tool_stop_camera_recording, "BUILD 17: stop (or cancel) a camera recording.", {}),
    "focus_kali_vm": (tool_focus_kali_vm, "BUILD 17: find and focus the Kali VM window (VirtualBox/VMware) — plain message if Kali is not running, never type blindly.", {}),
    "type_in_kali": (tool_type_in_kali, "BUILD 17: type a command into the focused Kali VM terminal and press Enter — TWO-STEP: first call WITHOUT confirmed to show the plan, only call again with confirmed=true after the user says 'confirm'. Refuses unauthorised targets.", {"command": "The exact command to type", "confirmed": "Set to true ONLY after the user said confirm (optional)"}),
    "run_kali_command": (tool_run_kali_command, "BUILD 17: run a command in Kali — TWO-STEP: first call returns the exact command; call confirm_kali_command with confirmed=true ONLY after the user says 'confirm'.", {"command": "e.g. 'nmap -sn 192.168.1.0/24'"}),
    "confirm_kali_command": (tool_confirm_kali_command, "BUILD 17: confirm (confirmed=true) or cancel the pending Kali command.", {"confirmed": "Set to true ONLY after the user said confirm"}),
    "clap_wake_status": (tool_clap_wake_status, "BUILD 18: clap-wake state — OFF by default, double clap only, speech never wakes.", {}),
    "enable_clap_wake": (tool_enable_clap_wake, "BUILD 18: turn clap wake on/off — a double clap wakes TORVIS and switches on the HUD.", {"enabled": "true to turn clap wake on, false to turn it off", "sensitivity": "0.1-1.0, optional"}),
    "gesture_status": (tool_gesture_status, "BUILD 18: gesture state — OFF by default, camera only, local only, no face recognition.", {}),
    "enable_gestures": (tool_enable_gestures, "BUILD 18: turn hand-gesture control on/off — open palm wakes, swipe is next/previous, pinch selects, fist stops speaking.", {"enabled": "true to turn gestures on, false to turn them off"}),
    "hud_mode_on": (tool_hud_mode_on, "BUILD 18: switch HUD mode on — the full animated TORVIS HUD.", {}),
    "hud_mode_off": (tool_hud_mode_off, "BUILD 18: switch HUD mode off — back to the normal view.", {}),
    "printer_status": (tool_printer_status, "BUILD 18: 3D-printer hook status — plainly 'No 3D printer connected' unless an OctoPrint URL is set in Settings.", {}),
    "autopilot_status": (tool_autopilot_status, "BUILD 19: master + YouTube autopilot state — both OFF by default; ON means no confirm on his own PC / own accounts, but the protected list, own-stuff-only, no-pay and no-delete-outside-H: limits still apply.", {}),
    "enable_autopilot": (tool_enable_autopilot, "BUILD 19: turn master autopilot on/off — ON skips confirm gates on his own PC / own accounts (installs from official sources only); OFF brings every confirm gate back.", {"enabled": "true to turn autopilot on, false to turn it off"}),
    "enable_youtube_autopilot": (tool_enable_youtube_autopilot, "BUILD 19: turn YouTube autopilot on/off — ON means YouTube uploads/posts need no confirm; OFF means the two-step YouTube confirm (unless master autopilot is on).", {"enabled": "true to turn YouTube autopilot on, false to turn it off"}),
    "analyze_youtube_channel": (tool_analyze_youtube_channel, "BUILD 19: analyse HIS YouTube channel (official API, OAuth only) — best niche from real video views/likes, with numbers. Says plainly if YouTube is not connected; never invents channel data.", {}),
    "make_youtube_caption": (tool_make_youtube_caption, "BUILD 19: caption + hashtags for a video from its title/topic and the channel's best topics. No invented views.", {"title": "Video title", "topic": "Video topic (optional)", "best_topics": "Best topics from analyze_youtube_channel, comma-separated (optional)"}),
    "youtube_autopilot_post": (tool_youtube_autopilot_post, "BUILD 19: caption/hashtags + YouTube upload in one go — no confirm when YouTube autopilot (or master autopilot) is ON, two-step confirm when both are OFF. Video must exist on the H: drive.", {"video_path": "Existing video file on H: drive", "title": "Video title", "description": "Description (optional, defaults to the generated caption)", "thumbnail_path": "Existing thumbnail image (optional)", "privacy": "private, unlisted or public (optional, default private)", "topic": "Video topic (optional)", "confirmed": "Set to true ONLY after the user said confirm, when autopilot is off (optional)"}),
    "watch_site": (tool_watch_site, "BUILD 19: watch a site — add a URL to the watched list. Checking is read-only and never needs a confirm.", {"url": "https://… URL to watch"}),
    "list_watched_sites": (tool_list_watched_sites, "BUILD 19: list the watched sites and their last status.", {}),
    "site_status": (tool_site_status, "BUILD 19: check the watched sites now (read-only, no confirm) — reports down / back up / changed.", {}),
    "pronunciation_status": (tool_pronunciation_status, "BUILD 19: which language voices are actually installed on this PC — ur-PK for Urdu/Roman Urdu, matching locale for other languages. Falls back plainly when a locale is not installed; never forces an English voice on Urdu text.", {"available_voices": "Installed voice names (optional, test hook)", "voice_per_language": "Settings voice-per-language list (optional)"}),
    "type_text": (tool_type_text, "BUILD 14: type text into the focused window on this PC (needs pyautogui on Windows).", {"text": "Text to type"}),
    "click_at": (tool_click_at, "BUILD 14: click at screen coordinates the user gave (needs pyautogui on Windows).", {"x": "X coordinate", "y": "Y coordinate"}),
    "download_file": (tool_download_file, "Download a file directly from a URL to the Downloads folder (or a named folder) — no browser, no clicking. Use for 'download <link>' requests; prefer official sources.", {"url": "The http(s) URL to download", "folder": "Destination folder (optional, defaults to ~/Downloads)"}),
    "install_software": (tool_install_software, "Install an already-downloaded .msi or .exe installer silently/unattended. TWO-STEP per the owner's rule: first call WITHOUT confirmed to get the plan, tell the user what will change, and only call again with confirmed=true after the user says 'confirm'.", {"path": "Path to the downloaded installer file", "confirmed": "Set to true ONLY after the user said confirm (optional)", "installer_type": "auto, nsis, inno, quiet or msi (optional, default auto)"}),
}

SYSTEM_PROMPT = (
    "You are TORVIS, the user's personal AI agent living on their own computer (formerly called JARVIS — answer to Torvis, and to Jarvis as a legacy alias). "
    "You can use tools to inspect and operate this computer: browse and read files, "
    "create files, run commands, open apps and folders, search, and take screenshots. "
    "Prefer acting over describing: when the user asks something you can do with a tool, do it. "
    "Finish the task you are given: work through it with tools until it is complete, "
    "then give the final result. Do not stop mid-task to ask the user to continue — keep going. "
    "The user has switched approval prompts OFF: execute tasks immediately, even risky ones — "
    "never ask for confirmation and never warn instead of acting. "
    "There is exactly ONE hard restriction: files and folders the user has marked as protected "
    "(in Settings) are completely off-limits. Never read, list, create, modify, delete, open or "
    "run commands touching a protected path, and never try to work around the block — the tools "
    "refuse automatically; if that happens, tell the user plainly that the path is protected by "
    "their own rule and move on. "
    "You have your own computer workspace at ~/JARVIS-Computer (Work, Downloads, Notes): "
    "that is where you keep your own files, notes and things you download for yourself, "
    "like an assistant's own desk. You can also access the user's computer through your "
    "other tools when the user asks — the workspace is your home base, not a limit on "
    "what you can reach. "
    "You have a built-in web search tool (search_web, no API key, no download needed): "
    "when the user asks something you do not know, asks you to search, or says yes to "
    "a search offer, call search_web first and answer from its results. Never stop at "
    "'I don't have that in my local data' when a search could answer it. "
    "When the user says 'download <something>', use search_download: it searches, "
    "downloads a direct file link, opens the file, and reports it for notification. "
    "If no direct link exists, open the search page and say so — never automate "
    "Chrome clicks, logins, or CAPTCHAs. When the user says 'upload a video to "
    "YouTube', use youtube_upload: show the plan first, upload only after the user "
    "says 'confirm', through the official API only, never a password and never a "
    "Chrome login as the user, privacy private unless the user explicitly says "
    "otherwise, and only an existing video file — never invent a video. "
    "You can also fetch software directly: download_file pulls a URL straight to the Downloads "
    "folder with no browser involved — prefer official sources for downloads. For INSTALLS the "
    "owner has one extra rule that overrides the no-confirmation default: call install_software "
    "first WITHOUT confirmed, tell the user its plan (what will change), and only call it with "
    "confirmed=true after the user says 'confirm'. "
    "BUILD 14: you have real memory (remember_this / recall_memory) — use it, and remember what the user tells you to remember. "
    "BUILD 15: you remember the FULL chat history — load it, summarise older chats, and answer 'what were we working on?' without making the user re-explain. "
    "BUILD 15: keep replies short and natural by default — 1-3 sentences, no filler like 'let me check', no repeating yourself. If the user wants detail, they will ask. "
    "No false refusals: if the user states a lawful purpose, act on it. If something is genuinely unclear, ask ONE clarifying question instead of blocking — never refuse and stop. "
    "BUILD 16: WORLD-BEST VOICE — speak the first chunk immediately, keep replies short, never guess: if you do not know a fact (price, date, meeting, time), say you do not know and check the source (search / calendar / memory) instead of guessing. If speech was unclear, say so and ask the user to repeat once — never guess what they said. "
    "BUILD 16 ethical security: only check YOUR OWN PC and YOUR OWN files — never scan, access, or attack anyone else's system without their written permission; refuse unauthorised hacking plainly. Use security_check_ports / security_check_passwords (confirm first) / security_scan_h_drive for your own PC only. ""BUILD 16: you can BOOK a calendar event with book_meeting + confirm_meeting — two-step, book only after the user says 'confirm'. Use check_my_status for a one-go briefing (calendar + reminders + tasks + Gmail unread). Use handoff_to_muse to hand a task to Muse (saves TASK-STATUS.md in H: drive JARVIS-Work). "
    "BUILD 15: you can read today's Google Calendar (todays_schedule / next_meeting, read-only) and Gmail (read_gmail, read-only) — both OAuth only, never a password. If either is not connected, say so plainly and say what setup is needed; never invent meetings or mail. "
    "BUILD 17: the camera is OFF by default and local only — never streamed, never sent anywhere. Turn it on only when the user asks (camera_on), take a photo only to H:\\JARVIS-Work\\Photos\\ (take_photo), record video only after the user says 'confirm' (record_camera_video, two-step), and never do face recognition or name a person. If no camera is found, say 'No camera found' plainly — never fake a feed. "
    "BUILD 17: Kali VM — when the user is using Kali in a VM, type commands into the Kali window only, and only after they say 'confirm' (run_kali_command + confirm_kali_command, two-step). Only run commands against their own PC/network or a target on their written authorisation list (H:\\JARVIS-Work\\authorised-targets.txt) — refuse any other target plainly. Use focus_kali_vm first; if Kali is not running, say so and never type into another window. "
    "BUILD 18: clap wake is OFF by default — a double clap wakes TORVIS and switches on the HUD; one clap or normal speech never wakes (clap_wake_status / enable_clap_wake). Gestures are OFF by default and need the camera on, local only, never streamed, no face recognition — open palm wakes and shows the HUD, swipe right is next, swipe left is previous, pinch selects, fist stops speaking (gesture_status / enable_gestures). HUD mode switches the normal view to the full animated TORVIS HUD (hud_mode_on / hud_mode_off). Minimising stays in the Windows taskbar AND the tray — the taskbar icon restores the window directly. 3D printer: hook only — say 'No 3D printer connected' plainly unless an OctoPrint URL is set in Settings (printer_status); never invent a printer. "
    "BUILD 19: FULL AUTOPILOT — both autopilot toggles are OFF by default and only Faizan turns them on in Settings. When master autopilot is ON (autopilot_status / enable_autopilot), do NOT ask for confirm before doing things on his own PC and his own accounts — installs from official sources only, YouTube and other own-account posts/uploads, Kali VM commands, file operations in the H: drive. When it is OFF, every confirm gate works as before. YouTube autopilot (enable_youtube_autopilot) is the same for YouTube only. HARD LIMITS even in autopilot: NEVER touch a protected file (skip it, say so, continue); NEVER scan/hack/access anyone else's system, network, account or website without their written permission; NEVER pay for anything; NEVER delete files outside the H: drive without the user naming that exact file in that moment. Use analyze_youtube_channel to find the best niche for HIS channel from real views/likes (never invent channel data — if YouTube is not connected, say so plainly), make_youtube_caption for caption + hashtags, and youtube_autopilot_post for caption + upload in one go (video must be on the H: drive). Use watch_site / list_watched_sites / site_status to watch his sites — checking is read-only and never needs a confirm. Meeting alerts (15 minutes before, from Google Calendar) are notifications, never actions — they never need a confirm, in autopilot or not. "
    "BUILD 19: MULTILINGUAL VOICE — detect the language of each reply (Urdu, Roman Urdu, English, Hindi, French, Spanish, German, Turkish, Arabic and more) and speak it with the matching native neural voice when one is installed (ur-PK for Urdu/Roman Urdu, en-GB/en-US for English, matching locale for the rest). If that locale is not installed, fall back to the default voice and say so plainly — never force an English voice on Urdu text (pronunciation_status lists what is actually installed; voice_per_language in Settings picks a voice per language). "
    "BUILD 19: HUMAN-LIKE SPEAKING — sound like a person talking, not a robot: short natural sentences (1–3), natural pauses, no robotic filler, never read code or a URL aloud, warm tone matching the conversation, speech interruptible at any time. NEVER claim to be human, and NEVER hide that you are TORVIS when asked directly — if the user asks 'are you human?', answer plainly that you are TORVIS, an AI assistant that tries to sound natural. "
    "Reply in the same language the user used: English, Roman Urdu, or Urdu — never switch their mix. "
    "Keep replies concise and clear. When a tool fails, say what happened and suggest the next step. "
    f"This computer runs {platform.system()} and the user's home folder is {Path.home()}. "
    "Use paths that fit this operating system."
)

# ------------------------------------------------------- screen advisor ---
# NOVA can glance at the screen every so often and suggest the single most
# useful next step. The advisor is deliberately separate from chat(): it
# never touches conversation history and never triggers the fallback brain.

ADVISOR_PROMPT = (
    "Look at this screen. In ONE short sentence, suggest the single most "
    "useful next action for the user, or reply exactly 'NOTHING' if there "
    "is nothing worth suggesting. No preamble."
)

def capture_screen_b64(max_width=1280, quality=70):
    """Screenshot -> base64 JPEG string, downscaled to max_width.
    Raises RuntimeError if Pillow is unavailable."""
    try:
        from PIL import ImageGrab
    except ImportError:
        raise RuntimeError("Pillow is not installed, screenshots unavailable.")
    img = ImageGrab.grab().convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()

_BOILERPLATE = (
    "nothing to suggest", "nothing worth suggesting", "no suggestion",
    "no action needed", "no action necessary", "nothing to recommend",
    "nothing at this time", "nothing to do",
)

def _suggestion_key(text):
    """Normalized comparison key: lowercase alphanumerics + single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(text).lower())).strip()

def normalize_suggestion(raw):
    """Clean a raw vision-model reply into a one-line suggestion, or None
    when the model effectively said there is nothing worth suggesting.
    Pure function — no I/O — so it is unit-testable anywhere."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # the model was told one sentence, no preamble — keep the first real line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = lines[0] if lines else ""
    text = re.sub(r"^(suggestion|answer|response)\s*:\s*", "", text, flags=re.I)
    text = text.strip().strip("💡\"'").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return None
    key = _suggestion_key(text)
    if key == "nothing" or (key.startswith("nothing ") and len(key) < 40):
        return None
    if key in _BOILERPLATE or any(key.startswith(b) for b in _BOILERPLATE):
        return None
    return text[:240]

def should_deliver(new, last):
    """True when `new` is a real suggestion that isn't just a repeat (or
    near-repeat) of the last one delivered. Pure function."""
    if not new:
        return False
    if not last:
        return True
    a, b = _suggestion_key(new), _suggestion_key(last)
    if not a:
        return False
    if a == b:
        return False
    if a in b or b in a:
        return False
    sa, sb = set(a.split()), set(b.split())
    if sa and sb and len(sa & sb) / len(sa | sb) >= 0.8:
        return False
    return True

def _openai_vision_messages(prompt, image_b64):
    """OpenAI-style chat messages carrying a base64 JPEG (works for OpenAI,
    Gemini's OpenAI-compatible endpoint, and vision-capable Ollama)."""
    return [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url",
         "image_url": {"url": "data:image/jpeg;base64," + image_b64}},
    ]}]

def _anthropic_vision_content(prompt, image_b64):
    """Anthropic-style content blocks carrying a base64 JPEG."""
    return [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
        {"type": "text", "text": prompt},
    ]

# ------------------------------------------------------- model providers ---

# Google retired gemini-2.5-flash for new users (404 NOT_FOUND — Google's own
# error says to use gemini-3.8-flash). Map the dead name to its replacement
# wherever a model is applied, so even a stale saved config keeps working.
# BUILD 10, permanent Ollama replacement: llama3.1 -> llama3.2:3b.
_RETIRED_MODELS = {"gemini-2.5-flash": "gemini-3.8-flash",
                   "llama3.1": "llama3.2:3b", "llama3.1:8b": "llama3.2:3b"}

def _migrate_model(model):
    m = str(model or "").strip()
    bare = m[len("models/"):] if m.startswith("models/") else m
    return _RETIRED_MODELS.get(bare, m)



# --------------------------------------------- transient-error handling ---
# Providers (Gemini especially) intermittently refuse requests with
# 429 / 500 / 503 — "high demand" spikes that usually clear within
# seconds. Those are TRANSIENT: retry a few times with backoff before
# giving up. Everything else (400/401/403/404 — bad request, bad key,
# dead model name) is a hard failure and must surface immediately.

class TransientModelError(RuntimeError):
    """A model-API failure that is usually temporary (429/500/503).
    Subclasses RuntimeError so existing handlers keep working; the
    distinct type lets callers tell 'provider busy, try later' apart
    from 'this will never work'."""

_TRANSIENT_CODES = {429, 500, 503}
_TRANSIENT_STATUSES = ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL")
_RETRY_WAITS = (2, 5, 10)    # seconds waited before attempts 2, 3, 4

_sleep = time.sleep          # injectable so tests never really sleep

# The Screen Advisor's vision call uploads a full screenshot and waits on
# the slowest answer NOVA ever asks for, so screen_suggestion() gives it
# its own, longer HTTP budget. Chat keeps the shared _http_json default
# (180s) exactly as before — this constant is used ONLY on the vision
# path.
VISION_HTTP_TIMEOUT = 240

# ------------------------------------------------ daily-quota errors ----
# A 429 is NOT always "provider busy". On free tiers (Gemini especially)
# a 429 can mean the DAILY request quota is finished — Google's body
# says so plainly: "Quota exceeded for metric:
# .../generate_content_free_tier_requests, limit: 20 ... Generate
# content requests per day limit exceeded on Free Tier ... Please
# retry in 15h22m". That is a QUOTA error, not overload: retrying in
# seconds is pointless, the friendly message is different ("your daily
# quota is finished", not "high demand"), and chat() treats it like an
# unreachable brain — one attempt on the fallback brain.
#
# A quota verdict needs DAILY evidence in the text. A bare 429 or a
# bare RESOURCE_EXHAUSTED status is just per-minute rate limiting and
# stays transient (it gets one short retry — see _http_json). The
# per-minute metric name (..._requests_per_minute) even CONTAINS the
# per-day metric name as a substring, so per-minute wording is ruled
# out first.

_QUOTA_MARKERS = ("quota exceeded", "generate_content_free_tier_requests",
                  "per day", "requests per day")

def _http_code(err):
    """The HTTP status code embedded in a 'Model API error NNN' text,
    or None. Pure function."""
    m = re.search(r"Model API error (\d{3})\b", str(err))
    return int(m.group(1)) if m else None

def is_quota_error(err):
    """True when `err` is a DAILY-quota exhaustion (the free tier's
    per-day request cap is used up), as opposed to a momentary
    overload or per-minute rate-limit spike. Pure function. Signals:
    'quota exceeded' wording, the free-tier metric name, a 'per day'
    limit description, or a retry delay measured in HOURS ('Please
    retry in 15h22m…')."""
    text = str(err)
    low = text.lower()
    if ("per_minute" in low or "per minute" in low) and "per day" not in low:
        return False   # per-minute rate limit wearing quota wording
    if any(marker in low for marker in _QUOTA_MARKERS):
        return True
    if re.search(r"retry in\s*\d+\s*h", low):          # 'retry in 15h22m…'
        return True
    if re.search(r"retrydelay\D{0,4}\d{4,}s", low):   # 'retryDelay': '54926s'
        return True
    return False

def is_transient_error(err):
    """True when `err` (an exception or error text) is a transient
    provider failure: HTTP 429/500/503, or a body carrying a
    RESOURCE_EXHAUSTED / UNAVAILABLE / INTERNAL status. A DAILY-quota
    exhaustion is NOT transient even though it arrives as a 429 with
    RESOURCE_EXHAUSTED — see is_quota_error. Pure function."""
    if is_quota_error(err):
        return False
    if isinstance(err, TransientModelError):
        return True
    text = str(err)
    m = re.search(r"Model API error (\d{3})\b", text)
    if m and int(m.group(1)) in _TRANSIENT_CODES:
        return True
    return any(re.search(r"\b" + s + r"\b", text) for s in _TRANSIENT_STATUSES)

# Shown (instead of a raw JSON dump) when every retry hit provider overload.
OVERLOAD_MESSAGE = (
    "⚠ The model is overloaded right now (503 — high demand on the "
    "provider's side; these spikes are usually temporary). Give it a "
    "minute and ask me again, or switch the model in Settings "
    "(gemini-3.5-flash is usually quieter)."
)

# Shown when the brain's free DAILY quota is exhausted and there is no
# fallback brain to switch to. Deliberately different from
# OVERLOAD_MESSAGE: waiting a minute will not fix this one — the quota
# resets on the provider's own (hours-long) timer.
QUOTA_MESSAGE = (
    "⚠ This brain's free daily quota is finished (Google's free tier "
    "allows only a small number of requests per day). It resets on "
    "Google's timer, or switch the model/brain in Settings."
)

def is_timeout_error(err):
    """True when `err` is a socket/read timeout rather than a real
    answer from the provider: a TimeoutError / socket.timeout instance
    (an HTTPS read that stalls raises exactly this — 'The read
    operation timed out'), or any error text saying it 'timed out'.
    Pure function."""
    if isinstance(err, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(err).lower()

_NETWORK_TEXT_HINTS = ("could not reach the model api", "eof occurred",
                       "connection reset", "connection refused",
                       "connection aborted", "name resolution",
                       "network is unreachable", "remote end closed",
                       "ssl", "urlerror", "broken pipe")

def is_network_error(err):
    """True when `err` is a network-level failure — the request never
    got a real answer from the provider (DNS failure, refused/reset
    connection, an SSL EOF like 'EOF occurred in violation of protocol
    (_ssl.c:2427)', ...). Pure function. NOTE: chat() keeps its own,
    narrower trigger ('Could not reach the model API') for engaging
    the fallback brain; this wider net exists for the Screen Advisor,
    where any network hiccup should mean 'skip this cycle', never
    'vision is broken, switch off'."""
    if isinstance(err, urllib.error.URLError):
        return True
    low = str(err).lower()
    return any(hint in low for hint in _NETWORK_TEXT_HINTS)

def advisor_failure_action(err):
    """What the Screen Advisor should do after a failed vision call:
    "skip" — transient trouble (provider overloaded/rate-limited,
    the call TIMED OUT — a slow vision answer is not 'vision
    unavailable' — a NETWORK-level failure such as an SSL EOF, or
    the brain's daily quota being finished): stay ON and simply try
    again next cycle. "disable" — hard failure (dead model 404, bad
    key 401/403, vision unsupported 400, ...): switch OFF rather
    than failing on every interval. Pure function. NOTE: this
    leniency belongs to the advisor only — chat()'s network-error
    handling (immediate fallback, no retry) is deliberately
    untouched by it."""
    if (is_quota_error(err) or is_transient_error(err)
            or is_timeout_error(err) or is_network_error(err)):
        return "skip"
    return "disable"

MODEL_API_USER_AGENT = "JARVIS/1.0"

def _http_json_once(url, headers, payload, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    for k, v in headers.items(): req.add_header(k, v)
    # Cloudflare (in front of Groq and others) blocks requests whose
    # User-Agent is Python's urllib default ("Python-urllib/3.x") with
    # a 403 error code 1010, before the request ever reaches the API
    # — so a correct key still fails. Send a descriptive User-Agent
    # instead, unless the caller already set one.
    if not any(k.lower() == "user-agent" for k in headers):
        req.add_header("User-Agent", MODEL_API_USER_AGENT)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:600]
        err = RuntimeError(f"Model API error {e.code}: {body}")
        if e.code in _TRANSIENT_CODES or is_transient_error(err):
            raise TransientModelError(str(err)) from e
        raise err from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach the model API: {e.reason}") from e

def _http_json(url, headers, payload, timeout=180):
    """POST JSON to a model API, retrying TRANSIENT failures (500/503
    overload spikes) up to 3 extra times with ~2s/5s/10s backoff. A
    per-minute 429 rate limit gets ONE short retry only — hammering a
    rate limit just prolongs it. A DAILY-quota 429 is never retried:
    seconds of waiting cannot refill a quota that resets in hours, so
    it is raised at once and chat() switches brains / explains. Hard
    HTTP errors fail immediately, and network failures keep their
    original 'Could not reach the model API' error — they are not
    retried, so chat()'s auto-fallback engages exactly as before."""
    retries = 0
    while True:
        try:
            return _http_json_once(url, headers, payload, timeout)
        except TransientModelError as e:
            if is_quota_error(e):
                raise
            allowed = 1 if _http_code(e) == 429 else len(_RETRY_WAITS)
            if retries >= allowed:
                raise
            _sleep(_RETRY_WAITS[min(retries, len(_RETRY_WAITS) - 1)])
            retries += 1

def _anthropic_tools():
    out = []
    for name, (_fn, desc, params) in TOOLS.items():
        props = {k: {"type": "string", "description": v} for k, v in params.items()}
        req = [k for k in params if "optional" not in params[k]]
        out.append({"name": name, "description": desc,
                    "input_schema": {"type": "object", "properties": props, "required": req}})
    return out

def _openai_tools():
    out = []
    for name, (_fn, desc, params) in TOOLS.items():
        props = {k: {"type": "string", "description": v} for k, v in params.items()}
        req = [k for k in params if "optional" not in params[k]]
        out.append({"type": "function", "function": {"name": name, "description": desc,
                    "parameters": {"type": "object", "properties": props, "required": req}}})
    return out

# BUILD 16 — WORLD-BEST VOICE: LOW LATENCY, BARGE-IN, NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 16 — TORVIS: WORLD-BEST VOICE, LOW LATENCY, BARGE-IN, NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 15 — FULL CHAT MEMORY, GOOGLE CALENDAR, NEURAL VOICE, LOW LATENCY, NEVER SILENT, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 14 — VOICE FIXED, MEMORY, PROACTIVE, STREAMING, ROMAN URDU, PC CONTROL, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK
# BUILD 13 (2026-11-10): long tasks must FINISH, not stop mid-task.
# Old limit was 12 tool rounds per reply, then the agent returned
# the old stop line ("ask me to continue") is retired for good.
# A build + deploy easily needs far more than 12 rounds.
# Now 40 rounds per pass, up to 2 auto-continuations (120 rounds
# total). The continuation instruction is appended to the message
# list and the loop runs again — the user is never asked to continue.
MAX_TOOL_ROUNDS = 40
MAX_AUTO_CONTINUATIONS = 2
CONTINUATION_MESSAGE = (
    "Continue the task from where you left off. Do not stop, do not ask "
    "me to continue — keep working with tools until the task is complete, "
    "then give the final result.")
def _progress_summary(tools_used, rounds):
    """After the hard 120-round limit, report what was done and what
    is left — never ask the user to continue."""
    if tools_used:
        counts = {}
        for name in tools_used:
            counts[name] = counts.get(name, 0) + 1
        used = ", ".join(f"{n} x{c}" for n, c in counts.items())
        last = ", ".join(tools_used[-5:])
    else:
        used, last = "no tools", "none"
    return (
        f"I worked through {rounds} tool rounds and the task is still not finished — "
        "I stopped at the safety limit, not because the task is done. "
        f"What I did so far: {used}. Last steps: {last}. "
        "What is left: the remaining steps of the original task, which I did not "
        "reach yet. Tell me the task again in a shorter form, or split it into "
        "smaller parts, and I will carry on from here.")


class Agent:
    """One conversation. Tools execute immediately — there is no approval
    step. `on_tool(name, detail)` is called for display as tools run. The
    config's `protected_paths` list is the single enforced restriction."""
    def __init__(self, config, on_tool=None):
        self.protected_paths = [str(x) for x in (config.get("protected_paths") or [])]
        set_protected_paths(self.protected_paths)
        self._primary = {
            "provider": config.get("provider", "anthropic"),
            "api_key": config.get("api_key", ""),
            "model": config.get("model", ""),
            "base_url": config.get("base_url", ""),
        }
        fb = config.get("fallback") or {}
        self.fallback = {
            "enabled": fb.get("enabled", True),
            "provider": fb.get("provider") or "openai",
            "api_key": fb.get("api_key", ""),
            "model": fb.get("model", "") or "gemini-3.5-flash-lite",
            "base_url": fb.get("base_url", "") or "https://generativelanguage.googleapis.com/v1beta/openai/",
        }
        self._apply_provider(self._primary)
        self.on_tool = on_tool or (lambda _n, _d: None)
        self.history = []  # provider-neutral: {"role": "user"/"assistant", "text": ...}
        self.chat_history = None
        self.chat_summary = ""
        if b15 is not None:
            try:
                self.chat_history = b15.ChatHistoryStore()
                self.chat_summary = self.chat_history.summary
                # BUILD 15: the last turns go into the SYSTEM PROMPT
                # (see _system_prompt), NOT into self.history — the
                # Screen Advisor must stay history-free, and history
                # is this session's turns only.
            except Exception:  # noqa: BLE001
                self.chat_history = None
        self.language = "english"
        self.memory = None
        if b14 is not None:
            try:
                self.memory = b14.MemoryStore()
            except Exception:  # noqa: BLE001
                self.memory = None

    def _system_prompt(self):
        prompt = SYSTEM_PROMPT
        if self.memory is not None:
            lines = self.memory.as_prompt_lines()
            if lines:
                prompt += " " + " ".join(lines)
        if self.chat_history is not None:
            hlines = self.chat_history.as_prompt_lines()
            if hlines:
                prompt += " Recent conversation: " + " | ".join(hlines)
        if b14 is not None:
            prompt += " " + b14.reply_language_note(self.language)
        if not self.protected_paths:
            return prompt
        listing = "; ".join(self.protected_paths)
        return (prompt + " Protected paths set by the user (never touch these): "
                + listing + ".")

    def _default_model(self):
        return ("claude-sonnet-5" if self.provider == "anthropic" else
                "gpt-4o" if self.provider == "openai" else "llama3.2:3b")

    def _default_base(self):
        return ("https://api.openai.com/v1" if self.provider == "openai"
                else "http://localhost:11434/v1")

    def _apply_provider(self, spec):
        self.provider = spec.get("provider", "anthropic")
        self.api_key = spec.get("api_key", "")
        self.model = _migrate_model(spec.get("model", "")) or self._default_model()
        self.base_url = spec.get("base_url", "") or self._default_base()

    def _run_tool(self, name, args):
        fn, _desc, _p = TOOLS.get(name, (None, None, None))
        if fn is None: return {"ok": False, "error": f"Unknown tool {name}"}
        detail = json.dumps(args)[:300]
        self.on_tool(name, detail)
        try: return fn(args)
        except Exception as e: return {"ok": False, "error": f"{type(e).__name__}: {e}"}  # noqa: BLE001

    def chat(self, user_text):
        if b14 is not None:
            self.language = b14.detect_language(user_text)
        self.history.append({"role": "user", "text": user_text})
        if self.chat_history is not None:
            try:
                self.chat_history.add("user", user_text)
            except Exception:  # noqa: BLE001
                pass
        try:
            reply = self._run_provider_loop()
        except RuntimeError as e:  # noqa: BLE001
            quota = is_quota_error(e)
            unreachable = "Could not reach the model API" in str(e)
            overloaded = is_transient_error(e)
            # BUILD 11: a fallback must differ in provider, base URL,
            # or model — not just provider name. Groq main and Gemini
            # fallback are both "openai" as a provider string, so the
            # old provider-only check would never switch to Gemini.
            def _spec_key(spec):
                return (str(spec.get("provider") or "").strip().lower(),
                        str(spec.get("base_url") or "").strip(),
                        str(spec.get("model") or "").strip())
            if (self.fallback.get("enabled")
                    and _spec_key(self.fallback) != _spec_key(self._primary)
                    and (unreachable or quota or overloaded)):
                # Main brain unusable for this message — either it can't
                # be reached at all (e.g. no internet), its free DAILY
                # quota is finished, or it stayed overloaded (429/500/
                # 503) after every retry: retry this message once on the
                # fallback brain, then restore the main one so recovery
                # is automatic when the network/quota/load comes back.
                # BUILD 10: overload now falls back too — before this,
                # an overloaded main brain just stopped, even though
                # Ollama was sitting there ready (Faizan's Python
                # research died after 3 steps on a Groq 503, 2026-10-26).
                if quota:
                    note = ("↪ Main brain's daily quota is finished — switched to "
                            f"your fallback brain ({self.fallback['provider']}) "
                            "for this reply.")
                elif overloaded:
                    note = ("↪ Main brain is overloaded right now — switched to "
                            f"your fallback brain ({self.fallback['provider']}) "
                            "for this reply. I'll try the main brain again "
                            "on your next message.")
                else:
                    note = (f"⚠ {self.provider} unreachable — switched to the fallback brain "
                            f"({self.fallback['provider']}) for this reply. "
                            "I'll try the main brain again on your next message.")
                self._apply_provider(self.fallback)
                try:
                    reply = note + "\n\n" + self._run_provider_loop()
                except RuntimeError as e2:  # noqa: BLE001
                    # The usual cause here is Ollama not actually being
                    # installed/running on this PC — the fallback is
                    # configured, but there is nothing listening on
                    # localhost:11434. Say that plainly, with both fixes,
                    # instead of a raw "Could not reach" error.
                    if self.fallback.get("provider") == "ollama":
                        reply = (note + "\n⚠ The fallback brain (Ollama) failed too — "
                                 "Ollama does not look installed or running on this PC. "
                                 "Fix (free API, no Ollama, no Groq): switch your main brain to Mistral "
                                 "in Settings — provider openai, base URL "
                                 "https://api.mistral.ai/v1, model "
                                 "mistral-medium-latest, with a Mistral key from console.mistral.ai.")
                    else:
                        reply = (note + f"\n⚠ The fallback brain failed too: {e2}.")
                finally:
                    self._apply_provider(self._primary)
            elif quota:
                # Daily quota finished and no fallback brain to switch
                # to: say so plainly (this is NOT a demand spike —
                # waiting a minute won't help), raw error as details.
                reply = QUOTA_MESSAGE + f"\n(Details: {e})"
            elif is_transient_error(e):
                # Provider overload (429/500/503) that survived every
                # retry, with no fallback brain to switch to: explain it
                # like a human, keep the raw error as a details line.
                # With a fallback configured, the branch above already
                # switched to it (BUILD 10) instead of stopping here.
                reply = OVERLOAD_MESSAGE + f"\n(Details: {e})"
            else:
                reply = f"⚠ {e}"
        self.history.append({"role": "assistant", "text": reply})
        # BUILD 15: save every turn, so the next restart remembers it.
        if self.chat_history is not None:
            try:
                self.chat_history.add("assistant", reply)
                self.chat_summary = self.chat_history.summary
            except Exception:  # noqa: BLE001
                pass
        return reply

    def chat_stream(self, user_text, on_first_sentence=None):
        """BUILD 14 streaming: run chat(), then hand the FIRST sentence
        to `on_first_sentence` as soon as the reply exists, so the
        caller can speak it while the rest is queued. Returns the
        full reply. (The brain APIs return whole replies; the first
        sentence is spoken first, the rest follows in queue order.)"""
        reply = self.chat(user_text)
        if on_first_sentence is not None and b14 is not None:
            first = b14.first_sentence(reply)
            if first:
                on_first_sentence(first)
        return reply

    def first_sentence(self, reply):
        """First sentence of a reply, for speak-while-thinking."""
        return b14.first_sentence(reply) if b14 is not None else str(reply or "")

    def screen_suggestion(self, image_b64, prompt=ADVISOR_PROMPT):
        """ONE vision call on the current brain: look at a screenshot and
        answer `prompt`. Returns the model's raw text. Deliberately does
        NOT touch self.history and does NOT use the chat fallback — the
        Screen Advisor must never pollute the conversation or silently
        switch brains. Raises RuntimeError on any failure (no vision,
        bad key, offline...): hard failures mean 'vision not available',
        while transient provider overload (429/500/503, after the usual
        retries) raises TransientModelError, and a stalled call raises a
        timeout error — advisor_failure_action() tells the caller which
        of the two it was (both mean 'skip this cycle', not 'disable')."""
        if self.provider == "anthropic":
            if not self.api_key:
                raise RuntimeError("No API key set. Open Settings and add your Anthropic API key.")
            data = _http_json("https://api.anthropic.com/v1/messages",
                {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                {"model": self.model, "max_tokens": 120,
                 "messages": [{"role": "user",
                               "content": _anthropic_vision_content(prompt, image_b64)}]},
                timeout=VISION_HTTP_TIMEOUT)
            return "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text").strip()
        headers = {}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        data = _http_json(self.base_url.rstrip("/") + "/chat/completions", headers,
            {"model": self.model,
             "messages": _openai_vision_messages(prompt, image_b64),
             "max_tokens": 120},
            timeout=VISION_HTTP_TIMEOUT)
        return (data["choices"][0]["message"].get("content") or "").strip()

    def _run_provider_loop(self):
        return self._anthropic_loop() if self.provider == "anthropic" else self._openai_loop()

    # --- Anthropic ---
    def _anthropic_loop(self):
        if not self.api_key: raise RuntimeError("No API key set. Open Settings and add your Anthropic API key.")
        msgs = []
        for h in self.history:
            msgs.append({"role": h["role"], "content": [{"type": "text", "text": h["text"]}]})
        tools_used, rounds = [], 0
        for _continuation in range(MAX_AUTO_CONTINUATIONS + 1):
            for _ in range(MAX_TOOL_ROUNDS):
                rounds += 1
                data = _http_json("https://api.anthropic.com/v1/messages",
                    {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                    {"model": self.model, "max_tokens": 4096, "system": self._system_prompt(),
                     "messages": msgs, "tools": _anthropic_tools()})
                blocks = data.get("content", [])
                msgs.append({"role": "assistant", "content": blocks})
                uses = [b for b in blocks if b.get("type") == "tool_use"]
                if not uses:
                    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip() or "(no reply)"
                results = []
                for u in uses:
                    tools_used.append(u["name"])
                    res = self._run_tool(u["name"], u.get("input") or {})
                    results.append({"type": "tool_result", "tool_use_id": u["id"],
                                    "content": json.dumps(res)[:24000]})
                msgs.append({"role": "user", "content": results})
            if _continuation == MAX_AUTO_CONTINUATIONS:
                break
            # Anthropic requires alternating roles: the last message is
            # a user tool_result, so merge the continuation text into
            # that message instead of adding a second user message.
            msgs[-1]["content"].append({"type": "text", "text": CONTINUATION_MESSAGE})
        return _progress_summary(tools_used, rounds)

    # --- OpenAI / compatible (incl. Ollama local) ---
    def _openai_loop(self):
        msgs = [{"role": "system", "content": self._system_prompt()}]
        for h in self.history:
            msgs.append({"role": h["role"], "content": h["text"]})
        headers = {}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        tools_used, rounds = [], 0
        for _continuation in range(MAX_AUTO_CONTINUATIONS + 1):
            for _ in range(MAX_TOOL_ROUNDS):
                rounds += 1
                data = _http_json(self.base_url.rstrip("/") + "/chat/completions", headers,
                    {"model": self.model, "messages": msgs, "tools": _openai_tools(), "tool_choice": "auto"})
                msg = data["choices"][0]["message"]
                calls = msg.get("tool_calls") or []
                if not calls:
                    return (msg.get("content") or "(no reply)").strip()
                msgs.append({"role": "assistant", "content": msg.get("content"), "tool_calls": calls})
                for c in calls:
                    tools_used.append(c["function"]["name"])
                    try: args = json.loads(c["function"].get("arguments") or "{}")
                    except json.JSONDecodeError: args = {}
                    res = self._run_tool(c["function"]["name"], args)
                    msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res)[:24000]})
            if _continuation == MAX_AUTO_CONTINUATIONS:
                break
            msgs.append({"role": "user", "content": CONTINUATION_MESSAGE})
        return _progress_summary(tools_used, rounds)
