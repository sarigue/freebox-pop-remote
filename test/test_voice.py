import freebox_pop_remote.voice as voice_module
from freebox_pop_remote.voice import VOICE_CHUNK_SIZE, VoiceCapture
from PySide6.QtMultimedia import QtAudio


def test_audio_sink_write_data_accepts_qt_max_size_argument():
    sink = voice_module._AudioSink()
    chunks = []
    sink.chunk_received.connect(chunks.append)

    assert sink.writeData(b"abcdef", 3) == 3
    assert chunks == [b"abc"]


def test_voice_capture_buffers_full_chunks_and_remainder():
    capture = VoiceCapture()
    chunks = []
    capture.data_ready.connect(chunks.append)

    capture._receive(b"a" * (VOICE_CHUNK_SIZE + 6))
    assert chunks == [b"a" * VOICE_CHUNK_SIZE]

    capture.stop()
    assert chunks == [b"a" * VOICE_CHUNK_SIZE, b"a" * 6]


class FakeSignal:
    def connect(self, callback):
        self.callback = callback


class FakeDevice:
    def __init__(self, *, null=False, supported=True):
        self.null = null
        self.supported = supported
        self.requested_format = None

    def isNull(self):
        return self.null

    def isFormatSupported(self, audio_format):
        self.requested_format = audio_format
        return self.supported


class FakeAudioSource:
    def __init__(self, device, audio_format, parent):
        self.stateChanged = FakeSignal()
        self.buffer_size = None

    def setBufferSize(self, size):
        self.buffer_size = size

    def start(self, sink):
        self.sink = sink

    def error(self):
        return QtAudio.Error.NoError

    def stop(self):
        pass

    def deleteLater(self):
        pass


def test_capture_requests_exact_android_tv_format(monkeypatch):
    device = FakeDevice()
    monkeypatch.setattr(
        voice_module.QMediaDevices, "defaultAudioInput", staticmethod(lambda: device)
    )
    monkeypatch.setattr(voice_module, "QAudioSource", FakeAudioSource)
    capture = VoiceCapture()

    capture.start()

    assert capture.active
    assert device.requested_format.sampleRate() == 8000
    assert device.requested_format.channelCount() == 1
    assert device.requested_format.sampleFormat().name == "Int16"
    assert capture._audio.buffer_size == VOICE_CHUNK_SIZE
    capture.stop()


def test_capture_rejects_unsupported_format_without_starting(monkeypatch):
    device = FakeDevice(supported=False)
    monkeypatch.setattr(
        voice_module.QMediaDevices, "defaultAudioInput", staticmethod(lambda: device)
    )
    capture = VoiceCapture()
    errors = []
    capture.error.connect(errors.append)

    capture.start()

    assert not capture.active
    assert errors == [
        "Le microphone ne prend pas en charge le format requis (PCM 16 bits mono à 8 kHz)."
    ]
