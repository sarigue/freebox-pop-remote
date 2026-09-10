"""Distribution-level checks for desktop identity and icon assets."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "freebox-pop-remote.desktop"
ASSETS = ROOT / "src" / "assets"


def test_desktop_entry_uses_project_icon_and_identity():
    text = DESKTOP.read_text(encoding="utf-8")

    assert "Icon=freebox-pop-remote\n" in text
    assert "StartupWMClass=freebox-pop-remote\n" in text
    assert "SingleMainWindow=true\n" in text
    assert "input-gaming" not in text


def test_all_linux_icon_sizes_are_present():
    assert (ASSETS / "freebox-pop-remote.svg").is_file()
    for size in (48, 64, 128, 256, 512):
        assert (ASSETS / f"freebox-pop-remote-{size}.png").is_file()
