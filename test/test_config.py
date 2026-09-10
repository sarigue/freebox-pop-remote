import json
from pathlib import Path

import pytest
from freebox_pop_remote.config import (
    ConfigStore,
    default_config,
    normalize_config,
)


def test_default_config_is_fresh():
    first = default_config()
    second = default_config()

    first["app_links"]["free"] = "changed"
    assert second["app_links"]["free"] != "changed"


def test_normalize_deduplicates_players_and_validates_last_host():
    config = normalize_config(
        {
            "players": [
                {"host": "192.168.1.10", "name": "Pop", "alias": "Salon"},
                {"host": "192.168.1.10", "name": "Duplicate"},
                {"host": "", "name": "Invalid"},
                {"host": "192.168.1.11", "name": "Pop 2"},
            ],
            "last_host": "192.168.1.11",
        }
    )

    assert [p["host"] for p in config["players"]] == [
        "192.168.1.10",
        "192.168.1.11",
    ]
    assert config["last_host"] == "192.168.1.11"


def test_normalize_drops_unknown_last_host():
    config = normalize_config(
        {
            "players": [{"host": "192.168.1.10"}],
            "last_host": "192.168.1.99",
        }
    )
    assert config["last_host"] == ""


def test_store_round_trip(tmp_path):
    path = tmp_path / "config.json"
    store = ConfigStore(path)

    config = default_config()
    config["players"] = [{"host": "192.168.1.42", "name": "Freebox Player", "alias": "Salon"}]
    config["last_host"] = "192.168.1.42"
    store.save(config)

    loaded = store.load()
    assert loaded == config
    assert json.loads(path.read_text(encoding="utf-8"))["last_host"] == "192.168.1.42"


def test_invalid_json_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")

    assert ConfigStore(path).load() == default_config()


def test_read_error_is_not_silently_ignored(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")

    def fail_read(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", fail_read)

    with pytest.raises(PermissionError, match="denied"):
        ConfigStore(path).load()
