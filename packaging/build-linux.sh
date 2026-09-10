#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_VENV="$ROOT/.venv-build-linux"
DIST="$ROOT/dist/linux"
BIN="$DIST/freebox-pop-remote"
ZEROCONF_VERSION="0.151.3"

if ! command -v gcc >/dev/null 2>&1; then
  echo "Erreur: gcc est requis." >&2
  echo "Ubuntu/Debian: sudo apt install build-essential patchelf python3-venv" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Erreur: python3 est requis pour construire le binaire." >&2
  exit 1
fi

VERSION="$(sed -n 's/^__version__ = "\([^"]*\)"/\1/p' "$ROOT/src/__init__.py" | head -n1)"
if [ -z "$VERSION" ]; then
  echo "Erreur: impossible de lire la version dans src/__init__.py" >&2
  exit 1
fi

printf 'Construction de Freebox Pop Remote %s pour Linux...\n' "$VERSION"

# Repartir d'un environnement propre évite d'embarquer une ancienne wheel
# zeroconf contenant ses extensions Cython optionnelles.
rm -rf "$BUILD_VENV"
python3 -m venv "$BUILD_VENV"
# shellcheck disable=SC1091
source "$BUILD_VENV/bin/activate"

python -m pip install --upgrade pip
python -m pip install 'Nuitka[onefile]' "$ROOT"

# zeroconf fonctionne en Python pur. Ses accélérateurs Cython peuvent entrer en
# conflit avec les classes recompilées par Nuitka dans un one-file.
python -m pip uninstall -y zeroconf
SKIP_CYTHON=1 python -m pip install \
  --no-cache-dir \
  --no-binary=zeroconf \
  "zeroconf==$ZEROCONF_VERSION"

python - <<'PY'
from pathlib import Path
import zeroconf

root = Path(zeroconf.__file__).resolve().parent
extensions = sorted([*root.rglob("*.so"), *root.rglob("*.pyd")])
if extensions:
    print("Erreur: extensions natives zeroconf détectées:")
    for path in extensions:
        print(f"  - {path}")
    raise SystemExit(1)
print(f"zeroconf pur Python: {root}")
PY

rm -rf "$DIST"
mkdir -p "$DIST"

ENTRY="$ROOT/packaging/standalone_entry.py"
python -m nuitka \
  --mode=onefile \
  --enable-plugin=pyside6 \
  --include-package=androidtvremote2 \
  --include-package=zeroconf \
  --include-package-data=freebox_pop_remote \
  --include-data-dir="$ROOT/src/assets=freebox_pop_remote/assets" \
  --linux-icon="$ROOT/src/assets/freebox-pop-remote-512.png" \
  --output-dir="$DIST" \
  --output-filename=freebox-pop-remote \
  "$ENTRY"

# Smoke tests: ils chargent le payload one-file et détectent les dépendances
# manquantes/incompatibles sans ouvrir l'interface graphique.
"$BIN" --check-runtime
ACTUAL_VERSION="$("$BIN" --version)"
EXPECTED_VERSION="Freebox Pop Remote $VERSION"
if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "Erreur: version du binaire inattendue: $ACTUAL_VERSION" >&2
  echo "Attendu: $EXPECTED_VERSION" >&2
  exit 1
fi

printf '\nBinaire Linux autonome: %s\n' "$BIN"
file "$BIN" || true
