"""TV-mode central widget for V3.

Phase 1 deliverable: a QWidget whose entire client area is a libvlc video sink.
Subsequent phases mount the (now translucent, sliding) menu and the bottom
controls overlay on top of this same widget.

Why a separate module: keeps V2's existing IPTVPlayerApp construction intact —
we only swap in TVRoot when the user enables TV mode in Settings. Classic V2
layout still works for users who want the legacy look.
"""

import sys

from PyQt5.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, pyqtSignal, QTimer
from PyQt5.QtGui import QPalette, QColor, QCursor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QStackedLayout, QLabel,
    QPushButton, QGraphicsOpacityEffect, QSlider, QApplication,
)


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


_CONTROLS_STYLE = """
QWidget#tvControls {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 rgba(0,0,0,60), stop:1 rgba(0,0,0,210));
}
QPushButton#tvCtrlBtn {
    background: rgba(45, 45, 48, 130);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 16px;
    min-width: 34px;
}
QPushButton#tvCtrlBtn:hover { background: rgba(91, 141, 239, 220); }
QPushButton#tvCtrlBtn:disabled { color: #888; background: rgba(45,45,48,60); }
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
        vlc_args = ["--quiet"]
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

        # Phase 2 chrome: hamburger toggle, edge trigger, sliding menu.
        self.hamburger = QPushButton("☰", self)
        self.hamburger.setObjectName("hamburgerButton")
        self.hamburger.setStyleSheet(_SLIDING_MENU_STYLE)
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

        self.btn_prev   = QPushButton("⏮")
        self.btn_rewind = QPushButton("⏪")
        self.btn_play   = QPushButton("⏯")
        self.btn_ffwd   = QPushButton("⏩")
        self.btn_next   = QPushButton("⏭")
        self.btn_mute   = QPushButton("\U0001f50a")
        self.btn_fs     = QPushButton("⛶")
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setObjectName("tvVol")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(80)
        self.vol_slider.setFixedWidth(120)
        self.player.audio_set_volume(80)

        self.seek_slider = _ClickableSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("tvSeek")
        self.seek_slider.setRange(0, 1000)
        self._seeking = False

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("tvTimeLabel")

        for b in (self.btn_prev, self.btn_rewind, self.btn_play, self.btn_ffwd,
                  self.btn_next, self.btn_mute, self.btn_fs):
            b.setObjectName("tvCtrlBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(34)
        self.vol_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.setCursor(Qt.PointingHandCursor)

        self.btn_play.clicked.connect(self.toggle_play_pause)
        self.btn_rewind.clicked.connect(lambda: self.seek_by(-10000))
        self.btn_ffwd.clicked.connect(lambda: self.seek_by(10000))
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_fs.clicked.connect(self.toggle_fullscreen)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek_slider.sliderReleased.connect(self._seek_released)

        # ⏮ / ⏭ are wired by the host app (it knows the playlist) — exposed
        # as signals so the host can connect to its own next/prev.
        self.next_requested = pyqtSignal  # placeholder; real signal below
        # Re-define via a tiny inner emitter so pyqtSignal lives on a QObject:
        class _ButtonSignals(QWidget):
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
        btn_row.addStretch(1)
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

        media = self.instance.media_new(url)
        self.player.set_media(media)
        self._bind_video_output()
        self.player.play()

    def stop(self):
        try:
            self.player.stop()
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
        if self.player.is_playing():
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
        self.player.audio_toggle_mute()
        muted = self.player.audio_get_mute() == 1
        self.btn_mute.setText("\U0001f507" if muted else "\U0001f50a")
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

    # --------------------------------------------------------- next/prev hooks
    def connect_next_prev(self, on_next, on_prev):
        """Host app supplies callbacks that walk the visible playlist."""
        self._signals.next_requested.connect(on_next)
        self._signals.prev_requested.connect(on_prev)
        self.btn_next.setEnabled(True)
        self.btn_prev.setEnabled(True)

    # ------------------------------------------------------------- chrome
    def _wake_chrome(self):
        self.controls.show()
        self.hamburger.show()
        self.video_frame.unsetCursor()
        if self.player.is_playing():
            self._hide_timer.start(3000)
        else:
            self._hide_timer.stop()

    def _hide_chrome(self):
        if self.menu.is_open():
            return
        if not self.player.is_playing():
            return
        self.controls.hide()
        self.hamburger.hide()
        self.video_frame.setCursor(Qt.BlankCursor)

    def _poll_state(self):
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

    def eventFilter(self, obj, event):
        if not self._is_in_self(obj):
            return False
        et = event.type()
        if et in (QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            self._wake_chrome()
        if et == QEvent.Wheel:
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0
            if delta:
                self.vol_slider.setValue(max(0, min(100, self.vol_slider.value() + (5 if delta > 0 else -5))))
            return True
        if et == QEvent.MouseButtonDblClick:
            self.toggle_fullscreen()
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

        # Phase 2 chrome positions:
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
        ch = 110
        self.controls.setGeometry(0, self.height() - ch, self.width(), ch)
        self.controls.raise_()

        # Phase 3 overlays will use this hook to position themselves at the
        # top / bottom / left edges.
        for w in self._overlay_widgets:
            try:
                w.parentWidget_resize_hint(self.width(), self.height())
            except AttributeError:
                pass
