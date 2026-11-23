# TORVIS — Native Edition (renamed from JARVIS in BUILD 16, 2026-11-21)

**TORVIS is Faizan's own name for his model — cool and friendly, his own name, not JARVIS/Marvel.** Wake word is now **"Torvis"** / **"Hey Torvis"**; **"Jarvis" is kept as a legacy alias for one build** so he is not locked out. The exe file, config folder (`%APPDATA%\NovaAgent\`), `jarvis.log`, and the internal `window.JARVIS_NATIVE` bridge name stay as they are in this build — only the user-facing name, HUD title, Settings marker, voice greeting, and icon changed. Similar names, if he ever wants one: **TORVIX / TORVUS / TORVIN** — TORVIS stays primary; do not rename again unless he picks one.

Icon: **logo v2.5** — same as v2 (gold helmet, cyan TORVIS text, friendly eyes, dark navy, HUD rings, sound-wave, shield/lock for ethical security), just a small smile under TORVIS and a little more glow (`icon.png` 512x512, `icon.ico` 16–256px, made from `media-generation-torvis-logo-v2-5-0-b76ed8b8-fd1f-4cb7-a680-ea5083cf1e49.png`). v3 (wings/panels) was rejected — too much. Do NOT use v3. **Note: Faizan later said "nope" to the v2.5 logo too — the icon is UNDECIDED. Do not change icon.png/icon.ico until he picks a version.**

## BUILD 19 — full autopilot (no-confirm, opt-in), YouTube autopilot, channel niche, site watcher, multilingual voice, human-like speaking (2026-11-23)

Faizan's explicit request: TORVIS must not ask for confirmation before doing things — not only YouTube, for ALL things. Implemented as an explicit opt-in, so the default product is still safe, but when Faizan turns it on it really does not ask.

- **Full autopilot — OFF by default, only Faizan turns it on in Settings** (`autopilot_enabled`): when ON, TORVIS does NOT ask for confirm before doing things on his own PC / his own accounts — installs from official sources only, YouTube and other own-account posts/uploads, Kali VM commands, file operations in the H: drive, site actions. When OFF, every old confirm gate stays exactly as before. Tools: `autopilot_status` / `enable_autopilot`. Voice: "turn autopilot on". HUD: AUTOPILOT chip + Settings toggle.
- **YouTube autopilot — OFF by default** (`youtube_autopilot_enabled`): when ON, YouTube uploads/posts need no confirm. When OFF, the old two-step YouTube confirm stays — unless full autopilot is ON, which also covers YouTube. Tools: `enable_youtube_autopilot`, `youtube_autopilot_post` (caption + hashtags + upload in one go, video must be on the H: drive).
- **HARD LIMITS — even in autopilot, and autopilot never overrides them:** protected list (never touch protected files — skip only that item, say so, continue); own stuff only (never scan/hack/access anyone else's system, network, account or website without their written permission); NEVER auto-pay for anything; NEVER auto-delete files outside the H: drive without a separate explicit instruction naming that exact file in that moment. Installs in autopilot are official sources only — an unknown installer file still asks for confirm, even on autopilot.
- **Channel niche — real data only**: `analyze_youtube_channel` reads HIS channel's videos/views/likes via the official YouTube Data API v3 (OAuth only, never a password) and recommends the best niche for HIS channel, with the numbers shown. Not connected → plain "YouTube not connected yet" + OAuth setup steps, never invented data. `make_youtube_caption` builds a caption + best hashtags from a title/topic and his best-performing topics.
- **Site watcher**: `SiteWatcher` watches his sites (default: his Whop store https://whop.com/zero-to-first-dollar-online-2d4f/ and his roofing site https://summit-roofing-co-denver-2.whop.site, from `H:\JARVIS-Work\watched-sites.txt`, one URL per line) every 30 minutes while TORVIS runs, and notifies him (voice + Task Log) when a site goes down / comes back up / changes. Checking is read-only and never needs a confirm. Tools: `watch_site` / `list_watched_sites` / `site_status`.
- **Meeting alerts — no confirm, ever**: an alert is a notification, not an action. TORVIS tells you 15 minutes before a meeting from your connected Google Calendar, in autopilot or not.
- **Multilingual voice — pronunciation in Urdu and any other language, not just English**: TORVIS detects the language of EACH reply (Urdu, Roman Urdu, English, Hindi, Punjabi, Arabic, Bengali, French, Spanish, German, Turkish, Russian, Chinese, Greek) and speaks it with the matching native neural voice when one is installed on Windows — ur-PK for Urdu/Roman Urdu, en-GB/en-US for English, matching locale for the rest. If that locale is not installed, it falls back to the default voice and says so plainly — it never forces an English voice on Urdu text. Settings voice-per-language list (`voice_per_language`, e.g. Urdu → "Microsoft Asad Online (Natural)"). Tool: `pronunciation_status` lists which language voices are actually installed.
- **Human-like speaking — sound like a person, not a robot**: short natural sentences (1–3 at a time), natural pauses, no robotic filler ("let me check…", "as an AI…"), never reads code or a URL aloud, warm tone matching the conversation (questions lift, good news brightens, apologies soften), and speech that can be interrupted at any time (STOP SPEAKING / fist gesture / barge-in). **Hard rule: TORVIS must NOT claim to be human, and must NOT hide that it is TORVIS when asked directly** — asked "are you human?", it answers plainly: it is TORVIS, an AI assistant that tries to sound natural.
- **Honest limits (Linux-tested only):** autopilot confirm-skipping, YouTube API calls, site checks, voice picking and the human-like cleanup were verified with fake states/APIs/voices on Linux, **not** on real Windows — the first real test is on his PC. YouTube needs the one-time OAuth setup; a real neural ur-PK voice needs to be installed in Windows Settings > Time & language > Language.

## How to test BUILD 19 (on your PC)

1. **Autopilot OFF (default)**: say "upload this video to YouTube" — TORVIS must show the plan and wait for "confirm". Say "turn autopilot on" — now the same upload must go ahead with no confirm. Say "turn autopilot off" — the confirm gate must be back.
2. **Hard limits in autopilot**: with autopilot ON, ask it to delete a file outside H: (it must still ask), to pay for something (it must refuse/ask), or to scan someone else's PC (it must refuse plainly).
3. **YouTube**: Settings → turn YouTube autopilot ON, then "post this video" with a video on H: — caption + hashtags + upload in one go, no confirm. Turn it OFF — confirm is asked again.
4. **Channel niche**: say "analyse my YouTube channel" — it must name the best niche with real view numbers, or say plainly "YouTube not connected yet" if OAuth is not set up.
5. **Sites**: say "site status" — it must check the Whop store and roofing site and report up/down/changed. Say "watch https://example.com" — it must add it.
6. **Voice**: say something in Roman Urdu ("mujhe batao…") — it must answer in Roman Urdu with a ur-PK voice if one is installed, and say plainly if none is installed. Say something in French/Spanish — same, with the matching voice. Ask "are you human?" — it must say it is TORVIS, an AI assistant.
7. **Meetings**: with Google Calendar connected, a meeting starting in 15 minutes must be announced with no confirm asked.

## BUILD 18 — clap wake, gesture control, HUD mode, taskbar + tray (2026-11-23)

Faizan watched a Fatih Makes (@fatihmakes) TikTok demo and asked for the same kind of features in TORVIS. This is an **original build — no Fatih Makes code was copied** (his Mark 59 / Mark 58 are paid releases).

- **Clap wake — OFF by default**: two sharp claps close together wake TORVIS and switch on the HUD. One clap never wakes, and normal speech never wakes (sustained loud sound is ignored). Sensitivity in Settings (0.1–1.0). No microphone → TORVIS says so plainly. Tools: `clap_wake_status` / `enable_clap_wake`. Voice: "turn clap wake on".
- **Hand-gesture control — OFF by default, needs the camera on** (BUILD 17, local only, never streamed, no face recognition): open palm = wake / show HUD, swipe right = next, swipe left = previous, pinch = select / confirm, fist = stop speaking. MediaPipe when installed, otherwise a simple OpenCV hand-contour fallback (open palm / fist); no camera or backend → TORVIS says so plainly and never guesses. On-screen gesture indicator in the HUD. Tools: `gesture_status` / `enable_gestures`. Voice: "turn gestures on".
- **HUD mode**: switches the normal view to the full animated TORVIS HUD (BUILD 17 rotating rings / pulsing orb) on a clap, a gesture, or a wake word, and back on "hud mode off" / "normal mode". Tools: `hud_mode_on` / `hud_mode_off`.
- **Taskbar + tray minimise — Faizan's explicit request**: minimising now stays in the Windows taskbar AND in the system tray — it does NOT hide to tray-only. Clicking the taskbar icon restores the window directly, no need to go to the tray first. The tray icon is still there, right-click menu is Show / Hide / Quit. Closing the window still hides to the tray (Quit is the only real exit).
- **3D printer — hook only**: Faizan has not confirmed he has a printer. `printer_status` says plainly "No 3D printer connected" unless an OctoPrint URL is set in Settings; printer control refuses plainly without a configured printer. No full printer driver, no invented printer.
- **Honest limits (Linux-tested only):** clap detection, gesture classification, HUD-mode switching and the minimise behaviour were verified with fake mic levels / landmarks / windows on Linux, **not** on real Windows — the first real test is on his PC. MediaPipe is optional (not in `requirements.txt` — gestures fall back to OpenCV); if he wants the full MediaPipe tracking, install `mediapipe` on his PC.

## How to test BUILD 18 (on your PC)

1. **Minimise**: click the — button (or the taskbar minimise). TORVIS must stay in the taskbar — click its taskbar icon and it comes straight back, no tray needed. The tray icon must still be there, right-click → Show / Hide / Quit.
2. **Clap wake**: Settings → turn clap wake ON, then clap twice, sharply, about half a second apart — the HUD must switch on. Clap once only, or talk normally, and nothing must happen.
3. **Gestures**: turn the camera on, then turn gestures on. Open palm → HUD shows; swipe right → next; pinch → select; fist → TORVIS stops speaking.
4. **HUD mode**: say "show the hud" — the full animated HUD; say "normal mode" — back to normal.
5. **Printer**: say "printer status" — it must say "No 3D printer connected" plainly (he has no printer set up yet).

## BUILD 17 HUD — redesigned to match Faizan's pic (torvis.PNG)

Faizan sent a pic of the interface he wants: dark navy, one large central circle of thin cyan/green rings, a glowing blue orb in the middle, small white "J.A.R.V.I.S." letters across the middle — clean and minimal, no side panels, no clutter. `jarvis-hud.html` was redesigned to match it exactly in style, as **T.O.R.V.I.S.**:

- **Dark navy background** (`#020814`), no heavy panels, no grid/scanlines, no 3D background.
- **One large central circular HUD**: concentric thin cyan/green rings (SVG, slowly rotating dashed arcs), a glowing blue orb in the middle that pulses and breathes with the live voice level, and small white **T.O.R.V.I.S.** letters across the middle.
- **Top bar, slim**: small T.O.R.V.I.S. wordmark, clock/date, and chips — SCREEN WATCH, **CAMERA: OFF** (red when on), FILES, LOG — plus Settings, Minimize, voice and STOP SPEAKING buttons.
- **Side panels are on-demand drawers now** (FILES / LOG chips open them as overlays) — the file explorer and task log still work exactly as before, they are just hidden by default so the circle is the whole screen. CPU/RAM/DISK gauges are hidden too; the same numbers live in one small line under the orb.
- **Camera preview**: a small circular video inset on the ring, shown only while the camera is on, with a red **● CAMERA: ON** indicator above the orb. Camera controls live in Settings too (toggle + TEST CAMERA + status line). The HUD calls `native_camera` / `native_take_photo` / `native_describe_camera` / `native_test_camera` when the exe provides them, and falls back to a browser `getUserMedia` preview in the demo.
- **Kept, unchanged in behaviour**: TEST VOICE, STOP SPEAKING, Settings (brain/model/API key, voice picker, calendar status), voice status, wake word, screen watch, command bar, waveform, boot sequence. Also fixed in passing: the browser-demo wake-word listener only heard "jarvis" — it now hears **"Torvis"** first (Jarvis stays a legacy alias). The 3D reactor/background canvases stay in the DOM (hidden) so the existing Three.js scripts never break; the visible orb is pure CSS/SVG.
- **Mock**: `torvis-hud-mock.png` in this folder shows the new look. It is a **mock, not a live screenshot** — a real screenshot was not possible on this Linux VM (the available Chromium build refuses to start without a Hatch WebGL domain policy file, and its headless `--screenshot`/`--dump-dom` produced no output). Verify the real look by opening `jarvis-hud.html` in a browser on your PC.
- **Camera wiring — DONE in BUILD 17**: `jarvis_build17.py` is now wired into `jarvis.py` (JsApi natives `native_camera` / `native_take_photo` / `native_describe_camera` / `native_test_camera`, `camera_enabled` config default OFF, photo save to `H:\JARVIS-Work\Photos\` only, two-step recording confirm, no-camera fallback, `[SELF-CHECK]` camera line) and `backend.py` (tools `camera_status` / `camera_on` / `camera_off` / `test_camera` / `take_photo` / `describe_camera` / `record_camera_video` / `stop_camera_recording`, plus the camera rule in the system prompt). Voice commands ("turn camera on", "take my photo", "what do you see?", "test camera") are handled locally in `jarvis.py` and never sent to the brain as chat. OpenCV is now in `requirements.txt` (`opencv-python-headless`) with a `cv2` hidden import in the build workflow — the earlier claim that it was already there was wrong and is fixed.
- **Animated HUD — CONFIRMED, not a static image**: the circle background moves continuously while the HUD is open — the three dashed rings rotate at different speeds and directions (70s forward, 50s reverse, 24s fast), a bright scan arc sweeps around the rings every 12s, and the blue orb pulses every 3.2s and breathes with the live voice level (JS scales it from the mic/speech volume each frame). Nothing in the file disables the animation (no reduced-motion media query, no paused play-state); only the hidden 3D background canvas pauses when the tab is hidden — the visible CSS orb never does. Covered by tests in `tests/test_build17.py` (keyframes, classes, scan arc, voice-level scaling).
- **Kali VM typing — DONE in BUILD 17**: TORVIS can type commands while Faizan is using Kali in a VM. Tools: `focus_kali_vm` (find/focus the VirtualBox/VMware Kali window by title, plain message if not found/running), `type_in_kali` (type a command + Enter, two-step with a spoken confirm first), `run_kali_command` + `confirm_kali_command` (show the exact command, wait for "confirm", then focus the VM + type it + Enter). Safety: only types into the Kali VM window it just focused, never into other windows; never runs a command against any target except his own PC/network (localhost, private LAN) or a target on his written authorisation list (`H:\JARVIS-Work\authorised-targets.txt`, one per line) — unauthorised targets are refused plainly. Every typed command is logged to `jarvis.log` with a `[KALI]` prefix. If pyautogui is missing, it says so plainly.

## How to test BUILD 17 (on your PC)

**Camera:**
1. Open TORVIS, say "turn camera on" — the HUD must show the red CAMERA: ON chip and the Task Log a `[SELF-CHECK] Camera` line. If no camera is found, it must say "No camera found" plainly — never a fake feed.
2. Say "take my photo" — the photo must appear in `H:\JARVIS-Work\Photos\` as `torvis-photo-YYYYMMDD-HHMMSS.jpg`, nowhere else.
3. Say "what do you see?" — it describes the scene in plain words, never names a person.
4. Say "record a video" — it must show the plan and wait; say "confirm" — only then does it record (max 60 seconds).
5. Say "turn camera off" — the chip goes off and the preview closes.

**Animated HUD:** open the HUD and watch the circle for 15 seconds — the rings must keep rotating (different speeds/directions), the scan arc must sweep around, and the orb must pulse and grow slightly while TORVIS is speaking. It is never a static image.

**Kali VM typing:**
1. Open Kali in VirtualBox/VMware and click its terminal once so it is the focused window inside the VM.
2. Say "Torvis, type nmap -sn 192.168.1.0/24 in Kali" — TORVIS must show the exact command and wait; say "confirm" — only then does it focus the Kali window, type the command, and press Enter. Check `jarvis.log` — the command must be there with a `[KALI]` prefix.
3. Say "run nmap -sV 8.8.8.8 in Kali" — it must refuse plainly (not your own network, not authorised). To allow a target you have written permission for, add it on its own line to `H:\JARVIS-Work\authorised-targets.txt` first.
4. Close the Kali VM and ask again — it must say it could not find the Kali window and type nothing anywhere.

**Honest limits (Linux-tested only):** the camera, OpenCV capture, pyautogui typing, and VM window focusing were verified with fake cameras/windows on Linux, **not** on real Windows — the first real test is the list above on your PC. Video recording needs OpenCV on Windows (now in `requirements.txt`, so the GitHub build includes it); if it is missing, TORVIS says so plainly. The HUD mock (`torvis-hud-mock.png`) is a mock, not a live screenshot.

**BUILD 16 (2026-11-21) — TORVIS: WORLD-BEST VOICE, LOW LATENCY, BARGE-IN, NEURAL TONE, ACCURATE LISTENING, MEMORY, CALENDAR BOOKING, GUARDRAILS, PRIVACY LOCAL-ONLY, OBSERVABILITY, ETHICAL SECURITY.** Personal assistant for Faizan on his own Windows PC — NOT customer support or sales. Audited against the world-best voice-agent checklist (Retell / Stream / Mastra / Rasa). No paid APIs anywhere.

## BUILD 16 — the full checklist

| # | Item | Status |
|---|---|---|
| LATENCY | First chunk spoken immediately (first sentence/clause), short replies, no filler; latency to first spoken word logged in HUD + Task Log, target 800 ms, with a latency check | DONE |
| LATENCY | Honest limit: the free Mistral brain itself takes seconds — sub-second *brain* latency is NOT claimed; only the first spoken chunk is instant | DONE (stated in code + README) |
| BARGE-IN | Interrupt mid-sentence (STOP SPEAKING / "stop speaking"), stops at once; pause threshold setting (default 0.8s) so short thinking pauses do not cut you off; listening sensitivity setting | DONE |
| TONE | Expressive speech — warmth, urgency, apology, excitement, calm, question lift; small rate/pitch shifts only, never a cartoon voice | DONE |
| LISTENING | High-accuracy listening — accents, noise, fast speech, Roman Urdu + English code-switching; Windows built-in recognition where available, NO paid STT; if speech is unclear, say so and ask to repeat once — never guess | DONE |
| MEMORY | Full chat memory (BUILD 15 kept) + preference learning — "I like short replies" / "reply in Roman Urdu" is remembered | DONE |
| TOOLS | Calendar booking WITH a spoken confirm gate (two-step: `book_meeting` then `confirm_meeting`) | DONE |
| TOOLS | "Check my status" briefing — calendar + reminders + open tasks + Gmail unread + last work, in one go | DONE |
| GUARDRAILS | No hallucination on sensitive facts — "I don't know" + check the source, never guess; protected list + confirm gates kept | DONE |
| GUARDRAILS | Clean handoff to Muse — `handoff_to_muse` saves full context to TASK-STATUS.md in H:\JARVIS-Work\ | DONE |
| STABILITY | Every voice/speech failure falls back and logs, never crashes; one [SELF-CHECK] block at startup (voice, brain, memory, calendar, Gmail, listening, privacy) | DONE |
| PRIVACY | Voice, transcripts, memory, tokens stay LOCAL (H: / %APPDATA%); only brain text leaves the PC (Mistral/Gemini); no cloud recording — Privacy note in Settings/README | DONE |
| OBSERVABILITY | Transcripts, latency, task completion, failures in jarvis.log + daily stats view + "Voice Quality" report command (`voice_quality_report`) | DONE |
| SECURITY | Ethical security mode — authorised-only checks on YOUR OWN PC/network: open ports on your own PC, weak passwords in your own H: files (confirm first, passwords never shown), scan your own H: drive files, explain security risks. Rule in code + README: never scan, access, or attack anyone else's system without their written permission; refuse unauthorised hacking. Tools: `security_check_ports`, `security_check_passwords`, `security_scan_h_drive`, `explain_security_risk` | DONE |
| RENAME | TORVIS primary name — HUD title, wake word, Settings marker, README, icon v2.5, voice greeting ("Hello, Sir. This is TORVIS…") | DONE |

**Honest limits (Linux-tested only):** all tests pass except the 7 pre-existing failures (see Tests below); the neural voice, real Windows SAPI/WebView2 speech, real Google Calendar/Gmail OAuth, pyautogui type/click, and real open-port scanning were verified with fake engines/data on Linux, **not** on real Windows/Google. The first real test is on your PC: Settings → TEST VOICE, then ask two questions in a row and check both are spoken, then ask "what were we working on?" after a restart, and "check my status".

## How to test BUILD 16 (on your PC)

1. Say "Torvis" — it must answer. Say "Jarvis" once — it must still answer (legacy alias, one build only).
2. Ask two questions in a row — both must be spoken, first sentence straight away.
3. Interrupt it mid-sentence with STOP SPEAKING — it must stop at once.
4. Say "check my status" — one briefing: today's meetings, reminders, tasks, Gmail unread, last work.
5. Say "book a meeting with Ali tomorrow at 3pm" — it must show the plan and wait; say "confirm" — only then is it booked.
6. Say "check the open ports on my PC" — it must list them; ask it to scan someone else's PC — it must refuse plainly.
7. Say "give me a voice quality report" — it must show replies spoken fully, average latency, tasks done/failed.

## BUILD 15 — history (kept in BUILD 16)

**BUILD 15 (2026-11-21) — FULL CHAT MEMORY, GOOGLE CALENDAR, NEURAL VOICE, LOW LATENCY, NEVER SILENT, NO GROQ, NO OLLAMA, MISTRAL MAIN, GEMINI LITE FALLBACK.** The complete best/perfect version — every item Faizan asked for is either DONE, or HOOK-ONLY (needs his one-time setup, with a plain message saying what). Nothing was silently skipped. No paid APIs anywhere.

## BUILD 15 — the full checklist

| # | Item | Status |
|---|---|---|
| VOICE | Human-like neural voice first — Microsoft Ryan / Guy / Aria Online (Natural), free, built into Windows/Edge | DONE |
| VOICE | Voice picker in Settings (voice_name) + voice pitch (voice_pitch, 1.0 = natural) | DONE |
| VOICE | Natural speed/pitch/pauses — rate 1.0, pitch 1.0, tone shifts a little by sentence type (question lifts, good news brightens, apology softens) | DONE |
| VOICE | Emotion in tone (small rate/pitch shifts, never a cartoon voice) | DONE |
| VOICE | English + Roman Urdu + Urdu script — replies in the mix you used, ur-PK voice when offered | DONE |
| VOICE | Wake word "Torvis" (also "Hey Torvis"; "Jarvis" legacy alias for one build, "Nova" still works), works minimized | DONE (BUILD 16) |
| VOICE | Barge-in interrupt — STOP SPEAKING button / "stop speaking" | DONE |
| VOICE | Never silent, FIFO queue, never drops a reply, never repeats itself (duplicate guard) | DONE |
| VOICE | TEST VOICE button in Settings | DONE |
| VOICE | Fallback chain: HUD neural voice → pyttsx3 backup → plain text, never silence | DONE |
| VOICE | Latency to first spoken word logged — Task Log `[VOICE-QUALITY]` line: engine, latency ms, last reply fully spoken yes/no | DONE |
| BRAIN | Fast streaming replies — first sentence spoken immediately, rest queued after | DONE |
| BRAIN | Short natural sentences by default (1–3), no filler ("let me check" stripped), no repeating | DONE |
| BRAIN | No false refusals — if you state a lawful purpose JARVIS acts; if genuinely unclear it asks ONE clarifying question instead of blocking | DONE |
| BRAIN | Remembers full chat history + facts + tasks + files, learns preferences (`learn_preference`) | DONE |
| MEMORY | Full chat history saved/loaded/summarised — `jarvis-chat-history.json`, last 12 turns into the brain, older chats collapse into a rolling summary | DONE |
| MEMORY | Last-task recall — ask "what were we working on?" / tool `what_were_we_working_on` | DONE |
| MEMORY | TASK-STATUS resume behaviour | DONE (unchanged) |
| PROACTIVE | Morning briefing on open — date, today's meetings, reminders, last work | DONE |
| PROACTIVE | Meeting alert 15 min before a meeting starts (spoken + HUD, once each) | DONE |
| PROACTIVE | Reminders ("remind me in 10 minutes / at 9:30 / tomorrow at 8 am") | DONE |
| PROACTIVE | Daily summary — what we talked about, open tasks, today's meetings | DONE |
| CALENDAR | Google Calendar read-only via official OAuth — today's schedule, next meeting, "you have a meeting at 3pm" | DONE (code) / HOOK-ONLY (needs his one-time Google setup below) |
| CALENDAR | Plain "Calendar not connected yet — connect it in Settings" if not set up — never invents meetings | DONE |
| CALENDAR | Meeting creation — NOT in BUILD 15 (read-only on purpose; creation with a confirm gate is a later build) | NOT IN THIS BUILD |
| PC CONTROL | Open apps (allow-list only, never a path) | DONE |
| PC CONTROL | Open/search files in H: drive only (`search_h_drive`) — never C: | DONE |
| PC CONTROL | Download (official sources), screenshot / Screen Watch on request | DONE (unchanged) |
| PC CONTROL | Type/click — pyautogui is now in requirements.txt, so it works on Windows; if missing, a plain message says so | DONE / HOOK-ONLY if pyautogui missing |
| PC CONTROL | Volume up/down/mute (media keys, pyautogui) — plain message if missing | DONE |
| PC CONTROL | Brightness — HOOK-ONLY: no safe free cross-laptop method in this build; JARVIS says so plainly if asked | HOOK-ONLY |
| ACCOUNTS | Gmail read — official Google API, read-only, OAuth only, never a password | DONE (code) / HOOK-ONLY (needs his one-time Google setup) |
| ACCOUNTS | YouTube upload — official API, OAuth, confirm gate, privacy private | DONE (unchanged) |
| ACCOUNTS | Google Calendar — official API, read-only, OAuth only | DONE (code) / HOOK-ONLY (setup below) |
| SAFETY | Protected list, confirm gates for installs/posts/deletes/payments, H: drive only never C: | DONE (unchanged) |
| SAFETY | No errors — human messages, not raw error walls; self-check on startup; Task Log for everything | DONE |
| UI | Clean HUD, STOP SPEAKING + TEST VOICE buttons, tray, Settings showing BUILD 15 + voice/memory/calendar status | DONE |

**Honest limits (Linux-tested only):** all 249 unit tests pass except the 7 pre-existing failures (see Tests below); the neural voice, real Windows SAPI/WebView2 speech, real Google Calendar/Gmail OAuth, and pyautogui type/click were verified with fake engines/data on Linux, **not** on real Windows/Google. The first real test is on your PC: Settings → TEST VOICE, then ask two questions in a row and check both are spoken, then ask "what were we working on?" after a restart.

## How to test BUILD 15 (on your PC)

1. Ask two questions in a row — both must be spoken, in a natural voice, with no long pause.
2. Say "remember this: my shop is in Lahore" — then restart TORVIS and ask "what were we working on?" — it must answer from saved chat history without you re-explaining.
3. Say "what's my schedule today?" — before Google setup it must say plainly "Calendar not connected yet", and never invent a meeting.
4. After Google setup (below), ask the same — it must list today's real meetings with times.
5. Check the Task Log: it must show `[SELF-CHECK]` lines for chat memory, calendar, Gmail, and `[VOICE-QUALITY]` with engine + latency + fully spoken.

## Google Calendar + Gmail setup (one time, free, OAuth only)

No password is ever typed into JARVIS. You do this once, in your own browser:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project (any name, e.g. "JARVIS").
2. APIs & Services → Library → enable **Google Calendar API** and **Gmail API**.
3. APIs & Services → Credentials → Create Credentials → **OAuth client ID** → Application type **Desktop app** → Create.
4. Download the JSON (Download button) and save it as `%APPDATA%\NovaAgent\google-calendar-credentials.json` (the same file is used for Gmail — one file, both services).
5. In TORVIS Settings, the calendar status will now say what is missing. The first time TORVIS reads the calendar or Gmail, it opens Google sign-in in your own browser — sign in once, allow **read-only** calendar + Gmail access. The token is saved locally as `%APPDATA%\NovaAgent\google-calendar-token.json` / `google-gmail-token.json` and never leaves your PC, never goes in chat or the repo.
6. If the Google libraries are missing, JARVIS says so plainly: run `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2` (already in `requirements.txt`, so the GitHub build includes them).

## Build JARVIS.exe (GitHub — the way NOVA was built)

Faizan's repo is the **private** `Faizan399722/rebuild` (BUILD 13 was built there). Upload **all** files from this folder to that repo (replace the old files), including the new `jarvis_build15.py` and `tests/test_build15.py`:
1. In the repo, upload/replace all files from this folder
   (`jarvis.py`, `backend.py`, `jarvis_build14.py`, `jarvis_build15.py`, `jarvis-hud.html`, `requirements.txt`,
   `build.bat`, `icon.ico`, `README.md`; `tests/` optional).
2. ⚠️ **The workflow file must end up at
   `.github/workflows/build-exe.yml`.** GitHub's web upload has a habit
   of flattening it to the repo root, where Actions ignores it. If
   that happens: **Add file → Create new file**, type the path
   `.github/workflows/build-exe.yml`, paste the file's contents,
   commit.
3. Open the **Actions** tab and wait for the green run
   ("Build JARVIS.exe").
4. Download the **JARVIS-exe** artifact from the run page — use
   **Microsoft Edge** (Chrome tends to block the zip as a "dangerous
   file"; in Edge: ⋯ → **Keep** → **Keep anyway**). Delete any older
   JARVIS zips from Downloads first so there's no mix-up.
5. Unzip, **delete the old JARVIS.exe**, run the new **JARVIS.exe**. Windows SmartScreen will warn about an
   unsigned app: **More info → Run anyway**. It's your own build.
6. Check Settings / the HUD top line says **BUILD 15**. Then test the voice: Settings → **TEST VOICE**, then ask two questions in a row — both must be spoken. If Q2 is silent again, send the Task Log lines (they now include `[SELF-CHECK] Voice primary/backup`, `[VOICE-QUALITY]`, and `[SPEAK]` attempts) plus a screenshot.

Prefer building on your own PC? Install Python 3.11+, unzip this
folder, double-click **build.bat** — the exe lands in `dist\`.

### Build on your own PC with auto-py-to-exe (BUILD 19)

1. Install Python 3.12 from python.org (tick **"Add Python to PATH"**).
2. Install auto-py-to-exe: `pip install auto-py-to-exe`, then run `auto-py-to-exe`.
3. In auto-py-to-exe, click **Open Config from JSON** and pick
   `auto-py-to-exe-config.json` from this folder. It fills in everything:
   - **Script Location:** `jarvis.py`
   - **One File** (one `.exe`), **Window Based** (no console window)
   - **Icon:** `icon.ico`, **Name:** `JARVIS`
   - **Additional Files:** `jarvis-hud.html`, `icon.ico`, `icon.png`,
     `backend.py`, `jarvis_build14.py` … `jarvis_build19.py`,
     `requirements.txt` — all to `.` (the exe folder)
   - **Collect All:** `webview`, `pystray`, `pyttsx3`
   - **Hidden Imports:** `pyttsx3.drivers.sapi5`, `speech_recognition`,
     `pyaudio`, `pystray`, `comtypes`, `PIL`, `cv2`, `googleapiclient.discovery`,
     `googleapiclient.http`, `google.oauth2.credentials`, `google_auth_oauthlib.flow`, `pyautogui`,
     plus `backend` and `jarvis_build14` … `jarvis_build19`
4. Click **CONVERT .PY TO .EXE**. The exe lands in the output folder
   (default `output/`), as `JARVIS.exe`.
5. No auto-py-to-exe? Just double-click `build.bat` — it runs the exact
   same build. The exact PyInstaller command both of them represent is:

```bat
python -m PyInstaller --noconfirm --onefile --windowed --name JARVIS --icon icon.ico --add-data "jarvis-hud.html;." --add-data "icon.ico;." --add-data "icon.png;." --add-data "backend.py;." --add-data "jarvis_build14.py;." --add-data "jarvis_build15.py;." --add-data "jarvis_build16.py;." --add-data "jarvis_build17.py;." --add-data "jarvis_build18.py;." --add-data "jarvis_build19.py;." --add-data "requirements.txt;." --collect-all webview --collect-all pystray --collect-all pyttsx3 --hidden-import pyttsx3.drivers.sapi5 --hidden-import speech_recognition --hidden-import pyaudio --hidden-import pystray --hidden-import comtypes --hidden-import PIL --hidden-import cv2 --hidden-import googleapiclient.discovery --hidden-import googleapiclient.http --hidden-import google.oauth2.credentials --hidden-import google_auth_oauthlib.flow --hidden-import pyautogui --hidden-import backend --hidden-import jarvis_build14 --hidden-import jarvis_build15 --hidden-import jarvis_build16 --hidden-import jarvis_build17 --hidden-import jarvis_build18 --hidden-import jarvis_build19 jarvis.py
```

(GitHub Actions and GitLab CI run the exact same Windows command — same `--add-data "file;."` form, same hidden imports. All three routes — `build.bat`, `auto-py-to-exe-config.json`, GitHub, GitLab — build the same exe.)

## BUILD 14 — what it added (all kept in BUILD 15)

Brain unchanged (Mistral main / Gemini Lite fallback, BUILD 12; long tasks still finish — 40 rounds, up to 2 auto-continuations, never "ask me to continue"). What changed:

1. **Voice, fixed properly this time** — the HUD's browser speech (`speechSynthesis`) is now the **primary** voice: every typed reply is spoken by the HUD the moment it arrives, through a FIFO queue, so replies are never cut or dropped. `pyttsx3` is now only the **backup** (wake word, or when the HUD is hidden / speech is unavailable). It spoke on Q1 then went silent on Q2, and BUILD 13's engine reuse did not fix that — so the primary path no longer depends on it. The Python backup still reuses one engine, speaks queued replies in order, and **every** speak attempt/failure is logged to `jarvis.log` as `[SPEAK]`, so a silent reply leaves a trace. **Test it:** Settings → **TEST VOICE**, or the ⏹ **STOP SPEAKING** button in the top bar / Settings to interrupt JARVIS mid-sentence. Check the Task Log after Q2: it must show `[SELF-CHECK] Voice primary: HUD speechSynthesis` and `[SELF-CHECK] Voice backup: pyttsx3 ready`.
2. **Real memory** — `jarvis-memory.json` in `%APPDATA%\NovaAgent\` (same folder as `config.json`) remembers facts and open tasks across restarts and loads them into the brain on startup. Say *"remember this …"* or use the brain tool `remember_this`. `TASK-STATUS.md` resume behaviour is unchanged.
3. **Proactive** — morning briefing at startup (date, due reminders, remembered facts, open tasks) plus reminders: *"remind me in 10 minutes to …"* / *"remind me at 9:30 to …"* / *"remind me tomorrow at 8 am to …"*. Due reminders are spoken and shown in the HUD, once each. Reminders live in `jarvis-reminders.json` next to the memory file.
4. **Faster + interruptible** — the first sentence of a reply is spoken as soon as the reply exists, the rest follows in queue order; press **STOP SPEAKING** (or say "stop speaking") to interrupt.
5. **Roman Urdu / Urdu** — JARVIS detects English, Roman Urdu, Urdu script, or a mix, and replies in the same mix; Urdu replies are spoken with an `ur-PK` voice when Windows offers one.
6. **See and do more on PC** — new brain tools: `open_app` (notepad, calculator, Chrome, Edge, Word, Excel, Settings, Terminal, PowerShell, Spotify, VS Code — allow-list only, never a path), `type_text` and `click_at` (need pyautogui on Windows; coordinates must be given by you). Screenshots already existed. Files JARVIS creates for itself go to `H:\JARVIS-Work\` when that drive exists on your PC, otherwise `~/JARVIS-Computer` — never the C: drive. Install/account-post confirm gates and the Protected List are untouched.

The JARVIS HUD with a real body. The demo HUD (a web page) could only
*pretend*: a browser tab stops listening when it is minimized and can't
look at your screen on a timer. This native edition runs the abilities
as **background services inside the .exe itself**:

- 🎧 **Wake word that works minimized** — say **"Jarvis"** (or "Hey
  Jarvis"; "Nova" still works) and JARVIS answers out loud — *"Yes,
  Sir?"* — then takes your command, even with the window minimized or
  hidden in the system tray. Say *"Jarvis, open downloads"* in one
  breath and it just does it.
- 👁 **Screen Watch that really watches** — while ON, JARVIS glances
  at your screen every interval, asks its vision brain for the single
  best next step, and delivers it by tray popup + voice + HUD log.
  Suggestions are deduped (never the same one twice), a busy/quota-hit
  brain just skips that glance, and **screenshots are never saved to
  disk or logged** — they exist in memory only for the one request.
- ⬇️ **Downloads & installs by voice** — *"Jarvis, download <link>"*
  fetches the file straight to `~/Downloads` (no browser, no
  clicking). *"Jarvis, install <file>"* runs an already-downloaded
  installer silently — after your spoken **"confirm"** (see below).
- 🛡 **The Protected List is still the one law** — files/folders in
  `protected_paths` are never read, opened, moved, deleted, downloaded
  into, or installed from. Refusals are instant and total.
- 🧏 **A calmer, deeper voice** — replies are spoken in a British-male
  JARVIS register when Windows offers one (Ryan/George/Daniel/Arthur,
  then David), at a measured rate (≈165). Spoken replies are kept to
  1–4 sentences; the full text is always on screen.
- 🌌 **A living background** — behind the panels, a slow 3D starfield
  with holographic rings drifts at low opacity. If the frame rate ever
  dips, the background sheds detail *first* so the interface itself
  never stutters — and rendering pauses entirely while hidden.

## Your existing setup carries over

JARVIS reads the **same config file as NOVA**:
`%APPDATA%\NovaAgent\config.json`. Your provider, API keys (Gemini /
Groq), model, fallback brain and protected list are already there — no
re-typing. JARVIS adds its own keys next to them:
`wake_word_enabled` (default **false**), `screen_watch_enabled`
(default **false**), `screen_watch_interval_sec` (default 90, min 30),
`voice_name_contains` (default "" — force a specific voice name) and
`voice_rate` (default 165). NOVA's older `screen_advisor_*` keys are
honoured as an alias.

## Turn the two headline features on

Both are **off by default** (your rule: nothing watches or listens
until you say so):

- **Wake word:** right-click the tray icon → *Wake word: On* — or set
  `"wake_word_enabled": true` in the config and restart.
- **Screen Watch:** click the **SCREEN WATCH** chip in the HUD's top
  bar, use the tray menu, or set `"screen_watch_enabled": true`. The
  chip/tray checkmark always shows the true state.
- **Quit:** closing or minimizing the window only hides JARVIS to the
  tray. *Quit JARVIS* in the tray menu is the only real exit.

## Downloads & installs — the honest limits

- Downloads come from the URL **you** give; prefer official sources
  (the maker's own site). The file name comes from the server/URL, an
  existing file is never overwritten (`name (1).ext` instead), and a
  protected destination is refused.
- Installs are **two-step by your rule**: the first request changes
  nothing — JARVIS states the plan (which installer, which silent
  flags, that system files/settings may change) and waits. Only after
  you say **"confirm"** does it run.
- Silent flags are chosen automatically: `.msi` →
  `msiexec /i … /qn /norestart`; Inno Setup → `/VERYSILENT …`;
  NSIS and most other `.exe` installers → `/S`. The real exit code is
  always reported honestly (0 = success, 3010 = success + restart
  needed, 1603 = usually a permissions problem…).
- **UAC:** if Windows shows the admin (UAC) prompt, it appears on the
  secure desktop — *no program can click it for you*. Approve it by
  hand (or it times out) and ask again.
- **GUI-only installers:** a few installers have no silent mode at
  all; they may open their window despite the flags. JARVIS reports
  what actually happened rather than pretending.

## Errors — you will not see them

Every service is wrapped: no tracebacks, no raw JSON error walls.
Failures are written to **`jarvis.log`** (in `%APPDATA%\NovaAgent\`)
and you get **one calm line** in the HUD log instead. Degradation is
graceful: no microphone → wake word turns itself off with one friendly
line and typing keeps working; no API key → one clear instruction;
brain busy/quota/network → the fallback brain or a skipped glance;
TTS engine dead → replies still appear as text; window engine dead →
the HUD opens in your browser while services keep running.
On startup, JARVIS types a **[SELF-CHECK]** report into the HUD log —
config, brain/key, protected list, mic, voice — each green, or with
the exact fix for whatever is missing. It makes **no** model call, so
it never burns quota.

## Files

| File | What it is |
|---|---|
| `jarvis.py` | Native launcher: HUD window, tray, wake listener, screen watcher, TTS, self-check, error log, BUILD 15 chat memory / calendar / neural voice / voice quality, BUILD 16 world-best voice, BUILD 17 camera natives + voice routing, BUILD 18 clap/gesture/HUD-mode natives + taskbar minimise (never tray-only) |
| `jarvis_build14.py` | BUILD 14 pure logic (stdlib only): voice FIFO queue, memory + reminder stores, reminder parsing, morning briefing, language detection, first-sentence streaming, app/type/click helpers |
| `jarvis_build15.py` | BUILD 15 pure logic (stdlib only): full chat history + rolling summary, Google Calendar + Gmail read-only clients (OAuth, lazy imports), neural voice picker, tone, filler strip, duplicate guard, VoiceQualityTracker, meeting alerts, daily summary, H: drive search, volume hook |
| `jarvis_build17.py` | BUILD 17 pure logic (stdlib only): camera state + probe/capture/photo/describe/recording (two-step), Kali VM focus/type/confirm + target authorisation + [KALI] logging, camera self-check line |
| `jarvis_build18.py` | BUILD 18 pure logic (stdlib only): double-clap detector (never speech), clap-wake state + sensitivity, gesture classification (MediaPipe landmarks + OpenCV finger-count fallback, cooldown), HUD-mode switch, taskbar+tray minimise/close/restore behaviour, 3D-printer hook (stub only, never invents a printer), BUILD 18 self-check lines |
| `jarvis_build19.py` | BUILD 19 pure logic (stdlib only): master autopilot + YouTube autopilot (both OFF by default, hard limits never overridden), channel niche analysis from real video data, caption + hashtags, site watcher (30-minute, read-only), multilingual voice (language detection per reply + matching native voice, ur-PK for Urdu, plain fallback), human-like speaking (strip robotic filler, never read code/URLs aloud, short natural sentences, warm tone, never claims to be human), BUILD 19 self-check lines |
| `backend.py` | The brain (from NOVA, JARVIS wake words added): chat + tools, protected-paths, downloads/installs, vision, quota/transient policies, BUILD 15 tools (`recall_last_chat`, `what_were_we_working_on`, `todays_schedule`, `next_meeting`, `calendar_status`, `daily_summary`, `learn_preference`, `search_h_drive`, `set_volume`, `read_gmail`, `gmail_status`) plus all BUILD 14 tools, BUILD 17 camera + Kali tools, BUILD 18 tools (`clap_wake_status`, `enable_clap_wake`, `gesture_status`, `enable_gestures`, `hud_mode_on`, `hud_mode_off`, `printer_status`), BUILD 19 tools (`autopilot_status`, `enable_autopilot`, `enable_youtube_autopilot`, `analyze_youtube_channel`, `make_youtube_caption`, `youtube_autopilot_post`, `watch_site`, `list_watched_sites`, `site_status`, `pronunciation_status`) — YouTube upload and installs skip their confirm only in autopilot, and only for official-source installers |
| `jarvis-hud.html` | The HUD face — BUILD 17 circular T.O.R.V.I.S. HUD (animated rings + scan arc + pulsing orb, camera chip + preview, on-demand drawers), BUILD 18 clap/gesture/HUD-mode chips + gesture indicator + Settings toggles (clap sensitivity, OctoPrint URL) + minimise-to-taskbar button, BUILD 19 autopilot chip + Settings toggles (master + YouTube autopilot, voice-per-language, watched sites, pronunciation check), multilingual voice picking per reply and human-like speaking cleanup, plus a native bridge that activates only inside this shell; BUILD 15: neural voice picker (Ryan/Guy/Aria Online Natural), natural rate/pitch + tone, voice-quality log, Settings voice picker + calendar/Gmail status |
| `tests/` | Run `python3 -m pytest tests/` — **514 passed, 0 failed** (2026-11-23). The 8 failures from BUILD 17/18 are fixed, not skipped: 7 were one real bug — `load_config()`/`save_config()` used a config path frozen at import time, so the full suite read a deleted temp folder; they now resolve `%APPDATA%` at call time. The 8th (`test_todays_schedule_with_test_hook`) used a hard-coded 2026-11-21 event date, which correctly stopped matching "today" after that day; the test now builds its event for today. No mic/screen/network needed. New: `tests/test_build19.py` (autopilot on/off, YouTube no-confirm, niche analysis, caption/hashtags, site watcher down/up/change, meeting alert no-confirm, language detection + voice picking, human-like speaking, JsApi natives, backend tools, HUD chips, BUILD 19 marker) |
| `requirements.txt` | pywebview, pystray, SpeechRecognition, pyaudio, pyttsx3, Pillow, pyinstaller, google-api-python-client, google-auth-oauthlib, google-auth-httplib2, pyautogui, opencv-python-headless (BUILD 17 camera, BUILD 18 gesture fallback — MediaPipe is optional, not listed) |
| `build.bat` / `.github/workflows/build-exe.yml` / `.gitlab-ci.yml` | Local / GitHub / GitLab builds of JARVIS.exe — all run the same PyInstaller command |
| `auto-py-to-exe-config.json` | auto-py-to-exe config for the same build: open it in auto-py-to-exe (Open Config from JSON), then CONVERT — One File, Windowed, icon.ico, all data files and hidden imports included |

## Honest notes

- Screen Watch sends each glance (a screenshot) to your **configured
  cloud brain** while ON — that's how it sees. A vision-capable local
  **Ollama** model keeps screenshots on your PC entirely.
- The wake word needs a **working microphone**; with none present it
  stays off and tells you once, plainly.
- Voice *recognition* uses the free Google speech service (via
  SpeechRecognition), so wake commands need internet; a fully offline
  recognizer is a possible future upgrade.
- Everything here is code-verified and unit-tested, but the real
  Windows test — your mic, your voices, WebView2, your screen — only
  happens on your PC. If anything misbehaves, `jarvis.log` has the
  details; send a screenshot as usual.
