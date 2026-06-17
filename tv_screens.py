"""V3 redesign: progressive full-window screens.

The user model: this app is a TV, not a windowed desktop app. Each interaction
takes you to a *new screen* that fills the whole window:

    Home  ─►  Browse(LIVE)   ─►  Player
        \─►  Browse(Movies)  ─►  Player
        \─►  Browse(Series)  ─►  Player
        \─►  Settings
        \─►  Info

Screens are pushed onto a `TVScreenStack` (a QStackedWidget with slide animation
between pages). Each non-home screen has a back arrow that pops the stack.

The V2 widgets (category_list_*, streaming_list_*, LiveInfoBox, MovieInfoBox,
SeriesInfoBox, settings widgets, iptv_info_text) are NOT rewritten — they're
reparented into the new screens so all the existing wiring (clicks, filters,
favorites, etc.) keeps working.
"""

import sys
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QSize, QRect, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QSplitter, QSizePolicy, QComboBox,
    QMenu, QAction, QApplication,
)


_HOME_STYLE_DARK = """
/* HomeScreen Nord-dark — used when theme = Dark (or System resolves to Dark). */
QWidget#homeScreen { background: #2e3440; }    /* nord0 */
QLabel#homeTitle {
    color: #eceff4;                            /* nord6 — softest off-white */
    font-size: 36px;
    font-weight: 300;
    letter-spacing: 1px;
}
QLabel#homeSubtitle {
    color: #81a1c1;                            /* nord9 — muted blue-grey */
    font-size: 14px;
    letter-spacing: 2px;
}
QPushButton#homeTile {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #434c5e, stop:1 #3b4252);  /* nord2 → nord1 */
    color: #eceff4;
    border: 1px solid #4c566a;                /* nord3 */
    border-radius: 16px;
    padding: 18px;
    font-size: 22px;
    font-weight: 500;
    text-align: center;
}
QPushButton#homeTile:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #5e81ac, stop:1 #4c6790);  /* nord10 */
    border: 1px solid #88c0d0;                /* nord8 */
}
QLabel#homeTileIcon, QLabel#homeTileLabel {
    color: #eceff4;
    background: transparent;
}
QPushButton#homeTileSmall {
    background: #3b4252;                      /* nord1 */
    color: #d8dee9;                            /* nord4 */
    border: 1px solid #4c566a;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 13px;
}
QPushButton#homeTileSmall:hover {
    background: #5e81ac;
    color: #eceff4;
}
QPushButton#homeChip {
    background: #3b4252;
    color: #d8dee9;
    border: 1px solid #4c566a;
    border-radius: 18px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#homeChip:hover {
    background: #5e81ac;
    color: #eceff4;
}
QPushButton#homeChip::menu-indicator { image: none; }
QPushButton#homeExit {
    background: #4c566a;
    color: #eceff4;
    border: 1px solid #bf616a;                /* nord11 — danger accent */
    border-radius: 18px;
    padding: 8px 18px;
    font-size: 12px;
}
QPushButton#homeExit:hover {
    background: #bf616a;
    color: #eceff4;
}
QMenu {
    background: #3b4252;
    color: #d8dee9;
    border: 1px solid #4c566a;
}
QMenu::item:selected {
    background: #5e81ac;
    color: #eceff4;
}
"""


_HOME_STYLE_LIGHT = """
/* HomeScreen Nord-light — dimmed bg, deep text, much higher contrast than
   the previous near-white. Tiles use a deeper grey so labels pop. */
QWidget#homeScreen { background: #d8dee9; }    /* nord4 — dimmed, not pure white */
QLabel#homeTitle {
    color: #1c2128;                            /* deeper than nord0 for max contrast */
    font-size: 36px;
    font-weight: 300;
    letter-spacing: 1px;
}
QLabel#homeSubtitle {
    color: #3b4252;                            /* nord1 — readable on dimmed bg */
    font-size: 14px;
    letter-spacing: 2px;
}
QPushButton#homeTile {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #c5cad3, stop:1 #aab2bf);  /* deeper grey */
    color: #1c2128;
    border: 1px solid #8d96a3;
    border-radius: 16px;
    padding: 18px;
    font-size: 22px;
    font-weight: 500;
    text-align: center;
}
QPushButton#homeTile:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #88c0d0, stop:1 #5e81ac);
    color: #eceff4;
    border: 1px solid #4c6790;
}
QLabel#homeTileIcon, QLabel#homeTileLabel {
    color: #1c2128;                            /* dark text on dimmed tile */
    background: transparent;
}
QPushButton#homeTile:hover QLabel#homeTileIcon,
QPushButton#homeTile:hover QLabel#homeTileLabel {
    color: #eceff4;
}
QPushButton#homeTileSmall {
    background: #c5cad3;
    color: #1c2128;
    border: 1px solid #8d96a3;
    border-radius: 10px;
    padding: 10px 18px;
    font-size: 13px;
}
QPushButton#homeTileSmall:hover {
    background: #5e81ac;
    color: #eceff4;
}
QPushButton#homeChip {
    background: #c5cad3;
    color: #1c2128;
    border: 1px solid #8d96a3;
    border-radius: 18px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#homeChip:hover {
    background: #5e81ac;
    color: #eceff4;
}
QPushButton#homeChip::menu-indicator { image: none; }
QPushButton#homeExit {
    background: #c5cad3;
    color: #b03a3a;
    border: 1px solid #b03a3a;
    border-radius: 18px;
    padding: 8px 18px;
    font-size: 12px;
}
QPushButton#homeExit:hover {
    background: #b03a3a;
    color: #eceff4;
}
QMenu {
    background: #d8dee9;
    color: #1c2128;
    border: 1px solid #8d96a3;
}
QMenu::item:selected {
    background: #5e81ac;
    color: #eceff4;
}
"""

_BACK_STYLE = """
QPushButton#backButton {
    background: #3b4252;
    color: #eceff4;
    border: 1px solid #4c566a;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 15px;
}
QPushButton#backButton:hover { background: #5e81ac; }
"""

_BROWSE_STYLE = """
QWidget#browseScreen { background: #2e3440; }
QLabel#browseHeader {
    color: #eceff4;
    font-size: 24px;
    font-weight: 500;
    padding-left: 8px;
}
"""


class _Tile(QPushButton):
    """A large Smart-TV style button.

    Renders a large emoji glyph as the icon (no external asset dependency —
    rendered by the system's emoji font, e.g. Segoe UI Emoji on Windows) and
    a label underneath.
    """

    def __init__(self, label, emoji="", parent=None, big=True):
        super().__init__(parent)
        self.setObjectName("homeTile" if big else "homeTileSmall")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        if big:
            self.setMinimumSize(220, 220)
            if emoji:
                icon_label = QLabel(emoji)
                icon_label.setObjectName("homeTileIcon")
                icon_label.setAlignment(Qt.AlignCenter)
                # No color hardcoded — _HOME_STYLE_DARK / _HOME_STYLE_LIGHT
                # set it on #homeTileIcon and #homeTileLabel so the tile text
                # actually flips colour when the theme changes.
                icon_label.setStyleSheet("font-size: 72px; background: transparent;")
                layout.addWidget(icon_label)
            text_label = QLabel(label)
            text_label.setObjectName("homeTileLabel")
            text_label.setAlignment(Qt.AlignCenter)
            text_label.setStyleSheet("font-size: 20px; font-weight: 500; background: transparent;")
            layout.addWidget(text_label)
        else:
            self.setMinimumSize(160, 48)
            if emoji:
                self.setText(f"{emoji}   {label}")
            else:
                self.setText(label)


class HomeScreen(QWidget):
    """First screen the user lands on.

    Layout: Nebula IPTV title at the top, three big tiles in a horizontal
    row (LIVE / Movies / Series), small tile row underneath for Settings
    and Info.
    """
    tile_clicked  = pyqtSignal(str)   # 'LIVE' | 'Movies' | 'Series' | 'Settings' | 'Info'
    theme_changed = pyqtSignal(str)   # 'System' | 'Light' | 'Dark'
    about_clicked = pyqtSignal()
    exit_clicked  = pyqtSignal()

    def __init__(self, parent=None, icons=None, current_theme="System"):
        super().__init__(parent)
        self.setObjectName("homeScreen")
        self._effective_theme = "Dark"  # default, host calls set_theme afterwards
        self.setStyleSheet(_HOME_STYLE_DARK)
        # `icons` argument is accepted for backward compat with the V2 .ico paths,
        # but V3 uses Unicode emoji from the system font so we ignore it.

        # --- Top-right chip bar: Style button (rounded) + About ---
        self._style_value = current_theme
        self.style_btn = QPushButton(f"Theme: {current_theme}")
        self.style_btn.setObjectName("homeChip")
        self.style_btn.setCursor(Qt.PointingHandCursor)
        self.style_btn.setFocusPolicy(Qt.NoFocus)
        style_menu = QMenu(self.style_btn)
        for opt in ("System", "Light", "Dark"):
            act = QAction(opt, self.style_btn)
            act.triggered.connect(lambda _, o=opt: self._on_style_picked(o))
            style_menu.addAction(act)
        self.style_btn.setMenu(style_menu)

        about_btn = QPushButton("About")
        about_btn.setObjectName("homeChip")
        about_btn.setCursor(Qt.PointingHandCursor)
        about_btn.setFocusPolicy(Qt.NoFocus)
        about_btn.clicked.connect(self.about_clicked.emit)

        top_right = QHBoxLayout()
        top_right.setSpacing(10)
        top_right.addStretch(1)
        top_right.addWidget(self.style_btn)
        top_right.addWidget(about_btn)

        # --- Title block ---
        title = QLabel("Nebula IPTV")
        title.setObjectName("homeTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("CHOOSE WHAT TO WATCH")
        subtitle.setObjectName("homeSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)

        # --- Three primary tiles ---
        tile_live   = _Tile("Live TV",  "\U0001F4FA", self, big=True)  # 📺
        tile_movies = _Tile("Movies",   "\U0001F3AC", self, big=True)  # 🎬
        tile_series = _Tile("Series",   "\U0001F39E", self, big=True)  # 🎞
        tile_live.clicked.connect(lambda: self.tile_clicked.emit('LIVE'))
        tile_movies.clicked.connect(lambda: self.tile_clicked.emit('Movies'))
        tile_series.clicked.connect(lambda: self.tile_clicked.emit('Series'))

        primary_row = QHBoxLayout()
        primary_row.setSpacing(28)
        primary_row.addStretch(1)
        primary_row.addWidget(tile_live)
        primary_row.addWidget(tile_movies)
        primary_row.addWidget(tile_series)
        primary_row.addStretch(1)

        # --- Two secondary tiles ---
        tile_links    = _Tile("Links",    "🔗", self, big=False)
        tile_settings = _Tile("Settings", "⚙",  self, big=False)
        tile_links.clicked.connect(lambda: self.tile_clicked.emit('Info'))
        tile_settings.clicked.connect(lambda: self.tile_clicked.emit('Settings'))

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(14)
        secondary_row.addStretch(1)
        secondary_row.addWidget(tile_links)
        secondary_row.addWidget(tile_settings)
        secondary_row.addStretch(1)

        # --- Bottom-left exit ---
        exit_btn = QPushButton("Exit")
        exit_btn.setObjectName("homeExit")
        exit_btn.setCursor(Qt.PointingHandCursor)
        exit_btn.setFocusPolicy(Qt.NoFocus)
        exit_btn.clicked.connect(self.exit_clicked.emit)

        bottom_left = QHBoxLayout()
        bottom_left.addWidget(exit_btn)
        bottom_left.addStretch(1)

        # --- Main layout ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)
        layout.addLayout(top_right)
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch(1)
        layout.addLayout(primary_row)
        layout.addSpacing(12)
        layout.addLayout(secondary_row)
        layout.addStretch(2)
        layout.addLayout(bottom_left)


    def _on_style_picked(self, value):
        self._style_value = value
        self.style_btn.setText(f"Theme: {value}")
        self.theme_changed.emit(value)

    def set_theme(self, effective):
        """Switch the HomeScreen stylesheet based on the resolved theme.
        `effective` is "Light" or "Dark" — the host must resolve "System"
        before calling this."""
        if effective == "Light":
            self._effective_theme = "Light"
            self.setStyleSheet(_HOME_STYLE_LIGHT)
        else:
            self._effective_theme = "Dark"
            self.setStyleSheet(_HOME_STYLE_DARK)


class _BackBar(QWidget):
    """Top strip with a Back arrow + screen title. Used by all non-home screens."""
    back_clicked = pyqtSignal()

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(_BACK_STYLE)
        self.setFixedHeight(56)

        back = QPushButton("◀  Back")
        back.setObjectName("backButton")
        back.setCursor(Qt.PointingHandCursor)
        back.setFocusPolicy(Qt.NoFocus)
        back.clicked.connect(self.back_clicked.emit)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("browseHeader")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.addWidget(back)
        layout.addSpacing(14)
        layout.addWidget(self.title_label, 1)

    def set_title(self, text):
        self.title_label.setText(text)

    def set_theme(self, effective):
        self.setStyleSheet(_BACK_STYLE_LIGHT if effective == "Light" else _BACK_STYLE)


_BROWSE_STYLE_LIGHT = """
QWidget#browseScreen { background: #eceff4; }
QLabel#browseHeader {
    color: #2e3440;
    font-size: 24px;
    font-weight: 500;
    padding-left: 8px;
}
"""

_BACK_STYLE_LIGHT = """
QPushButton#backButton {
    background: #e5e9f0;
    color: #2e3440;
    border: 1px solid #c5cad3;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 15px;
}
QPushButton#backButton:hover { background: #5e81ac; color: #eceff4; }
"""


class BrowseScreen(QWidget):
    """Hosts a V2 category list + streaming list + info pane as a full screen.

    The host app injects the existing V2 widgets via `set_content(...)` —
    we don't recreate any of the channel-list logic, we just give it a
    dedicated screen instead of a tab.
    """
    back_clicked = pyqtSignal()

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("browseScreen")
        self.setStyleSheet(_BROWSE_STYLE)

        self.bar = _BackBar(title, self)
        self.bar.back_clicked.connect(self.back_clicked.emit)

        self.body_holder = QWidget(self)
        self.body_layout = QVBoxLayout(self.body_holder)
        self.body_layout.setContentsMargins(20, 0, 20, 20)
        self.body_layout.setSpacing(10)

        self._init_status_bar()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.bar)
        layout.addWidget(self.body_holder, 1)

    def set_content(self, widget, title=""):
        if title:
            self.bar.set_title(title)
        # Detach previous content.
        while self.body_layout.count():
            it = self.body_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
        widget.setParent(self.body_holder)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        widget.show()
        self.body_layout.addWidget(widget, 1)
        self.body_layout.addWidget(self._status_bar)  # always last

    def set_status(self, text):
        """Show a diagnostic message in the status bar at the bottom."""
        if not text:
            self._status_bar.hide()
            return
        self._status_lbl.setText(text)
        self._status_bar.show()
        # Auto-clear non-error messages after 4 s
        if not any(w in text.lower() for w in ('error', 'fail', 'timeout', 'lost', 'invalid')):
            self._status_timer.start(4000)
        else:
            self._status_timer.stop()
        # Colour: red for errors, amber for warnings, grey for info
        if any(w in text.lower() for w in ('error', 'fail', 'timeout', 'invalid')):
            colour = "rgba(220,60,60,200)"
        elif any(w in text.lower() for w in ('connect', 'loading', 'fetching', 'wait')):
            colour = "rgba(100,160,240,200)"
        else:
            colour = "rgba(160,160,160,180)"
        self._status_lbl.setStyleSheet(
            f"color: {colour}; font-size: 11px; padding: 0 8px;")

    def _init_status_bar(self):
        self._status_bar = QWidget(self)
        self._status_bar.setFixedHeight(22)
        self._status_bar.setStyleSheet(
            "background: rgba(0,0,0,120); border-top: 1px solid rgba(255,255,255,15);")
        sl = QHBoxLayout(self._status_bar)
        sl.setContentsMargins(6, 0, 6, 0)
        sl.setSpacing(0)
        self._status_lbl = QLabel("", self._status_bar)
        self._status_lbl.setStyleSheet("color: rgba(160,160,160,180); font-size: 11px; padding: 0 8px;")
        sl.addWidget(self._status_lbl)
        self._status_bar.hide()
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(lambda: self.set_status(""))

    def set_theme(self, effective):
        if effective == "Light":
            self.setStyleSheet(_BROWSE_STYLE_LIGHT)
        else:
            self.setStyleSheet(_BROWSE_STYLE)
        self.bar.set_theme(effective)


class _FlatIconBtn(QLabel):
    """Transparent icon button using QLabel + mouse events.

    QPushButton cannot be made truly transparent on Windows — Fusion style always
    paints a platform-specific background for hover/focus states regardless of CSS
    or setFlat().  QLabel with background:transparent works reliably because it
    doesn't go through QStyle's button-chrome rendering path.
    """
    clicked = pyqtSignal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: transparent; color: white;")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)
        self._pressed = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.setStyleSheet("background: transparent; color: rgba(255,255,255,170);")
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setStyleSheet("background: transparent; color: white;")
            if self._pressed and self.rect().contains(event.pos()):
                self.clicked.emit()
            self._pressed = False
        super().mouseReleaseEvent(event)

class _CloseBtn(QWidget):
    """Elegant circular close button — draws a rounded rect with an × inside.
    Used for the mini player dismiss button (top-right corner)."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(28, 28)
        self._hovered = False
        self._pressed = False
        self.setMouseTracking(True)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPainterPath, QColor, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        # Background circle
        if self._pressed:
            bg = QColor(220, 50, 50, 220)
        elif self._hovered:
            bg = QColor(180, 40, 40, 180)
        else:
            bg = QColor(60, 60, 60, 140)
        path = QPainterPath()
        path.addEllipse(1, 1, w - 2, h - 2)
        p.fillPath(path, bg)
        # × cross
        pen = QPen(QColor(255, 255, 255, 230))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        m = 8
        p.drawLine(m, m, w - m, h - m)
        p.drawLine(w - m, m, m, h - m)
        p.end()

    def enterEvent(self, e):   self._hovered = True;  self.update(); super().enterEvent(e)
    def leaveEvent(self, e):   self._hovered = False; self._pressed = False; self.update(); super().leaveEvent(e)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True; self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            fired = self._pressed and self.rect().contains(event.pos())
            self._pressed = False; self.update()
            if fired:
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class _MiniOverlay(QWidget):
    """Separate transparent top-level window that floats over MiniPlayerWindow.

    WA_TranslucentBackground enables DWM composition on Windows so the video
    shows through every unpainted pixel — buttons appear as pure floating icons.
    nativeEvent returns HTTRANSPARENT for the non-button area so all clicks and
    hover events pass through to MiniPlayerWindow's WM_NCHITTEST handler (drag,
    resize, wake).  HTCLIENT is returned only for actual button areas so Qt
    dispatches those clicks to the buttons normally.
    """

    play_clicked   = pyqtSignal()
    mute_clicked   = pyqtSignal()
    expand_clicked = pyqtSignal()

    def __init__(self, mini_win):
        super().__init__(None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._mini_win = mini_win
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_NoMousePropagation, False)
        self.setWindowOpacity(1.0)

        self._btn_mute  = _FlatIconBtn("\U0001f50a", self)
        self._btn_play  = _FlatIconBtn("⏸",         self)
        self._btn_close = _CloseBtn(self)
        for b in (self._btn_mute, self._btn_play):
            f = b.font(); f.setPointSize(22); b.setFont(f)
            b.setFocusPolicy(Qt.NoFocus)
        self._btn_close.setFocusPolicy(Qt.NoFocus)
        self._btn_mute.setToolTip("Mute / Unmute")
        self._btn_play.setToolTip("Play / Pause")
        self._btn_close.setToolTip("Return to normal player")
        self._btn_mute.clicked.connect(self.mute_clicked)
        self._btn_play.clicked.connect(self.play_clicked)
        self._btn_close.clicked.connect(self.expand_clicked)

        self._htimer = QTimer(self)
        self._htimer.setSingleShot(True)
        self._htimer.timeout.connect(self.hide)

    # ---------------------------------------------------------------- sync
    def sync(self):
        """Match geometry exactly to the mini player window (full coverage).
        The CompositionMode_Clear paintEvent ensures truly transparent alpha
        everywhere there's no button — no black box."""
        if self._mini_win:
            self.setGeometry(self._mini_win.geometry())
            self._reposition()
            if self.isVisible():
                self.raise_()

    def _reposition(self):
        bw, bh = 44, 44
        gap = 12
        cw = self._btn_close.width()
        ch = self._btn_close.height()
        # ✕ — top-right corner
        self._btn_close.move(self.width() - cw - 8, 8)
        # mute + play — centered horizontally at bottom
        total = bw * 2 + gap
        x = (self.width() - total) // 2
        y = self.height() - bh - 14
        self._btn_mute.setGeometry(x,            y, bw, bh)
        self._btn_play.setGeometry(x + bw + gap, y, bw, bh)

    def wake(self):
        self.sync()
        self.show()
        self.raise_()
        self._htimer.start(1500)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition()

    def paintEvent(self, event):
        # Explicitly clear to transparent so DWM alpha is properly initialised.
        # paintEvent: pass leaves the alpha channel uninitialized on some Windows
        # configurations, rendering as opaque black where no button is painted.
        from PyQt5.QtGui import QPainter, QColor
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
        p.end()

    # --- pass non-button events through to the window beneath ---------------
    def nativeEvent(self, eventType, message):
        if sys.platform.startswith('win') and eventType == b'windows_generic_MSG':
            try:
                import ctypes, ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:   # WM_NCHITTEST
                    gx = ctypes.c_short(msg.lParam & 0xFFFF).value
                    gy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    pos = self.mapFromGlobal(QPoint(gx, gy))
                    for btn in (self._btn_mute, self._btn_play, self._btn_close):
                        if btn.geometry().contains(pos):
                            return True, 1    # HTCLIENT — button receives click
                    return True, -1           # HTTRANSPARENT — pass to video/drag
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def sync_icons(self, is_paused, is_muted):
        self._btn_play.setText("▶" if is_paused else "⏸")
        self._btn_mute.setText("\U0001f507" if is_muted else "\U0001f50a")


class MiniPlayerWindow(QWidget):
    """Chrome-PiP-style mini player.

    - Pure video, completely frameless.
    - On hover: 3 white icon buttons appear centered at the bottom:
        [🔇 mute]   [⏸ play/pause]   [⛶ expand]
      Transparent background, no colored backgrounds, auto-hide after 1.5s.
    - Expand resumes the normal player (stream keeps playing, no stop).
    - Drag: anywhere on video.
    - Resize: QApplication event filter (works with VLC's child HWND);
      always AR-constrained.
    """

    expand_requested = pyqtSignal()   # expand → restore normal player

    _E = 8   # resize edge margin px

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMinimumSize(160, 90)
        self.resize(400, 225)
        self.setStyleSheet("background: black;")

        self._tv_root     = None
        self._ar          = 16 / 9
        self._drag_pos    = None
        self._resize_edge = None
        self._resize_sgeo = None
        self._resize_spos = None

        # Video host — fills entire window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._vhost = QWidget(self)
        self._vhost.setStyleSheet("background: black;")
        vh = QVBoxLayout(self._vhost)
        vh.setContentsMargins(0, 0, 0, 0)
        vh.setSpacing(0)
        lay.addWidget(self._vhost, 1)

        # Separate DWM-transparent overlay window for buttons (no HWND painting)
        self._overlay = _MiniOverlay(self)
        self._overlay.play_clicked.connect(self._on_play)
        self._overlay.mute_clicked.connect(self._on_mute)
        self._overlay.expand_clicked.connect(self.expand_requested.emit)

    # ----------------------------------------------------------------- attach
    def attach(self, tv_root):
        self._tv_root = tv_root
        tv_root._mini_mode = True
        # Hide AND park every TVRoot overlay far off-screen. hide() alone is
        # insufficient — resizeEvent or wake_chrome can race and re-raise them
        # before _mini_mode propagates, leaving visible boxes in the PiP window.
        # Detach ALL overlay widgets from TVRoot's HWND tree entirely.
        # hide()/move()/resize() are not enough — Qt can still paint them
        # and VLC's DirectX z-ordering can let them bleed through.
        # setParent(None) is the only guaranteed removal from the tree.
        self._mini_orphaned = {}
        for attr in ('controls', 'hamburger', 'menu', 'edge_trigger',
                     'playlist_panel', '_sub_hide_strip'):
            try:
                w = getattr(tv_root, attr)
                w.hide()
                w.setParent(None)   # fully detach from TVRoot's HWND tree
                self._mini_orphaned[attr] = w
            except Exception:
                pass
        tv_root._hide_timer.stop()
        QApplication.instance().processEvents()
        # Reset VLC crop/scale so the video letterboxes naturally in mini mode
        try:
            tv_root.player.video_set_aspect_ratio(None)
            tv_root.player.video_set_crop_geometry(None)
            tv_root.player.video_set_scale(0)
        except Exception:
            pass
        # Reparent TVRoot into the video host (VLC keeps playing)
        lay = self._vhost.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        tv_root.setParent(self._vhost)
        tv_root.show()
        lay.addWidget(tv_root, 1)
        # Re-bind VLC to the new native HWND — setParent() on Windows destroys
        # and recreates the underlying HWND, so libvlc's render handle is stale
        # (audio plays but video is black). Force rebind without restarting stream.
        try:
            tv_root._bound = False
            tv_root._bind_video_output()
        except Exception:
            pass
        self._sync_icons()
        # Wire TVRoot mouse-move → wake overlay
        tv_root._mini_wake_cb = self._wake
        # AR from _poll_state
        ar = getattr(tv_root, '_video_ar', None)
        if ar and ar > 0.2:
            self._ar = ar
        self.resize(self.width(), max(90, int(self.width() / self._ar)))
        # Install event filter on video_frame for Qt-level drag — same mechanism
        # TVRoot already uses for _wake_chrome, guaranteed to receive mouse events
        # even through VLC's DirectX child HWND.
        # Allow TVRoot and video_frame to shrink to any size — Qt layouts otherwise
        # enforce an implicit minimum from sizeHint, which stops VLC scaling below
        # roughly 480p and causes cropping on further resize.
        try:
            tv_root.setMinimumSize(0, 0)
            tv_root.video_frame.setMinimumSize(0, 0)
        except Exception:
            pass
        # Clear any BlankCursor Qt set during _hide_chrome so resize cursors show
        try:
            tv_root.video_frame.unsetCursor()
        except Exception:
            pass
        tv_root.video_frame.installEventFilter(self)
        self._filtered_vf = tv_root.video_frame
        # Also install WM_NCHITTEST hook for native resize (best-effort)
        QTimer.singleShot(300, tv_root.install_mini_hittest_hook)

    def detach(self):
        self._overlay.hide()
        if self._tv_root is None:
            return None
        tv = self._tv_root
        self._tv_root = None
        tv._mini_mode    = False
        tv._mini_wake_cb = None
        try:
            if getattr(self, '_filtered_vf', None):
                self._filtered_vf.removeEventFilter(self)
                self._filtered_vf = None
        except Exception:
            pass
        self._drag_pos = None
        tv.uninstall_mini_hittest_hook()
        # Re-parent overlay widgets back into TVRoot so the normal player works
        for attr, w in getattr(self, '_mini_orphaned', {}).items():
            try:
                w.setParent(tv)
                w.setUpdatesEnabled(True)
            except Exception:
                pass
        self._mini_orphaned = {}
        try:
            tv._sub_hide_strip.resize(640, 60)
        except Exception:
            pass
        lay = self._vhost.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        return tv  # caller restores chrome AFTER reparenting to avoid freeze

    # ----------------------------------------------------------------- buttons
    def _on_play(self):
        if not self._tv_root:
            return
        self._tv_root.toggle_play_pause()
        self._sync_icons()

    def _on_mute(self):
        if not self._tv_root:
            return
        self._tv_root.toggle_mute()
        self._sync_icons()

    def _sync_icons(self):
        if not self._tv_root:
            return
        self._overlay.sync_icons(
            getattr(self._tv_root, '_is_paused', False),
            getattr(self._tv_root, '_is_muted',  False))

    # -------------------------------------------------------------- overlay
    def _wake(self):
        self._overlay.wake()

    # ---------------------------------------------------------------- layout
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.sync()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._overlay.sync()   # keep overlay aligned during native HTCAPTION drag

    _EDGE_CURSORS = {
        'L': Qt.SizeHorCursor,  'R': Qt.SizeHorCursor,
        'T': Qt.SizeVerCursor,  'B': Qt.SizeVerCursor,
        'TL': Qt.SizeFDiagCursor, 'BR': Qt.SizeFDiagCursor,
        'TR': Qt.SizeBDiagCursor, 'BL': Qt.SizeBDiagCursor,
    }
    _E = 10   # resize edge zone px

    def _edge_at(self, gpos):
        lp = self.mapFromGlobal(gpos)
        m, w, h = self._E, self.width(), self.height()
        L = lp.x() < m;  R = lp.x() > w - m
        T = lp.y() < m;  B = lp.y() > h - m
        if L and T: return 'TL'
        if R and T: return 'TR'
        if L and B: return 'BL'
        if R and B: return 'BR'
        if L: return 'L'
        if R: return 'R'
        if T: return 'T'
        if B: return 'B'
        return None

    def _do_resize(self, gpos):
        e = self._resize_edge
        dx = gpos.x() - self._resize_spos.x()
        dy = gpos.y() - self._resize_spos.y()
        g  = QRect(self._resize_sgeo)
        ar = self._ar
        mw, mh = 160, 90
        # Width leads for L/R/corners; height leads for T/B
        if 'R' in e:
            nw = max(mw, g.width() + dx)
        elif 'L' in e:
            nw = max(mw, g.width() - dx)
        else:
            nh = max(mh, g.height() + (dy if 'B' in e else -dy))
            nw = max(mw, int(nh * ar))
        nh = max(mh, int(nw / ar))
        nw = max(mw, int(nh * ar))
        if 'L' in e: g.setLeft(g.right()   - nw)
        else:         g.setRight(g.left()   + nw)
        if 'T' in e: g.setTop(g.bottom()   - nh)
        else:         g.setBottom(g.top()   + nh)
        self.setGeometry(g)
        # Tell VLC to re-scale to the new window size; without this VLC keeps
        # its previous render dimensions and the window crops below ~480p.
        if self._tv_root:
            try:
                self._tv_root.player.video_set_scale(0)
            except Exception:
                pass

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        et = event.type()
        gp = getattr(event, 'globalPos', lambda: None)()

        if et == QEvent.MouseMove:
            if not gp:
                return False
            if self._resize_edge and (event.buttons() & Qt.LeftButton):
                self._do_resize(gp)
                self._overlay.sync()
                return True
            if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
                self.move(gp - self._drag_pos)
                self._overlay.sync()
                return True
            edge = self._edge_at(gp)
            self.setCursor(self._EDGE_CURSORS[edge]) if edge else self.unsetCursor()
            return False

        if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            if not gp:
                return False
            edge = self._edge_at(gp)
            if edge:
                self._resize_edge = edge
                self._resize_sgeo = self.geometry()
                self._resize_spos = gp
            else:
                self._drag_pos = gp - self.frameGeometry().topLeft()
            return True

        if et == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            self._drag_pos = self._resize_edge = self._resize_sgeo = self._resize_spos = None
            return False

        return False

    def showEvent(self, event):
        super().showEvent(event)
        self._overlay.sync()
        self._overlay.show()
        self._overlay.raise_()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._overlay.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self._on_play(); event.accept()
        else:
            super().keyPressEvent(event)

    # --- native drag + AR-constrained resize via WM_NCHITTEST / WM_SIZING ---
    # VLC's DirectX child HWND intercepts WM_NCHITTEST before Qt sees it.
    # The install_mini_hittest_hook() on TVRoot forwards WM_NCHITTEST from
    # VLC's child HWND to this window so these handlers actually fire.
    def nativeEvent(self, eventType, message):
        if sys.platform.startswith('win') and eventType == b'windows_generic_MSG':
            try:
                import ctypes, ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))

                if msg.message == 0x0084:   # WM_NCHITTEST
                    gx = ctypes.c_short(msg.lParam & 0xFFFF).value
                    gy = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    pos = self.mapFromGlobal(QPoint(gx, gy))
                    # Button zone → HTCLIENT (Qt dispatches click normally)
                    for btn in (self._btn_mute, self._btn_play, self._btn_close):
                        if btn.geometry().contains(pos):
                            return True, 1   # HTCLIENT
                    m = self._E; w, h = self.width(), self.height()
                    L = pos.x() < m;  R = pos.x() > w - m
                    T = pos.y() < m;  B = pos.y() > h - m
                    if L and T: return True, 13   # HTTOPLEFT
                    if R and T: return True, 14   # HTTOPRIGHT
                    if L and B: return True, 16   # HTBOTTOMLEFT
                    if R and B: return True, 17   # HTBOTTOMRIGHT
                    if L:       return True, 10   # HTLEFT
                    if R:       return True, 11   # HTRIGHT
                    if T:       return True, 12   # HTTOP
                    if B:       return True, 15   # HTBOTTOM
                    # Video area → HTCAPTION: OS handles drag natively
                    return True, 2

                elif msg.message == 0x0214:  # WM_SIZING — enforce AR
                    ar   = self._ar
                    side = msg.wParam
                    rect = ctypes.wintypes.RECT.from_address(msg.lParam)
                    w = rect.right  - rect.left
                    h = rect.bottom - rect.top
                    mw, mh = 160, 90
                    if side in (3, 6):          # top/bottom: height leads
                        nw = max(mw, int(h * ar))
                        if side == 3: rect.left = rect.right - nw
                        else:         rect.right = rect.left + nw
                    else:                       # sides/corners: width leads
                        nh = max(mh, int(w / ar))
                        if side in (4, 5, 3):   # top corners/edge: keep bottom
                            rect.top = rect.bottom - nh
                        else:                   # bottom corners/edge: keep top
                            rect.bottom = rect.top + nh
                    return True, 1
            except Exception:
                pass
        return super().nativeEvent(eventType, message)


class PlayerScreen(QWidget):
    """Full-bleed player screen — video fills 100% of the window, no surrounding
    margins or back bar eating space. A small floating Back button sits in the
    top-left corner; it auto-hides with the rest of the player chrome.
    """
    back_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: black;")
        self._tv_root = None
        self._mini_win = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Body host — the TVRoot will be reparented into this on demand.
        self.video_host = QWidget(self)
        host_lay = QVBoxLayout(self.video_host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        host_lay.setSpacing(0)
        layout.addWidget(self.video_host)

        # Floating back button overlay.
        self.back_btn = QPushButton("◀  Back", self)
        self.back_btn.setAttribute(Qt.WA_TranslucentBackground, True)
        self.back_btn.setStyleSheet(
            "QPushButton { background: rgba(46,52,64,210); color: #eceff4;"
            " border: 1px solid rgba(216,222,233,60); border-radius: 8px;"
            " padding: 8px 14px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(94,129,172,220); }"
        )
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.setFocusPolicy(Qt.NoFocus)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        self.back_btn.raise_()

    def set_video(self, tv_root):
        self._tv_root = tv_root
        # Replace any previous video widget.
        host_lay = self.video_host.layout()
        while host_lay.count():
            it = host_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
        tv_root.setParent(self.video_host)
        tv_root.show()
        host_lay.addWidget(tv_root, 1)
        # Wire the mini-player button on TVRoot to this screen's toggle
        tv_root.set_mini_player_callback(self.toggle_mini_player)

    def toggle_mini_player(self):
        """Enter or exit mini-player mode."""
        if self._mini_win is not None and self._mini_win.isVisible():
            self._exit_mini()
        else:
            self._enter_mini()

    def set_go_home_callback(self, cb):
        """Called by the host app so _exit_mini can navigate home."""
        self._go_home_cb = cb

    def _enter_mini(self):
        if self._tv_root is None:
            return
        if self._mini_win is None:
            self._mini_win = MiniPlayerWindow()
            self._mini_win.expand_requested.connect(self._exit_mini)
        # Use the screen where the main window currently lives, not primaryScreen
        main = self.window()
        cur_screen = (QApplication.screenAt(main.geometry().center())
                      if main else None) or QApplication.primaryScreen()
        screen_geo = cur_screen.availableGeometry()

        # Size: half the main window's width, height from AR
        target_w = max(240, (main.width() if main else 800) // 2)
        self._mini_win.resize(target_w, target_w)  # attach() will correct height
        self._mini_win.attach(self._tv_root)        # snaps to real AR

        self._mini_win.move(
            screen_geo.right()  - self._mini_win.width()  - 100,
            screen_geo.bottom() - self._mini_win.height() - 100,
        )
        self._mini_win.show()
        self._mini_win.raise_()
        main = self.window()
        if main:
            main.showMinimized()

    def _exit_mini(self):
        """Expand: detach TVRoot, restore it to this screen, resume playing."""
        if self._mini_win is None:
            return
        tv = self._mini_win.detach()
        self._mini_win.hide()
        if tv is not None:
            # Re-host TVRoot in this PlayerScreen (stream was never stopped)
            host_lay = self.video_host.layout()
            while host_lay.count():
                it = host_lay.takeAt(0)
                if it.widget():
                    it.widget().setParent(None)
            tv.setParent(self.video_host)
            tv.show()
            host_lay.addWidget(tv, 1)
            # Restore chrome NOW that TVRoot has a real parent again —
            # doing it before reparenting (in detach) caused a freeze because
            # Qt tried to repaint controls on a parentless top-level widget.
            tv.controls.show()
            tv._wake_chrome()
            # Defer VLC rebind after window is shown (avoids brief UI block)
            _tv = tv
            QTimer.singleShot(80, lambda: (
                setattr(_tv, '_bound', False) or _tv._bind_video_output()
            ))
        # Restore and focus the main window, staying on the player screen
        main = self.window()
        if main:
            main.showNormal()
            main.raise_()
            main.activateWindow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.back_btn.adjustSize()
        self.back_btn.move(14, 14)
        self.back_btn.raise_()

    def set_chrome_visible(self, visible):
        if visible:
            self.back_btn.show()
        else:
            self.back_btn.hide()


class TVScreenStack(QStackedWidget):
    """QStackedWidget with push / pop semantics and a slide animation.

    The first widget added (the home screen) is pinned at index 0. push()
    appends a screen and animates the transition to it from the right.
    pop() animates the reverse and removes the top screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim = None

    def push(self, widget, animated=True):
        self.addWidget(widget)
        if animated and self.count() > 1:
            self._slide_to(self.count() - 1, direction='left')
        else:
            self.setCurrentIndex(self.count() - 1)

    def pop(self, animated=True):
        if self.count() <= 1:
            return
        old_idx = self.count() - 1
        if animated:
            self._slide_to(old_idx - 1, direction='right', remove_after=old_idx)
        else:
            self.setCurrentIndex(old_idx - 1)
            w = self.widget(old_idx)
            self.removeWidget(w)
            w.deleteLater()

    def reset_to_home(self):
        while self.count() > 1:
            w = self.widget(self.count() - 1)
            self.removeWidget(w)
            w.deleteLater()
        self.setCurrentIndex(0)

    def _slide_to(self, target_idx, direction='left', remove_after=None):
        cur = self.currentWidget()
        new = self.widget(target_idx)
        if cur is None or new is None or cur is new:
            self.setCurrentIndex(target_idx)
            return

        w = self.width()
        offset = w if direction == 'left' else -w
        new.setGeometry(offset, 0, w, self.height())
        new.show()
        new.raise_()

        anim_new = QPropertyAnimation(new, b"pos", self)
        anim_new.setDuration(280)
        anim_new.setEasingCurve(QEasingCurve.OutCubic)
        anim_new.setStartValue(QPoint(offset, 0))
        anim_new.setEndValue(QPoint(0, 0))

        anim_old = QPropertyAnimation(cur, b"pos", self)
        anim_old.setDuration(280)
        anim_old.setEasingCurve(QEasingCurve.OutCubic)
        anim_old.setStartValue(QPoint(0, 0))
        anim_old.setEndValue(QPoint(-offset, 0))

        def _finalize():
            self.setCurrentIndex(target_idx)
            cur.move(0, 0)
            if remove_after is not None:
                w = self.widget(remove_after)
                if w is not None:
                    self.removeWidget(w)
                    w.deleteLater()

        anim_new.finished.connect(_finalize)
        anim_new.start()
        anim_old.start()
        # Keep refs so they don't get GC'd mid-animation.
        self._anim = (anim_new, anim_old)
