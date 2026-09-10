"""Persistent application configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import CONFIG_FILE, DEFAULT_APP_LINKS

Config = dict[str, Any]


def default_config() -> Config:
    """Return a fresh default configuration."""
    return {
        "app_links": dict(DEFAULT_APP_LINKS),
        "players": [],
        "last_host": "",
    }


def normalize_config(raw: object) -> Config:
    """Normalize user configuration."""
    config = default_config()
    if not isinstance(raw, dict):
        return config

    stored_links = raw.get("app_links", {})
    if isinstance(stored_links, dict):
        links = dict(DEFAULT_APP_LINKS)
        for key in links:
            value = stored_links.get(key)
            if isinstance(value, str) and value.strip():
                links[key] = value.strip()
        config["app_links"] = links

    players: list[dict[str, str]] = []
    stored_players = raw.get("players", [])
    if isinstance(stored_players, list):
        seen: set[str] = set()
        for item in stored_players:
            if not isinstance(item, dict):
                continue
            host = str(item.get("host", "")).strip()
            if not host or host in seen:
                continue
            seen.add(host)
            players.append(
                {
                    "host": host,
                    "name": str(item.get("name", "")).strip(),
                    "alias": str(item.get("alias", "")).strip(),
                }
            )
    config["players"] = players

    last_host = str(raw.get("last_host", "")).strip()
    config["last_host"] = (
        last_host if any(player["host"] == last_host for player in players) else ""
    )

    return config


class ConfigStore:
    """JSON-backed configuration store."""

    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self.path = path

    def load(self) -> Config:
        """Load and normalize config; invalid JSON falls back safely."""
        if not self.path.exists():
            config = default_config()
            self.save(config)
            return config

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default_config()
        return normalize_config(raw)

    def save(self, config: Config) -> None:
        """Persist normalized config atomically."""
        normalized = normalize_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


_DEFAULT_STORE = ConfigStore()


def load_config() -> Config:
    """Compatibility wrapper used by the UI."""
    return _DEFAULT_STORE.load()


def save_config(config: Config) -> None:
    """Compatibility wrapper used by the UI."""
    _DEFAULT_STORE.save(config)
