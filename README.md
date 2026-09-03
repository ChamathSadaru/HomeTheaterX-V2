# HomeTheaterX

HomeTheaterX is a Windows desktop controller for multi-channel home-theater audio devices.  
It combines a local HTTP API, WebSocket stream, and a PyWebView desktop UI to manage speaker levels, Dolby state, audio effects, and media controls.

## Highlights

- Device detection and output switching for active speaker devices
- Master + per-channel volume control (optimized for 5.1 layouts)
- Real-time audio peak metering over WebSocket
- Dolby state check/toggle automation
- Audio Processing Object (APO) controls (bass management / 8D)
- System tray controls (open, mute, reset, startup toggle)
- Native Windows toast notifications
- Persistent settings in `config.json`

## Tech Stack

- Python backend (`web_server.py`)
- Local web frontend in `/web`
- PyWebView desktop shell
- Pycaw + COM for Windows audio endpoints
- WebSockets for live sync

## Requirements

- Windows 10/11
- Python 3.10+
- Installed packages from `requirements.txt`

> This project is Windows-specific and depends on Windows audio/COM APIs.

## Setup

1. Open a terminal in the repository root.
2. Create and activate a virtual environment.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

Start the app with:

```bash
python web_server.py
```

When launched, HomeTheaterX starts:

- HTTP API server (default: `http://localhost:5000`, auto-fallback to next ports)
- WebSocket server (default: `ws://localhost:5010`, auto-fallback to next ports)
- Desktop window + tray icon

## Configuration

Runtime settings are stored in `config.json`, including:

- `last_device`
- `launch_on_startup`
- `notifications_enabled`
- calibration and profile settings
- `access_token` for non-local API/WebSocket access

Localhost clients are trusted. External clients must provide the configured access token.

## Project Structure

- `/web` – HTML/CSS/JS frontend assets
- `/services` – backend service modules (API handler, websocket, UI, Dolby/APO/media services)
- `web_server.py` – application entry point
- `audio_backend.py` – core device/volume/meter logic
- `config_manager.py` – persistent settings store

## Build (Optional)

A PyInstaller spec file is included:

```bash
pyinstaller HomeTheaterX.spec
```

## Notes

- This repository currently has no dedicated automated test suite.
- Use at your own risk when changing system audio properties.
