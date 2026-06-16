# Nebula IPTV Desktop

PyQt5 IPTV player with a **libvlc** decode backend and an opt-in **TV-mode UX** — the video fills the window as the background, and the channel browser slides in as a translucent overlay.

Forked from [V2 of Xtream-m3u_plus-IPTV-Player](https://github.com/Youri666/Xtream-m3u_plus-IPTV-Player). Working repo for the V3 redesign. See [`PLAN.md`](PLAN.md) for the architectural plan.

## Screenshots

| Home | Live TV |
|---|---|
| ![Home screen](screenshots/01-home.png) | ![Live TV browser](screenshots/02-live-tv.png) |

| TV mode — playback | TV mode — sliding playlist |
|---|---|
| ![TV-mode playback](screenshots/03-tv-mode-playback.png) | ![TV-mode with sliding playlist over live video](screenshots/04-tv-mode-playlist.png) |

## Status

| Phase | Status |
|---|---|
| 1. TV root + in-window video background | shipped |
| 2. Sliding translucent menu (hamburger + edge trigger + slide animation) | shipped |
| 3. In-window player controls overlay (seek, transport, volume, fullscreen) | shipped |
| 4. Polish — auto-close menu after channel pick | shipped |

Everything that was in V2 (internal player, bug fixes, theme switcher, Arabic / CP1256 EPG fallback, file logging) is still there. V3 mode is opt-in via Settings → "TV mode".

## Installation

### macOS (pre-built .app)

1. Clone the repo and `cd` into it.
2. Create a Python 3.12 virtualenv and install deps:
   ```bash
   python3.12 -m venv .venv
   .venv/bin/pip install requests "lxml>=5.0" python-dateutil "PyQt5==5.15.9" python-vlc pyinstaller Pillow
   ```
3. Build the `.app` bundle:
   ```bash
   bash build.sh
   ```
4. Copy `dist/NebulaIPTV.app` to `/Applications` and open it.

> **Note:** TV mode (embedded player) requires [VLC](https://www.videolan.org/vlc/) to be installed at the default `/Applications/VLC.app` path. Without it, a warning is shown and playback is unavailable.

### Windows

1. Install Python 3.12 and [VLC](https://www.videolan.org/vlc/).
2. `pip install -r requirements.txt pyinstaller`
3. `build.bat` → produces `dist\NebulaIPTV.exe`

### Linux

1. Install `python3`, `python3-pyqt5`, `vlc`, and `pip install -r requirements.txt pyinstaller`.
2. `bash build.sh` → produces `dist/NebulaIPTV`

### Running from source (all platforms)

```bash
pip install -r requirements.txt   # add python-vlc for embedded player support
python nebula_iptv.py
```

## User data

All settings, saved accounts, cache, and watch history are stored in a platform-appropriate location — never in the app bundle or install directory:

| Platform | Path |
|----------|------|
| macOS    | `~/Library/Application Support/NebulaIPTV/` |
| Windows  | `%APPDATA%\NebulaIPTV\` |
| Linux    | `~/.config/NebulaIPTV/` |

## Debugging

The app runs in windowed mode (no console). To see errors:

**macOS / Linux**
```bash
/Applications/NebulaIPTV.app/Contents/MacOS/NebulaIPTV 2>&1 | tee /tmp/nebula.log
# or from source:
python nebula_iptv.py 2>&1 | tee /tmp/nebula.log
```

**Windows**
```bat
dist\NebulaIPTV.exe > %TEMP%\nebula.log 2>&1
```

Common things to look for in the log:

| Message | Cause | Fix |
|---------|-------|-----|
| `vlc: unknown option … '--foo'` | Invalid VLC arg — `libvlc_new()` returns NULL, player silently fails | Remove the bad arg from `vlc_args` in `tv_root.py` |
| `Cannot load lib specified by PYTHON_VLC_LIB_PATH` | `PYTHON_VLC_LIB_PATH` set without pre-loading `libvlccore` first | Let `_setup_vlc_env()` handle path setup; don't set the env var manually |
| `TV mode needs libvlc installed` | VLC not found at default path | Install VLC or set `PYTHON_VLC_LIB_PATH` / `PYTHON_VLC_MODULE_PATH` |
| `failed item double click: …` | Unhandled exception during channel open | Check the full traceback in the log above that line |

## Layout

### Classic mode (V2, still the default)

```
+----+------------+---------------+
|tabs|  channels  |  info pane    |   <- QTabWidget covering the whole window
+----+------------+---------------+
| progress bar                    |
+---------------------------------+
```

### TV mode (V3)

```
+---------------------------------------------+
|  [ menu ]                              -[]X |
|                                             |
|                                             |
|              [   video fills the   ]        |
|              [   whole window      ]        |
|                                             |
|                                             |
|    <<  <<  pp  >>  >>          vol===   fs  |   <- auto-hide overlay
+---------------------------------------------+

Click the menu button (or hover the left edge) -> menu slides in:

+----------+----------------------------------+
|  LIVE    |                                  |
|  Movies  |                                  |
|  Series  |   video still plays behind       |
|  Info    |   translucent menu               |
|  Settings|                                  |
+----------+----------------------------------+
```

## Keyboard shortcuts (TV view)

| Key | Action |
|---|---|
| `Ctrl+T` | Flip between Classic / TV view |
| `M`      | Toggle the sliding menu |
| `Space`  | Play / pause |
| `Left` / `Right` | Seek +/- 10 s |
| `Up` / `Down`    | Volume |
| Mouse wheel | Volume |
| Middle-click | Pause / resume |
| Double-click | Fullscreen toggle |
| `Esc`    | Exit fullscreen |

## What's planned next

- Slide-from-right Settings overlay (so settings doesn't live inside the menu)
- Picture-in-picture mode
- EPG overlay on top of the video (no need to switch views)
- Channel preview thumbnails in the sliding menu
- A non-frameless variant of TV mode for users who want native window decorations

## License

Inherited from the upstream project — GPL-3.0. See `LICENSE`.
