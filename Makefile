APP := freebox-pop-remote
DISPLAY_NAME := Freebox Pop Remote
VERSION := $(shell sed -n 's/^__version__ = "\([^"]*\)"/\1/p' src/__init__.py | head -n1)

PREFIX ?= /usr/local
DESTDIR ?=
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share
DOCDIR ?= $(DATADIR)/doc/$(APP)
ICONROOT ?= $(DATADIR)/icons/hicolor

LINUX_BIN := dist/linux/$(APP)
SOURCE_FILES := $(shell find src -type f -print) pyproject.toml packaging/standalone_entry.py packaging/build-linux.sh
WINDOWS_BIN := dist/windows/$(APP).exe
MACOS_APP := dist/macos/$(DISPLAY_NAME).app

UNAME_S := $(shell uname -s 2>/dev/null || printf 'Unknown')

ifeq ($(OS),Windows_NT)
HOST_OS := windows
else ifeq ($(UNAME_S),Darwin)
HOST_OS := macos
else ifeq ($(UNAME_S),Linux)
HOST_OS := linux
else
HOST_OS := unknown
endif

.PHONY: all build linux windows macos deb rpm install uninstall check-install \
        test lint clean distclean help

all: build

build:
ifeq ($(HOST_OS),linux)
	@$(MAKE) --no-print-directory linux
else ifeq ($(HOST_OS),macos)
	@$(MAKE) --no-print-directory macos
else ifeq ($(HOST_OS),windows)
	@$(MAKE) --no-print-directory windows
else
	@echo "OS non reconnu automatiquement. Utilise 'make linux', 'make windows' ou 'make macos'." >&2
	@exit 1
endif

linux: $(LINUX_BIN)

windows:
ifeq ($(OS),Windows_NT)
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File packaging/build-windows.ps1
else
	@echo "Le binaire Windows doit être construit sous Windows." >&2
	@exit 1
endif

macos:
ifeq ($(UNAME_S),Darwin)
	./packaging/build-macos.sh
else
	@echo "Le bundle macOS doit être construit sous macOS." >&2
	@exit 1
endif

deb:
	./packaging/build-deb.sh

rpm:
	./packaging/build-rpm.sh

# Installation classique Unix/Linux. Aucun ./configure n'est nécessaire :
# l'application n'a pas de fonctionnalités dépendant d'options de compilation.
install: $(LINUX_BIN)
ifeq ($(UNAME_S),Linux)
	install -Dm755 "$(LINUX_BIN)" "$(DESTDIR)$(BINDIR)/$(APP)"
	install -Dm644 freebox-pop-remote.desktop "$(DESTDIR)$(DATADIR)/applications/freebox-pop-remote.desktop"
	install -Dm644 src/assets/freebox-pop-remote.svg "$(DESTDIR)$(ICONROOT)/scalable/apps/freebox-pop-remote.svg"
	@for size in 48 64 128 256 512; do \
		install -Dm644 "src/assets/freebox-pop-remote-$${size}.png" \
			"$(DESTDIR)$(ICONROOT)/$${size}x$${size}/apps/freebox-pop-remote.png"; \
	done
	install -Dm644 README.md "$(DESTDIR)$(DOCDIR)/README.md"
	install -Dm644 LICENSE.md "$(DESTDIR)$(DOCDIR)/LICENSE.md"
	@if [ -z "$(DESTDIR)" ]; then \
		command -v update-desktop-database >/dev/null 2>&1 && \
			update-desktop-database "$(DATADIR)/applications" >/dev/null 2>&1 || true; \
		command -v gtk-update-icon-cache >/dev/null 2>&1 && \
			gtk-update-icon-cache -q -t -f "$(ICONROOT)" >/dev/null 2>&1 || true; \
	fi
	@printf 'Installé dans %s (version %s)\n' "$(DESTDIR)$(PREFIX)" "$(VERSION)"
else
	@echo "'make install' est actuellement prévu pour Linux." >&2
	@exit 1
endif

uninstall:
ifeq ($(UNAME_S),Linux)
	rm -f "$(DESTDIR)$(BINDIR)/$(APP)"
	rm -f "$(DESTDIR)$(DATADIR)/applications/freebox-pop-remote.desktop"
	rm -f "$(DESTDIR)$(ICONROOT)/scalable/apps/freebox-pop-remote.svg"
	@for size in 48 64 128 256 512; do \
		rm -f "$(DESTDIR)$(ICONROOT)/$${size}x$${size}/apps/freebox-pop-remote.png"; \
	done
	rm -rf "$(DESTDIR)$(DOCDIR)"
	@if [ -z "$(DESTDIR)" ]; then \
		command -v update-desktop-database >/dev/null 2>&1 && \
			update-desktop-database "$(DATADIR)/applications" >/dev/null 2>&1 || true; \
		command -v gtk-update-icon-cache >/dev/null 2>&1 && \
			gtk-update-icon-cache -q -t -f "$(ICONROOT)" >/dev/null 2>&1 || true; \
	fi
	@echo "Freebox Pop Remote désinstallé de $(DESTDIR)$(PREFIX)."
else
	@echo "'make uninstall' est actuellement prévu pour Linux." >&2
	@exit 1
endif

check-install:
ifeq ($(UNAME_S),Linux)
	@test -x "$(DESTDIR)$(BINDIR)/$(APP)"
	@test -f "$(DESTDIR)$(DATADIR)/applications/freebox-pop-remote.desktop"
	@test -f "$(DESTDIR)$(ICONROOT)/scalable/apps/freebox-pop-remote.svg"
	@for size in 48 64 128 256 512; do \
		test -f "$(DESTDIR)$(ICONROOT)/$${size}x$${size}/apps/freebox-pop-remote.png" || exit 1; \
	done
	@grep -qx 'Icon=freebox-pop-remote' "$(DESTDIR)$(DATADIR)/applications/freebox-pop-remote.desktop"
	@echo "Installation et icônes : OK"
else
	@echo "'make check-install' est actuellement prévu pour Linux." >&2
	@exit 1
endif

test:
	python3 -m pytest

lint:
	python3 -m ruff check .
	python3 -m ruff format --check .

clean:
	rm -rf build dist .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

distclean: clean
	rm -rf .venv-build-linux .venv-build-macos .venv-build-windows

help:
	@printf '%s\n' \
	  'Freebox Pop Remote $(VERSION)' \
	  '' \
	  '  make              Build natif pour l OS courant' \
	  '  make linux        Binaire Linux autonome' \
	  '  make windows      Exécutable Windows (à lancer sous Windows)' \
	  '  make macos        Bundle .app (à lancer sous macOS)' \
	  '  make deb          Paquet Debian/Ubuntu (build Linux auto si nécessaire)' \
	  '  make rpm          Paquet RPM (build Linux auto si nécessaire)' \
	  '  sudo make install Installation classique Linux sous /usr/local' \
	  '  sudo make uninstall Désinstallation classique Linux' \
	  '  make check-install Vérifie binaire, .desktop et icônes installés' \
	  '  make test         Tests unitaires' \
	  '  make lint         Ruff' \
	  '  make clean        Nettoyage des artefacts'

$(LINUX_BIN): $(SOURCE_FILES)
	./packaging/build-linux.sh
