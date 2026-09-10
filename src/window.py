"""Main frameless remote-control window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .backend import RemoteBackend
from .config import load_config, save_config
from .constants import APP_NAME, CONFIG_FILE, DEFAULT_APP_LINKS
from .dialogs import AppLinksDialog, PlayerSettingsDialog
from .models import DiscoveredDevice
from .voice import VoiceCapture
from .widgets import DPad, GoogleVoiceButton, RemoteButton


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.backend = RemoteBackend()
        self.config = load_config()
        self.app_links = dict(self.config["app_links"])
        self.players: list[dict[str, str]] = list(self.config["players"])

        self._devices: list[DiscoveredDevice] = []
        self._connected = False
        self._current_host = ""
        self._pending_host = ""
        self._pending_alias: str | None = None
        self._settings_dialog: PlayerSettingsDialog | None = None
        self._closing = False
        self.voice_capture = VoiceCapture(self)

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        central = QWidget()
        central.setObjectName("transparentRoot")
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(0)

        remote_holder = QHBoxLayout()
        remote_holder.setContentsMargins(0, 0, 0, 0)
        remote_holder.addStretch()
        self.remote_body = self._build_remote()
        remote_holder.addWidget(self.remote_body)
        remote_holder.addStretch()
        root.addLayout(remote_holder)

        # Fit the native window to the remote shell, so transparent pixels only
        # exist around the rounded corners rather than forming a large square.
        QTimer.singleShot(0, self._fit_window_to_remote)

        self._apply_style()
        self._wire_backend()
        self._populate_player_selector()
        self._set_remote_enabled(False)

        last_host = str(self.config.get("last_host", ""))
        known_hosts = {player.get("host", "") for player in self.players}
        if last_host and last_host in known_hosts:
            QTimer.singleShot(300, lambda host=last_host: self._connect_to_player(host))
        elif self.players:
            first_host = self.players[0].get("host", "")
            if first_host:
                QTimer.singleShot(300, lambda host=first_host: self._connect_to_player(host))
        else:
            self.status.setText("Aucune Pop configurée — clique sur ⚙ pour commencer.")
            QTimer.singleShot(400, self._open_settings)

    def _build_remote(self) -> QWidget:
        body = QFrame()
        body.setObjectName("remoteBody")
        # The physical shell should hug the 218 px D-pad: 12 px of shell
        # on each side, for a total width of 242 px.
        body.setFixedWidth(242)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 22, 12, 28)
        layout.setSpacing(10)

        # Frameless-window controls, treated visually like tiny engravings on
        # the remote rather than desktop title-bar buttons.
        window_controls = QHBoxLayout()
        window_controls.setContentsMargins(0, 0, 0, -2)
        window_controls.addStretch()
        minimize_button = QToolButton()
        minimize_button.setText("−")
        minimize_button.setObjectName("windowEngraving")
        minimize_button.setToolTip("Minimiser")
        minimize_button.setFixedSize(22, 18)
        minimize_button.clicked.connect(self.showMinimized)
        window_controls.addWidget(minimize_button)
        close_button = QToolButton()
        close_button.setText("×")
        close_button.setObjectName("windowEngraving")
        close_button.setToolTip("Quitter")
        close_button.setFixedSize(22, 18)
        close_button.clicked.connect(self.close)
        window_controls.addWidget(close_button)
        layout.addLayout(window_controls)

        # Header: settings at left, active Pop in the middle, power at right.
        header = QHBoxLayout()
        header.setSpacing(8)

        settings_button = QToolButton()
        settings_button.setText("⚙")
        settings_button.setObjectName("remoteSettingsButton")
        settings_button.setToolTip("Configurer les Players Pop")
        settings_button.setFixedSize(44, 44)
        settings_button.clicked.connect(self._open_settings)
        header.addWidget(settings_button)

        self.player_selector = QComboBox()
        self.player_selector.setObjectName("playerSelector")
        self.player_selector.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.player_selector.setFixedHeight(38)
        self.player_selector.currentIndexChanged.connect(self._player_selected)
        header.addWidget(self.player_selector, 1)

        self.power_button = RemoteButton("⏻", object_name="powerButton")
        self.power_button.setFixedSize(44, 44)
        self.power_button.setToolTip("Marche / arrêt")
        self.power_button.clicked.connect(lambda: self.backend.send_key("POWER"))
        header.addWidget(self.power_button)
        layout.addLayout(header)

        self.remote_controls = QWidget()
        self.remote_controls.setObjectName("remoteControls")
        controls = QVBoxLayout(self.remote_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)

        apps = QGridLayout()
        apps.setHorizontalSpacing(8)
        apps.setVerticalSpacing(8)

        netflix = RemoteButton("NETFLIX", object_name="netflixButton", fixed_height=36)
        prime = RemoteButton("prime video", object_name="primeButton", fixed_height=36)
        canal = RemoteButton("CANAL+", object_name="canalButton", fixed_height=36)
        disney = RemoteButton("Disney+", object_name="disneyButton", fixed_height=36)
        apps.addWidget(netflix, 0, 0)
        apps.addWidget(prime, 0, 1)
        apps.addWidget(canal, 1, 0)
        apps.addWidget(disney, 1, 1)
        netflix.clicked.connect(lambda: self._launch("netflix"))
        prime.clicked.connect(lambda: self._launch("prime"))
        canal.clicked.connect(lambda: self._launch("canal"))
        disney.clicked.connect(lambda: self._launch("disney"))
        controls.addLayout(apps)

        free = RemoteButton("free", object_name="freeButton", fixed_height=42)
        free.setToolTip("Ouvrir Free TV")
        free.clicked.connect(lambda: self._launch("free"))
        controls.addWidget(free)

        # Align the microphone and Home buttons exactly with the left and
        # right columns of the numeric keypad below (56 px keys, 14 px gaps).
        assistant_home_grid = QGridLayout()
        assistant_home_grid.setContentsMargins(0, 0, 0, 0)
        assistant_home_grid.setHorizontalSpacing(14)
        assistant_home_grid.setVerticalSpacing(0)
        for column in range(3):
            assistant_home_grid.setColumnMinimumWidth(column, 56)

        self.voice_button = GoogleVoiceButton()
        self.voice_button.pressed.connect(self._voice_pressed)
        self.voice_button.released.connect(self._voice_released)
        assistant_home_grid.addWidget(self.voice_button, 0, 0)

        home = RemoteButton("⌂", object_name="homeButton")
        home.setToolTip("Accueil Android TV")
        home.setFixedSize(56, 42)
        home.clicked.connect(lambda: self.backend.send_key("HOME"))
        assistant_home_grid.addWidget(home, 0, 2)

        assistant_home = QHBoxLayout()
        assistant_home.setContentsMargins(0, 0, 0, 0)
        assistant_home.addStretch()
        assistant_home.addLayout(assistant_home_grid)
        assistant_home.addStretch()
        controls.addLayout(assistant_home)

        # D-pad + Back form one compact block: no layout spacing or margin
        # between the lower edge of the pad and the upper edge of Back.
        navigation_block = QWidget()
        navigation_block.setObjectName("transparentPanel")
        navigation_layout = QVBoxLayout(navigation_block)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(0)

        dpad_row = QHBoxLayout()
        dpad_row.setContentsMargins(0, 0, 0, 0)
        dpad_row.addStretch()
        dpad_row.addWidget(DPad(self.backend.send_key))
        dpad_row.addStretch()
        navigation_layout.addLayout(dpad_row)

        back = RemoteButton("↩", object_name="backButton")
        back.setFixedWidth(96)
        back.setFixedHeight(38)
        back.setToolTip("Retour / sortie")
        back.clicked.connect(lambda: self.backend.send_key("BACK"))
        back_row = QHBoxLayout()
        back_row.setContentsMargins(0, 0, 0, 0)
        back_row.addStretch()
        back_row.addWidget(back)
        back_row.addStretch()
        navigation_layout.addLayout(back_row)

        controls.addWidget(navigation_block)

        rockers = QHBoxLayout()
        rockers.setSpacing(14)
        vol = self._make_rocker(
            "+",
            "V",
            "−",
            lambda: self.backend.send_key("VOLUME_UP"),
            lambda: self.backend.send_key("VOLUME_DOWN"),
            "Volume",
        )
        mute = RemoteButton("🔇", object_name="muteButton")
        mute.setFixedSize(56, 42)
        mute.setToolTip("Muet")
        mute.clicked.connect(lambda: self.backend.send_key("MUTE"))
        channel = self._make_rocker(
            "+",
            "P",
            "−",
            lambda: self.backend.send_key("CHANNEL_UP"),
            lambda: self.backend.send_key("CHANNEL_DOWN"),
            "Chaîne",
        )
        rockers.addStretch()
        rockers.addWidget(vol, 0, Qt.AlignmentFlag.AlignVCenter)
        rockers.addWidget(mute, 0, Qt.AlignmentFlag.AlignVCenter)
        rockers.addWidget(channel, 0, Qt.AlignmentFlag.AlignVCenter)
        rockers.addStretch()
        controls.addLayout(rockers)

        keypad = QGridLayout()
        keypad.setHorizontalSpacing(14)
        keypad.setVerticalSpacing(8)
        for number in range(1, 10):
            row = (number - 1) // 3
            col = (number - 1) % 3
            button = RemoteButton(str(number), object_name="numberButton")
            button.setFixedSize(56, 42)
            button.clicked.connect(lambda _checked=False, n=str(number): self.backend.send_key(n))
            keypad.addWidget(button, row, col)

        zero = RemoteButton("0", object_name="numberButton")
        zero.setFixedSize(56, 42)
        zero.clicked.connect(lambda: self.backend.send_key("0"))
        keypad.addWidget(zero, 3, 1)

        keywrap = QHBoxLayout()
        keywrap.addStretch()
        keywrap.addLayout(keypad)
        keywrap.addStretch()
        controls.addLayout(keywrap)

        brand = QLabel("free")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setObjectName("bottomBrand")
        controls.addWidget(brand)

        self.status = QLabel("Prêt.")
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setWordWrap(True)
        controls.addWidget(self.status)

        layout.addWidget(self.remote_controls)
        return body

    def _make_rocker(
        self,
        top_text: str,
        center_text: str,
        bottom_text: str,
        top_action,
        bottom_action,
        tooltip: str,
    ) -> QWidget:
        frame = QFrame()
        frame.setObjectName("rocker")
        frame.setFixedSize(56, 106)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QPushButton(top_text)
        top.setObjectName("rockerPart")
        top.setToolTip(f"{tooltip} +")
        top.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        top.clicked.connect(top_action)

        center = QLabel(center_text)
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.setObjectName("rockerLabel")

        bottom = QPushButton(bottom_text)
        bottom.setObjectName("rockerPart")
        bottom.setToolTip(f"{tooltip} −")
        bottom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        bottom.clicked.connect(bottom_action)

        lay.addWidget(top, 1)
        lay.addWidget(center, 1)
        lay.addWidget(bottom, 1)
        return frame

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, #transparentRoot {
                background: transparent;
                color: #eeeeee;
            }
            QWidget {
                background: #111315;
                color: #eeeeee;
                font-family: "Inter", "DejaVu Sans", sans-serif;
                font-size: 13px;
            }
            QLineEdit, QComboBox {
                background: #25292d;
                border: 1px solid #3c4148;
                border-radius: 7px;
                padding: 7px;
                selection-background-color: #a42128;
            }
            QPushButton {
                background: #2c3035;
                border: 1px solid #444a51;
                border-radius: 7px;
                padding: 7px 10px;
            }
            QPushButton:hover { background: #383d43; }
            QPushButton:pressed { background: #202327; }
            #remoteBody {
                background: #282b2e;
                border: 1px solid #3c3f43;
                border-radius: 58px;
            }
            #remoteControls {
                background: transparent;
            }
            #remoteSettingsButton {
                background: #111315;
                border: 1px solid #464a4f;
                border-radius: 22px;
                color: #f3f3f3;
                font-size: 18px;
            }
            #remoteSettingsButton:hover { background: #383d43; }
            #playerSelector {
                background: #282b2e;
                border: 0;
                color: #eeeeee;
                padding: 3px 7px;
                font-weight: 600;
            }
            #playerSelector QAbstractItemView {
                background: #25292d;
                border: 1px solid #464a4f;
                selection-background-color: #3a3f44;
            }
            #powerButton, #backButton, #homeButton, #muteButton,
            #numberButton, #remoteButton, #voiceButton {
                background: #111315;
                border: 1px solid #464a4f;
                color: #f3f3f3;
            }
            #powerButton {
                border-radius: 22px;
                font-size: 22px;
                font-weight: 600;
            }
            #backButton, #homeButton {
                border-radius: 18px;
                font-size: 20px;
            }
            #muteButton {
                border-radius: 18px;
                font-size: 17px;
                padding: 0;
            }
            #numberButton {
                border-radius: 18px;
                font-size: 17px;
                font-weight: 600;
            }
            #netflixButton, #primeButton, #canalButton, #disneyButton,
            #freeButton {
                background: #121416;
                border: 1px solid #45494e;
                border-radius: 18px;
                font-weight: 700;
            }
            #netflixButton { color: #e50914; }
            #primeButton {
                color: #f4f4f4;
                font-size: 11px;
            }
            #canalButton { color: #ffffff; }
            #disneyButton { color: #94b9ff; }
            #freeButton {
                color: #e23036;
                font-size: 23px;
                font-style: italic;
                border-radius: 21px;
            }
            #voiceButton {
                background: #17191b;
                border: 1px solid #3c4044;
                border-radius: 18px;
            }
            #voiceButton[voiceActive="true"] {
                background: #a42128;
                border-color: #dc555b;
            }
            #voiceButton:disabled {
                background: #1c1e20;
                border-color: #34373a;
            }
            #dpadPart {
                background: transparent;
                border: 0;
                color: #c7c9cb;
                font-size: 18px;
            }
            #dpadPart:hover {
                background: #303438;
                border-radius: 24px;
            }
            #dpadCenter {
                background: #222529;
                border: 1px solid #5b6066;
                border-radius: 36px;
                color: #eeeeee;
                font-size: 13px;
                font-weight: 700;
            }
            #dpadCenter:hover { background: #383d42; }
            #rocker {
                background: #111315;
                border: 1px solid #464a4f;
                border-radius: 22px;
            }
            #rockerPart {
                background: transparent;
                border: 0;
                border-radius: 0;
                color: #eeeeee;
                font-size: 18px;
                font-weight: 600;
                padding: 0;
                margin: 0;
                text-align: center;
            }
            #rockerPart:hover { background: #303438; }
            #rockerLabel {
                background: transparent;
                color: #d8d8d8;
                font-weight: 600;
            }
            #bottomBrand {
                background-color: #282b2e;
                border: 0;
                color: #9a9da1;
                font-size: 17px;
                font-style: italic;
                padding-top: 2px;
            }
            #status {
                background-color: #282b2e;
                color: #858a8f;
                font-size: 10px;
                padding: 1px 4px 0 4px;
            }
            #transparentPanel {
                background: transparent;
            }
            #windowEngraving {
                background: transparent;
                border: 0;
                color: #676c71;
                font-size: 13px;
                font-weight: 500;
                padding: 0;
            }
            #windowEngraving:hover {
                color: #b7bcc1;
            }
            #dialogHelp {
                color: #b7bcc1;
                padding-bottom: 6px;
            }
            #settingsGroup {
                background: #1a1d20;
                border: 1px solid #30343a;
                border-radius: 10px;
            }
            #settingsGroupTitle {
                background: transparent;
                font-weight: 700;
            }
            #dialogStatus {
                color: #b7bcc1;
                padding: 4px 0;
            }
            """
        )

    def _wire_backend(self) -> None:
        self.backend.devices_found.connect(self._devices_found)
        self.backend.scan_started.connect(self._scan_started)
        self.backend.scan_finished.connect(self._scan_finished)
        self.backend.status_changed.connect(self._backend_status)
        self.backend.error.connect(self._show_error)
        self.backend.pairing_code_requested.connect(self._ask_pairing_code)
        self.backend.pairing_invalid.connect(self._pairing_invalid)
        self.backend.connected_changed.connect(self._connected_changed)
        self.backend.voice_started.connect(self._voice_started)
        self.backend.voice_stopped.connect(self._voice_stopped)
        self.voice_capture.data_ready.connect(self.backend.send_voice_data)
        self.voice_capture.error.connect(self._voice_capture_error)

    def _player_label(self, player: dict[str, str]) -> str:
        return player.get("alias") or player.get("name") or player.get("host") or "Pop"

    def _player_by_host(self, host: str) -> dict[str, str] | None:
        for player in self.players:
            if player.get("host") == host:
                return player
        return None

    def _populate_player_selector(self, selected_host: str | None = None) -> None:
        selected_host = selected_host or self._current_host or str(self.config.get("last_host", ""))
        self.player_selector.blockSignals(True)
        self.player_selector.clear()
        if not self.players:
            self.player_selector.addItem("Aucune Pop", "")
            self.player_selector.setEnabled(False)
        else:
            self.player_selector.setEnabled(True)
            selected_index = 0
            for index, player in enumerate(self.players):
                host = player.get("host", "")
                self.player_selector.addItem(self._player_label(player), host)
                self.player_selector.setItemData(index, host, Qt.ItemDataRole.ToolTipRole)
                if host == selected_host:
                    selected_index = index
            self.player_selector.setCurrentIndex(selected_index)
        self.player_selector.blockSignals(False)

    def _player_selected(self, index: int) -> None:
        host = self.player_selector.itemData(index)
        if not isinstance(host, str) or not host or host == self._current_host:
            return
        self._connect_to_player(host)

    def _open_settings(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        dialog = PlayerSettingsDialog(self.players, self._current_host, self)
        self._settings_dialog = dialog
        dialog.scan_requested.connect(self.backend.scan)
        dialog.connect_requested.connect(self._connect_from_settings)
        dialog.app_links_requested.connect(self._edit_app_links)
        dialog.finished.connect(self._settings_closed)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        QTimer.singleShot(120, self.backend.scan)

    def _settings_closed(self, _result: int) -> None:
        self._settings_dialog = None

    def _connect_from_settings(self, host: str, alias: str) -> None:
        self._pending_alias = alias
        self._connect_to_player(host)

    def _connect_to_player(self, host: str) -> None:
        host = host.strip()
        if not host:
            return
        self._pending_host = host
        if self._pending_alias is None:
            player = self._player_by_host(host)
            self._pending_alias = player.get("alias", "") if player else ""
        self._set_remote_enabled(False)
        self.status.setText(f"Connexion à {host}…")
        if self._settings_dialog is not None:
            self._settings_dialog.set_connection_pending(True)
        self.backend.connect(host)

    def _devices_found(self, devices: list[DiscoveredDevice]) -> None:
        self._devices = devices
        if self._settings_dialog is not None:
            self._settings_dialog.set_devices(devices)

    def _scan_started(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.set_scanning(True)

    def _scan_finished(self) -> None:
        if self._settings_dialog is not None:
            self._settings_dialog.set_scanning(False)

    def _backend_status(self, text: str) -> None:
        self.status.setText(text)
        if self._settings_dialog is not None:
            self._settings_dialog.set_status(text)

    def _ask_pairing_code(self, host: str) -> None:
        code, ok = QInputDialog.getText(
            self,
            "Appairage Freebox Pop",
            f"Un code d'appairage est affiché sur le Player ({host}).\n\nCode :",
        )
        if ok:
            self.backend.submit_pairing_code(code)
        else:
            self.backend.cancel_pairing()

    def _pairing_invalid(self) -> None:
        self.status.setText("Code d'appairage refusé — vérifie le nouveau code affiché sur la TV.")
        if self._settings_dialog is not None:
            self._settings_dialog.set_status(self.status.text())

    def _connected_changed(self, connected: bool, display: str) -> None:
        self._connected = connected
        self._set_remote_enabled(connected)

        if connected:
            host = self._pending_host or self._current_host
            if not host:
                return

            player = self._player_by_host(host)
            if player is None:
                player = {"host": host, "name": display or host, "alias": ""}
                self.players.append(player)
            elif display:
                player["name"] = display

            if self._pending_alias is not None:
                player["alias"] = self._pending_alias

            self._current_host = host
            self.config["players"] = self.players
            self.config["last_host"] = host
            self.config["app_links"] = self.app_links
            save_config(self.config)
            self._populate_player_selector(host)

            self.status.setText(f"Connecté à {self._player_label(player)}.")
            if self._settings_dialog is not None:
                self._settings_dialog.set_status(
                    f"Connecté à {self._player_label(player)}. Configuration enregistrée."
                )
                self._settings_dialog.set_connection_pending(False)
                QTimer.singleShot(250, self._settings_dialog.accept)

            self._pending_alias = None
            self._pending_host = host
        else:
            if self._settings_dialog is not None:
                self._settings_dialog.set_connection_pending(False)

    def _set_remote_enabled(self, enabled: bool) -> None:
        # Header (settings, Player selector, power) stays usable. The command
        # area is disabled while no Player is connected.
        self.remote_controls.setEnabled(enabled)
        self.power_button.setEnabled(enabled)

    def _voice_pressed(self) -> None:
        self.voice_button.set_voice_active(True)
        self.status.setText("Démarrage de la commande vocale…")
        self.backend.start_voice()

    def _voice_started(self) -> None:
        if not self.voice_button.isDown():
            self.backend.stop_voice()
            return
        self.voice_capture.start()

    def _voice_released(self) -> None:
        self.voice_capture.stop()
        self.backend.stop_voice()
        self.voice_button.set_voice_active(False)

    def _voice_stopped(self) -> None:
        self.voice_capture.stop()
        self.voice_button.set_voice_active(False)

    def _voice_capture_error(self, message: str) -> None:
        self.voice_capture.stop()
        self.backend.stop_voice()
        self.voice_button.set_voice_active(False)
        self.status.setText(message)

    def _show_error(self, message: str) -> None:
        if self._closing:
            return
        if self._settings_dialog is not None:
            self._settings_dialog.set_connection_pending(False)
            self._settings_dialog.set_status(message)
        self._pending_alias = None
        QMessageBox.warning(self, APP_NAME, message)

    def _launch(self, key: str) -> None:
        url = self.app_links.get(key, "")
        if url:
            self.backend.launch(url)

    def _edit_app_links(self) -> None:
        dialog = AppLinksDialog(self.app_links, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            for key in DEFAULT_APP_LINKS:
                if not values.get(key):
                    values[key] = DEFAULT_APP_LINKS[key]
            self.app_links = values
            self.config["app_links"] = values
            self.config["players"] = self.players
            self.config["last_host"] = self._current_host or self.config.get("last_host", "")
            save_config(self.config)
            self.status.setText(f"Raccourcis enregistrés dans {CONFIG_FILE}.")

    def _fit_window_to_remote(self) -> None:
        hint = self.remote_body.sizeHint()
        # The shell has a fixed width; height follows its layout. Eight pixels of
        # transparent margin on each edge preserve antialiasing on rounded corners.
        self.setFixedSize(self.remote_body.width() + 16, hint.height() + 16)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._connected:
            super().keyPressEvent(event)
            return

        key = event.key()
        modifiers = event.modifiers()
        if modifiers not in (
            Qt.KeyboardModifier.NoModifier,
            Qt.KeyboardModifier.KeypadModifier,
        ):
            super().keyPressEvent(event)
            return

        mapping = {
            Qt.Key.Key_Up: "DPAD_UP",
            Qt.Key.Key_Down: "DPAD_DOWN",
            Qt.Key.Key_Left: "DPAD_LEFT",
            Qt.Key.Key_Right: "DPAD_RIGHT",
            Qt.Key.Key_Return: "DPAD_CENTER",
            Qt.Key.Key_Enter: "DPAD_CENTER",
            Qt.Key.Key_Escape: "BACK",
            Qt.Key.Key_Backspace: "BACK",
            Qt.Key.Key_Home: "HOME",
            Qt.Key.Key_Space: "MEDIA_PLAY_PAUSE",
            Qt.Key.Key_Plus: "VOLUME_UP",
            Qt.Key.Key_Minus: "VOLUME_DOWN",
            Qt.Key.Key_PageUp: "CHANNEL_UP",
            Qt.Key.Key_PageDown: "CHANNEL_DOWN",
        }
        for number in range(10):
            mapping[getattr(Qt.Key, f"Key_{number}")] = str(number)

        command = mapping.get(key)
        if command:
            self.backend.send_key(command)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._closing = True
        self.voice_capture.stop()
        self.backend.shutdown()
        event.accept()
