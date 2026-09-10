#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_VENV="$ROOT/.venv-build-macos"
DIST="$ROOT/dist/macos"
ZEROCONF_VERSION="0.151.3"
VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/src/__init__.py" | head -n1)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Erreur: build-macos.sh doit être exécuté sous macOS." >&2
  exit 1
fi
if [ -z "$VERSION" ]; then
  echo "Erreur: impossible de lire la version dans src/__init__.py" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Erreur: python3 est requis." >&2
  exit 1
fi

printf 'Construction de Freebox Pop Remote %s pour macOS...\n' "$VERSION"
rm -rf "$BUILD_VENV"
python3 -m venv "$BUILD_VENV"
# shellcheck disable=SC1091
source "$BUILD_VENV/bin/activate"

python -m pip install --upgrade pip
python -m pip install 'Nuitka[onefile]' imageio "$ROOT"
python -m pip uninstall -y zeroconf
SKIP_CYTHON=1 python -m pip install --no-cache-dir --no-binary=zeroconf "zeroconf==$ZEROCONF_VERSION"

python - <<'PY'
from pathlib import Path
import zeroconf
root = Path(zeroconf.__file__).resolve().parent
extensions = sorted([*root.rglob("*.so"), *root.rglob("*.dylib")])
if extensions:
    print("Erreur: extensions natives zeroconf détectées:")
    for path in extensions:
        print(f"  - {path}")
    raise SystemExit(1)
print(f"zeroconf pur Python: {root}")
PY

rm -rf "$DIST"
mkdir -p "$DIST"

python -m nuitka \
  --mode=app \
  --enable-plugin=pyside6 \
  --include-package=androidtvremote2 \
  --include-package=zeroconf \
  --include-package-data=freebox_pop_remote \
  --include-data-dir="$ROOT/src/assets=freebox_pop_remote/assets" \
  --macos-app-icon="$ROOT/src/assets/freebox-pop-remote-512.png" \
  --macos-app-name="Freebox Pop Remote" \
  --macos-app-version="$VERSION" \
  --macos-app-protected-resource="NSMicrophoneUsageDescription:Freebox Pop Remote utilise le microphone uniquement pendant l'appui sur le bouton vocal." \
  --product-name="Freebox Pop Remote" \
  --company-name="Freebox Pop Remote" \
  --output-dir="$DIST" \
  "$ROOT/packaging/standalone_entry.py"

APP_BUNDLE="$(find "$DIST" -maxdepth 1 -type d -name '*.app' | head -n1)"
if [ -z "$APP_BUNDLE" ]; then
  echo "Erreur: aucun bundle .app produit." >&2
  exit 1
fi
TARGET="$DIST/Freebox Pop Remote.app"
if [ "$APP_BUNDLE" != "$TARGET" ]; then
  rm -rf "$TARGET"
  mv "$APP_BUNDLE" "$TARGET"
fi

MAC_BIN="$(find "$TARGET/Contents/MacOS" -maxdepth 1 -type f -perm -111 | head -n1)"
if [ -z "$MAC_BIN" ]; then
  echo "Erreur: exécutable macOS introuvable dans le bundle." >&2
  exit 1
fi
"$MAC_BIN" --check-runtime
ACTUAL_VERSION="$("$MAC_BIN" --version)"
EXPECTED_VERSION="Freebox Pop Remote $VERSION"
if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "Erreur: version du bundle inattendue: $ACTUAL_VERSION" >&2
  exit 1
fi

printf 'Bundle macOS autonome: %s\n' "$TARGET"
