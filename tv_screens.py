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

from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QSplitter, QSizePolicy, QComboBox,
    QMenu, QAction, QSizeGrip,
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

    def set_theme(self, effective):
        if effective == "Light":
            self.setStyleSheet(_BROWSE_STYLE_LIGHT)
        else:
            self.setStyleSheet(_BROWSE_STYLE)
        self.bar.set_theme(effective)


class MiniPlayerWindow(QWidget):
    """Compact floating player: frameless, always-on-top, freely resizable.

    Reparents the live TVRoot widget (with its playing VLC instance) into
    itself so the stream never drops.  The host app hands the TVRoot over
    with `attach()` and gets it back with `detach()` when the user exits.

    The window has no title bar — the user drags it by pressing anywhere on
    the dark overlay strip at the top.  Three micro-buttons sit in that
    strip: play/pause, mute, and ✕ (return to normal player).
    """

    exit_requested = pyqtSignal()   # user clicked ✕ → host should call detach()

    _BAR_H = 36          # height of the drag strip / button bar

    _STYLE = """
    MiniPlayerWindow {
        background: black;
        border: 1px solid rgba(255,255,255,30);
        border-radius: 6px;
    }
    QWidget#miniBar {
        background: rgba(20,20,28,220);
        border-bottom: 1px solid rgba(255,255,255,20);
    }
    QPushButton#miniBtn {
        background: rgba(255,255,255,15);
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 16px;
        padding: 2px 8px;
        min-width: 30px;
        min-height: 26px;
    }
    QPushButton#miniBtn:hover { background: rgba(94,129,172,200); }
    QPushButton#miniExitBtn {
        background: rgba(191,97,106,180);
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 13px;
        font-weight: bold;
        padding: 2px 8px;
        min-width: 30px;
        min-height: 26px;
    }
    QPushButton#miniExitBtn:hover { background: rgba(220,80,90,220); }
    """

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMinimumSize(200, 150)
        self.resize(400, 260)
        self.setStyleSheet(self._STYLE)
        self._tv_root = None
        self._drag_pos = None

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # --- top drag/button bar ---
        self._bar = QWidget(self)
        self._bar.setObjectName("miniBar")
        self._bar.setFixedHeight(self._BAR_H)
        bar_lay = QHBoxLayout(self._bar)
        bar_lay.setContentsMargins(6, 4, 6, 4)
        bar_lay.setSpacing(4)

        self._btn_play = QPushButton("⏯")
        self._btn_play.setObjectName("miniBtn")
        self._btn_play.setToolTip("Play / Pause  (Space)")
        self._btn_play.setFocusPolicy(Qt.NoFocus)
        self._btn_play.clicked.connect(self._on_play)

        self._btn_mute = QPushButton("\U0001f50a")   # 🔊
        self._btn_mute.setObjectName("miniBtn")
        self._btn_mute.setToolTip("Mute / Unmute")
        self._btn_mute.setFocusPolicy(Qt.NoFocus)
        self._btn_mute.clicked.connect(self._on_mute)

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("color: rgba(216,222,233,180); font-size: 12px;")
        self._lbl_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._lbl_title.setAlignment(Qt.AlignCenter)

        self._btn_exit = QPushButton("✕  Normal player")
        self._btn_exit.setObjectName("miniExitBtn")
        self._btn_exit.setToolTip("Return to normal player")
        self._btn_exit.setFocusPolicy(Qt.NoFocus)
        self._btn_exit.clicked.connect(self.exit_requested.emit)

        bar_lay.addWidget(self._btn_play)
        bar_lay.addWidget(self._btn_mute)
        bar_lay.addWidget(self._lbl_title, 1)
        bar_lay.addWidget(self._btn_exit)

        # --- video host ---
        self._video_host = QWidget(self)
        self._video_host.setStyleSheet("background: black;")
        vh_lay = QVBoxLayout(self._video_host)
        vh_lay.setContentsMargins(0, 0, 0, 0)
        vh_lay.setSpacing(0)

        # --- resize grip (bottom-right corner) ---
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)

        root_lay.addWidget(self._bar)
        root_lay.addWidget(self._video_host, 1)

    def attach(self, tv_root):
        """Reparent tv_root into this window (keeps the VLC stream alive)."""
        self._tv_root = tv_root
        lay = self._video_host.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        tv_root.setParent(self._video_host)
        tv_root.show()
        lay.addWidget(tv_root, 1)
        # Suppress normal chrome (controls bar, hamburger) — the mini bar
        # provides its own play/mute.  TVRoot's internal chrome was already
        # disabled by the host, so we only need to hide the controls widget.
        tv_root.controls.hide()
        tv_root._hide_timer.stop()
        # Sync mute icon to current state
        self._sync_mute_icon()
        self._lbl_title.setText(getattr(tv_root, '_current_title', '') or '')

    def detach(self):
        """Remove tv_root from this window and return it; caller re-hosts it."""
        if self._tv_root is None:
            return None
        tv = self._tv_root
        self._tv_root = None
        lay = self._video_host.layout()
        while lay.count():
            it = lay.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
        # Restore normal chrome auto-hide behaviour
        tv.controls.show()
        tv._wake_chrome()
        return tv

    # ---------------------------------------------------------------- buttons
    def _on_play(self):
        if self._tv_root:
            self._tv_root.toggle_play_pause()
            playing = not getattr(self._tv_root, '_is_paused', False)
            self._btn_play.setText("⏯" if playing else "▶")

    def _on_mute(self):
        if self._tv_root:
            self._tv_root.toggle_mute()
            self._sync_mute_icon()

    def _sync_mute_icon(self):
        if self._tv_root:
            muted = getattr(self._tv_root, '_is_muted', False)
            self._btn_mute.setText("\U0001f507" if muted else "\U0001f50a")

    # -------------------------------------------------------- frameless drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._bar.geometry().contains(event.pos()):
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep grip anchored to bottom-right
        self._grip.move(self.width() - self._grip.width(),
                        self.height() - self._grip.height())
        self._grip.raise_()

    def keyPressEvent(self, event):
        if self._tv_root and event.key() == Qt.Key_Space:
            self._on_play()
            event.accept()
        else:
            super().keyPressEvent(event)


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

    def _enter_mini(self):
        if self._tv_root is None:
            return
        if self._mini_win is None:
            self._mini_win = MiniPlayerWindow()
            self._mini_win.exit_requested.connect(self._exit_mini)
        # Position near the bottom-right of the screen
        from PyQt5.QtWidgets import QApplication
        screen_geo = QApplication.primaryScreen().availableGeometry()
        self._mini_win.move(screen_geo.right() - self._mini_win.width() - 24,
                            screen_geo.bottom() - self._mini_win.height() - 24)
        self._mini_win.attach(self._tv_root)
        self._mini_win.show()
        self._mini_win.raise_()
        # Show a placeholder in the main window so it doesn't go black
        self._placeholder_lbl = QLabel("Mini-player active", self.video_host)
        self._placeholder_lbl.setAlignment(Qt.AlignCenter)
        self._placeholder_lbl.setStyleSheet(
            "color: rgba(216,222,233,120); font-size: 18px; background: black;")
        self._placeholder_lbl.setGeometry(self.video_host.rect())
        self._placeholder_lbl.show()

    def _exit_mini(self):
        if self._mini_win is None:
            return
        tv = self._mini_win.detach()
        self._mini_win.hide()
        if tv is not None:
            # Restore TVRoot into this screen's host
            host_lay = self.video_host.layout()
            while host_lay.count():
                it = host_lay.takeAt(0)
                if it.widget():
                    it.widget().setParent(None)
            tv.setParent(self.video_host)
            tv.show()
            host_lay.addWidget(tv, 1)
        # Remove placeholder
        pl = getattr(self, '_placeholder_lbl', None)
        if pl:
            pl.deleteLater()
            self._placeholder_lbl = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.back_btn.adjustSize()
        self.back_btn.move(14, 14)
        self.back_btn.raise_()
        pl = getattr(self, '_placeholder_lbl', None)
        if pl:
            pl.setGeometry(self.video_host.rect())

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
