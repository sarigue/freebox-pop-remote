"""Android TV Remote v2 networking backend.

The Qt UI stays on the main thread. Async network operations run in a
dedicated asyncio thread and communicate with the UI through Qt signals.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import threading
from typing import Any

from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
)
from PySide6.QtCore import QObject, Signal
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo, AsyncZeroconf

from .constants import CLIENT_NAME, DATA_DIR, SERVICE_TYPE
from .models import DiscoveredDevice
from .utils import decode_mdns_property, safe_host_dir


class PairingCancelled(Exception):
    """Raised when the user cancels the TV pairing flow."""


class RemoteBackend(QObject):
    devices_found = Signal(object)
    scan_started = Signal()
    scan_finished = Signal()
    status_changed = Signal(str)
    error = Signal(str)
    pairing_code_requested = Signal(str)
    pairing_invalid = Signal()
    connected_changed = Signal(bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="freebox-pop-remote-asyncio",
            daemon=True,
        )
        self._thread.start()
        self._remote: AndroidTVRemote | None = None
        self._pairing_future: asyncio.Future[str | None] | None = None
        self._host: str | None = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def _submit(self, coro: Any) -> None:
        self._loop_ready.wait()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def done_callback(done: Any) -> None:
            try:
                done.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # defensive UI boundary
                self.error.emit(f"{type(exc).__name__}: {exc}")

        future.add_done_callback(done_callback)

    def scan(self, timeout: float = 4.0) -> None:
        self._submit(self._scan(timeout))

    async def _scan(self, timeout: float) -> None:
        self.scan_started.emit()
        self.status_changed.emit("Recherche des Players Android TV sur le réseau…")
        devices: dict[str, DiscoveredDevice] = {}
        resolver_tasks: set[asyncio.Task[Any]] = set()
        zc = AsyncZeroconf()

        async def resolve(service_type: str, name: str) -> None:
            info = AsyncServiceInfo(service_type, name)
            if not await info.async_request(zc.zeroconf, 3000):
                return
            addresses = info.parsed_scoped_addresses()
            if not addresses:
                return

            props = info.properties or {}
            friendly = decode_mdns_property(props.get(b"fn"))
            model = decode_mdns_property(props.get(b"md"))
            if not friendly:
                friendly = name.removesuffix("." + service_type).rstrip(".")

            for address in addresses:
                # IPv6 scoped addresses are usable, but for the first version we
                # favor simple LAN IPv4 addresses when both are announced.
                if ":" in address and any(
                    ":" not in existing.host for existing in devices.values()
                ):
                    continue
                devices[address] = DiscoveredDevice(
                    name=friendly or "Android TV",
                    host=address,
                    model=model,
                    port=int(info.port or 6466),
                )

        def on_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change: ServiceStateChange,
        ) -> None:
            if state_change is not ServiceStateChange.Added:
                return
            task = asyncio.create_task(resolve(service_type, name))
            resolver_tasks.add(task)
            task.add_done_callback(resolver_tasks.discard)

        browser = AsyncServiceBrowser(
            zc.zeroconf,
            [SERVICE_TYPE],
            handlers=[on_state_change],
        )

        try:
            await asyncio.sleep(timeout)
            if resolver_tasks:
                await asyncio.gather(*tuple(resolver_tasks), return_exceptions=True)
        finally:
            await browser.async_cancel()
            await zc.async_close()

        result = sorted(
            devices.values(),
            key=lambda item: (item.name.lower(), item.host),
        )
        self.devices_found.emit(result)
        self.scan_finished.emit()
        if result:
            self.status_changed.emit(f"{len(result)} appareil(s) Android TV détecté(s).")
        else:
            self.status_changed.emit(
                "Aucun Player détecté par mDNS. Tu peux saisir son IP manuellement."
            )

    def connect(self, host: str) -> None:
        self._submit(self._connect(host))

    async def _connect(self, host: str) -> None:
        host = host.strip()
        if not host:
            self.error.emit("Adresse IP vide.")
            return

        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            # Hostnames are accepted too. We only reject obviously malformed input.
            if any(c.isspace() for c in host):
                self.error.emit("Adresse IP / nom d’hôte invalide.")
                return

        if self._remote is not None:
            with contextlib.suppress(Exception):
                self._remote.disconnect()
            self._remote = None

        self._host = host
        device_dir = DATA_DIR / safe_host_dir(host)
        device_dir.mkdir(parents=True, exist_ok=True)
        certfile = str(device_dir / "cert.pem")
        keyfile = str(device_dir / "key.pem")

        # androidtvremote2 >= 0.3 supports the explicit enable_voice flag.
        # Ubuntu 25.10/26.04 currently ships 0.1.1, which provides all remote
        # functions used here but predates that optional argument.
        try:
            remote = AndroidTVRemote(
                CLIENT_NAME,
                certfile,
                keyfile,
                host,
                enable_voice=False,
            )
        except TypeError as exc:
            if "enable_voice" not in str(exc):
                raise
            remote = AndroidTVRemote(
                CLIENT_NAME,
                certfile,
                keyfile,
                host,
            )
        self._remote = remote

        self.status_changed.emit(f"Connexion à {host}…")

        try:
            generated = await remote.async_generate_cert_if_missing()
            if generated:
                await self._pair(remote, host)

            while True:
                try:
                    await remote.async_connect()
                    break
                except InvalidAuth:
                    self.status_changed.emit("Appairage requis.")
                    await self._pair(remote, host)
                except (CannotConnect, ConnectionClosed) as exc:
                    self.connected_changed.emit(False, "")
                    self.status_changed.emit(f"Connexion impossible à {host}.")
                    raise exc
        except PairingCancelled:
            self._remote = None
            self.connected_changed.emit(False, "")
            self.status_changed.emit("Appairage annulé.")
            return

        remote.keep_reconnecting()

        try:
            name, _mac = await remote.async_get_name_and_mac()
        except Exception:
            name = ""

        display = name or host
        self.connected_changed.emit(True, display)
        self.status_changed.emit(f"Connecté à {display}.")

        def available_updated(is_available: bool) -> None:
            if is_available:
                self.connected_changed.emit(True, display)
                self.status_changed.emit(f"Connecté à {display}.")
            else:
                self.connected_changed.emit(False, display)
                self.status_changed.emit(
                    f"{display} est momentanément indisponible — reconnexion automatique…"
                )

        remote.add_is_available_updated_callback(available_updated)

    async def _pair(self, remote: AndroidTVRemote, host: str) -> None:
        self.status_changed.emit(
            "Démarrage de l’appairage — un code doit apparaître sur le téléviseur…"
        )
        await remote.async_start_pairing()

        while True:
            loop = asyncio.get_running_loop()
            self._pairing_future = loop.create_future()
            self.pairing_code_requested.emit(host)
            code = await self._pairing_future
            self._pairing_future = None

            if code is None:
                raise PairingCancelled("Appairage annulé")

            cleaned = code.strip().replace(" ", "")
            if not cleaned:
                self.pairing_invalid.emit()
                continue

            try:
                await remote.async_finish_pairing(cleaned)
                self.status_changed.emit("Appairage accepté. Connexion au Player…")
                return
            except InvalidAuth:
                self.pairing_invalid.emit()
                self.status_changed.emit(
                    "Code refusé. Vérifie le code affiché sur la TV et réessaie."
                )
            except ConnectionClosed:
                self.status_changed.emit("Session d’appairage expirée, redémarrage de l’appairage…")
                await remote.async_start_pairing()

    def submit_pairing_code(self, code: str) -> None:
        self._loop_ready.wait()
        assert self._loop is not None

        def set_code() -> None:
            future = self._pairing_future
            if future is not None and not future.done():
                future.set_result(code)

        self._loop.call_soon_threadsafe(set_code)

    def cancel_pairing(self) -> None:
        self._loop_ready.wait()
        assert self._loop is not None

        def cancel() -> None:
            future = self._pairing_future
            if future is not None and not future.done():
                future.set_result(None)

        self._loop.call_soon_threadsafe(cancel)

    def send_key(self, key: str) -> None:
        self._loop_ready.wait()
        if self._loop is None:
            return

        def send() -> None:
            if self._remote is None:
                return
            try:
                self._remote.send_key_command(key)
            except Exception as exc:
                self.error.emit(f"Envoi de {key} impossible : {exc}")

        self._loop.call_soon_threadsafe(send)

    def launch(self, url: str) -> None:
        self._loop_ready.wait()
        if self._loop is None:
            return

        def send() -> None:
            if self._remote is None:
                return
            try:
                self._remote.send_launch_app_command(url)
            except Exception as exc:
                self.error.emit(f"Lancement de l’application impossible : {exc}")

        self._loop.call_soon_threadsafe(send)

    def shutdown(self) -> None:
        if not self._loop_ready.is_set() or self._loop is None:
            return

        def stop() -> None:
            if self._pairing_future is not None and not self._pairing_future.done():
                self._pairing_future.set_result(None)
            if self._remote is not None:
                with contextlib.suppress(Exception):
                    self._remote.disconnect()
            self._loop.stop()

        self._loop.call_soon_threadsafe(stop)
