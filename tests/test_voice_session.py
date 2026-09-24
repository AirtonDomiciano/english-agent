from io import StringIO
from pathlib import Path
from threading import Event, Thread

from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService, SpeechService
from app.voice import (
    SelfVoiceDetector,
    VoiceConversationController,
    VoiceConversationSession,
    VoiceSessionState,
    VoiceState,
    WakeWordService,
    is_voice_session_end,
)


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


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


class FailingAudioRecorder:
    def __init__(self, on_record=None) -> None:
        self.on_record = on_record
        self.calls = 0

    def record(self) -> Path:
        self.calls += 1

        if self.on_record:
            self.on_record()

        raise RuntimeError("microphone unavailable")


class ScriptedRecognitionProvider:
    def __init__(self, transcriptions: list[str]) -> None:
        self.transcriptions = list(transcriptions)
        self.calls = []

    def transcribe(self, audio_path: Path, language: str) -> str:
        self.calls.append(str(audio_path))

        if not self.transcriptions:
            return ""

        return self.transcriptions.pop(0)


class FailingRecognitionProvider:
    def transcribe(self, audio_path: Path, language: str) -> str:
        raise RuntimeError("transcription unavailable")


class RecordingSpeechProvider:
    def __init__(self, on_speak=None) -> None:
        self.spoken_texts = []
        self.on_speak = on_speak

    def speak(self, text: str) -> None:
        if self.on_speak:
            self.on_speak()

        self.spoken_texts.append(text)


class FailingSpeechProvider:
    def speak(self, text: str) -> None:
        raise RuntimeError("speaker unavailable")


class RaisingConversationService:
    def handle_message(self, message: str) -> str:
        raise RuntimeError("conversation unavailable")


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


def _build_session(
    tmp_path,
    conversation_service_factory,
    transcriptions,
    conversation=None,
    speech_provider=None,
    recorder=None,
    recognition_provider=None,
    self_voice_detector=None,
    clock=None,
    timeout_seconds: float = 15.0,
    on_state_change=None,
):
    output = StringIO()
    observed_states = []
    speech_provider = speech_provider or RecordingSpeechProvider()
    controller = VoiceConversationController(
        recognition=SpeechRecognitionService(
            provider=recognition_provider
            or ScriptedRecognitionProvider(transcriptions),
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
            self_voice_detector=self_voice_detector,
        ),
        output=output,
        on_state_change=on_state_change or (
            lambda _previous, current: observed_states.append(current)
        ),
        self_voice_detector=self_voice_detector,
    )
    session = VoiceConversationSession(
        controller=controller,
        timeout_seconds=timeout_seconds,
        clock=clock,
        output=output,
    )

    return session, controller, output, observed_states, speech_provider


def test_is_voice_session_end_recognizes_configured_phrases():
    assert is_voice_session_end("Bye!")
    assert is_voice_session_end("goodbye")
    assert is_voice_session_end("See you later.")
    assert is_voice_session_end("that's all")
    assert not is_voice_session_end("How are you today?")


def test_wake_word_starts_session_and_first_turn_works(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    spoken = Event()
    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How are you today?", "bye"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            speech_provider=RecordingSpeechProvider(
                on_speak=spoken.set
            ),
        )
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        session=session,
        enabled=True,
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    detector.emit(True)
    assert spoken.wait(timeout=1)
    assert _wait_until(lambda: not session.is_active)
    service.stop()

    assert "You: How are you today?" in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: How are you today?"
    ]
    assert controller.state is VoiceState.IDLE
    assert session.state is VoiceSessionState.INACTIVE


def test_session_returns_to_listening_and_handles_second_turn(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    observed = []
    session, controller, output, states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=[
                "How are you today?",
                "I'm working right now.",
                "bye",
            ],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            on_state_change=lambda _previous, current: (
                observed.append(current)
            ),
        )
    )

    session.run()

    listening_indexes = [
        index
        for index, state in enumerate(observed)
        if state is VoiceState.LISTENING
    ]

    assert len(listening_indexes) >= 2
    assert VoiceState.SPEAKING in observed[:listening_indexes[1]]
    assert "You: I'm working right now." in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: How are you today?",
        "Fake response for: I'm working right now.",
    ]
    assert controller.state is VoiceState.IDLE
    assert session.state is VoiceSessionState.INACTIVE


def test_self_voice_is_ignored_during_session(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    detector = SelfVoiceDetector(clock=FakeClock(10.0))
    detector.remember_agent_speech(
        "Fake response for: How are you today?"
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=[
                "Fake response for: How are you today?",
                "I'm working right now.",
                "bye",
            ],
            conversation=conversation,
            self_voice_detector=detector,
        )
    )

    session.run()

    assert inspectable_ai_client.messages[-1]["content"] == (
        "I'm working right now."
    )
    assert "You: Fake response for: How are you today?" not in (
        output.getvalue()
    )
    assert speech_provider.spoken_texts == ["Fake response"]
    assert controller.state is VoiceState.IDLE


def test_silence_ends_session(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    clock = FakeClock(0.0)

    def transcribe(audio_path: Path, language: str) -> str:
        if not hasattr(transcribe, "calls"):
            transcribe.calls = 0

        transcribe.calls += 1

        if transcribe.calls == 1:
            return "How are you today?"

        clock.now = 16.0

        return ""

    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=[],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            recognition_provider=type(
                "Provider",
                (),
                {"transcribe": staticmethod(transcribe)},
            )(),
            clock=clock,
            timeout_seconds=15.0,
        )
    )

    session.run()

    assert speech_provider.spoken_texts == [
        "Fake response for: How are you today?"
    ]
    assert "I'll wait until you say the wake word." in (
        output.getvalue()
    )
    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_farewell_ends_session_without_llm(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["See you later."],
            conversation=conversation,
        )
    )

    session.run()

    assert inspectable_ai_client.messages == []
    assert conversation.memory.load() == []
    assert "You: See you later." in output.getvalue()
    assert "Agent: See you later." in output.getvalue()
    assert speech_provider.spoken_texts == []
    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_wake_word_works_again_after_session_ends(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["bye", "bye"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
        )
    )
    detector = ControllableDetector()
    service = WakeWordService(
        controller=controller,
        detector=detector,
        session=session,
        enabled=True,
    )

    service.start()
    assert detector.wait_started.wait(timeout=1)
    detector.emit(True)
    assert _wait_until(lambda: detector.wait_calls >= 2)
    assert session.state is VoiceSessionState.INACTIVE
    detector.emit(True)
    assert _wait_until(lambda: detector.wait_calls >= 3)
    service.stop()

    assert output.getvalue().count("You: bye") == 2
    assert speech_provider.spoken_texts == []


def test_duplicate_wake_word_does_not_start_second_session(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    started = Event()
    release = Event()
    session, controller, _output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How are you today?", "bye"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            recorder=FakeAudioRecorder(
                tmp_path / "voice.wav",
                on_record=lambda: (
                    started.set(),
                    release.wait(timeout=1),
                ),
            ),
        )
    )
    first = Thread(target=session.run)
    second_done = Event()

    def start_second():
        session.run()
        second_done.set()

    first.start()
    assert started.wait(timeout=1)
    assert session.is_active is True
    assert session.can_start() is False
    second = Thread(target=start_second)
    second.start()
    assert second_done.wait(timeout=1)
    release.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert speech_provider.spoken_texts == [
        "Fake response for: How are you today?"
    ]
    assert session.state is VoiceSessionState.INACTIVE


def test_stt_error_does_not_leave_session_stuck(
    tmp_path,
    conversation_service_factory,
):
    clock = FakeClock(0.0)
    session, controller, _output, _states, _speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=[],
            recorder=FailingAudioRecorder(
                on_record=lambda: setattr(clock, "now", 16.0)
            ),
            clock=clock,
            timeout_seconds=15.0,
        )
    )

    session.run()

    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_llm_error_does_not_leave_session_stuck(
    tmp_path,
    conversation_service_factory,
):
    session, controller, _output, _states, _speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How are you today?", "bye"],
            conversation=RaisingConversationService(),
        )
    )

    session.run()

    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_tts_error_does_not_leave_session_stuck(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    session, controller, output, _states, _speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How are you today?", "bye"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            speech_provider=FailingSpeechProvider(),
        )
    )

    session.run()

    assert "You: How are you today?" in output.getvalue()
    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_shutdown_stops_active_session(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    started = Event()
    session, controller, _output, _states, _speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How are you today?"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
            recorder=FakeAudioRecorder(
                tmp_path / "voice.wav",
                on_record=started.set,
            ),
        )
    )
    worker = Thread(target=session.run)

    worker.start()
    assert started.wait(timeout=1)
    session.stop()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert session.state is VoiceSessionState.INACTIVE
    assert controller.state is VoiceState.IDLE


def test_voice_command_still_runs_a_single_turn(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    session, controller, output, _states, speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["How was your day?"],
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
        )
    )

    result = controller.handle_voice_turn()

    assert session.is_active is False
    assert result.accepted is True
    assert result.transcription == "How was your day?"
    assert result.heard_user is True
    assert "Listening..." in output.getvalue()
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert controller.state is VoiceState.IDLE


def test_from_env_reads_session_timeout(
    tmp_path,
    conversation_service_factory,
    monkeypatch,
):
    monkeypatch.setenv(
        "ENGLISH_AGENT_VOICE_SESSION_TIMEOUT_SECONDS",
        "12",
    )
    session, _controller, _output, _states, _speech_provider = (
        _build_session(
            tmp_path,
            conversation_service_factory,
            transcriptions=["bye"],
        )
    )
    configured = VoiceConversationSession.from_env(
        controller=session.controller
    )

    assert configured.timeout_seconds == 12.0
