"""Application entry point."""

from __future__ import annotations

import sys
from importlib.resources import files

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__
from .constants import APP_NAME
from .window import MainWindow


def _application_icon() -> QIcon:
    """Return the bundled application icon when available."""
    icon = files("freebox_pop_remote").joinpath("assets", "freebox-pop-remote-256.png")
    return QIcon(str(icon))


def main() -> int:
    """Start the Qt application."""
    if "--version" in sys.argv:
        print(f"Freebox Pop Remote {__version__}")
        return 0

    if "--check-runtime" in sys.argv:
        print("Freebox Pop Remote runtime OK")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("freebox-pop-remote")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("FreeboxPopRemote")
    # Explicitly associate this process/window with the installed desktop entry.
    # This is important on GNOME/Wayland, where relying on WM_CLASS/executable
    # heuristics can result in a generic or mismatched dock icon.
    app.setDesktopFileName("freebox-pop-remote")
    app.setStyle("Fusion")

    bundled_icon = _application_icon()
    app.setWindowIcon(QIcon.fromTheme("freebox-pop-remote", bundled_icon))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
