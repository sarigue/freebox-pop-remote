"""Application constants and platform-specific filesystem locations."""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "Freebox Pop Remote"
CLIENT_NAME = "Freebox Pop Remote Linux"
SERVICE_TYPE = "_androidtvremote2._tcp.local."

APP_ID = "io.github.freebox_pop_remote"
APP_DIR_NAME = "freebox-pop-remote"


@dataclass(frozen=True)
class StoragePaths:
    """Resolved configuration and application-data directories."""

    config_dir: Path
    data_dir: Path
    source: str


def _absolute_env_path(environ: Mapping[str, str], name: str) -> Path | None:
    """Return an absolute path from an environment variable, if usable."""
    value = environ.get(name, "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else None


def _fallback_executable_dir(argv0: str | None = None) -> Path:
    """Return the directory containing the executable/script started by the user."""
    raw = argv0 if argv0 is not None else (sys.argv[0] if sys.argv else "")
    if raw:
        with contextlib.suppress(OSError):
            candidate = Path(raw).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            return candidate.resolve().parent
    return Path.cwd()


def resolve_storage_paths(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    executable_dir: Path | None = None,
) -> StoragePaths:
    """Resolve persistent storage according to the conventions of the host OS.

    If the expected environment variables are unavailable, the last-resort
    fallback is a ``freebox-pop-remote-data`` directory next to the executable.
    Write errors are intentionally not swallowed: the GUI startup boundary will
    display them to the user instead of silently starting with ephemeral data.
    """

    platform_name = sys.platform if platform_name is None else platform_name
    environ = os.environ if environ is None else environ
    executable_dir = _fallback_executable_dir() if executable_dir is None else Path(executable_dir)
    portable_fallback = executable_dir / "freebox-pop-remote-data"

    if platform_name.startswith("win"):
        # APPDATA is the primary Windows location chosen for the standalone EXE.
        # LOCALAPPDATA is a sensible secondary location if APPDATA is absent.
        root = _absolute_env_path(environ, "APPDATA")
        source = "%APPDATA%"
        if root is None:
            root = _absolute_env_path(environ, "LOCALAPPDATA")
            source = "%LOCALAPPDATA%"
        if root is None:
            user_profile = _absolute_env_path(environ, "USERPROFILE")
            if user_profile is not None:
                root = user_profile / "AppData" / "Roaming"
                source = "%USERPROFILE%\\AppData\\Roaming"
        if root is None:
            return StoragePaths(portable_fallback, portable_fallback, "executable fallback")

        app_dir = root / APP_DIR_NAME
        return StoragePaths(app_dir, app_dir, source)

    if platform_name == "darwin":
        home = _absolute_env_path(environ, "HOME")
        if home is None:
            return StoragePaths(portable_fallback, portable_fallback, "executable fallback")
        app_dir = home / "Library" / "Application Support" / APP_NAME
        return StoragePaths(app_dir, app_dir, "$HOME/Library/Application Support")

    # Linux and other freedesktop/POSIX systems: honor XDG first, then the
    # conventional locations under HOME.
    home = _absolute_env_path(environ, "HOME")
    config_root = _absolute_env_path(environ, "XDG_CONFIG_HOME")
    data_root = _absolute_env_path(environ, "XDG_DATA_HOME")

    if config_root is None and home is not None:
        config_root = home / ".config"
    if data_root is None and home is not None:
        data_root = home / ".local" / "share"

    config_dir = config_root / APP_DIR_NAME if config_root is not None else portable_fallback
    data_dir = data_root / APP_DIR_NAME if data_root is not None else portable_fallback

    source = (
        "XDG/HOME" if config_root is not None and data_root is not None else "executable fallback"
    )
    return StoragePaths(config_dir, data_dir, source)


STORAGE_PATHS = resolve_storage_paths()
DATA_DIR = STORAGE_PATHS.data_dir
CONFIG_DIR = STORAGE_PATHS.config_dir
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_APP_LINKS: dict[str, str] = {
    "free": "https://oq.ee/home/",
    "netflix": "netflix://",
    "prime": "https://app.primevideo.com",
    "canal": "https://www.canalplus.com/",
    "disney": "https://www.disneyplus.com",
}
