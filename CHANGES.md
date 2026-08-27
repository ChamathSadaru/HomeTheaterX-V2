# Samsung HT-F4B3 Audioscape Controller — Update Notes

## New files
- `notifier.py` — sends **native Windows toast notifications** (Action Center), with
  automatic fallback across `winotify` → `win11toast` → `plyer`, rate-limited so repeated
  triggers (e.g. hammering the locked subwoofer slider) don't spam the notification center.
- `startup_manager.py` — registers/unregisters the app in
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` so it can **launch automatically when
  Windows starts** (per-user, no admin rights needed).
- `config_manager.py` — small JSON file (`config.json`, created on first run) that
  **persists settings** across restarts: notifications on/off, launch-on-startup,
  minimize-to-tray-on-close, last selected device, crossover frequency.
- `requirements.txt` — was missing entirely; now lists every dependency including the new
  notification package.

## Feature: Check speakers one by one (solo / isolate)
Click a speaker cabinet icon:
- It glows (amber highlight + scale-up) and plays a test tone.
- Every other channel dims and drops to 0% (mute) — **except the subwoofer**, which is
  hardware-locked to 100% and can't be silenced from software.
- Click the same speaker again → all channels are restored to **exactly the levels they had
  before you started the test** (snapshot taken server-side in `AudioBackend.start_solo`, so
  it's correct even across page reloads).
- Click a different speaker while one is active → isolation just moves to the new speaker;
  the *original* pre-test snapshot is preserved.

Backend: `POST /api/solo/start {channel}`, `POST /api/solo/stop`, status included in
`GET /api/status`.

## Feature: Subwoofer lock + notification
The subwoofer fader was already forced to 100% server-side, but the UI used a `disabled`
`<input>` — **disabled inputs never fire click/drag events in browsers**, so no toast could
ever appear. Fixed by making the real slider `pointer-events:none` and adding a transparent
overlay on top that *does* receive clicks/drags. Clicking it now:
- Shows an in-app toast.
- Calls `POST /api/subwoofer_lock_notice`, which fires a native Windows notification:
  *"Subwoofer volume is fixed at 100%. Use the physical remote control to adjust subwoofer level."*

Also hardened: if anything calls `POST /api/channel_volume` for the subwoofer channel
directly (bypassing the UI), the server now rejects it with `423 Locked` and fires the same
notification, instead of silently overwriting the value.

## Feature: Startup auto-run
Settings tab → **"Launch on Windows Startup"** toggle. Backed by `startup_manager.py`.
Also exposed in the system tray menu as a checkable **"Start with Windows"** item.

## Feature: System tray (enhanced)
- Tray icon now changes glyph (gold → red with an X) when the system is muted.
- Menu: Open Dashboard, Mute/Unmute (dynamic label), Reset Balance, **Start with Windows**
  (checkable), Exit.
- Closing the window (X button) still minimizes to tray, but now also fires a one-time
  native "Still Running" notification so it's obvious the app hasn't quit.

## Feature: Native Windows notifications everywhere
Every state-changing action now fires a native OS toast (in addition to the existing
in-app toast), gated by a single Settings toggle: mute/unmute, reset balance, profile
applied, device changed, speaker isolate started, subwoofer lock attempt, startup setting
changed, minimize-to-tray, app started.

## Backend gaps filled
- **Receiver Console** and **Settings** tabs were "Coming Soon" placeholders even though
  `app.js` already contained fully-wired click handlers for HDMI/Optical/Bluetooth source
  buttons, DSP mode buttons, DRC toggle, and the LFE crossover selector — the HTML markup
  for those elements simply didn't exist. Both views are now built out and functional.
- Settings persistence (`config.json`) — previously every setting reset on each launch.
- `GET /api/settings`, `POST /api/settings/update`, `GET/POST /api/startup/...` endpoints.

## Bug fixes
- **Directory traversal**: static file serving joined the raw request path straight into
  the filesystem path with no containment check. Requests like `/../web_server.py` could
  potentially read files outside `web/`. Now resolves and validates the path stays inside
  `web/`/app root before serving.
- **Server could hang the whole app on one bad request**: `HTTPServer` is single-threaded —
  an unhandled exception in `do_GET`/`do_POST` (e.g. malformed JSON, missing device) could
  wedge the only request-processing thread. Switched to `ThreadingHTTPServer` and wrapped
  both handlers in try/except so one bad request returns a `500` instead of stalling every
  other request (including the UI's 600ms polling).
- **Subwoofer slider couldn't be clicked at all** (see above) — the root cause of the
  requested "click it and get a notification" feature not being possible.
- **Redundant COM writes**: `get_channel_volumes()` unconditionally wrote the subwoofer's
  locked value to the audio driver on *every single poll* (every 600ms) even when nothing
  had changed. Now only writes when the driver's actual value has drifted.
- **Stale solo/isolate snapshot across device switches**: switching output devices
  mid-solo-test would have left a snapshot referencing the old device's channel layout.
  Solo state now resets on `activate_device`.

## Recommended next features (not yet implemented)
- **Custom named profiles** — let users save their own fader arrangement (beyond the
  built-in Movie/Music/Game/Night) with a name, not just the 4 presets.
- **Global hotkeys** (e.g. media-key or Ctrl+Alt+M) to mute/unmute without opening the window.
- **Device hot-plug detection** — background thread that watches for the output device
  disconnecting/reconnecting (e.g. HDMI-ARC drop) and pushes a native notification instead
  of the UI just going stale.
- **Per-channel history/undo** — small ring buffer of recent balance changes with an undo
  button, useful after a solo test if something doesn't restore as expected.
- **Sinhala/English language toggle** for the UI, since usage/testing language mixes both.
- **Auto light/dark or accent-color theme picker** in Settings (currently gold/amber only).
- **Export/import balance profile** as a `.json` file to back up or share a calibration.
- **Basic automated tests** for `audio_backend.py` (mock `pycaw`) and for the HTTP handler
  routing, since there's currently no test suite at all.
- **Packaging**: a PyInstaller `.spec` + build script so this can ship as a single `.exe`
  instead of requiring `python web_server.py` — `startup_manager.py` already detects
  `sys.frozen` and will point the registry entry at the `.exe` once you do this.
