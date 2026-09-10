"""QtMultimedia microphone capture for Android TV voice streaming."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication, QIODevice, QObject, Qt, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices, QtAudio

VOICE_CHUNK_SIZE = 8 * 1024


class _AudioSink(QIODevice):
    """Writable QIODevice receiving native audio backend data."""

    chunk_received = Signal(bytes)

    def writeData(self, data: bytes | bytearray | memoryview) -> int:
        payload = bytes(data)
        if payload:
            self.chunk_received.emit(payload)
        return len(payload)

    def readData(self, maxlen: int) -> bytes:  # pragma: no cover - never read
        return b""


class VoiceCapture(QObject):
    """Capture exact 8 kHz/mono/signed-16-bit PCM and emit buffered chunks."""

    data_ready = Signal(bytes)
    error = Signal(str)
    active_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._audio: QAudioSource | None = None
        self._sink: _AudioSink | None = None
        self._buffer = bytearray()
        self._starting = False

    @property
    def active(self) -> bool:
        return self._audio is not None

    def start(self) -> None:
        """Request permission when needed, then open the default microphone."""
        if self.active or self._starting:
            return
        self._starting = True

        if sys.platform == "darwin":
            try:
                from PySide6.QtCore import QMicrophonePermission
            except ImportError:
                self._start_audio()
                return

            app = QCoreApplication.instance()
            permission = QMicrophonePermission()
            status = app.checkPermission(permission) if app is not None else None
            if status == Qt.PermissionStatus.Denied:
                self._starting = False
                self.error.emit(
                    "Accès au microphone refusé. Autorise Freebox Pop Remote dans les réglages système."
                )
                return
            if status == Qt.PermissionStatus.Undetermined and app is not None:
                app.requestPermission(permission, self, self._permission_resolved)
                return

        self._start_audio()

    def _permission_resolved(self, permission) -> None:
        if permission.status() != Qt.PermissionStatus.Granted:
            self._starting = False
            self.error.emit(
                "Accès au microphone refusé. Autorise Freebox Pop Remote dans les réglages système."
            )
            return
        self._start_audio()

    def _start_audio(self) -> None:
        if not self._starting:
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self._starting = False
            self.error.emit("Aucun microphone disponible.")
            return

        audio_format = QAudioFormat()
        audio_format.setSampleRate(8000)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(audio_format):
            self._starting = False
            self.error.emit(
                "Le microphone ne prend pas en charge le format requis (PCM 16 bits mono à 8 kHz)."
            )
            return

        sink = _AudioSink(self)
        sink.open(QIODevice.OpenModeFlag.WriteOnly)
        sink.chunk_received.connect(self._receive)
        audio = QAudioSource(device, audio_format, self)
        audio.setBufferSize(VOICE_CHUNK_SIZE)
        audio.stateChanged.connect(self._state_changed)
        audio.start(sink)

        if audio.error() != QtAudio.Error.NoError:
            sink.close()
            audio.deleteLater()
            self._starting = False
            self.error.emit("Impossible d’accéder au microphone.")
            return

        self._sink = sink
        self._audio = audio
        self._starting = False
        self.active_changed.emit(True)

    def _receive(self, data: bytes) -> None:
        self._buffer.extend(data)
        while len(self._buffer) >= VOICE_CHUNK_SIZE:
            chunk = bytes(self._buffer[:VOICE_CHUNK_SIZE])
            del self._buffer[:VOICE_CHUNK_SIZE]
            self.data_ready.emit(chunk)

    def _state_changed(self, state: QtAudio.State) -> None:
        audio = self._audio
        if (
            audio is not None
            and state == QtAudio.State.StoppedState
            and audio.error() != QtAudio.Error.NoError
        ):
            self.stop()
            self.error.emit("La capture du microphone s’est interrompue.")

    def stop(self) -> None:
        """Stop capture immediately and flush the final partial PCM chunk."""
        self._starting = False
        audio, sink = self._audio, self._sink
        self._audio = None
        self._sink = None
        if audio is not None:
            audio.stop()
            audio.deleteLater()
        if sink is not None:
            sink.close()
            sink.deleteLater()
        if self._buffer:
            self.data_ready.emit(bytes(self._buffer))
            self._buffer.clear()
        if audio is not None:
            self.active_changed.emit(False)
