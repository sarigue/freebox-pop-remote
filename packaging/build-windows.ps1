$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildVenv = Join-Path $Root ".venv-build-windows"
$Dist = Join-Path $Root "dist\windows"
$Bin = Join-Path $Dist "freebox-pop-remote.exe"
$ZeroconfVersion = "0.151.3"
$Version = (Select-String -Path (Join-Path $Root "src\__init__.py") -Pattern '^__version__ = "([^"]+)"$').Matches.Groups[1].Value

if (-not $Version) { throw "Impossible de lire la version dans src\__init__.py" }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version invalide: $Version (format attendu: majeur.mineur.patch)" }
$WindowsVersion = "$Version.0"

Write-Host "Construction de Freebox Pop Remote $Version pour Windows..."

if (Test-Path $BuildVenv) { Remove-Item -Recurse -Force $BuildVenv }

$BootstrapPython = Get-Command python -ErrorAction SilentlyContinue
if ($BootstrapPython) {
    & $BootstrapPython.Source -m venv $BuildVenv
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv $BuildVenv
} else {
    throw "Python 3 est requis pour construire le binaire Windows."
}

$Python = Join-Path $BuildVenv "Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install "Nuitka[onefile]" imageio $Root
& $Python -m pip uninstall -y zeroconf
$env:SKIP_CYTHON = "1"
& $Python -m pip install --no-cache-dir --no-binary=zeroconf "zeroconf==$ZeroconfVersion"
Remove-Item Env:SKIP_CYTHON

& $Python -c @'
from pathlib import Path
import zeroconf
root = Path(zeroconf.__file__).resolve().parent
extensions = sorted([*root.rglob("*.pyd"), *root.rglob("*.so")])
if extensions:
    raise SystemExit("Extensions natives zeroconf détectées: " + ", ".join(map(str, extensions)))
print(f"zeroconf pur Python: {root}")
'@

if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
New-Item -ItemType Directory -Force -Path $Dist | Out-Null
$Entry = Join-Path $Root "packaging\standalone_entry.py"

& $Python -m nuitka `
    --mode=onefile `
    --assume-yes-for-downloads `
    --enable-plugin=pyside6 `
    --include-package=androidtvremote2 `
    --include-package=zeroconf `
    --include-package-data=freebox_pop_remote `
    --include-data-dir="$Root\src\assets=freebox_pop_remote\assets" `
    --windows-console-mode=attach `
    --windows-icon-from-ico="$Root\src\assets\freebox-pop-remote-512.png" `
    --product-name="Freebox Pop Remote" `
    --company-name="Freebox Pop Remote" `
    --file-version="$WindowsVersion" `
    --product-version="$WindowsVersion" `
    --output-dir="$Dist" `
    --output-filename="freebox-pop-remote.exe" `
    $Entry

if ($LASTEXITCODE -ne 0) {
    throw "Nuitka a échoué avec le code $LASTEXITCODE."
}
if (-not (Test-Path $Bin)) {
    throw "Binaire Windows non produit: $Bin"
}

& $Bin --check-runtime
$ActualVersion = (& $Bin --version | Out-String).Trim()
$ExpectedVersion = "Freebox Pop Remote $Version"
if ($ActualVersion -ne $ExpectedVersion) {
    throw "Version du binaire inattendue: $ActualVersion (attendu: $ExpectedVersion)"
}

Write-Host "Binaire Windows autonome: $Bin"
