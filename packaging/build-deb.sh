#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/dist/linux"
BIN="$DIST/freebox-pop-remote"
VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/src/__init__.py" | head -n1)"
ARCH="$(dpkg --print-architecture 2>/dev/null || true)"

if [ -z "$VERSION" ]; then
  echo "Erreur: impossible de lire la version dans src/__init__.py" >&2
  exit 1
fi
if [ -z "$ARCH" ]; then
  echo "Erreur: dpkg est requis pour construire un paquet .deb." >&2
  exit 1
fi
if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Erreur: dpkg-deb est requis." >&2
  exit 1
fi

# Le .deb ne contient jamais de runtime Python séparé. S'il manque le binaire
# autonome, on le construit d'abord avec exactement la même chaîne que pour la
# distribution portable Linux.
if [ ! -x "$BIN" ]; then
  echo "Binaire Linux absent; lancement automatique de build-linux.sh..."
  "$ROOT/packaging/build-linux.sh"
fi

OUT="${1:-$DIST/freebox-pop-remote_${VERSION}_${ARCH}.deb}"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/DEBIAN"

# Single source of truth for installed files: reuse the same layout as
# `make install`, staged under DESTDIR.
make -s -C "$ROOT" install PREFIX=/usr DESTDIR="$STAGE"

cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: freebox-pop-remote
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Maintainer: Freebox Pop Remote contributors <noreply@example.invalid>
Depends: libc6 (>= 2.34), libgl1, libegl1, libxkbcommon-x11-0, libxcb-cursor0
Description: Télécommande pour Freebox Player Pop
 Télécommande graphique pour Freebox Player Pop / Player TV Free 4K,
 utilisant le protocole Android TV Remote v2.
 Le paquet contient le binaire autonome Nuitka et ne crée aucun environnement
 Python, venv ou pipx sur la machine cible.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTINST
chmod 0755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
POSTRM
chmod 0755 "$STAGE/DEBIAN/postrm"

SIZE_KB="$(du -sk "$STAGE" | awk '{print $1}')"
echo "Installed-Size: $SIZE_KB" >> "$STAGE/DEBIAN/control"

mkdir -p "$(dirname "$OUT")"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
printf 'Paquet Debian: %s\n' "$OUT"
