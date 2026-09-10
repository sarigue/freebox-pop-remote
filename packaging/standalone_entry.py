"""Nuitka entry point used by native platform builds."""

from __future__ import annotations

import contextlib
import ctypes
import shutil
import subprocess
import sys
import traceback

APP_NAME = "Freebox Pop Remote"


def _show_emergency_error(message: str) -> None:
    """Best-effort native GUI error when Qt cannot even be imported/started."""
    # Keep the terminal useful when the executable was started from one.
    print(message, file=sys.stderr)

    # Nothing else can be done if this last-resort native GUI path also fails.
    with contextlib.suppress(Exception):
        if sys.platform.startswith("win"):
            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                None,
                message,
                f"{APP_NAME} - Erreur",
                0x10,  # MB_ICONERROR
            )
            return

        if sys.platform == "darwin" and shutil.which("osascript"):
            escaped = message.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display dialog "{escaped}" with title "{APP_NAME} - Erreur" '
                    'buttons {"OK"} default button "OK" with icon stop',
                ],
                check=False,
            )
            return

        if shutil.which("zenity"):
            subprocess.run(
                ["zenity", "--error", f"--title={APP_NAME} - Erreur", f"--text={message}"],
                check=False,
            )
            return

        if shutil.which("kdialog"):
            subprocess.run(
                ["kdialog", "--error", message, "--title", f"{APP_NAME} - Erreur"],
                check=False,
            )


def _run() -> int:
    try:
        from freebox_pop_remote.main import main

        return main()
    except Exception as exc:
        details = traceback.format_exc()
        _show_emergency_error(
            f"Freebox Pop Remote n'a pas pu démarrer.\n\n{type(exc).__name__}: {exc}\n\n{details}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(_run())
