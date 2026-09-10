"""Application entry point."""

from __future__ import annotations

import contextlib
import sys
import traceback
from importlib.resources import files
from types import TracebackType

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .constants import APP_NAME, CONFIG_FILE, DATA_DIR
from .window import MainWindow


def _application_icon() -> QIcon:
    """Return the bundled application icon when available."""
    icon = files("freebox_pop_remote").joinpath("assets", "freebox-pop-remote-256.png")
    return QIcon(str(icon))


def _exception_details(
    exc_type: type[BaseException],
    exc: BaseException,
    tb: TracebackType | None,
) -> str:
    return "".join(traceback.format_exception(exc_type, exc, tb))


def _show_error_dialog(
    message: str,
    *,
    details: str = "",
    parent=None,
) -> None:
    """Display a fatal/application error in a visible Qt dialog."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(f"{APP_NAME} - Erreur")
    box.setText(message)
    if details:
        box.setDetailedText(details)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def _startup_error_message(exc: BaseException) -> str:
    """Return a useful message for failures occurring before the main window opens."""
    if isinstance(exc, OSError):
        return (
            "Freebox Pop Remote ne peut pas accéder à ses fichiers persistants.\n\n"
            f"Configuration : {CONFIG_FILE}\n"
            f"Données / certificats : {DATA_DIR}\n\n"
            f"{type(exc).__name__}: {exc}"
        )
    return f"Freebox Pop Remote n'a pas pu démarrer.\n\n{type(exc).__name__}: {exc}"


def _install_exception_hook() -> None:
    """Show uncaught Qt/Python callback errors in a dialog, not only stderr."""

    def handle_exception(
        exc_type: type[BaseException],
        exc: BaseException,
        tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return

        details = _exception_details(exc_type, exc, tb)
        # If Qt itself is no longer able to display a dialog, preserve the
        # normal Python error path for launches from a terminal.
        with contextlib.suppress(Exception):
            _show_error_dialog(
                f"Une erreur inattendue s'est produite.\n\n{exc_type.__name__}: {exc}",
                details=details,
            )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = handle_exception


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
    _install_exception_hook()

    try:
        window = MainWindow()
    except Exception as exc:
        _show_error_dialog(
            _startup_error_message(exc),
            details=traceback.format_exc(),
        )
        return 1

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
