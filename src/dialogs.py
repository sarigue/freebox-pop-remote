"""Configuration dialogs."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .constants import APP_NAME, DEFAULT_APP_LINKS
from .models import DiscoveredDevice


class AppLinksDialog(QDialog):
    def __init__(self, links: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Raccourcis d’applications")
        self.setMinimumWidth(560)
        self._edits: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        info = QLabel(
            "Ces raccourcis sont envoyés comme Android TV App Links. "
            "Ils peuvent dépendre de la version installée sur le Player."
        )
        info.setWordWrap(True)
        info.setObjectName("dialogHelp")
        layout.addWidget(info)

        form = QFormLayout()
        labels = {
            "free": "Free TV",
            "netflix": "Netflix",
            "prime": "Prime Video",
            "canal": "CANAL+",
            "disney": "Disney+",
        }
        for key, label in labels.items():
            edit = QLineEdit(links.get(key, ""))
            self._edits[key] = edit
            form.addRow(label + " :", edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        reset.clicked.connect(self._restore_defaults)
        layout.addWidget(buttons)

    def _restore_defaults(self) -> None:
        for key, value in DEFAULT_APP_LINKS.items():
            self._edits[key].setText(value)

    def values(self) -> dict[str, str]:
        return {key: edit.text().strip() for key, edit in self._edits.items()}


class PlayerSettingsDialog(QDialog):
    scan_requested = Signal()
    connect_requested = Signal(str, str)
    app_links_requested = Signal()

    def __init__(
        self,
        players: list[dict[str, str]],
        current_host: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurer le Player Pop")
        self.setMinimumWidth(560)
        self._players = players

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Recherche un Player Pop sur le réseau, sélectionne-le puis lance la "
            "connexion. Si ce Player n'est pas encore autorisé, le code "
            "d'appairage sera demandé automatiquement."
        )
        intro.setWordWrap(True)
        intro.setObjectName("dialogHelp")
        layout.addWidget(intro)

        configured_row = QHBoxLayout()
        configured_row.addWidget(QLabel("Déjà configurée :"))
        self.configured_combo = QComboBox()
        self.configured_combo.addItem("Nouvelle Pop…", "")
        selected_index = 0
        for index, player in enumerate(players, start=1):
            label = player.get("alias") or player.get("name") or player.get("host")
            host = player.get("host", "")
            self.configured_combo.addItem(f"{label} ({host})", host)
            if host == current_host:
                selected_index = index
        self.configured_combo.setCurrentIndex(selected_index)
        self.configured_combo.currentIndexChanged.connect(self._configured_selected)
        configured_row.addWidget(self.configured_combo, 1)
        layout.addLayout(configured_row)

        discovery = QFrame()
        discovery.setObjectName("settingsGroup")
        discovery_layout = QVBoxLayout(discovery)
        discovery_layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("Recherche sur le réseau")
        title.setObjectName("settingsGroupTitle")
        discovery_layout.addWidget(title)

        scan_row = QHBoxLayout()
        self.discovered_combo = QComboBox()
        self.discovered_combo.addItem("Cliquer sur Scanner…", "")
        self.discovered_combo.currentIndexChanged.connect(self._discovered_selected)
        scan_row.addWidget(self.discovered_combo, 1)
        self.scan_button = QPushButton("Scanner")
        self.scan_button.clicked.connect(self.scan_requested.emit)
        scan_row.addWidget(self.scan_button)
        discovery_layout.addLayout(scan_row)
        layout.addWidget(discovery)

        form = QFormLayout()
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("192.168.1.42")
        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("Facultatif — ex. Salon")
        form.addRow("Adresse IP / hôte :", self.host_edit)
        form.addRow("Nom personnalisé :", self.alias_edit)
        layout.addLayout(form)

        self.status = QLabel("")
        self.status.setObjectName("dialogStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        app_links = QPushButton("Raccourcis d’applications…")
        app_links.clicked.connect(self.app_links_requested.emit)
        actions.addWidget(app_links)
        actions.addStretch()

        close = QPushButton("Fermer")
        close.clicked.connect(self.reject)
        actions.addWidget(close)

        self.connect_button = QPushButton("Connecter / appairer")
        self.connect_button.setDefault(True)
        self.connect_button.clicked.connect(self._connect)
        actions.addWidget(self.connect_button)
        layout.addLayout(actions)

        self._configured_selected(self.configured_combo.currentIndex())

    def _configured_selected(self, index: int) -> None:
        host = self.configured_combo.itemData(index)
        if not isinstance(host, str) or not host:
            self.host_edit.clear()
            self.alias_edit.clear()
            return
        for player in self._players:
            if player.get("host") == host:
                self.host_edit.setText(host)
                self.alias_edit.setText(player.get("alias", ""))
                return

    def _discovered_selected(self, index: int) -> None:
        host = self.discovered_combo.itemData(index)
        if not isinstance(host, str) or not host:
            return
        self.host_edit.setText(host)
        for player in self._players:
            if player.get("host") == host:
                self.alias_edit.setText(player.get("alias", ""))
                return
        self.alias_edit.clear()

    def _connect(self) -> None:
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.information(
                self,
                APP_NAME,
                "Sélectionne un Player détecté ou saisis son adresse IP.",
            )
            return
        self.connect_button.setEnabled(False)
        self.connect_button.setText("Connexion…")
        self.connect_requested.emit(host, self.alias_edit.text().strip())

    def set_devices(self, devices: list[DiscoveredDevice]) -> None:
        current = self.host_edit.text().strip()
        self.discovered_combo.blockSignals(True)
        self.discovered_combo.clear()
        if not devices:
            self.discovered_combo.addItem("Aucun appareil détecté", "")
            self.discovered_combo.setEnabled(False)
        else:
            self.discovered_combo.setEnabled(True)
            for device in devices:
                self.discovered_combo.addItem(device.label, device.host)
            if current:
                for index in range(self.discovered_combo.count()):
                    if self.discovered_combo.itemData(index) == current:
                        self.discovered_combo.setCurrentIndex(index)
                        break
            elif devices:
                self.host_edit.setText(devices[0].host)
        self.discovered_combo.blockSignals(False)

    def set_scanning(self, scanning: bool) -> None:
        self.scan_button.setEnabled(not scanning)
        self.scan_button.setText("Scan…" if scanning else "Scanner")

    def set_status(self, text: str) -> None:
        self.status.setText(text)

    def set_connection_pending(self, pending: bool) -> None:
        self.connect_button.setEnabled(not pending)
        self.connect_button.setText("Connexion…" if pending else "Connecter / appairer")
