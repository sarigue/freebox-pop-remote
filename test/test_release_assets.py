from pathlib import Path

from freebox_pop_remote import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_packaging_names_are_versioned_from_source():
    deb = (ROOT / "packaging/build-deb.sh").read_text()
    rpm = (ROOT / "packaging/build-rpm.sh").read_text()
    macos = (ROOT / "packaging/build-macos.sh").read_text()

    assert "freebox-pop-remote-${VERSION}-linux-${ARCH}.deb" in deb
    assert "freebox-pop-remote-${VERSION}-linux-${RPM_ARCH}.rpm" in rpm
    assert '--macos-app-version="$VERSION"' in macos
    assert "NSMicrophoneUsageDescription" in macos
    assert "libpulse0" in deb
    assert "pulseaudio-libs" in rpm


def test_release_workflow_declares_all_native_assets():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    expected = {
        f"freebox-pop-remote-${{VERSION}}-linux-{arch}"
        for arch in (
            "x86_64",
            "amd64.deb",
            "x86_64.rpm",
            "arm64",
            "arm64.deb",
            "aarch64.rpm",
        )
    }
    expected.update(
        {
            "freebox-pop-remote-$Version-windows-x86_64.exe",
            "freebox-pop-remote-${VERSION}-macos-x86_64.zip",
            "freebox-pop-remote-${VERSION}-macos-arm64.zip",
        }
    )

    assert "runner: ubuntu-24.04-arm" in workflow
    assert "name: release-assets" in workflow
    assert "SHA256SUMS.txt" in workflow
    assert all(name in workflow for name in expected)
    assert __version__ not in workflow


def test_ubuntu_jobs_install_qt_multimedia_runtime():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    release = (ROOT / ".github/workflows/release.yml").read_text()

    assert "apt-get install -y --no-install-recommends libpulse0" in ci
    assert release.count("libpulse0") == 2
