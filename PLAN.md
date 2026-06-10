# Nebula IPTV Desktop — V3 Plan

V3 is a UX redesign on top of V2. Same backend, same libvlc decode, same Xtream + m3u_plus support. The change is **how the user sees and interacts with the app**.

## North star

A **big-TV-screen** look:

- The window's entire client area is the video. No tab bar at the top, no chrome eating screen real-estate.
- Menus (LIVE / Movies / Series / Info / Settings) live as a **translucent panel that slides in from the left** when you ask for it (or hover the left edge), and out when you don't.
- Player controls live as a **bottom overlay** on the video, auto-hide 3 s after the last input — same UX as V2's internal player, but now in the main window itself.
- Switching channels never tears down the video — playback continues while you browse.

```
  +---------------------------------------------+
  |  [ ☰ ]                                -[]X  |   ← top bar (auto-hide)
  |                                             |
  |                                             |
  |                                             |
  |              [   video fills the   ]        |
  |              [   whole window      ]        |
  |                                             |
  |                                             |
  |                                             |
  |       ⏮  ⏯  ⏭     🔊====    CC  ⛶          |   ← bottom controls (auto-hide)
  +---------------------------------------------+

  Hover left edge → slides menu in:

  +----------+----------------------------------+
  |  LIVE    |                                  |
  |  Movies  |                                  |
  |  Series  |     video still plays behind     |
  |  Info    |     translucent menu             |
  |  Settings|                                  |
  |          |                                  |
  +----------+----------------------------------+
```

## Architectural shape

### V2 (today)

```
QMainWindow
└── centralWidget = QTabWidget
    ├── LIVE tab     (QSplitter: category list | channel list | info pane)
    ├── Movies tab   (same shape)
    ├── Series tab   (same shape)
    ├── Info tab
    └── Settings tab
```

Plus a separate `EmbeddedPlayerWindow` (top-level floating window) when the user picks the internal player.

### V3 (target)

```
QMainWindow
└── centralWidget = TVRoot (QWidget, manual layout)
    ├── VideoBackground (QFrame, fills 100% — libvlc sink)
    ├── SlidingMenu (QWidget, left edge, translucent, animated)
    │   └── current QTabWidget content lives in here
    ├── TopBar (QWidget, top edge, translucent, auto-hide)
    │   └── ☰ button, title, window controls
    ├── PlayerControlsOverlay (QWidget, bottom edge, translucent, auto-hide)
    │   └── seek bar, ⏮ ⏯ ⏭ ⏪ ⏩, volume, CC, ⛶
    └── LeftEdgeTrigger (invisible 18 px-wide widget, hover wakes the menu)
```

The libvlc player instance is owned by `TVRoot`, not by a separate window. There's no floating window in V3 — everything is in-window.

## Component contracts

### `TVRoot(QWidget)`
- Holds the libvlc `Instance` + `MediaPlayer`.
- Owns the video frame, menu, top bar, controls overlay, edge trigger.
- `set_playlist(items, current_index)` updates what the menu shows and what ⏮ ⏭ walk.
- `play(url, title, playlist=None, index=0)` switches the stream without reconstructing libvlc.
- Repositions all overlays in `resizeEvent`.

### `SlidingMenu(QWidget)`
- Subclass of QWidget. Hosts the existing tab pages from V2 unchanged — just re-parented.
- `set_open(bool, animated=True)` → animates x-position with QPropertyAnimation (200 ms ease-out cubic).
- Two states: pinned (stays open until user clicks elsewhere) vs auto-hide (closes 2.5 s after mouse leaves).
- Translucent background — opacity ~0.85 with blur if available, plain rgba otherwise.

### `PlayerControlsOverlay(QWidget)`
- Same widget set as V2's `EmbeddedPlayerWindow` bottom bar — seek slider, transport buttons, volume, speed, CC, fullscreen.
- Auto-hides after 3 s of no input. Cursor hides over the video only.
- Reused class lives in `iptv/ui/controls.py`.

### `LeftEdgeTrigger(QWidget)`
- 18 px wide, full height, transparent.
- `enterEvent` opens the menu (unpinned).
- Useful for users who don't know the ☰ button exists.

## Re-parenting strategy

The V2 tab pages (LIVE/Movies/Series/Info/Settings) are already self-contained `QWidget`s with their own layouts. V3 does NOT rewrite them — it puts them inside `SlidingMenu` instead of `QTabWidget`.

`SlidingMenu` itself can show them via a stacked layout + a list of tab-icon buttons on its own left edge. So the user still has tab-style navigation, just inside the sliding panel instead of at the top of the window.

## Phased rollout

1. **Phase 1 — TV root + video background** (PR #1)
   - Add `iptv/ui/tv_root.py` with `TVRoot`.
   - Wire IPTVPlayerApp to use `TVRoot` as central widget instead of `QTabWidget` directly.
   - Tabs continue to live where they are for now — just stacked above the video frame.
   - libvlc renders into the video frame. Existing internal-player code path now plays into the main window.

2. **Phase 2 — Sliding menu** (PR #2)
   - Move the existing QTabWidget into a `SlidingMenu`.
   - Add ☰ toggle, left-edge trigger, slide animation.
   - Translucent background.

3. **Phase 3 — In-window controls overlay** (PR #3)
   - Extract V2's `EmbeddedPlayerWindow` bottom bar into `PlayerControlsOverlay`.
   - Mount it on `TVRoot`. Auto-hide. Keyboard shortcuts.
   - Remove `EmbeddedPlayerWindow` as a separate top-level window.

4. **Phase 4 — Polish** (PR #4+)
   - Fade transitions when switching channels.
   - Settings as a separate slide-from-right panel.
   - Default-mode preference in `userdata.ini`.
   - Optional: picture-in-picture, EPG-over-video, channel preview thumbnails.

## Non-goals

- Not rewriting workers / threadpools — they're fine as-is.
- Not rewriting Xtream-API parsing — fine as-is.
- Not adding new media formats / DRM / live recording — out of scope.
- Not removing the external-player path — TV mode is opt-in via a Settings toggle. Classic mode (V2 layout) is still available.

## Open questions

- **Translucent acrylic background**: `Qt.WA_TranslucentBackground` + `setWindowFlags(Qt.FramelessWindowHint)` gets us the look on Windows, but breaks native window decorations. Worth losing the title bar for the aesthetic?
- **Multi-monitor fullscreen**: keep current behavior (showFullScreen on the current monitor)?
- **Default mode on fresh install**: TV mode or classic? Probably TV mode if libvlc is available, classic otherwise.

## Reference UX

The nebula-iptv browser extension's UX is the closest existing reference for the look-and-feel target. We're using its **visual language** (sidebar trigger, translucent panels, auto-hide controls) but the **decoding stack stays libvlc** — same as V2 — for HD compatibility.
