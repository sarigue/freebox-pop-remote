"""Android TV Remote v2 networking backend.

The Qt UI stays on the main thread. Async network operations run in a
dedicated asyncio thread and communicate with the UI through Qt signals.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import ipaddress
import threading
from typing import Any

from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
    VoiceSessionInProgress,
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
    voice_started = Signal()
    voice_stopped = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_ready = threading.Event()
        self._closing = threading.Event()
        self._shutdown_lock = threading.Lock()
        self._submitted_lock = threading.Lock()
        self._submitted: set[concurrent.futures.Future[Any]] = set()
        self._remote: AndroidTVRemote | None = None
        self._pairing_future: asyncio.Future[str | None] | None = None
        self._voice_stream: Any | None = None
        self._voice_requested = False
        self._host: str | None = None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._run_loop,
            name="freebox-pop-remote-asyncio",
            daemon=True,
        )
        self._thread.start()

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

    def _emit(self, signal: Any, *args: Any) -> None:
        """Emit only while the Qt receiver can still be alive."""
        if not self._closing.is_set():
            signal.emit(*args)

    def _submit(self, coro: Any) -> None:
        if self._closing.is_set():
            coro.close()
            return
        self._loop_ready.wait()
        loop = self._loop
        if loop is None or not loop.is_running() or self._closing.is_set():
            coro.close()
            return
        try:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
        except RuntimeError:
            coro.close()
            if not self._closing.is_set():
                raise
            return
        with self._submitted_lock:
            self._submitted.add(future)

        def done_callback(done: Any) -> None:
            with self._submitted_lock:
                self._submitted.discard(done)
            try:
                done.result()
            except (asyncio.CancelledError, concurrent.futures.CancelledError):
                pass
            except Exception as exc:  # defensive UI boundary
                self._emit(self.error, f"{type(exc).__name__}: {exc}")

        future.add_done_callback(done_callback)

    def scan(self, timeout: float = 4.0) -> None:
        self._submit(self._scan(timeout))

    async def _scan(self, timeout: float) -> None:
        self._emit(self.scan_started)
        self._emit(self.status_changed, "Recherche des Players Android TV sur le réseau…")
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
        self._emit(self.devices_found, result)
        self._emit(self.scan_finished)
        if result:
            self._emit(self.status_changed, f"{len(result)} appareil(s) Android TV détecté(s).")
        else:
            self._emit(
                self.status_changed,
                "Aucun Player détecté par mDNS. Tu peux saisir son IP manuellement.",
            )

    def connect(self, host: str) -> None:
        self._submit(self._connect(host))

    async def _connect(self, host: str) -> None:
        host = host.strip()
        if not host:
            self._emit(self.error, "Adresse IP vide.")
            return

        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            # Hostnames are accepted too. We only reject obviously malformed input.
            if any(c.isspace() for c in host):
                self._emit(self.error, "Adresse IP / nom d’hôte invalide.")
                return

        if self._remote is not None:
            await self._stop_voice()
            with contextlib.suppress(Exception):
                self._remote.disconnect()
            self._remote = None

        self._host = host
        device_dir = DATA_DIR / safe_host_dir(host)
        device_dir.mkdir(parents=True, exist_ok=True)
        certfile = str(device_dir / "cert.pem")
        keyfile = str(device_dir / "key.pem")

        remote = AndroidTVRemote(
            CLIENT_NAME,
            certfile,
            keyfile,
            host,
            enable_voice=True,
        )
        self._remote = remote

        self._emit(self.status_changed, f"Connexion à {host}…")

        try:
            generated = await remote.async_generate_cert_if_missing()
            if generated:
                await self._pair(remote, host)

            while True:
                try:
                    await remote.async_connect()
                    break
                except InvalidAuth:
                    self._emit(self.status_changed, "Appairage requis.")
                    await self._pair(remote, host)
                except (CannotConnect, ConnectionClosed) as exc:
                    self._emit(self.connected_changed, False, "")
                    self._emit(self.status_changed, f"Connexion impossible à {host}.")
                    raise exc
        except PairingCancelled:
            with contextlib.suppress(Exception):
                remote.disconnect()
            self._remote = None
            self._emit(self.connected_changed, False, "")
            self._emit(self.status_changed, "Appairage annulé.")
            return

        remote.keep_reconnecting()

        try:
            name, _mac = await remote.async_get_name_and_mac()
        except Exception:
            name = ""

        display = name or host
        self._emit(self.connected_changed, True, display)
        self._emit(self.status_changed, f"Connecté à {display}.")

        def available_updated(is_available: bool) -> None:
            if self._closing.is_set():
                return
            if is_available:
                self._emit(self.connected_changed, True, display)
                self._emit(self.status_changed, f"Connecté à {display}.")
            else:
                self._end_voice_stream()
                self._emit(self.connected_changed, False, display)
                self._emit(
                    self.status_changed,
                    f"{display} est momentanément indisponible — reconnexion automatique…",
                )

        remote.add_is_available_updated_callback(available_updated)

    async def _pair(self, remote: AndroidTVRemote, host: str) -> None:
        self._emit(
            self.status_changed,
            "Démarrage de l’appairage — un code doit apparaître sur le téléviseur…",
        )
        await remote.async_start_pairing()

        while True:
            loop = asyncio.get_running_loop()
            self._pairing_future = loop.create_future()
            self._emit(self.pairing_code_requested, host)
            try:
                code = await self._pairing_future
            finally:
                self._pairing_future = None

            if code is None:
                raise PairingCancelled("Appairage annulé")

            cleaned = code.strip().replace(" ", "")
            if not cleaned:
                self._emit(self.pairing_invalid)
                continue

            try:
                await remote.async_finish_pairing(cleaned)
                self._emit(self.status_changed, "Appairage accepté. Connexion au Player…")
                return
            except InvalidAuth:
                self._emit(self.pairing_invalid)
                self._emit(
                    self.status_changed,
                    "Code refusé. Vérifie le code affiché sur la TV et réessaie.",
                )
            except ConnectionClosed:
                self._emit(
                    self.status_changed,
                    "Session d’appairage expirée, redémarrage de l’appairage…",
                )
                await remote.async_start_pairing()

    def submit_pairing_code(self, code: str) -> None:
        if self._closing.is_set():
            return
        self._loop_ready.wait()
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def set_code() -> None:
            future = self._pairing_future
            if future is not None and not future.done():
                future.set_result(code)

        loop.call_soon_threadsafe(set_code)

    def cancel_pairing(self) -> None:
        if self._closing.is_set():
            return
        self._loop_ready.wait()
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def cancel() -> None:
            future = self._pairing_future
            if future is not None and not future.done():
                future.set_result(None)

        loop.call_soon_threadsafe(cancel)

    def send_key(self, key: str) -> None:
        if self._closing.is_set():
            return
        self._loop_ready.wait()
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def send() -> None:
            if self._remote is None or self._closing.is_set():
                return
            try:
                self._remote.send_key_command(key)
            except Exception as exc:
                self._emit(self.error, f"Envoi de {key} impossible : {exc}")

        loop.call_soon_threadsafe(send)

    def launch(self, url: str) -> None:
        if self._closing.is_set():
            return
        self._loop_ready.wait()
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def send() -> None:
            if self._remote is None or self._closing.is_set():
                return
            try:
                self._remote.send_launch_app_command(url)
            except Exception as exc:
                self._emit(self.error, f"Lancement de l’application impossible : {exc}")

        loop.call_soon_threadsafe(send)

    def start_voice(self) -> None:
        """Start one voice stream without blocking the Qt thread."""
        if self._closing.is_set():
            return
        if self._voice_requested:
            self._emit(self.status_changed, "Une session vocale est déjà en cours.")
            return
        self._voice_requested = True
        self._submit(self._start_voice())

    async def _start_voice(self) -> None:
        remote = self._remote
        if remote is None:
            self._voice_requested = False
            self._emit(self.status_changed, "Aucun Player connecté pour la commande vocale.")
            return
        if remote.is_voice_enabled is False:
            self._voice_requested = False
            self._emit(self.status_changed, "Ce Player ne prend pas en charge la commande vocale.")
            return
        if self._voice_stream is not None:
            self._voice_requested = False
            self._emit(self.status_changed, "Une session vocale est déjà en cours.")
            return

        try:
            stream = await remote.start_voice()
        except VoiceSessionInProgress:
            self._voice_requested = False
            self._emit(self.status_changed, "Une session vocale est déjà en cours sur le Player.")
            return
        except TimeoutError:
            self._voice_requested = False
            self._emit(self.status_changed, "Le Player n’a pas répondu à la demande vocale.")
            return
        except ConnectionClosed:
            self._voice_requested = False
            self._emit(self.status_changed, "Connexion perdue avant le démarrage de la voix.")
            return

        if not self._voice_requested or self._closing.is_set():
            with contextlib.suppress(Exception):
                stream.end()
            return
        self._voice_stream = stream
        self._emit(self.voice_started)
        self._emit(self.status_changed, "Microphone actif — relâche pour envoyer.")

    def send_voice_data(self, pcm_data: bytes) -> None:
        """Queue exact-format PCM data for the active voice stream."""
        if not pcm_data or self._closing.is_set():
            return
        self._submit(self._send_voice_data(bytes(pcm_data)))

    async def _send_voice_data(self, pcm_data: bytes) -> None:
        stream = self._voice_stream
        if stream is None:
            return
        try:
            stream.send_chunk(pcm_data)
        except ConnectionClosed:
            self._end_voice_stream(send_end=False)
            self._emit(self.status_changed, "Connexion perdue pendant la commande vocale.")

    def stop_voice(self) -> None:
        """Stop the current voice stream, if any."""
        self._voice_requested = False
        self._submit(self._stop_voice())

    def _end_voice_stream(self, *, send_end: bool = True) -> None:
        stream = self._voice_stream
        self._voice_stream = None
        self._voice_requested = False
        if stream is not None and send_end:
            with contextlib.suppress(ConnectionClosed):
                stream.end()
        if stream is not None:
            self._emit(self.voice_stopped)

    async def _stop_voice(self) -> None:
        self._end_voice_stream()

    async def _shutdown_async(self) -> None:
        self._voice_requested = False
        with contextlib.suppress(Exception):
            self._end_voice_stream()
        if self._pairing_future is not None and not self._pairing_future.done():
            self._pairing_future.set_result(None)
        if self._remote is not None:
            with contextlib.suppress(Exception):
                self._remote.disconnect()
            self._remote = None

        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks() if task is not current]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def shutdown(self) -> None:
        """Release all async/network resources; safe to call more than once."""
        with self._shutdown_lock:
            if self._closing.is_set():
                return
            self._closing.set()

        if not self._loop_ready.wait(timeout=2):
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        cleanup = asyncio.run_coroutine_threadsafe(self._shutdown_async(), loop)
        try:
            cleanup.result(timeout=5)
        except (asyncio.CancelledError, concurrent.futures.CancelledError):
            pass
        except concurrent.futures.TimeoutError:
            cleanup.cancel()
        finally:
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(loop.stop)

        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=5)
