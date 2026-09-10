import asyncio
import threading
import time

import freebox_pop_remote.backend as backend_module
import pytest
from androidtvremote2 import ConnectionClosed, VoiceSessionInProgress
from freebox_pop_remote.backend import RemoteBackend
from PySide6.QtCore import QCoreApplication


def wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition non satisfaite avant expiration")


@pytest.fixture
def backend(monkeypatch, tmp_path):
    monkeypatch.setattr(backend_module, "DATA_DIR", tmp_path)
    instance = RemoteBackend()
    yield instance
    instance.shutdown()


@pytest.fixture(scope="module", autouse=True)
def qt_application():
    return QCoreApplication.instance() or QCoreApplication([])


class FakeStream:
    def __init__(self):
        self.chunks = []
        self.end_calls = 0

    def send_chunk(self, data):
        self.chunks.append(data)

    def end(self):
        self.end_calls += 1


class FakeRemote:
    is_voice_enabled = True

    def __init__(self, stream=None, start_error=None):
        self.stream = stream or FakeStream()
        self.start_error = start_error
        self.start_calls = 0
        self.disconnect_calls = 0

    async def start_voice(self):
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        return self.stream

    def disconnect(self):
        self.disconnect_calls += 1


def test_cancelled_concurrent_future_does_not_emit_error(backend):
    errors = []
    backend.error.connect(errors.append)

    async def cancelled():
        raise asyncio.CancelledError

    backend._submit(cancelled())
    wait_until(lambda: not backend._submitted)
    assert errors == []


def test_real_submit_exception_is_still_reported(backend):
    errors = []
    backend.error.connect(errors.append)

    async def broken():
        raise ValueError("boom")

    backend._submit(broken())
    wait_until(lambda: bool(errors))
    assert errors == ["ValueError: boom"]


def test_shutdown_during_scan_without_configured_player(monkeypatch, tmp_path):
    started = threading.Event()

    class FakeZeroconf:
        zeroconf = object()

        async def async_close(self):
            pass

    class FakeBrowser:
        def __init__(self, *args, **kwargs):
            pass

        async def async_cancel(self):
            pass

    monkeypatch.setattr(backend_module, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backend_module, "AsyncZeroconf", FakeZeroconf)
    monkeypatch.setattr(backend_module, "AsyncServiceBrowser", FakeBrowser)
    backend = RemoteBackend()
    errors = []
    backend.error.connect(errors.append)
    backend.scan_started.connect(started.set)
    backend.scan(30)
    wait_until(started.is_set)

    backend.shutdown()

    assert errors == []
    assert not backend._thread.is_alive()


def test_shutdown_is_idempotent(backend):
    backend.shutdown()
    backend.shutdown()
    assert not backend._thread.is_alive()


def test_voice_start_send_stop(backend):
    stream = FakeStream()
    remote = FakeRemote(stream)
    backend._remote = remote
    started = threading.Event()
    stopped = threading.Event()
    backend.voice_started.connect(started.set)
    backend.voice_stopped.connect(stopped.set)

    backend.start_voice()
    wait_until(started.is_set)
    backend.send_voice_data(b"\x01\x00" * 4096)
    wait_until(lambda: len(stream.chunks) == 1)
    backend.stop_voice()
    wait_until(stopped.is_set)

    assert stream.chunks == [b"\x01\x00" * 4096]
    assert stream.end_calls == 1


def test_voice_double_start_is_refused(backend):
    remote = FakeRemote()
    backend._remote = remote
    started = threading.Event()
    statuses = []
    backend.voice_started.connect(started.set)
    backend.status_changed.connect(statuses.append)

    backend.start_voice()
    wait_until(started.is_set)
    backend.start_voice()

    assert remote.start_calls == 1
    assert any("déjà en cours" in status for status in statuses)


def test_disconnect_during_voice_session_stops_it(backend):
    stream = FakeStream()
    backend._voice_stream = stream
    backend._voice_requested = True

    backend._end_voice_stream()

    assert backend._voice_stream is None
    assert stream.end_calls == 1


def test_shutdown_during_voice_session(backend):
    stream = FakeStream()
    remote = FakeRemote(stream)
    backend._remote = remote
    started = threading.Event()
    backend.voice_started.connect(started.set)
    backend.start_voice()
    wait_until(started.is_set)

    backend.shutdown()

    assert stream.end_calls == 1
    assert remote.disconnect_calls == 1
    assert not backend._thread.is_alive()


def test_voice_timeout_is_a_status_not_an_error(backend):
    backend._remote = FakeRemote(start_error=TimeoutError())
    statuses = []
    errors = []
    backend.status_changed.connect(statuses.append)
    backend.error.connect(errors.append)

    backend.start_voice()
    wait_until(lambda: bool(statuses))

    assert any("n’a pas répondu" in status for status in statuses)
    assert errors == []


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (ConnectionClosed(), "Connexion perdue"),
        (VoiceSessionInProgress(), "déjà en cours"),
    ],
)
def test_expected_voice_start_errors_do_not_crash(backend, exception, expected):
    backend._remote = FakeRemote(start_error=exception)
    statuses = []
    errors = []
    backend.status_changed.connect(statuses.append)
    backend.error.connect(errors.append)

    backend.start_voice()
    wait_until(lambda: bool(statuses))

    assert any(expected in status for status in statuses)
    assert errors == []


def test_voice_unsupported_by_player_is_non_fatal(backend):
    remote = FakeRemote()
    remote.is_voice_enabled = False
    backend._remote = remote
    statuses = []
    backend.status_changed.connect(statuses.append)

    backend.start_voice()
    wait_until(lambda: bool(statuses))

    assert remote.start_calls == 0
    assert any("ne prend pas en charge" in status for status in statuses)
