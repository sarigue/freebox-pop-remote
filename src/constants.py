"""Application constants and filesystem locations."""

from pathlib import Path

APP_NAME = "Freebox Pop Remote"
CLIENT_NAME = "Freebox Pop Remote Linux"
SERVICE_TYPE = "_androidtvremote2._tcp.local."

APP_ID = "io.github.freebox_pop_remote"
DATA_DIR = Path.home() / ".local" / "share" / "freebox-pop-remote"
CONFIG_DIR = Path.home() / ".config" / "freebox-pop-remote"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_APP_LINKS: dict[str, str] = {
    "free": "https://oq.ee/home/",
    "netflix": "netflix://",
    "prime": "https://app.primevideo.com",
    "canal": "https://www.canalplus.com/",
    "disney": "https://www.disneyplus.com",
}
