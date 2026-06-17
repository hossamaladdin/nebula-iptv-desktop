# Nebula IPTV Desktop

PyQt5 IPTV player with a **libvlc** decode backend and a full-screen TV-mode UX — the video fills the window, the channel browser slides in as a translucent overlay, and a Chrome-style Picture-in-Picture mini player lets you watch while browsing.

## Screenshots

| Home | Live TV |
|---|---|
| ![Home screen](screenshots/01-home.png) | ![Live TV browser](screenshots/02-live-tv.png) |

| TV mode — playback | Mini-player (PiP) |
|---|---|
| ![TV-mode playback](screenshots/03-tv-mode-playback.png) | ![Mini-player over live video](screenshots/04-tv-mode-playlist.png) |

## Features

- **Progressive-screens UI** — Home → Browse → Player, each screen slides in full-bleed
- **Mini-player (PiP)** — click 🖼 in the controls bar; video floats in a frameless, always-on-top window
  - Freely draggable; AR-constrained resize from all 8 edges
  - Transparent button overlay (DWM-composited on Windows, Quartz on macOS): 🔊 mute, ⏸ play/pause, ✕ close (top-right)
  - Main window auto-minimizes on enter; stream resumes in full player on close
- **Recently Watched** pseudo-category at the top of Live TV, Movies and Series
- **Progressive loading** — Live TV is browsable as soon as it loads, without waiting for Movies/Series
- **Status bar** — thin diagnostic bar in each browse screen (blue = loading, red = error, grey = info)
- Arabic / CP1256 EPG fallback, file logging, theme switcher (System / Light / Dark)
- Account names preserved (configparser case fix)
- Audio stops cleanly on Back and on window close (no ghost audio)

## Installation

### macOS

1. Install [VLC](https://www.videolan.org/vlc/) at the default `/Applications/VLC.app` path.
2. Clone the repo, create a virtualenv, install deps:
   ```bash
   python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pyinstaller
   ```
3. Build the `.app`:
   ```bash
   bash build.sh
   ```
4. Copy `dist/NebulaIPTV.app` to `/Applications`.

### Windows

1. Install Python 3.12 and [VLC](https://www.videolan.org/vlc/).
2. `pip install -r requirements.txt pyinstaller`
3. `build.bat` → `dist\NebulaIPTV.exe`

> **Note (Windows):** unsigned PyInstaller binaries may be blocked by WDAC / Defender SmartScreen. Right-click → Properties → Unblock, or run from source via `pythonw nebula_iptv.py`.

### Linux

1. Install `python3`, `python3-pyqt5`, `vlc`, then `pip install -r requirements.txt`.
2. `bash build.sh` → `dist/NebulaIPTV`

> **Note (Linux):** the mini-player's transparent overlay requires a compositing window manager (GNOME/KDE with compositor). Without one it falls back to opaque — the player still works, buttons are just on a dark background.

### Running from source (all platforms)

```bash
pip install -r requirements.txt
python nebula_iptv.py
```

## User data

Settings, accounts, cache, favorites and watch history live in a platform-appropriate location:

| Platform | Path |
|----------|------|
| macOS    | `~/Library/Application Support/NebulaIPTV/` |
| Windows  | `%APPDATA%\NebulaIPTV\` |
| Linux    | `~/.config/NebulaIPTV/` |

## Keyboard shortcuts

| Key | Action |
|---|---|
| `Space` | Play / pause |
| `Left` / `Right` | Seek ±10 s |
| `Up` / `Down` | Volume |
| Mouse wheel | Volume |
| Middle-click | Play / pause |
| Double-click | Fullscreen toggle |
| `Esc` | Exit fullscreen |
| `Ctrl+T` | Toggle Classic / TV view |
| `M` | Toggle sliding menu |

## Debugging

**macOS / Linux**
```bash
python nebula_iptv.py 2>&1 | tee /tmp/nebula.log
```

**Windows**
```bat
pythonw nebula_iptv.py   # log written to %APPDATA%\NebulaIPTV\log.txt
```

Common log messages:

| Message | Cause | Fix |
|---------|-------|-----|
| `vlc: unknown option '--foo'` | Invalid VLC arg — player silently fails | Remove bad arg from `vlc_args` in `tv_root.py` |
| `TV mode needs libvlc installed` | VLC not found | Install VLC or set `PYTHON_VLC_LIB_PATH` |
| `failed item double click: …` | Exception during channel open | Check traceback above that line |

## License

GPL-3.0 — inherited from the upstream [Xtream-m3u_plus-IPTV-Player](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player). See `LICENSE`.
