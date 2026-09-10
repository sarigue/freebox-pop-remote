from pathlib import Path

from freebox_pop_remote.constants import resolve_storage_paths


def test_windows_prefers_appdata(tmp_path):
    appdata = tmp_path / "Roaming"
    localappdata = tmp_path / "Local"
    paths = resolve_storage_paths(
        platform_name="win32",
        environ={
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(localappdata),
        },
        executable_dir=tmp_path / "bin",
    )

    expected = appdata / "freebox-pop-remote"
    assert paths.config_dir == expected
    assert paths.data_dir == expected
    assert paths.source == "%APPDATA%"


def test_windows_uses_localappdata_when_appdata_is_missing(tmp_path):
    localappdata = tmp_path / "Local"
    paths = resolve_storage_paths(
        platform_name="win32",
        environ={"LOCALAPPDATA": str(localappdata)},
        executable_dir=tmp_path / "bin",
    )

    expected = localappdata / "freebox-pop-remote"
    assert paths.config_dir == expected
    assert paths.data_dir == expected
    assert paths.source == "%LOCALAPPDATA%"


def test_windows_can_derive_roaming_path_from_userprofile(tmp_path):
    paths = resolve_storage_paths(
        platform_name="win32",
        environ={"USERPROFILE": str(tmp_path)},
        executable_dir=tmp_path / "bin",
    )

    expected = tmp_path / "AppData" / "Roaming" / "freebox-pop-remote"
    assert paths.config_dir == expected
    assert paths.data_dir == expected


def test_windows_falls_back_next_to_executable_without_profile_variables(tmp_path):
    executable_dir = tmp_path / "bin"
    paths = resolve_storage_paths(
        platform_name="win32",
        environ={},
        executable_dir=executable_dir,
    )

    expected = executable_dir / "freebox-pop-remote-data"
    assert paths.config_dir == expected
    assert paths.data_dir == expected
    assert paths.source == "executable fallback"


def test_linux_uses_xdg_locations_when_defined(tmp_path):
    config_root = tmp_path / "xdg-config"
    data_root = tmp_path / "xdg-data"
    paths = resolve_storage_paths(
        platform_name="linux",
        environ={
            "HOME": str(tmp_path),
            "XDG_CONFIG_HOME": str(config_root),
            "XDG_DATA_HOME": str(data_root),
        },
        executable_dir=tmp_path / "bin",
    )

    assert paths.config_dir == config_root / "freebox-pop-remote"
    assert paths.data_dir == data_root / "freebox-pop-remote"


def test_linux_keeps_standard_home_locations_without_xdg_overrides(tmp_path):
    paths = resolve_storage_paths(
        platform_name="linux",
        environ={"HOME": str(tmp_path)},
        executable_dir=tmp_path / "bin",
    )

    assert paths.config_dir == tmp_path / ".config" / "freebox-pop-remote"
    assert paths.data_dir == tmp_path / ".local" / "share" / "freebox-pop-remote"


def test_macos_uses_application_support(tmp_path):
    paths = resolve_storage_paths(
        platform_name="darwin",
        environ={"HOME": str(tmp_path)},
        executable_dir=tmp_path / "bin",
    )

    expected = tmp_path / "Library" / "Application Support" / "Freebox Pop Remote"
    assert paths.config_dir == expected
    assert paths.data_dir == expected


def test_posix_without_home_falls_back_next_to_executable(tmp_path):
    executable_dir = Path(tmp_path) / "bin"
    paths = resolve_storage_paths(
        platform_name="linux",
        environ={},
        executable_dir=executable_dir,
    )

    expected = executable_dir / "freebox-pop-remote-data"
    assert paths.config_dir == expected
    assert paths.data_dir == expected
