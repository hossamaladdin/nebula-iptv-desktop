"""TV-mode central widget for V3.

Phase 1 deliverable: a QWidget whose entire client area is a libvlc video sink.
Subsequent phases mount the (now translucent, sliding) menu and the bottom
controls overlay on top of this same widget.

Why a separate module: keeps V2's existing IPTVPlayerApp construction intact —
we only swap in TVRoot when the user enables TV mode in Settings. Classic V2
layout still works for users who want the legacy look.
"""

import sys

from PyQt5.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QStackedLayout, QLabel,
    QPushButton, QGraphicsOpacityEffect,
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
        # * Hamburger top-left with a small margin.
        # * Edge trigger covers the left edge below the hamburger.
        # * Menu spans full height. If it's open it sits at x=0; otherwise off-screen left.
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

        # Phase 3 overlays will use this hook to position themselves at the
        # top / bottom / left edges.
        for w in self._overlay_widgets:
            try:
                w.parentWidget_resize_hint(self.width(), self.height())
            except AttributeError:
                pass
