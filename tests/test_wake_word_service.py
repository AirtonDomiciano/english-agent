from io import BytesIO, StringIO
from pathlib import Path
from threading import Event, Thread

from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService, SpeechService
from app.voice import (
    NullWakeWordDetector,
    VoiceConversationController,
    VoiceState,
    WakeWordService,
)
from app.voice.wake_word_providers.openwakeword import (
    ArecordFrameSource,
    OpenWakeWordDetector,
    _resolve_wake_word_model,
)


class FakeAudioRecorder:
    def __init__(
        self,
        audio_path: Path,
        payload: bytes = b"audio",
        on_record=None,
    ) -> None:
        self.audio_path = audio_path
        self.payload = payload
        self.on_record = on_record
        self.calls = 0

    def record(self) -> Path:
        self.calls += 1

        if self.on_record:
            self.on_record()

        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_path.write_bytes(self.payload)

        return self.audio_path


class RecordingRecognitionProvider:
    def transcribe(self, audio_path: Path, language: str) -> str:
        return "How was your day?"


class RecordingSpeechProvider:
    def __init__(self, on_speak=None) -> None:
        self.spoken_texts = []
        self.on_speak = on_speak

    def speak(self, text: str) -> None:
        if self.on_speak:
            self.on_speak()

        self.spoken_texts.append(text)


class ControllableDetector:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.closed = False
        self.wait_started = Event()
        self._results = []
        self._available = Event()

    def emit(self, detected: bool = True) -> None:
        self._results.append(detected)
        self._available.set()

    def wait(self, stop_event: Event) -> bool:
        self.wait_calls += 1
        self.wait_started.set()

        while not stop_event.is_set():
            if self._available.wait(timeout=0.05):
                if self._results:
                    result = self._results.pop(0)

                    if not self._results:
                        self._available.clear()

                    return result

                self._available.clear()

        return False

    def close(self) -> None:
        self.closed = True
        self._available.set()


class FailingDetector:
    def __init__(self) -> None:
        self.closed = False
        self.failed = Event()

    def wait(self, stop_event: Event) -> bool:
        self.failed.set()
        raise RuntimeError("detector failed")

    def close(self) -> None:
        self.closed = True


class FakeFrameSource:
    def __init__(self, frames: list[bytes] | None = None) -> None:
        self.frames = list(frames or [])
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def read(self, nbytes: int) -> bytes | None:
        if self.frames:
            return self.frames.pop(0)

        return None

    def stop(self) -> None:
        self.stopped += 1


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    reached = Event()

    def run():
        while not reached.is_set():
            if predicate():
                reached.set()
                return

            if reached.wait(0.02):
                return

    waiter = Thread(target=run)
    waiter.start()
    found = reached.wait(timeout=timeout)
    reached.set()
    waiter.join(timeout=0.2)

    return found


def _build_controller(
    tmp_path,
    conversation_service_factory,
    recorder=None,
    speech_provider=None,
    conversation=None,
):
    output = StringIO()
    speech_provider = speech_provider or RecordingSpeechProvider()
    controller = VoiceConversationController(
        recognition=SpeechRecognitionService(
            provider=RecordingRecognitionProvider(),
            recorder=recorder
            or FakeAudioRecorder(tmp_path / "voice.wav"),
            enabled=True,
        ),
        conversation=conversation or conversation_service_factory(),
        presenter=AgentOutputPresenter(
            speech_service=SpeechService(
                provider=speech_provider,
                enabled=True,
            ),
            output=output,
        ),
        output=output,
    )

    return controller, output, speech_provider


def test_wake_word_starts_a_voice_turn(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    spoken = Event()
    controller, output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
        speech_provider=RecordingSpeechProvider(on_speak=spoken.set),
        conversation=conversation_service_factory(
            ai_client=fake_ai_client
        ),
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
        wake_word="pran",
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    detector.emit(True)
    assert spoken.wait(timeout=1)
    service.stop()

    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert "Listening..." in output.getvalue()
    assert controller.state is VoiceState.IDLE
    assert detector.closed is True


def test_wake_word_is_ignored_when_controller_is_busy(
    tmp_path,
    conversation_service_factory,
):
    controller, _output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )
    controller.state = VoiceState.THINKING
    turns = []
    controller.handle_voice_turn = (
        lambda: turns.append("started") or VoiceState.IDLE
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    detector.emit(True)
    assert _wait_until(lambda: detector.wait_calls >= 2)
    service.stop()

    assert turns == []
    assert speech_provider.spoken_texts == []
    assert controller.state is VoiceState.THINKING


def test_wake_word_does_not_start_while_speaking(
    tmp_path,
    conversation_service_factory,
):
    controller, _output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )
    controller.state = VoiceState.SPEAKING
    turns = []
    controller.handle_voice_turn = lambda: turns.append("started")
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    detector.emit(True)
    assert _wait_until(lambda: detector.wait_calls >= 2)
    service.stop()

    assert turns == []
    assert controller.can_start_turn() is False
    assert speech_provider.spoken_texts == []


def test_wake_word_does_not_create_two_simultaneous_turns(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    listening = Event()
    release = Event()
    recorder = FakeAudioRecorder(
        tmp_path / "voice.wav",
        on_record=lambda: (listening.set(), release.wait(timeout=1)),
    )
    controller, _output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
        recorder=recorder,
        conversation=conversation_service_factory(
            ai_client=fake_ai_client
        ),
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
    )
    voice_thread = Thread(target=controller.handle_voice_turn)

    service.start()
    voice_thread.start()
    assert listening.wait(timeout=1)
    detector.emit(True)
    assert _wait_until(lambda: detector.wait_calls >= 1)
    release.set()
    voice_thread.join(timeout=1)
    service.stop()

    assert recorder.calls == 1
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert controller.state is VoiceState.IDLE


def test_disabled_wake_word_service_does_nothing(
    tmp_path,
    conversation_service_factory,
):
    controller, _output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=False,
    )

    service.start()
    detector.emit(True)
    service.stop()

    assert service._thread is None
    assert detector.wait_calls == 0
    assert speech_provider.spoken_texts == []


def test_from_env_disabled_uses_null_detector(
    tmp_path,
    conversation_service_factory,
    monkeypatch,
):
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD_ENABLED", "false")
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD", "hey mycroft")
    controller, _output, _speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )

    service = WakeWordService.from_env(controller=controller)

    assert service.enabled is False
    assert service.wake_word == "hey mycroft"
    assert isinstance(service.detector, NullWakeWordDetector)


def test_provider_error_does_not_crash_the_app(
    tmp_path,
    conversation_service_factory,
):
    controller, _output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )
    errors = []
    detector = FailingDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
        error_handler=errors.append,
    )

    service.start()
    assert detector.failed.wait(timeout=1)
    service.stop()

    assert errors
    assert str(errors[0]) == "detector failed"
    assert detector.closed is True
    assert speech_provider.spoken_texts == []
    assert controller.state is VoiceState.IDLE


def test_from_env_provider_failure_disables_service(
    tmp_path,
    conversation_service_factory,
    monkeypatch,
):
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD_ENABLED", "true")
    monkeypatch.setattr(
        "app.voice.wake_word._provider_from_env",
        lambda wake_word: (_ for _ in ()).throw(
            RuntimeError("openwakeword unavailable")
        ),
    )
    errors = []
    controller, _output, _speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )

    service = WakeWordService.from_env(
        controller=controller,
        error_handler=errors.append,
    )

    assert service.enabled is False
    assert isinstance(service.detector, NullWakeWordDetector)
    assert "openwakeword unavailable" in str(errors[0])


def test_shutdown_closes_detector_and_stops_thread(
    tmp_path,
    conversation_service_factory,
):
    controller, _output, _speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    thread = service._thread
    service.stop()

    assert detector.closed is True
    assert service._thread is None
    assert thread is not None
    assert not thread.is_alive()


def test_voice_command_works_independently_of_wake_word(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    controller, output, speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
        conversation=conversation_service_factory(
            ai_client=fake_ai_client
        ),
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        enabled=True,
    )

    service.start()
    result = controller.handle_voice_turn()
    service.stop()

    assert result.accepted is True
    assert result.transcription == "How was your day?"
    assert "Listening..." in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert detector.wait_calls >= 1


def test_openwakeword_detector_starts_turn_signal_without_real_mic():
    source = FakeFrameSource([b"\x00" * 2560])
    detector = OpenWakeWordDetector(
        wake_word="pran",
        model_name="pran",
        threshold=0.5,
        frame_source=source,
        predictor=lambda raw: {"pran": 0.91},
    )

    detected = detector.wait(Event())

    assert detected is True
    assert source.started == 1
    assert source.stopped == 1


def test_openwakeword_detector_releases_mic_when_stopped():
    stop_event = Event()
    stop_event.set()
    source = FakeFrameSource()
    detector = OpenWakeWordDetector(
        wake_word="pran",
        model_name="pran",
        frame_source=source,
        predictor=lambda raw: {"pran": 0.1},
    )

    detected = detector.wait(stop_event)
    detector.close()

    assert detected is False
    assert source.stopped >= 1


def test_custom_wake_word_requires_trained_model_path():
    try:
        _resolve_wake_word_model("pran")
    except RuntimeError as error:
        message = str(error)
        assert "no pretrained model" in message
        assert "ENGLISH_AGENT_WAKE_WORD_MODEL" in message
    else:
        raise AssertionError("custom wake word must require a model")


def test_custom_wake_word_uses_configured_model_path(tmp_path):
    model_path = tmp_path / "pran.onnx"
    model_path.write_bytes(b"onnx")

    resolved = _resolve_wake_word_model("pran", str(model_path))

    assert resolved == str(model_path)


def test_pretrained_wake_word_still_resolves_without_custom_model():
    assert _resolve_wake_word_model("hey jarvis") == "hey_jarvis"
    assert _resolve_wake_word_model("hey mycroft") == "hey_mycroft"


def test_from_env_custom_wake_word_without_model_disables_safely(
    tmp_path,
    conversation_service_factory,
    monkeypatch,
):
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD", "pran")
    monkeypatch.delenv("ENGLISH_AGENT_WAKE_WORD_MODEL", raising=False)
    errors = []
    controller, _output, _speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )

    service = WakeWordService.from_env(
        controller=controller,
        error_handler=errors.append,
    )

    assert service.enabled is False
    assert service.wake_word == "pran"
    assert isinstance(service.detector, NullWakeWordDetector)
    assert "ENGLISH_AGENT_WAKE_WORD_MODEL" in str(errors[0])


def test_from_env_custom_wake_word_with_model_keeps_provider(
    tmp_path,
    conversation_service_factory,
    monkeypatch,
):
    model_path = tmp_path / "pran.onnx"
    model_path.write_bytes(b"onnx")
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD_ENABLED", "true")
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD", "pran")
    monkeypatch.setenv("ENGLISH_AGENT_WAKE_WORD_MODEL", str(model_path))
    controller, _output, _speech_provider = _build_controller(
        tmp_path,
        conversation_service_factory,
    )

    service = WakeWordService.from_env(controller=controller)

    assert service.enabled is True
    assert service.wake_word == "pran"
    assert isinstance(service.detector, OpenWakeWordDetector)
    assert service.detector.model_name == str(model_path)


def test_arecord_frame_source_does_not_hardcode_device(monkeypatch):
    started = {}

    class FakeProcess:
        def __init__(self, command, stdout, stderr):
            started["command"] = command
            started["stderr"] = stderr
            self.stdout = BytesIO(b"")

        def terminate(self) -> None:
            started["terminated"] = True

        def wait(self, timeout=None) -> int:
            return 0

        def kill(self) -> None:
            started["killed"] = True

    monkeypatch.setattr(
        "app.voice.wake_word_providers.openwakeword.subprocess.Popen",
        FakeProcess,
    )
    source = ArecordFrameSource(command=("arecord",))

    source.start()
    source.stop()

    assert started["command"][0] == "arecord"
    assert "-D" not in started["command"]
    assert started["terminated"] is True
