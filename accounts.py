import sys
import os
from os import path
import time
import requests
import subprocess
import configparser

def _make_config():
    """ConfigParser that preserves key case (default lowercases everything)."""
    c = configparser.ConfigParser()
    c.optionxform = str
    return c
import re
import json
import html
from lxml import etree, html
from datetime import datetime
from dateutil import parser, tz
import xml.etree.ElementTree as ET
from PyQt5.QtGui import QIcon, QFont, QImage, QPixmap, QColor
from PyQt5.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QObject, pyqtSignal, 
    QRunnable, pyqtSlot, QThreadPool, QModelIndex, QAbstractItemModel, QVariant
)
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QPushButton,
    QListWidget, QWidget, QFileDialog, QCheckBox, QSizePolicy, QHBoxLayout,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget, QListWidgetItem,
    QSpinBox, QMenu, QAction, QTextEdit, QGridLayout, QMessageBox, QListView,
    QTreeWidget, QTreeWidgetItem, QTreeView
)

class AccountManager(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IPTV accounts")
        self.setMinimumSize(400, 300)
        self.parent = parent

        account_manager_layout = QtWidgets.QGridLayout(self)

        #Create startup account label with options widget
        self.startup_account_label = QLabel("Startup account:")

        self.startup_account_options = QtWidgets.QComboBox()
        self.startup_account_options.currentTextChanged.connect(self.set_startup_credentials)

        #Create accounts list
        self.accounts_list = QtWidgets.QListWidget()
        self.accounts_list.itemDoubleClicked.connect(self.double_click_account)

        #Create buttons for adding, selecting and deleting accounts
        self.add_button = QPushButton("Add")
        self.add_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.add_button.clicked.connect(self.add_account)

        self.select_button = QPushButton("Select")
        self.select_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogYesButton))
        self.select_button.clicked.connect(self.select_account)

        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_FileDialogDetailedView))
        self.edit_button.clicked.connect(self.edit_account)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        self.delete_button.clicked.connect(self.delete_account)

        #Add widgets to layout
        account_manager_layout.addWidget(self.startup_account_label,        0, 0)
        account_manager_layout.addWidget(self.startup_account_options,      0, 1, 1, 2)
        account_manager_layout.addWidget(self.accounts_list,                1, 0, 1, 4)
        account_manager_layout.addWidget(self.add_button,                   2, 0)
        account_manager_layout.addWidget(self.select_button,                2, 1)
        account_manager_layout.addWidget(self.edit_button,                  2, 2)
        account_manager_layout.addWidget(self.delete_button,                2, 3)

        #Load saved accounts from .ini file
        self.load_saved_accounts()

    def set_startup_credentials(self):
        selected_item = self.startup_account_options.currentText()

        config = _make_config()
        config.read(self.parent.user_data_file)

        if 'Startup credentials' not in config:
            config['Startup credentials'] = {}

        config['Startup credentials']['startup_credentials'] = f"{selected_item}"

        with open(self.parent.user_data_file, 'w') as config_file:
            config.write(config_file)

    def load_saved_accounts(self):
        self.startup_account_options.currentTextChanged.disconnect(self.set_startup_credentials)

        self.accounts_list.clear()
        self.startup_account_options.clear()
        self.startup_account_options.addItem("None")

        config = _make_config()
        config.read(self.parent.user_data_file)

        if 'Credentials' in config:
            for key in config['Credentials']:
                self.accounts_list.addItem(key)
                self.startup_account_options.addItem(key)

        if 'Startup credentials' in config:
            selected_startup_credentials = config['Startup credentials']['startup_credentials']
            idx = self.startup_account_options.findText(f"{selected_startup_credentials}")
            self.startup_account_options.setCurrentIndex(idx)

        self.startup_account_options.currentTextChanged.connect(self.set_startup_credentials)

    def edit_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()
            config = _make_config()
            config.read(self.parent.user_data_file)

            if 'Credentials' in config and name in config['Credentials']:
                account_data = config['Credentials'][name]
                parts = account_data.split('|')
                method = parts[0]
                credentials = parts[1:]

                dialog = AccountDialog(self, AccountDialog.MODE_EDIT, (method, name, *credentials))

                if dialog.exec_() == QtWidgets.QDialog.Accepted:
                    updated_method, updated_name, *updated_credentials = dialog.get_credentials()

                    if updated_name:
                        # Create a dictionary with the updated credentials
                        credentials_dict = {
                            'method': updated_method,
                            'old_name': name,
                            'name': updated_name,
                            'credentials': updated_credentials
                        }
                        self.save_credentials(credentials_dict)
                        self.load_saved_accounts()

    def add_account(self):
        dialog = AccountDialog(self, AccountDialog.MODE_ADD)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            method, name, *credentials = dialog.get_credentials()

            if name:
                # Create a dictionary with the new credentials
                credentials_dict = {
                    'method': method,
                    'name': name,
                    'credentials': credentials
                }
                self.save_credentials(credentials_dict)
                self.load_saved_accounts()

    def save_credentials(self, credentials_dict):
        # Load the configuration file
        config = _make_config()
        config.read(self.parent.user_data_file)

        # Extract the credentials from the dictionary
        method = credentials_dict['method']
        name = credentials_dict['name']
        credentials = credentials_dict['credentials']

        # Remove the old name if it has been changed (renaming)
        if 'old_name' in credentials_dict:
            old_name = credentials_dict['old_name']
            if old_name != name and old_name in config['Credentials']:
                del config['Credentials'][old_name]
                # Update the startup credentials if the old name was used
                if 'Startup credentials' in config and config['Startup credentials']['startup_credentials'] == old_name:
                    config['Startup credentials']['startup_credentials'] = name

        # Ensure the 'Credentials' section exists
        if 'Credentials' not in config:
            config['Credentials'] = {}

        # Save the credentials
        if method == 'manual':
            server, username, password, live_url_format, movie_url_format, series_url_format = credentials
            config['Credentials'][name] = f"manual|{server}|{username}|{password}|{live_url_format}|{movie_url_format}|{series_url_format}"

        elif method == 'm3u_plus':
            m3u_url, live_url_format, movie_url_format, series_url_format = credentials
            config['Credentials'][name] = f"m3u_plus|{m3u_url}|{live_url_format}|{movie_url_format}|{series_url_format}"

        # Write the updated configuration back to the file
        with open(self.parent.user_data_file, 'w') as config_file:
            config.write(config_file)

    def select_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()

            config = _make_config()
            config.read(self.parent.user_data_file)

            if 'Credentials' in config and name in config['Credentials']:
                data = config['Credentials'][name]

                if data.startswith('manual|'):
                    _, server, username, password, live_url_format, movie_url_format, series_url_format = data.split('|', 6)
                    
                    self.parent.server            = server
                    self.parent.username          = username
                    self.parent.password          = password
                    self.parent.live_url_format   = live_url_format
                    self.parent.movie_url_format  = movie_url_format
                    self.parent.series_url_format = series_url_format

                    self.parent.login()

                elif data.startswith('m3u_plus|'):
                    _, m3u_url, live_url_format, movie_url_format, series_url_format = data.split('|')

                    self.parent.live_url_format   = live_url_format
                    self.parent.movie_url_format  = movie_url_format
                    self.parent.series_url_format = series_url_format

                    #Get credentials from M3U plus url and check if valid
                    if self.parent.extract_credentials_from_m3u_plus_url(m3u_url):
                        self.parent.login()

                self.accept()

    def double_click_account(self, item):
        self.select_account()
        self.accept()

    def delete_account(self):
        selected_item = self.accounts_list.currentItem()

        if selected_item:
            name = selected_item.text()

            config = _make_config()
            config.read(self.parent.user_data_file)

            if 'Credentials' in config and name in config['Credentials']:
                del config['Credentials'][name]

                # Update startup credentials if the deleted account was used for startup
                if 'Startup credentials' in config and config['Startup credentials']['startup_credentials'] == name:
                    config['Startup credentials']['startup_credentials'] = "None"

                with open(self.parent.user_data_file, 'w') as config_file:
                    config.write(config_file)

                self.load_saved_accounts()

class AccountDialog(QtWidgets.QDialog):
    MODE_ADD = "add"
    MODE_EDIT = "edit"

    def __init__(self, parent=None, mode=MODE_ADD, account=None):
        super().__init__(parent)
        self.parent = parent
        self.mode = mode
        self.account = account
        self.setWindowTitle("Edit Link" if self.mode == self.MODE_EDIT else "Add Link")
        self.setupUi()

    def setupUi(self):
        layout = QVBoxLayout(self)

        self.manual_entry_name    = "Xtream username + password"
        self.m3u_plus_entry_name  = "M3U-plus URL"
        self.m3u_file_entry_name  = "M3U file on disk"
        self.default_url_formats  = self.parent.parent.default_url_formats

        # Connection method
        self.method_selector = QtWidgets.QComboBox()
        self.method_selector.addItems([
            self.manual_entry_name,
            self.m3u_plus_entry_name,
            self.m3u_file_entry_name,
        ])
        layout.addWidget(QtWidgets.QLabel("Connection type:"))
        layout.addWidget(self.method_selector)

        # Stack of forms
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Manual form
        self.manual_form = QtWidgets.QWidget()
        manual_layout = QFormLayout(self.manual_form)

        self.name_entry_manual  = QLineEdit()
        self.server_entry       = QLineEdit()
        self.username_entry     = QLineEdit()
        self.password_entry     = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)

        self.live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.series_url_format_entry = QLineEdit(self.default_url_formats['series'])

        manual_layout.addRow("Name:", self.name_entry_manual)
        manual_layout.addRow("Server URL:", self.server_entry)
        manual_layout.addRow("Username:", self.username_entry)
        manual_layout.addRow("Password:", self.password_entry)

        # URL format rows are advanced — most users never touch them. Wrap
        # them in a "▼ Advanced" toggle so the dialog isn't cluttered with
        # `{server}/{username}/...` template strings on first open.
        self.manual_adv_button = QPushButton("▶  Advanced (URL format templates)")
        self.manual_adv_button.setFlat(True)
        self.manual_adv_button.setCursor(Qt.PointingHandCursor)
        self.manual_adv_button.setStyleSheet("text-align: left; padding: 4px;")
        self.manual_adv_box = QtWidgets.QWidget()
        manual_adv_layout = QFormLayout(self.manual_adv_box)
        manual_adv_layout.setContentsMargins(0, 0, 0, 0)
        manual_adv_layout.addRow("Live URL format:", self.live_url_format_entry)
        manual_adv_layout.addRow("Movie URL format:", self.movie_url_format_entry)
        manual_adv_layout.addRow("Series URL format:", self.series_url_format_entry)
        self.manual_adv_box.hide()
        manual_layout.addRow(self.manual_adv_button)
        manual_layout.addRow(self.manual_adv_box)
        def _toggle_manual_adv():
            shown = not self.manual_adv_box.isVisible()
            self.manual_adv_box.setVisible(shown)
            self.manual_adv_button.setText(("▼" if shown else "▶") + "  Advanced (URL format templates)")
        self.manual_adv_button.clicked.connect(_toggle_manual_adv)

        #Set placeholder texts for xtream credentials
        self.name_entry_manual.setPlaceholderText("e.g. Home / Family / Provider X")
        self.server_entry.setPlaceholderText("e.g. http://your-provider.tv:8080/")
        self.username_entry.setPlaceholderText("Your IPTV username")
        self.password_entry.setPlaceholderText("Your IPTV password")

        # M3U form
        self.m3u_form = QtWidgets.QWidget()
        m3u_layout = QFormLayout(self.m3u_form)

        self.name_entry_m3u = QLineEdit()
        self.m3u_url_entry  = QLineEdit()

        self.m3u_live_url_format_entry = QLineEdit(self.default_url_formats['live'])
        self.m3u_movie_url_format_entry = QLineEdit(self.default_url_formats['movie'])
        self.m3u_series_url_format_entry = QLineEdit(self.default_url_formats['series'])

        m3u_layout.addRow("Name:", self.name_entry_m3u)
        m3u_layout.addRow("M3U-plus URL:", self.m3u_url_entry)

        self.m3u_adv_button = QPushButton("▶  Advanced (URL format templates)")
        self.m3u_adv_button.setFlat(True)
        self.m3u_adv_button.setCursor(Qt.PointingHandCursor)
        self.m3u_adv_button.setStyleSheet("text-align: left; padding: 4px;")
        self.m3u_adv_box = QtWidgets.QWidget()
        m3u_adv_layout = QFormLayout(self.m3u_adv_box)
        m3u_adv_layout.setContentsMargins(0, 0, 0, 0)
        m3u_adv_layout.addRow("Live URL format:", self.m3u_live_url_format_entry)
        m3u_adv_layout.addRow("Movie URL format:", self.m3u_movie_url_format_entry)
        m3u_adv_layout.addRow("Series URL format:", self.m3u_series_url_format_entry)
        self.m3u_adv_box.hide()
        m3u_layout.addRow(self.m3u_adv_button)
        m3u_layout.addRow(self.m3u_adv_box)
        def _toggle_m3u_adv():
            shown = not self.m3u_adv_box.isVisible()
            self.m3u_adv_box.setVisible(shown)
            self.m3u_adv_button.setText(("▼" if shown else "▶") + "  Advanced (URL format templates)")
        self.m3u_adv_button.clicked.connect(_toggle_m3u_adv)

        #Set placeholder texts for m3u credentials
        self.name_entry_m3u.setPlaceholderText("e.g. Home / Family / Provider X")
        self.m3u_url_entry.setPlaceholderText("e.g. http://your-provider.tv/get.php?username=...&password=...&type=m3u_plus")

        # M3U file form (third option)
        self.m3u_file_form = QtWidgets.QWidget()
        m3u_file_layout = QFormLayout(self.m3u_file_form)
        self.name_entry_m3u_file = QLineEdit()
        self.name_entry_m3u_file.setPlaceholderText("e.g. My local playlist")
        self.m3u_file_path_entry = QLineEdit()
        self.m3u_file_path_entry.setPlaceholderText("Click 'Browse…' to pick a .m3u / .m3u8 file")
        self.m3u_file_path_entry.setReadOnly(True)
        m3u_file_browse = QPushButton("Browse…")
        m3u_file_browse.setCursor(Qt.PointingHandCursor)
        def _pick_m3u_file():
            from PyQt5.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(
                self, "Choose M3U file", "",
                "M3U playlists (*.m3u *.m3u8);;All files (*)"
            )
            if p:
                self.m3u_file_path_entry.setText(p)
        m3u_file_browse.clicked.connect(_pick_m3u_file)
        path_row = QtWidgets.QWidget()
        path_row_lay = QHBoxLayout(path_row)
        path_row_lay.setContentsMargins(0, 0, 0, 0)
        path_row_lay.addWidget(self.m3u_file_path_entry)
        path_row_lay.addWidget(m3u_file_browse)
        m3u_file_layout.addRow("Name:", self.name_entry_m3u_file)
        m3u_file_layout.addRow("M3U file:", path_row)
        hint = QLabel(
            "Nebula will read the file and look for an Xtream get.php URL "
            "inside it. Plain channel-only M3U files are not yet supported."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: rgba(150,150,150,200); font-size: 11px;")
        m3u_file_layout.addRow(hint)

        self.stack.addWidget(self.manual_form)
        self.stack.addWidget(self.m3u_form)
        self.stack.addWidget(self.m3u_file_form)

        self.method_selector.currentIndexChanged.connect(self.stack.setCurrentIndex)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            Qt.Horizontal, self)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout.addWidget(buttons)

        # Set form data if in edit mode
        if self.mode == self.MODE_EDIT and self.account:
            method, *credentials = self.account
            if method == 'manual':
                self.method_selector.setCurrentText(self.manual_entry_name)
                self.name_entry_manual.setText(credentials[0])
                self.server_entry.setText(credentials[1])
                self.username_entry.setText(credentials[2])
                self.password_entry.setText(credentials[3])
                self.live_url_format_entry.setText(credentials[4])
                self.movie_url_format_entry.setText(credentials[5])
                self.series_url_format_entry.setText(credentials[6])
            else:
                self.method_selector.setCurrentText(self.m3u_plus_entry_name)
                self.name_entry_m3u.setText(credentials[0])
                self.m3u_url_entry.setText(credentials[1])
                self.m3u_live_url_format_entry.setText(credentials[2])
                self.m3u_movie_url_format_entry.setText(credentials[3])
                self.m3u_series_url_format_entry.setText(credentials[4])

        font_metrics = self.fontMetrics()
        max_width = max(
            font_metrics.width(self.name_entry_manual.text()),
            font_metrics.width(self.server_entry.text()),
            font_metrics.width(self.live_url_format_entry.text()),
            font_metrics.width(self.movie_url_format_entry.text()),
            font_metrics.width(self.series_url_format_entry.text()),
            font_metrics.width(self.name_entry_m3u.text()),
            font_metrics.width(self.m3u_url_entry.text()),
            font_metrics.width(self.m3u_live_url_format_entry.text()),
            font_metrics.width(self.m3u_movie_url_format_entry.text()),
            font_metrics.width(self.m3u_series_url_format_entry.text())
        )

        self.setMinimumWidth(max_width + 150)
    
    def validate_and_accept(self):
        method = self.method_selector.currentText()

        if method == self.manual_entry_name:
            name        = self.name_entry_manual.text().strip()
            server      = self.server_entry.text().strip()
            username    = self.username_entry.text().strip()
            password    = self.password_entry.text().strip()

            # Try to auto-parse whatever was pasted into any field.
            # Handles three common formats providers send:
            #   1. get.php URL:  http://host/get.php?username=X&password=Y&type=m3u_plus
            #   2. Credential block (any field, any separator):
            #         User : X   /   Username : X
            #         Password : Y
            #         Host : Z   /   URL : Z   /   Server : Z
            raw_paste = server or username or password
            parsed_server = parsed_user = parsed_pass = None

            import re as _re
            from urllib.parse import urlparse as _up, parse_qs as _pq

            # Format 1 — get.php URL in any field
            get_php_src = next((f for f in (server, username, password) if f and 'get.php' in f), None)
            if get_php_src:
                _parsed = _up(get_php_src)
                _qs = _pq(_parsed.query)
                _u = (_qs.get('username') or [None])[0]
                _p = (_qs.get('password') or [None])[0]
                if _u and _p:
                    parsed_server = f"{_parsed.scheme}://{_parsed.netloc}"
                    parsed_user   = _u
                    parsed_pass   = _p

            # Format 2 — multi-line credential block pasted into any field
            if not parsed_server:
                block = "\n".join(f for f in (server, username, password) if f)
                _u = _re.search(r'(?:user(?:name)?)\s*[:\-=]\s*(\S+)', block, _re.I)
                _p = _re.search(r'pass(?:word)?\s*[:\-=]\s*(\S+)', block, _re.I)
                _h = _re.search(r'(?:host|url|server)\s*[:\-=]\s*(\S+)', block, _re.I)
                if _u and _p and _h:
                    host = _h.group(1).strip().rstrip('/')
                    if not host.startswith(('http://', 'https://')):
                        host = 'http://' + host
                    parsed_server = host
                    parsed_user   = _u.group(1).strip()
                    parsed_pass   = _p.group(1).strip()

            if parsed_server:
                server   = parsed_server
                username = parsed_user
                password = parsed_pass
                self.server_entry.setText(server)
                self.username_entry.setText(username)
                self.password_entry.setText(password)

            # Normalise server: add http:// if the user typed a bare hostname
            if server and not server.startswith(('http://', 'https://')):
                server = 'http://' + server
                self.server_entry.setText(server)

            if not name or not server or not username or not password:
                QtWidgets.QMessageBox.warning(self, "Missing fields",
                    "Please fill in name, server URL, username and password.")
                return
            self.accept()
        elif method == self.m3u_plus_entry_name:
            name    = self.name_entry_m3u.text().strip()
            m3u_url = self.m3u_url_entry.text().strip()
            if not name or not m3u_url:
                QtWidgets.QMessageBox.warning(self, "Missing fields",
                    "Please give the link a name and paste its M3U-plus URL.")
                return
            self.accept()
        else:  # m3u_file
            name = self.name_entry_m3u_file.text().strip()
            path_ = self.m3u_file_path_entry.text().strip()
            if not name or not path_:
                QtWidgets.QMessageBox.warning(self, "Missing fields",
                    "Please give the link a name and pick an .m3u file.")
                return
            # Extract the Xtream get.php URL from the file. We accept the
            # first http(s) line that contains get.php — that's how V2's
            # parser identifies the M3U-plus shape.
            try:
                with open(path_, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except OSError as e:
                QtWidgets.QMessageBox.warning(self, "Could not read file", str(e))
                return
            import re as _re
            m = _re.search(r"https?://[^\s\"']*get\.php\?[^\s\"']*", content)
            if not m:
                QtWidgets.QMessageBox.warning(self, "Unsupported M3U file",
                    "This file doesn't contain an Xtream `get.php` URL. "
                    "Plain channel-only M3U files aren't supported yet.")
                return
            # Stash the resolved URL on the dialog so get_credentials can
            # return it as a regular m3u_plus entry — re-using the existing
            # save/login machinery.
            self._resolved_m3u_url = m.group(0)
            self.accept()

    def get_credentials(self):
        method = self.method_selector.currentText()

        if method == self.manual_entry_name:
            name              = self.name_entry_manual.text().strip()
            server            = self.server_entry.text().strip()
            username          = self.username_entry.text().strip()
            password          = self.password_entry.text().strip()
            live_url_format   = self.live_url_format_entry.text().strip()
            movie_url_format  = self.movie_url_format_entry.text().strip()
            series_url_format = self.series_url_format_entry.text().strip()
            return ('manual', name, server, username, password, live_url_format, movie_url_format, series_url_format)
        elif method == self.m3u_plus_entry_name:
            name              = self.name_entry_m3u.text().strip()
            m3u_url           = self.m3u_url_entry.text().strip()
            live_url_format   = self.m3u_live_url_format_entry.text().strip()
            movie_url_format  = self.m3u_movie_url_format_entry.text().strip()
            series_url_format = self.m3u_series_url_format_entry.text().strip()
            return ('m3u_plus', name, m3u_url, live_url_format, movie_url_format, series_url_format)
        else:  # m3u_file — resolved into m3u_plus at validate-time
            name = self.name_entry_m3u_file.text().strip()
            m3u_url = getattr(self, '_resolved_m3u_url', '')
            return ('m3u_plus', name, m3u_url,
                    self.default_url_formats['live'],
                    self.default_url_formats['movie'],
                    self.default_url_formats['series'])
