"""TV-mode central widget for V3.

Phase 1 deliverable: a QWidget whose entire client area is a libvlc video sink.
Subsequent phases mount the (now translucent, sliding) menu and the bottom
controls overlay on top of this same widget.

Why a separate module: keeps V2's existing IPTVPlayerApp construction intact —
we only swap in TVRoot when the user enables TV mode in Settings. Classic V2
layout still works for users who want the legacy look.
"""

import sys
import os

from PyQt5.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QColor, QCursor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QStackedLayout, QLabel,
    QPushButton, QGraphicsOpacityEffect, QSlider, QApplication, QMenu, QAction,
    QFileDialog, QMessageBox, QScrollArea,
)


def _setup_vlc_env():
    """Pre-load libvlc (and libvlccore on macOS) from the standard install
    location so python-vlc can find them inside a PyInstaller bundle.

    DO NOT use PYTHON_VLC_LIB_PATH: python-vlc's env-var fast-path skips the
    libvlccore pre-load, causing ctypes to fail with 'Cannot load lib' and
    calling sys.exit(1). Pre-loading via ctypes directly keeps the libraries
    in ctypes' internal cache so python-vlc's normal discovery reuses them.
    """
    import ctypes

    if sys.platform == "darwin":
        base    = "/Applications/VLC.app/Contents/MacOS"
        core    = os.path.join(base, "lib", "libvlccore.dylib")
        lib     = os.path.join(base, "lib", "libvlc.dylib")
        plugins = os.path.join(base, "plugins")
        if not os.path.isfile(lib):
            return
        try:
            if os.path.isfile(core):
                ctypes.CDLL(core)   # must be loaded before libvlc
            ctypes.CDLL(lib)
        except OSError:
            return
        if os.path.isdir(plugins):
            os.environ.setdefault("VLC_PLUGIN_PATH", plugins)

    elif sys.platform.startswith("win"):
        import ctypes.util
        pf   = os.environ.get("ProgramFiles",       r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)",  r"C:\Program Files (x86)")
        for root in (pf, pf86):
            lib = os.path.join(root, "VideoLAN", "VLC", "libvlc.dll")
            if os.path.isfile(lib):
                plugins = os.path.join(os.path.dirname(lib), "plugins")
                # Add VLC dir to DLL search path so Windows finds its deps
                if hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(os.path.dirname(lib))
                try:
                    ctypes.CDLL(lib)
                except OSError:
                    pass
                if os.path.isdir(plugins):
                    os.environ.setdefault("VLC_PLUGIN_PATH", plugins)
                break

    # Linux: libvlc.so is in the system library path via ldconfig — no action needed


_setup_vlc_env()


_SLIDING_MENU_STYLE = """
QWidget#slidingMenu {
    background: rgba(20, 20, 24, 220);
    border-right: 1px solid rgba(255,255,255,30);
}
QPushButton#hamburgerButton {
    background: rgba(40, 40, 44, 200);
    color: white;
    border: none;
    border-radius: 6px;
    font-size: 20px;
    padding: 4px 10px;
}
QPushButton#hamburgerButton:hover { background: rgba(91, 141, 239, 220); }
"""


class _SubHideStrip(QWidget):
    """Draggable opaque black rectangle the user can park over hardcoded /
    burned-in subtitles. Bottom-right resize handle (drag) and a small ✕
    in the top-right to hide.

    Mouse interactions:
    * Drag anywhere on the strip → move
    * Drag the bottom-right 14×14 square → resize
    * Click ✕ → hide
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: black;")
        self.setCursor(Qt.SizeAllCursor)
        self.resize(640, 60)
        self._drag_offset = None
        self._resizing = False
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setStyleSheet(
            "QPushButton { color: white; background: rgba(255,255,255,40); "
            "border: none; border-radius: 8px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(255,80,80,200); }"
        )
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.clicked.connect(self.hide)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.close_btn.move(self.width() - 20, 4)

    def _is_in_resize_corner(self, pos):
        return pos.x() >= self.width() - 14 and pos.y() >= self.height() - 14

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._is_in_resize_corner(event.pos()):
            self._resizing = True
            self._drag_offset = event.pos()
        else:
            self._resizing = False
            self._drag_offset = event.pos()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is None:
            return
        if self._resizing:
            new_w = max(120, event.pos().x())
            new_h = max(24,  event.pos().y())
            # Stay inside the parent's bounds.
            if self.parentWidget() is not None:
                new_w = min(new_w, self.parentWidget().width() - self.x())
                new_h = min(new_h, self.parentWidget().height() - self.y())
            self.resize(new_w, new_h)
        else:
            new_pos = self.mapToParent(event.pos() - self._drag_offset)
            if self.parentWidget() is not None:
                new_pos.setX(max(0, min(new_pos.x(), self.parentWidget().width() - self.width())))
                new_pos.setY(max(0, min(new_pos.y(), self.parentWidget().height() - self.height())))
            self.move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._resizing = False
        event.accept()


_PLAYLIST_PANEL_STYLE = """
QWidget#playlistPanel {
    background: rgba(15, 16, 22, 200);
    border-left: 1px solid rgba(255,255,255,40);
}
QLabel#playlistHeader {
    color: white;
    font-size: 14px;
    font-weight: 600;
    padding: 8px 12px;
    background: rgba(0,0,0,80);
}
QPushButton#playlistRow {
    text-align: left;
    color: rgba(255,255,255,230);
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 12px;
    font-size: 13px;
}
QPushButton#playlistRow:hover {
    background: rgba(91,141,239,60);
    border-left: 3px solid rgba(91,141,239,140);
}
QPushButton#playlistRowCurrent {
    text-align: left;
    color: white;
    background: rgba(91,141,239,90);
    border: none;
    border-left: 3px solid #7c3aed;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
}
"""


_CONTROLS_STYLE = """
QWidget#tvControls {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(0,0,0,60), stop:1 rgba(0,0,0,210));
}
QPushButton#tvCtrlBtn {
    background: transparent;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 16px;
    min-width: 34px;
}
QPushButton#tvCtrlBtn:hover { background: rgba(91, 141, 239, 180); }
QPushButton#tvCtrlBtn:disabled { color: rgba(255,255,255,40); background: transparent; }
QLabel#tvTimeLabel { color: #eee; font-size: 11px; padding: 0 8px; }
QSlider#tvSeek::groove:horizontal { height: 6px; background: rgba(255,255,255,70); border-radius: 3px; }
QSlider#tvSeek::handle:horizontal { background: #7c3aed; width: 14px; margin: -4px 0; border-radius: 7px; }
QSlider#tvSeek::handle:horizontal:hover { background: #9b6dff; }
QSlider#tvSeek::sub-page:horizontal { background: #7c3aed; border-radius: 3px; }
QSlider#tvVol::groove:horizontal  { height: 4px; background: rgba(255,255,255,60); border-radius: 2px; }
QSlider#tvVol::handle:horizontal  { background: #7c3aed; width: 12px; margin: -4px 0; border-radius: 6px; }
QSlider#tvVol::sub-page:horizontal { background: #7c3aed; border-radius: 2px; }
"""


class _ClickableSlider(QSlider):
    """Click-to-position behaviour for the seek bar (same trick as V2)."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.maximum() != self.minimum():
            ratio = max(0.0, min(1.0, event.x() / max(1, self.width())))
            val = self.minimum() + ratio * (self.maximum() - self.minimum())
            self.setValue(int(val))
            self.sliderPressed.emit()
            self.sliderReleased.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _EdgeTrigger(QWidget):
    """Invisible left-edge widget. Emits `entered` when the cursor enters it.
    Lets users summon the sliding menu by sliding their mouse to the left edge.
    """
    entered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(18)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        # Stay invisible — only the parent needs to know we exist.
        self.setStyleSheet("background: transparent;")

    def enterEvent(self, event):
        self.entered.emit()
        super().enterEvent(event)


class SlidingMenu(QWidget):
    """Left-anchored panel that slides in/out with a QPropertyAnimation.

    The host widget (TVRoot) provides this menu the geometry of the area it
    should cover when open. The menu re-parents the existing V2 tab widget so
    we keep the LIVE / Movies / Series / Info / Settings UI unchanged — only
    its container moves.
    """

    def __init__(self, parent=None, width=380):
        super().__init__(parent)
        self.setObjectName("slidingMenu")
        self.setStyleSheet(_SLIDING_MENU_STYLE)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(width)
        self._target_width = width

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        # Translucent across the whole panel; combined with the rgba background
        # this gives the "frosted overlay" effect requested for V3.
        opacity = QGraphicsOpacityEffect(self)
        opacity.setOpacity(0.96)
        self.setGraphicsEffect(opacity)

        self.hide()

    def set_content(self, widget):
        """Re-parent and host the provided widget (typically the V2 tab widget)."""
        # Clear any previous content.
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        widget.setParent(self)
        self._layout.addWidget(widget)

    def open(self):
        if not self.parentWidget():
            return
        self.show()
        self.raise_()
        # Slide in from off-screen left to x=0.
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        from PyQt5.QtCore import QPoint
        self._anim.setEndValue(QPoint(0, self.y()))
        self._anim.start()

    def close_panel(self):
        if not self.parentWidget():
            return
        from PyQt5.QtCore import QPoint
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(-self.width(), self.y()))
        try:
            self._anim.finished.disconnect()
        except Exception:
            pass
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def is_open(self):
        return self.isVisible() and self.x() >= 0


class TVRoot(QWidget):
    """Owns the libvlc player + a video frame that fills the whole widget.

    The video frame is a native QFrame whose winId() is handed to libvlc's
    set_hwnd / set_xwindow / set_nsobject so the decoder writes pixels there
    directly. Overlay widgets (menu, controls, top bar) are added in later
    phases as raised children of TVRoot, positioned absolutely in
    `_reposition_overlays`.

    The libvlc instance lives here — there is no separate `EmbeddedPlayerWindow`
    top-level in TV mode. `_play_embedded` in the main app calls
    `self.tv_root.play_url(...)` instead of creating a floating player window.
    """

    def __init__(self, parent=None, user_agent="", on_overlay_event=None):
        super().__init__(parent)
        self.setObjectName("tvRoot")
        # Force a black background so the video frame doesn't flash the theme's
        # window colour while libvlc is buffering the first frame.
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("black"))
        self.setPalette(palette)

        import vlc
        self._vlc = vlc
        vlc_args = [
            "--quiet",
            # Reduce initial buffering delay for live/network streams
            "--network-caching=1500",
            "--live-caching=1000",
            # Let VLC pick the best available HW decoder (VideoToolbox / DXVA2 / VA-API)
            "--avcodec-hw=any",
        ]
        ua = (user_agent or "").strip()
        if ua:
            vlc_args.append(f"--http-user-agent={ua}")
        self.instance = vlc.Instance(vlc_args)
        self.player = self.instance.media_player_new()
        self._bound = False

        # The video sink. setMouseTracking is on so the future controls-overlay
        # can hook mouse-move events to wake the auto-hide chrome.
        self.video_frame = QFrame(self)
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setMouseTracking(True)
        self.video_frame.setMinimumSize(640, 360)

        # Placeholder text shown when nothing is playing yet. Removed once the
        # first stream starts. Keeps the bare video frame from looking broken.
        self._placeholder = QLabel("Pick a channel to start watching", self.video_frame)
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "color: rgba(255,255,255,180); font-size: 22px; font-weight: 300;"
        )

        # The TVRoot layout is just the video frame stretching to fill. All
        # overlays added in later phases are NOT in this layout — they are
        # raised children we position by hand in resizeEvent.
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self.video_frame)

        # Reserved hooks for the overlay widgets added by Phase 2 / Phase 3.
        # `on_overlay_event` is the IPTVPlayerApp callback used to wake the
        # menu / controls when the user moves the mouse over the video.
        self._on_overlay_event = on_overlay_event
        self._overlay_widgets = []  # filled by add_overlay()

        # Optional callback the host wires in V3 so an *external* chrome widget
        # (the PlayerScreen's floating Back button, which TVRoot doesn't own)
        # shows/hides in lock-step with the controls overlay. Without this the
        # Back button stayed permanently visible while the rest of the chrome
        # auto-hid, in both normal and fullscreen views.
        self._chrome_sync    = None
        self._mini_mode      = False   # True while hosted in MiniPlayerWindow
        self._mini_wake_cb   = None    # called by _wake_chrome in mini mode
        self._vlc_hwnd_hooked = None
        self._vlc_wndproc_ref = None
        self._vlc_wndproc_old = None

        # Whether TVRoot draws its own hamburger / sliding menu / edge trigger.
        # In V3 (progressive-screens mode) the menu and back nav are owned by
        # the screen stack at the app level, so we suppress these to avoid the
        # hamburger button overlapping the PlayerScreen's Back button.
        self._show_internal_chrome = True

        # Phase 2 chrome: hamburger toggle, edge trigger, sliding menu.
        self.hamburger = QPushButton("☰", self)
        self.hamburger.setObjectName("hamburgerButton")
        self.hamburger.setStyleSheet(_SLIDING_MENU_STYLE)
        self.hamburger.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hamburger.setCursor(Qt.PointingHandCursor)
        self.hamburger.setFixedSize(40, 36)
        self.hamburger.setToolTip("Open / close the channels panel (M)")
        self.hamburger.clicked.connect(self.toggle_menu)
        self.hamburger.raise_()

        self.menu = SlidingMenu(self, width=380)
        self.menu.move(-self.menu.width(), 0)

        self.edge_trigger = _EdgeTrigger(self)
        self.edge_trigger.entered.connect(self.open_menu)
        self.edge_trigger.raise_()

        # ---------- Phase 3: bottom controls overlay ----------
        self.controls = QWidget(self)
        self.controls.setObjectName("tvControls")
        self.controls.setStyleSheet(_CONTROLS_STYLE)
        self.controls.setAttribute(Qt.WA_StyledBackground, True)

        # --- Right-edge playlist panel (replaces the popup menu) ---
        self.playlist_panel = QWidget(self)
        self.playlist_panel.setObjectName("playlistPanel")
        self.playlist_panel.setStyleSheet(_PLAYLIST_PANEL_STYLE)
        self.playlist_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.playlist_panel.setFixedWidth(320)
        pl_layout = QVBoxLayout(self.playlist_panel)
        pl_layout.setContentsMargins(0, 0, 0, 0)
        pl_layout.setSpacing(0)
        pl_header = QLabel("Playlist")
        pl_header.setObjectName("playlistHeader")
        pl_layout.addWidget(pl_header)
        self._playlist_scroll = QScrollArea(self.playlist_panel)
        self._playlist_scroll.setWidgetResizable(True)
        self._playlist_scroll.setFrameShape(QFrame.NoFrame)
        self._playlist_scroll.setStyleSheet("background: transparent;")
        self._playlist_inner = QWidget()
        self._playlist_inner_layout = QVBoxLayout(self._playlist_inner)
        self._playlist_inner_layout.setContentsMargins(0, 4, 0, 4)
        self._playlist_inner_layout.setSpacing(0)
        self._playlist_inner_layout.addStretch(1)
        self._playlist_scroll.setWidget(self._playlist_inner)
        pl_layout.addWidget(self._playlist_scroll, 1)
        self.playlist_panel.hide()
        self._playlist_anim = QPropertyAnimation(self.playlist_panel, b"pos")
        self._playlist_anim.setDuration(200)
        self._playlist_anim.setEasingCurve(QEasingCurve.OutCubic)

        # Subtitle hide strip — child of TVRoot so it sits above the video.
        self._sub_hide_strip = _SubHideStrip(self)
        self._sub_hide_strip.hide()

        self.btn_prev   = QPushButton("⏮")
        self.btn_rewind = QPushButton("⏪")
        self.btn_play   = QPushButton("⏯")
        self.btn_ffwd   = QPushButton("⏩")
        self.btn_next   = QPushButton("⏭")
        self.btn_slow   = QPushButton("\U0001f422")    # 🐢
        self.btn_fast   = QPushButton("\U0001f407")    # 🐇
        self.rate_label = QLabel("1.00x")
        self.rate_label.setStyleSheet("color: white; padding: 0 8px; background: transparent;")
        self.btn_subs   = QPushButton("CC")
        self.btn_copy   = QPushButton("\U0001f517")    # 🔗 copy URL
        self.btn_playlist = QPushButton("\U0001f4cb") # 📋 show playlist
        self.btn_ar     = QPushButton("AR")            # aspect ratio
        self.btn_pin    = QPushButton("\U0001f4cc")    # 📌 always-on-top
        self.btn_mini   = QPushButton("\U0001f5bc")    # 🖼 mini-player
        self.btn_mute   = QPushButton("\U0001f50a")
        self.btn_fs     = QPushButton("⛶")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setObjectName("tvVol")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(120)
        self.player.audio_set_volume(80)

        self._current_url = ""

        self.seek_slider = _ClickableSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("tvSeek")
        self.seek_slider.setRange(0, 1000)
        self._seeking = False

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("tvTimeLabel")

        for b in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                  self.btn_next, self.btn_slow, self.btn_fast,
                  self.btn_subs, self.btn_copy, self.btn_playlist, self.btn_ar,
                  self.btn_pin, self.btn_mini, self.btn_mute, self.btn_fs):
            b.setObjectName("tvCtrlBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(34)
        self.vol_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.btn_subs.setEnabled(False)
        self.btn_copy.setToolTip("Copy stream URL to clipboard")
        self.btn_subs.setToolTip("Subtitles (S)")
        self.btn_slow.setToolTip("Slower")
        self.btn_fast.setToolTip("Faster")
        self.btn_playlist.setToolTip("Show current playlist")
        self.btn_ar.setToolTip("Aspect ratio (Auto / 16:9 / 4:3 / 1:1)")
        self.btn_pin.setToolTip("Keep window always on top (toggle)")
        self.btn_pin.setCheckable(True)
        self.btn_mini.setToolTip("Mini-player (compact floating window)")

        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_rewind.clicked.connect(lambda: self.seek_by(-10000))
        self.btn_ffwd.clicked.connect(lambda: self.seek_by(10000))
        self.btn_slow.clicked.connect(lambda: self._adjust_rate(-0.25))
        self.btn_fast.clicked.connect(lambda: self._adjust_rate(0.25))
        self.btn_subs.clicked.connect(self._show_subs_menu)
        self.btn_copy.clicked.connect(self._copy_url_to_clipboard)
        self.btn_playlist.clicked.connect(self._show_playlist_menu)
        self.btn_ar.clicked.connect(self._show_aspect_ratio_menu)
        self.btn_pin.toggled.connect(self._toggle_always_on_top)
        self.btn_mini.clicked.connect(self._request_mini_player)
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_fs.clicked.connect(self.toggle_fullscreen)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek_slider.sliderReleased.connect(self._seek_released)

        # ⏮ / ⏭ are wired by the host app (it knows the playlist) — exposed
        # as signals so the host can connect to its own next/prev.
        self.next_requested = pyqtSignal  # placeholder; real signal below
        # Re-define via a tiny inner emitter so pyqtSignal lives on a QObject.
        # Use QObject, not QWidget — a QWidget here creates a visible (0,0,100,30)
        # black rectangle at the top-left of the video in mini mode.
        class _ButtonSignals(QObject):
            next_requested = pyqtSignal()
            prev_requested = pyqtSignal()
        self._signals = _ButtonSignals(self)
        self.btn_next.clicked.connect(self._signals.next_requested.emit)
        self.btn_prev.clicked.connect(self._signals.prev_requested.emit)
        # Disabled until host sets the playlist.
        self.btn_next.setEnabled(False)
        self.btn_prev.setEnabled(False)

        seek_row = QHBoxLayout()
        seek_row.setContentsMargins(12, 4, 12, 0)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.time_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 0, 12, 8)
        btn_row.setSpacing(4)
        btn_row.addWidget(self.btn_prev)
        btn_row.addWidget(self.btn_rewind)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_ffwd)
        btn_row.addWidget(self.btn_next)
        btn_row.addSpacing(10)
        btn_row.addWidget(self.btn_slow)
        btn_row.addWidget(self.rate_label)
        btn_row.addWidget(self.btn_fast)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_playlist)
        btn_row.addWidget(self.btn_ar)
        btn_row.addWidget(self.btn_copy)
        btn_row.addWidget(self.btn_subs)
        btn_row.addWidget(self.btn_pin)
        btn_row.addWidget(self.btn_mini)
        btn_row.addSpacing(6)
        btn_row.addWidget(self.btn_mute)
        btn_row.addWidget(self.vol_slider)
        btn_row.addWidget(self.btn_fs)

        controls_lay = QVBoxLayout(self.controls)
        controls_lay.setContentsMargins(0, 0, 0, 0)
        controls_lay.setSpacing(2)
        controls_lay.addLayout(seek_row)
        controls_lay.addLayout(btn_row)

        # ---------- Auto-hide ----------
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_chrome)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_state)
        self._poll_timer.start()

        self.video_frame.installEventFilter(self)
        self.setMouseTracking(True)
        try:
            QApplication.instance().installEventFilter(self)
        except Exception:
            pass

        self._wake_chrome()

    # ------------------------------------------------------------------ libvlc
    @staticmethod
    def is_available():
        """True iff python-vlc + libvlc are loadable."""
        try:
            import vlc
            vlc.Instance()
            return True
        except Exception:
            return False

    def _bind_video_output(self):
        if self._bound:
            return
        win_id = int(self.video_frame.winId())
        if sys.platform.startswith("win"):
            self.player.set_hwnd(win_id)
        elif sys.platform == "darwin":
            self.player.set_nsobject(win_id)
        else:
            self.player.set_xwindow(win_id)
        # Forward mouse / key events from the libvlc child window to Qt so the
        # overlays (added in later phases) wake on any input over the video.
        try:
            self.player.video_set_mouse_input(False)
            self.player.video_set_key_input(False)
        except Exception:
            pass
        self._bound = True

    def play_url(self, url, title=""):
        """Play a stream URL — drop-in replacement for EmbeddedPlayerWindow.play_url."""
        if self._placeholder is not None:
            self._placeholder.hide()
            self._placeholder.deleteLater()
            self._placeholder = None

        # Force re-bind every play — when the host re-parents TVRoot (e.g.
        # mounting it inside the V3 PlayerScreen), the video_frame's native
        # winId() changes, and libvlc keeps drawing into the stale handle:
        # audio plays but the video is invisible. Resetting `_bound` makes
        # `_bind_video_output` re-issue set_hwnd/set_xwindow/set_nsobject.
        self._bound = False
        self._bind_video_output()

        self._current_url   = url
        self._current_title = title or ""
        self._is_paused     = False
        self.btn_play.setText("⏯")
        # stop() mutes VLC to prevent ghost audio; unmute on next play so new
        # streams don't start silently with a "correct-looking" mute icon.
        self._is_muted = False
        try:
            self.player.audio_set_mute(False)
        except Exception:
            pass
        self.btn_mute.setText("\U0001f50a")

        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()

    def stop(self):
        try:
            # Mute first — on Windows with HW decode, player.stop() is
            # asynchronous and the audio buffer drains audibly after return.
            # Silencing immediately prevents the "ghost audio" on Back.
            self.player.audio_set_mute(True)
            self.player.stop()
            # Detach the media so VLC fully tears down the decode pipeline
            # instead of leaving it in a half-stopped state.
            self.player.set_media(None)
        except Exception:
            pass

    # ----------------------------------------------------------------- overlays
    def add_overlay(self, widget):
        """Reserve API used by Phase 2 / Phase 3 for the menu and controls bars.

        Widgets passed here are reparented to TVRoot, raised above the video
        frame, and added to `_overlay_widgets` so `resizeEvent` can reposition
        them on window resize.
        """
        widget.setParent(self)
        widget.raise_()
        self._overlay_widgets.append(widget)

    # ------------------------------------------------------------- transport
    def toggle_play_pause(self):
        # Track state ourselves — libvlc's `is_playing()` can briefly return
        # the wrong value right after pause/play() is called, which made the
        # icon flicker out of sync with the user's spacebar / middle-click
        # presses.
        self._is_paused = not getattr(self, '_is_paused', False)
        if self._is_paused:
            self.player.pause()
            self.btn_play.setText("▶")
        else:
            self.player.play()
            self.btn_play.setText("⏯")
        self._wake_chrome()

    def seek_by(self, ms):
        cur = self.player.get_time()
        if cur < 0:
            return
        self.player.set_time(int(max(0, cur + ms)))
        self._wake_chrome()

    def set_volume(self, value):
        v = int(value)
        self.player.audio_set_volume(v)
        self.btn_mute.setText("\U0001f508" if v == 0 else "\U0001f50a")
        self._wake_chrome()

    def toggle_mute(self):
        # libvlc's `audio_get_mute()` returns -1 when no audio output exists
        # yet (early in the play() lifecycle), which made the icon flip back
        # and forth unreliably. Track the state ourselves and call
        # audio_set_mute explicitly.
        self._is_muted = not getattr(self, '_is_muted', False)
        try:
            self.player.audio_set_mute(self._is_muted)
        except Exception:
            pass
        self.btn_mute.setText("\U0001f507" if self._is_muted else "\U0001f50a")
        self._wake_chrome()

    def toggle_fullscreen(self):
        top = self.window()
        if top.isFullScreen():
            top.showNormal()
        else:
            top.showFullScreen()
        self._wake_chrome()

    def _seek_released(self):
        try:
            length = self.player.get_length()
            if length > 0:
                self.player.set_time(int(self.seek_slider.value() / 1000 * length))
        finally:
            self._seeking = False
            self._wake_chrome()

    def _adjust_rate(self, delta):
        try:
            rate = max(0.25, min(4.0, self.player.get_rate() + delta))
        except Exception:
            rate = 1.0
        self.player.set_rate(rate)
        self.rate_label.setText(f"{rate:.2f}x")
        self._wake_chrome()

    def _subs_tracks(self):
        try:
            descs = self.player.video_get_spu_description() or []
            return [(int(i), n.decode("utf-8", errors="replace") if isinstance(n, bytes) else str(n))
                    for i, n in descs]
        except Exception:
            return []

    def _update_subs_button(self):
        # Enable when libvlc reports any track OR we have a media loaded
        # (so the user can always reach "Load file..." even on a stream that
        # carries zero embedded subtitle tracks).
        self.btn_subs.setEnabled(bool(self._current_url))

    def _show_subs_menu(self):
        menu = QMenu(self)
        tracks = self._subs_tracks()
        if tracks:
            try:
                current = self.player.video_get_spu()
            except Exception:
                current = -1
            menu.addSection("Embedded tracks")
            for tid, name in tracks:
                act = QAction(name, self)
                act.setCheckable(True)
                act.setChecked(tid == current)
                act.triggered.connect(lambda _, t=tid: self.player.video_set_spu(t))
                menu.addAction(act)
            # Quick "off" entry — libvlc uses SPU id -1 for "disable".
            off_act = QAction("Disable subtitles", self)
            off_act.triggered.connect(lambda: self.player.video_set_spu(-1))
            menu.addAction(off_act)
            menu.addSeparator()
        load_act = QAction("Load subtitle file…", self)
        load_act.triggered.connect(self._load_subtitle_file)
        menu.addAction(load_act)
        os_act = QAction("Search OpenSubtitles…", self)
        os_act.triggered.connect(self._search_opensubtitles)
        menu.addAction(os_act)
        menu.addSeparator()
        hide_act = QAction("Hide hardcoded subs (black strip)", self)
        hide_act.setCheckable(True)
        hide_act.setChecked(self._sub_hide_strip.isVisible())
        hide_act.triggered.connect(self._toggle_sub_hide_strip)
        menu.addAction(hide_act)
        menu.exec_(self.btn_subs.mapToGlobal(self.btn_subs.rect().bottomLeft()))

    def _toggle_sub_hide_strip(self):
        if self._sub_hide_strip.isVisible():
            self._sub_hide_strip.hide()
        else:
            # Park it across the bottom of the video where hardcoded subs
            # usually sit. User can drag/resize from there.
            w = max(320, self.width() // 2)
            h = 60
            self._sub_hide_strip.setGeometry(
                (self.width() - w) // 2,
                max(0, self.height() - 200),
                w, h
            )
            self._sub_hide_strip.show()
            self._sub_hide_strip.raise_()

    def _opensubtitles_api_key(self):
        """Read (and on first use, prompt for) the OpenSubtitles API key.
        Stored in userdata.ini under [OpenSubtitles]."""
        import configparser as _cp
        cfg = _cp.ConfigParser()
        try:
            cfg.read(self._app_parent.user_data_file)
        except Exception:
            pass
        key = ""
        if cfg.has_option('OpenSubtitles', 'api_key'):
            key = cfg['OpenSubtitles']['api_key']
        if key:
            return key
        from PyQt5.QtWidgets import QInputDialog
        new_key, ok = QInputDialog.getText(
            self, "OpenSubtitles API key",
            "Paste your OpenSubtitles API key.\n"
            "Get one for free at https://www.opensubtitles.com/en/consumers (login → API key):"
        )
        if not ok or not new_key.strip():
            return None
        cfg['OpenSubtitles'] = {'api_key': new_key.strip()}
        try:
            with open(self._app_parent.user_data_file, 'w') as f:
                cfg.write(f)
        except OSError:
            pass
        return new_key.strip()

    def _search_opensubtitles(self):
        """Search the OpenSubtitles REST API, let the user pick a result,
        download the subtitle file, and apply it via libvlc."""
        api_key = self._opensubtitles_api_key()
        if not api_key:
            return

        # Default query is the title we got from the host. Let the user edit it.
        default_query = getattr(self, "_current_title", "") or ""
        try:
            media = self.player.get_media()
            if media is not None and not default_query:
                try:
                    t = media.get_meta(0)
                    if t:
                        default_query = t
                except Exception:
                    pass
        except Exception:
            pass

        from PyQt5.QtWidgets import QInputDialog, QDialog, QDialogButtonBox, QListWidget
        query, ok = QInputDialog.getText(
            self, "Search OpenSubtitles", "Search for:", text=default_query
        )
        if not ok or not query.strip():
            return

        # Network call — keep the UI responsive by showing a brief wait cursor.
        from PyQt5.QtGui import QGuiApplication
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import requests
            headers = {
                "Api-Key": api_key,
                "User-Agent": "Nebula IPTV V1.0",
                "Accept": "application/json",
            }
            resp = requests.get(
                "https://api.opensubtitles.com/api/v1/subtitles",
                headers=headers,
                params={"query": query.strip(), "languages": "en,ar"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "OpenSubtitles error",
                                f"Search failed:\n{e}\n\nCheck your API key in userdata.ini "
                                f"if the error mentions auth.")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        results = data.get('data') or []
        if not results:
            QMessageBox.information(self, "OpenSubtitles", "No subtitles found for that query.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("OpenSubtitles results")
        dlg.resize(560, 420)
        dlay = QVBoxLayout(dlg)
        listw = QListWidget()
        for entry in results[:50]:
            attrs = entry.get('attributes', {}) or {}
            release = attrs.get('release') or attrs.get('feature_details', {}).get('movie_name') or "(unknown)"
            lang    = attrs.get('language') or "?"
            dl      = attrs.get('download_count') or 0
            fps     = attrs.get('fps') or "?"
            listw.addItem(f"[{lang}] {release}  —  {dl} downloads  •  {fps} fps")
        dlay.addWidget(listw)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        dlay.addWidget(bb)
        if dlg.exec_() != QDialog.Accepted or listw.currentRow() < 0:
            return

        chosen = results[listw.currentRow()]
        attrs = chosen.get('attributes', {}) or {}
        files = attrs.get('files') or []
        if not files:
            QMessageBox.warning(self, "OpenSubtitles", "Selected entry has no downloadable file.")
            return
        file_id = files[0].get('file_id')
        if not file_id:
            QMessageBox.warning(self, "OpenSubtitles", "Missing file_id in API response.")
            return

        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            import requests, tempfile, os
            dl_resp = requests.post(
                "https://api.opensubtitles.com/api/v1/download",
                headers={"Api-Key": api_key, "User-Agent": "Nebula IPTV V1.0",
                         "Accept": "application/json", "Content-Type": "application/json"},
                json={"file_id": int(file_id)},
                timeout=15,
            )
            dl_resp.raise_for_status()
            link = dl_resp.json().get('link')
            if not link:
                raise RuntimeError("API didn't return a download link.")
            srt = requests.get(link, timeout=30)
            srt.raise_for_status()
            tmp = tempfile.NamedTemporaryFile(suffix=".srt", delete=False)
            tmp.write(srt.content)
            tmp.close()
        except Exception as e:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "OpenSubtitles error", f"Download failed:\n{e}")
            return
        finally:
            QGuiApplication.restoreOverrideCursor()

        # Apply via libvlc — same path as "Load subtitle file…".
        try:
            if hasattr(self.player, 'video_set_subtitle_file'):
                self.player.video_set_subtitle_file(tmp.name)
            elif hasattr(self.player, 'add_slave'):
                self.player.add_slave(self._vlc.MediaSlaveType.subtitle, tmp.name, True)
            QMessageBox.information(self, "OpenSubtitles", "Subtitle loaded.")
        except Exception as e:
            QMessageBox.warning(self, "Subtitle load failed", str(e))

    def _load_subtitle_file(self):
        path_, _ = QFileDialog.getOpenFileName(
            self, "Choose subtitle file", "",
            "Subtitle files (*.srt *.vtt *.ass *.ssa *.sub);;All files (*)"
        )
        if not path_:
            return
        try:
            # libvlc 3.x has video_set_subtitle_file; 4.x renamed it.
            ok = False
            if hasattr(self.player, 'video_set_subtitle_file'):
                ok = self.player.video_set_subtitle_file(path_) == 0
            elif hasattr(self.player, 'add_slave'):
                ok = self.player.add_slave(self._vlc.MediaSlaveType.subtitle, path_, True) == 0
            if not ok:
                QMessageBox.warning(self, "Subtitle load failed",
                                    f"libvlc could not load:\n{path_}")
        except Exception as e:
            QMessageBox.warning(self, "Subtitle load failed", str(e))

    def _copy_url_to_clipboard(self):
        if not self._current_url:
            return
        QApplication.clipboard().setText(self._current_url)
        # Tiny visual cue — flip the button text briefly.
        self.btn_copy.setText("✓")
        from PyQt5.QtCore import QTimer as _QTimer
        _QTimer.singleShot(900, lambda: self.btn_copy.setText("\U0001f517"))

    def set_navigable(self, navigable):
        """For dead-end media (a single movie), disable prev/next so the
        player chrome doesn't show buttons that go nowhere."""
        self.btn_prev.setEnabled(bool(navigable))
        self.btn_next.setEnabled(bool(navigable))
        self.btn_prev.setVisible(bool(navigable))
        self.btn_next.setVisible(bool(navigable))
        self.btn_playlist.setEnabled(bool(navigable))
        self.btn_playlist.setVisible(bool(navigable))

    # ---------------------------------------------------- playlist panel
    def set_playlist(self, items, current_index=0):
        """`items` is a list of {'name': str, 'url': str}. Rebuilds the
        right-edge slide-in panel so the user can jump straight to another
        item without going back to the browse screen."""
        self._playlist_items = list(items or [])
        self._playlist_index = max(0, min(int(current_index), max(0, len(self._playlist_items) - 1)))

        # Tear down the previous rows.
        lay = self._playlist_inner_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        # Rebuild — cap at 500 rows; the browse screen has the full list.
        for i, entry in enumerate(self._playlist_items[:500]):
            label = entry.get('name') or entry.get('url') or f"Item {i}"
            btn = QPushButton(("▶  " if i == self._playlist_index else "     ") + label)
            btn.setObjectName("playlistRowCurrent" if i == self._playlist_index else "playlistRow")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _, idx=i: self._jump_to_playlist_index(idx))
            lay.addWidget(btn)
        lay.addStretch(1)

    def _show_playlist_menu(self):
        # Slide the playlist panel in from the right (or hide it if open).
        items = getattr(self, '_playlist_items', []) or []
        if not items:
            return
        if self.playlist_panel.isVisible() and self.playlist_panel.x() >= self.width() - self.playlist_panel.width():
            self._hide_playlist_panel()
        else:
            self._open_playlist_panel()

    def _open_playlist_panel(self):
        from PyQt5.QtCore import QPoint
        self.playlist_panel.setGeometry(self.width(), 0,
                                        self.playlist_panel.width(),
                                        self.height())
        self.playlist_panel.show()
        self.playlist_panel.raise_()
        self._playlist_anim.stop()
        self._playlist_anim.setStartValue(QPoint(self.width(), 0))
        self._playlist_anim.setEndValue(QPoint(self.width() - self.playlist_panel.width(), 0))
        try:
            self._playlist_anim.finished.disconnect()
        except Exception:
            pass
        self._playlist_anim.start()

    def _hide_playlist_panel(self):
        from PyQt5.QtCore import QPoint
        self._playlist_anim.stop()
        self._playlist_anim.setStartValue(self.playlist_panel.pos())
        self._playlist_anim.setEndValue(QPoint(self.width(), 0))
        try:
            self._playlist_anim.finished.disconnect()
        except Exception:
            pass
        self._playlist_anim.finished.connect(self.playlist_panel.hide)
        self._playlist_anim.start()

    def _jump_to_playlist_index(self, idx):
        items = getattr(self, '_playlist_items', []) or []
        if not (0 <= idx < len(items)):
            return
        self._playlist_index = idx
        url = items[idx].get('url')
        if url:
            # Hide the panel after a brief delay so the user sees the click feedback.
            QTimer.singleShot(150, self._hide_playlist_panel)
            self.play_url(url, title=items[idx].get('name', ''))
            self.set_playlist(items, idx)  # refresh current-row highlight

    # --------------------------------------------------- aspect ratio menu
    def _show_aspect_ratio_menu(self):
        menu = QMenu(self)
        options = [("Auto", ""), ("16:9", "16:9"), ("4:3", "4:3"),
                   ("1:1", "1:1"), ("16:10", "16:10"),
                   ("2.35:1", "235:100"), ("2.39:1", "239:100")]
        for label, value in options:
            act = QAction(label, self)
            act.triggered.connect(lambda _, v=value: self._set_aspect_ratio(v))
            menu.addAction(act)
        menu.exec_(self.btn_ar.mapToGlobal(self.btn_ar.rect().topLeft()))

    def _toggle_always_on_top(self, checked):
        # Toggle WindowStaysOnTopHint on the TOP-LEVEL window (the main
        # QMainWindow), then re-show to make the flag take effect.
        top = self.window()
        if top is None:
            return
        flags = top.windowFlags()
        if checked:
            top.setWindowFlags(flags | Qt.WindowStaysOnTopHint)
        else:
            top.setWindowFlags(flags & ~Qt.WindowStaysOnTopHint)
        top.show()
        self._wake_chrome()

    def _set_aspect_ratio(self, value):
        try:
            # libvlc accepts None / b"" for "auto", or a "W:H" byte string.
            if value:
                self.player.video_set_aspect_ratio(value.encode("utf-8"))
            else:
                self.player.video_set_aspect_ratio(None)
            self.btn_ar.setText(value or "AR")
        except Exception:
            pass

    # --------------------------------------------------------- next/prev hooks
    def connect_next_prev(self, on_next, on_prev):
        """Host app supplies callbacks that walk the visible playlist."""
        self._signals.next_requested.connect(on_next)
        self._signals.prev_requested.connect(on_prev)
        self.btn_next.setEnabled(True)
        self.btn_prev.setEnabled(True)

    # ------------------------------------------------------------- chrome
    def set_chrome_sync(self, callback):
        """Register a `callback(visible: bool)` invoked whenever the controls
        overlay wakes or auto-hides. V3 uses it to keep the PlayerScreen's
        floating Back button in sync with the rest of the chrome."""
        self._chrome_sync = callback

    def _notify_chrome(self, visible):
        if self._chrome_sync:
            try:
                self._chrome_sync(visible)
            except Exception:
                pass

    def install_mini_hittest_hook(self):
        """Windows only: subclass VLC's DirectX child HWND so WM_NCHITTEST is
        forwarded to the containing MiniPlayerWindow.  Critical: use c_ssize_t
        (ULONG_PTR) not c_long/c_int for GetWindowLongPtrW — the old WndProc
        pointer is 64 bits on x64; truncating it to 32 bits corrupts the
        pointer and crashes the app when the hook is uninstalled."""
        if not sys.platform.startswith('win'):
            return
        try:
            import ctypes, ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            user32.GetWindowLongPtrW.restype  = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.restype  = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
            user32.CallWindowProcW.restype    = ctypes.c_ssize_t
            user32.SendMessageW.restype       = ctypes.c_ssize_t
            user32.IsWindow.restype           = ctypes.c_bool

            vf_hwnd  = int(self.video_frame.winId())
            vlc_hwnd = user32.GetWindow(vf_hwnd, 5)   # GW_CHILD
            if not vlc_hwnd:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(250, self.install_mini_hittest_hook)
                return
            mini_win = self.window()
            if not mini_win:
                return
            mini_hwnd = int(mini_win.winId())
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
            old = user32.GetWindowLongPtrW(vlc_hwnd, -4)
            def _hook(hwnd, msg, wp, lp):
                if msg == 0x0084:
                    return user32.SendMessageW(mini_hwnd, msg, wp, lp)
                return user32.CallWindowProcW(old, hwnd, msg, wp, lp)
            proc = WNDPROC(_hook)
            user32.SetWindowLongPtrW(vlc_hwnd, -4, proc)
            self._vlc_hwnd_hooked = vlc_hwnd
            self._vlc_wndproc_ref  = proc
            self._vlc_wndproc_old  = old
            import logging; logging.info("Mini hit-test hook installed (VLC HWND %d)", vlc_hwnd)
        except Exception as e:
            import logging; logging.error("install_mini_hittest_hook: %s", e)

    def uninstall_mini_hittest_hook(self):
        if not sys.platform.startswith('win'):
            return
        try:
            if not self._vlc_hwnd_hooked:
                return
            import ctypes, ctypes.wintypes as wt
            user32 = ctypes.windll.user32
            user32.SetWindowLongPtrW.restype  = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
            user32.IsWindow.restype = ctypes.c_bool
            if user32.IsWindow(self._vlc_hwnd_hooked):
                user32.SetWindowLongPtrW(
                    self._vlc_hwnd_hooked, -4, self._vlc_wndproc_old)
        except Exception as e:
            import logging; logging.error("uninstall_mini_hittest_hook: %s", e)
        finally:
            self._vlc_hwnd_hooked = None
            self._vlc_wndproc_ref  = None
            self._vlc_wndproc_old  = None

    def set_mini_player_callback(self, callback):
        """Register a zero-argument callback the host calls to enter/exit mini
        mode. TVRoot fires it when the user clicks the 🖼 mini-player button."""
        self._mini_player_cb = callback

    def _request_mini_player(self):
        cb = getattr(self, '_mini_player_cb', None)
        if cb:
            try:
                cb()
            except Exception as e:
                import logging, traceback
                logging.error("Mini-player toggle failed: %s\n%s", e, traceback.format_exc())

    def disable_internal_chrome(self):
        """Suppress the hamburger / sliding menu / edge trigger forever.
        Used by V3 where the app's screen stack owns navigation."""
        self._show_internal_chrome = False
        try:
            self.hamburger.hide()
            self.menu.hide()
            self.edge_trigger.hide()
        except AttributeError:
            pass

    def _wake_chrome(self):
        if self._mini_mode:
            # Forward the wake signal to the mini window's button overlay
            if self._mini_wake_cb:
                try:
                    self._mini_wake_cb()
                except Exception:
                    pass
            return
        self.controls.show()
        if self._show_internal_chrome:
            self.hamburger.show()
        self._notify_chrome(True)
        self.video_frame.unsetCursor()
        if self.player.is_playing():
            self._hide_timer.start(3000)
        else:
            self._hide_timer.stop()

    def _hide_chrome(self):
        if self._mini_mode:
            return
        if self._show_internal_chrome and self.menu.is_open():
            return
        if not self.player.is_playing():
            return
        self.controls.hide()
        if self._show_internal_chrome:
            self.hamburger.hide()
        self._notify_chrome(False)
        self.video_frame.setCursor(Qt.BlankCursor)

    def _poll_state(self):
        try:
            # Capture the real video AR while playing so mini mode can use it
            # reliably (video_get_size may return 0,0 right after a rebind).
            vw, vh = self.player.video_get_size(0)
            if vw and vh:
                self._video_ar = vw / vh
        except Exception:
            pass
        try:
            length = self.player.get_length()
            cur    = self.player.get_time()
            if length > 0 and not self._seeking:
                self.seek_slider.setEnabled(True)
                self.seek_slider.setValue(int(cur / length * 1000))
                self.time_label.setText(f"{self._fmt_ms(cur)} / {self._fmt_ms(length)}")
            else:
                self.seek_slider.setEnabled(False)
                self.seek_slider.setValue(0)
                self.time_label.setText("LIVE")
            self._update_subs_button()
        except Exception:
            pass

    @staticmethod
    def _fmt_ms(ms):
        if ms is None or ms < 0:
            return "00:00"
        s = int(ms // 1000)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
        return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    def _is_in_self(self, obj):
        w = obj
        while w is not None:
            if w is self:
                return True
            try:
                w = w.parent()
            except Exception:
                return False
        return False

    def _is_on_controls(self, obj):
        # True if obj is the bottom controls bar or any of its descendants.
        # Used so double-clicking a button doesn't accidentally toggle
        # fullscreen, and so the volume-wheel-on-video doesn't fire when the
        # user is dragging the volume slider itself.
        w = obj
        while w is not None:
            if w is self.controls:
                return True
            try:
                w = w.parent()
            except Exception:
                return False
        return False

    def eventFilter(self, obj, event):
        if not self._is_in_self(obj):
            return False
        et = event.type()
        if et in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            self._wake_chrome()

        on_controls = self._is_on_controls(obj)

        if et == QEvent.Wheel and not on_controls:
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0
            if delta:
                self.vol_slider.setValue(max(0, min(100, self.vol_slider.value() + (5 if delta > 0 else -5))))
            return True
        if et == QEvent.MouseButtonPress and not on_controls:
            try:
                btn = event.button()
            except Exception:
                btn = None
            if btn == Qt.MidButton:
                # Middle-click toggles play/pause — same icon-sync path as
                # the spacebar and the on-screen Play button.
                self.toggle_play_pause()
                return True
        if et == QEvent.MouseButtonDblClick and not on_controls and not self._mini_mode:
            # Only LEFT double-click toggles fullscreen — and never in mini mode
            # (would fullscreen the MiniPlayerWindow, not the main window).
            try:
                btn = event.button()
            except Exception:
                btn = None
            if btn == Qt.LeftButton:
                self.toggle_fullscreen()
                return True
            if btn == Qt.MidButton:
                # Second middle-click of a double-click sequence. The first
                # press already triggered play/pause; toggle again to land
                # back where we started — net effect = no change, no fs.
                self.toggle_play_pause()
                return True
        return False

    # --------------------------------------------------------------- menu API
    def set_menu_content(self, widget):
        """Host the V2 tab widget inside the sliding menu."""
        self.menu.set_content(widget)

    def open_menu(self):
        # Position the menu to span the full window height before sliding in.
        self.menu.setGeometry(self.menu.x(), 0, self.menu.width(), self.height())
        self.menu.open()

    def close_menu(self):
        self.menu.close_panel()

    def toggle_menu(self):
        if self.menu.is_open():
            self.close_menu()
        else:
            self.open_menu()

    # ------------------------------------------------------------------- events
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Center the placeholder label in the video frame.
        if self._placeholder is not None:
            self._placeholder.setGeometry(0, 0, self.video_frame.width(), self.video_frame.height())

        # Phase 2 chrome positions — skip entirely in mini mode.
        if not self._mini_mode:
            self.hamburger.move(10, 10)
            self.hamburger.raise_()
            self.edge_trigger.setGeometry(0, self.hamburger.height() + 14,
                                          self.edge_trigger.width(), self.height() - self.hamburger.height() - 14)
            self.edge_trigger.raise_()
            if self.menu.is_open():
                self.menu.setGeometry(0, 0, self.menu.width(), self.height())
            else:
                self.menu.move(-self.menu.width(), 0)
                self.menu.resize(self.menu.width(), self.height())

        # Phase 3 controls: bottom 110 px, full width.
        # Skip in mini mode — controls must stay hidden; repositioning would
        # un-hide them and produce the black overlay artifact in the PiP window.
        ch = 110
        if not self._mini_mode:
            self.controls.setGeometry(0, self.height() - ch, self.width(), ch)
            self.controls.raise_()

        # Playlist panel: right-anchored, full height (minus bottom controls).
        # If hidden, park it just off-screen so the slide-in animation has
        # a sensible start position.
        if self.playlist_panel.isVisible():
            self.playlist_panel.setGeometry(
                self.width() - self.playlist_panel.width(), 0,
                self.playlist_panel.width(), self.height() - ch
            )
        else:
            self.playlist_panel.resize(self.playlist_panel.width(), self.height() - ch)
            self.playlist_panel.move(self.width(), 0)
        self.playlist_panel.raise_()

        # Phase 3 overlays will use this hook to position themselves at the
        # top / bottom / left edges.
        for w in self._overlay_widgets:
            try:
                w.parentWidget_resize_hint(self.width(), self.height())
            except AttributeError:
                pass
