from io import StringIO
from pathlib import Path
from threading import Event, Thread

from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService, SpeechService
from app.voice import (
    SelfVoiceDetector,
    VoiceConversationController,
    VoiceState,
    WakeWordService,
)


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeAudioRecorder:
    def __init__(self, audio_path: Path, payload: bytes = b"audio") -> None:
        self.audio_path = audio_path
        self.payload = payload
        self.calls = 0

    def record(self) -> Path:
        self.calls += 1
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_path.write_bytes(self.payload)

        return self.audio_path


class RecordingRecognitionProvider:
    def __init__(self, transcription: str) -> None:
        self.transcription = transcription
        self.calls = 0

    def transcribe(self, audio_path: Path, language: str) -> str:
        self.calls += 1

        return self.transcription


class RecordingSpeechProvider:
    def __init__(self) -> None:
        self.spoken_texts = []

    def speak(self, text: str) -> None:
        self.spoken_texts.append(text)


class ControllableDetector:
    def __init__(self) -> None:
        self.wait_calls = 0
        self.wait_started = Event()
        self.closed = False
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


def _controller(
    tmp_path,
    conversation_service_factory,
    transcription: str,
    self_voice_detector: SelfVoiceDetector,
    conversation=None,
):
    output = StringIO()
    speech_provider = RecordingSpeechProvider()
    presenter = AgentOutputPresenter(
        speech_service=SpeechService(
            provider=speech_provider,
            enabled=True,
        ),
        output=output,
        self_voice_detector=self_voice_detector,
    )
    controller = VoiceConversationController(
        recognition=SpeechRecognitionService(
            provider=RecordingRecognitionProvider(transcription),
            recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
            enabled=True,
        ),
        conversation=conversation or conversation_service_factory(),
        presenter=presenter,
        output=output,
        self_voice_detector=self_voice_detector,
    )

    return controller, output, speech_provider


def test_nearly_identical_agent_speech_is_self_voice():
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )

    assert detector.is_probable_self_voice(
        "Hey Airton! How are you doing today?"
    )


def test_punctuation_and_capitalization_differences_are_self_voice():
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )

    assert detector.is_probable_self_voice(
        "Hey Airton, how are you doing today?"
    )


def test_different_text_is_not_self_voice():
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )

    assert not detector.is_probable_self_voice(
        "Let's practice the past tense."
    )


def test_similar_text_outside_window_is_not_blocked():
    clock = FakeClock(0.0)
    detector = SelfVoiceDetector(
        window_seconds=8.0,
        clock=clock,
    )
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )
    clock.now = 20.0

    assert not detector.is_probable_self_voice(
        "Hey Airton, how are you doing today?"
    )


def test_self_voice_does_not_reach_conversation_and_returns_to_idle(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    controller, output, speech_provider = _controller(
        tmp_path,
        conversation_service_factory,
        transcription="Hey Airton, how are you doing today?",
        self_voice_detector=detector,
        conversation=conversation,
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.transcription == (
        "Hey Airton, how are you doing today?"
    )
    assert result.response is None
    assert inspectable_ai_client.messages == []
    assert conversation.memory.load() == []
    assert controller.state is VoiceState.IDLE
    assert "You:" not in output.getvalue()
    assert speech_provider.spoken_texts == []


def test_normal_user_speech_still_reaches_conversation(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Hey Airton! How are you doing today?"
    )
    controller, output, speech_provider = _controller(
        tmp_path,
        conversation_service_factory,
        transcription="What did I learn yesterday?",
        self_voice_detector=detector,
        conversation=conversation_service_factory(
            ai_client=fake_ai_client
        ),
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.transcription == "What did I learn yesterday?"
    assert result.response == (
        "Fake response for: What did I learn yesterday?"
    )
    assert "You: What did I learn yesterday?" in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: What did I learn yesterday?"
    ]
    assert controller.state is VoiceState.IDLE


def test_voice_command_still_works_with_self_voice_detector(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    controller, output, speech_provider = _controller(
        tmp_path,
        conversation_service_factory,
        transcription="How was your day?",
        self_voice_detector=SelfVoiceDetector(clock=FakeClock(10.0)),
        conversation=conversation_service_factory(
            ai_client=fake_ai_client
        ),
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.transcription == "How was your day?"
    assert "Listening..." in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]


def test_wake_word_ignores_echo_of_last_agent_speech(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "I'm here when you want to practice."
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    controller, output, _speech_provider = _controller(
        tmp_path,
        conversation_service_factory,
        transcription="I'm here when you want to practice.",
        self_voice_detector=detector,
        conversation=conversation,
    )
    wake_detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=wake_detector,
        enabled=True,
        wake_word="pran",
    )

    service.start()
    assert wake_detector.wait_started.wait(timeout=1)
    wake_detector.emit(True)
    assert _wait_until(lambda: wake_detector.wait_calls >= 2)
    service.stop()

    assert inspectable_ai_client.messages == []
    assert conversation.memory.load() == []
    assert controller.state is VoiceState.IDLE
    assert "You:" not in output.getvalue()
    assert wake_detector.closed is True


def test_presenter_remembers_only_successfully_spoken_text():
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    presenter = AgentOutputPresenter(
        speech_service=SpeechService(
            provider=RecordingSpeechProvider(),
            enabled=True,
        ),
        output=StringIO(),
        self_voice_detector=detector,
    )

    presenter.show_agent_response(
        "Hey Airton! How are you doing today?"
    )

    assert detector.is_probable_self_voice(
        "Hey Airton, how are you doing today?"
    )


def test_from_env_reads_window_and_threshold(monkeypatch):
    monkeypatch.setenv("ENGLISH_AGENT_SELF_VOICE_WINDOW_SECONDS", "3")
    monkeypatch.setenv(
        "ENGLISH_AGENT_SELF_VOICE_SIMILARITY_THRESHOLD",
        "0.9",
    )

    detector = SelfVoiceDetector.from_env()

    assert detector.window_seconds == 3.0
    assert detector.similarity_threshold == 0.9
