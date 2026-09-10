#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist/linux"
BIN="$DIST/freebox-pop-remote"
VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/src/__init__.py" | head -n1)"

if [ -z "$VERSION" ]; then
  echo "Erreur: impossible de lire la version dans src/__init__.py" >&2
  exit 1
fi
if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "Erreur: rpmbuild est requis." >&2
  echo "Fedora/RHEL: sudo dnf install rpm-build" >&2
  echo "Ubuntu/Debian: sudo apt install rpm" >&2
  exit 1
fi

# Même politique que le .deb: aucune couche Python dans le paquet. On utilise
# le binaire autonome Linux et on le construit automatiquement s'il manque.
if [ ! -x "$BIN" ]; then
  echo "Binaire Linux absent; lancement automatique de build-linux.sh..."
  "$ROOT/packaging/build-linux.sh"
fi

if [ -z "${RPM_ARCH:-}" ]; then
  case "$(uname -m)" in
    x86_64|amd64) RPM_ARCH="x86_64" ;;
    aarch64|arm64) RPM_ARCH="aarch64" ;;
    *) RPM_ARCH="$(uname -m)" ;;
  esac
fi
case "$RPM_ARCH" in
  x86_64|aarch64) ;;
  *)
    echo "Erreur: architecture RPM non prise en charge: $RPM_ARCH" >&2
    exit 1
    ;;
esac

TOPDIR="$(mktemp -d)"
trap 'rm -rf "$TOPDIR"' EXIT
mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

cp "$BIN" "$TOPDIR/SOURCES/freebox-pop-remote"
cp "$ROOT/freebox-pop-remote.desktop" "$TOPDIR/SOURCES/freebox-pop-remote.desktop"
cp "$ROOT/README.md" "$TOPDIR/SOURCES/README.md"
cp "$ROOT/LICENSE.md" "$TOPDIR/SOURCES/LICENSE.md"
cp "$ROOT/src/assets/freebox-pop-remote.svg" "$TOPDIR/SOURCES/freebox-pop-remote.svg"
for size in 48 64 128 256 512; do
  cp "$ROOT/src/assets/freebox-pop-remote-${size}.png" \
    "$TOPDIR/SOURCES/freebox-pop-remote-${size}.png"
done

cat > "$TOPDIR/SPECS/freebox-pop-remote.spec" <<SPEC
Name:           freebox-pop-remote
Version:        $VERSION
Release:        1%{?dist}
Summary:        Télécommande pour Freebox Player Pop
License:        MIT
BuildArch:      $RPM_ARCH
Requires:       glibc

Source0:        freebox-pop-remote
Source1:        freebox-pop-remote.desktop
Source2:        freebox-pop-remote.svg
Source3:        freebox-pop-remote-48.png
Source4:        freebox-pop-remote-64.png
Source5:        freebox-pop-remote-128.png
Source6:        freebox-pop-remote-256.png
Source7:        freebox-pop-remote-512.png
Source8:        README.md
Source9:        LICENSE.md

%description
Télécommande graphique pour Freebox Player Pop / Player TV Free 4K utilisant
Android TV Remote v2. Le paquet contient un binaire autonome Nuitka et ne crée
aucun environnement Python, venv ou pipx sur la machine cible.

%prep

%build

%install
rm -rf %{buildroot}
install -Dm755 %{SOURCE0} %{buildroot}%{_bindir}/freebox-pop-remote
install -Dm644 %{SOURCE1} %{buildroot}%{_datadir}/applications/freebox-pop-remote.desktop
install -Dm644 %{SOURCE2} %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/freebox-pop-remote.svg
install -Dm644 %{SOURCE3} %{buildroot}%{_datadir}/icons/hicolor/48x48/apps/freebox-pop-remote.png
install -Dm644 %{SOURCE4} %{buildroot}%{_datadir}/icons/hicolor/64x64/apps/freebox-pop-remote.png
install -Dm644 %{SOURCE5} %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/freebox-pop-remote.png
install -Dm644 %{SOURCE6} %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/freebox-pop-remote.png
install -Dm644 %{SOURCE7} %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/freebox-pop-remote.png
install -Dm644 %{SOURCE8} %{buildroot}%{_docdir}/freebox-pop-remote/README.md
install -Dm644 %{SOURCE9} %{buildroot}%{_licensedir}/freebox-pop-remote/LICENSE.md

%post
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor >/dev/null 2>&1 || true
fi

%postun
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database %{_datadir}/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor >/dev/null 2>&1 || true
fi

%files
%{_bindir}/freebox-pop-remote
%{_datadir}/applications/freebox-pop-remote.desktop
%{_datadir}/icons/hicolor/scalable/apps/freebox-pop-remote.svg
%{_datadir}/icons/hicolor/48x48/apps/freebox-pop-remote.png
%{_datadir}/icons/hicolor/64x64/apps/freebox-pop-remote.png
%{_datadir}/icons/hicolor/128x128/apps/freebox-pop-remote.png
%{_datadir}/icons/hicolor/256x256/apps/freebox-pop-remote.png
%{_datadir}/icons/hicolor/512x512/apps/freebox-pop-remote.png
%dir %{_docdir}/freebox-pop-remote
%{_docdir}/freebox-pop-remote/README.md
%license %{_licensedir}/freebox-pop-remote/LICENSE.md

%changelog
* Thu Sep 10 2026 Freebox Pop Remote contributors <noreply@example.invalid> - $VERSION-1
- Freebox Pop Remote $VERSION.
SPEC

rpmbuild --define "_topdir $TOPDIR" -bb "$TOPDIR/SPECS/freebox-pop-remote.spec"

RPM_FILE="$(find "$TOPDIR/RPMS" -type f -name '*.rpm' | head -n1)"
if [ -z "$RPM_FILE" ]; then
  echo "Erreur: rpmbuild n'a produit aucun RPM." >&2
  exit 1
fi

mkdir -p "$DIST"
OUT="${1:-$DIST/freebox-pop-remote-${VERSION}-linux-${RPM_ARCH}.rpm}"
cp "$RPM_FILE" "$OUT"
printf 'Paquet RPM: %s\n' "$OUT"
