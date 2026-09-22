from io import StringIO
from pathlib import Path
from threading import Event, Thread

from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService, SpeechService
from app.voice import (
    VoiceConversationController,
    VoiceState,
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


class FailingAudioRecorder:
    def record(self) -> Path:
        raise RuntimeError("microphone unavailable")


class RecordingRecognitionProvider:
    def __init__(
        self,
        transcription: str = "How was your day?",
        on_transcribe=None,
    ) -> None:
        self.transcription = transcription
        self.on_transcribe = on_transcribe
        self.calls = []

    def transcribe(self, audio_path: Path, language: str) -> str:
        if self.on_transcribe:
            self.on_transcribe()

        self.calls.append(audio_path)

        return self.transcription


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


def _build_controller(
    tmp_path,
    conversation_service_factory,
    recorder=None,
    recognition_provider=None,
    speech_provider=None,
    conversation=None,
    on_state_change=None,
    enabled: bool = True,
):
    output = StringIO()
    observed_states = []
    speech_provider = speech_provider or RecordingSpeechProvider()
    recognition = SpeechRecognitionService(
        provider=recognition_provider
        or RecordingRecognitionProvider(),
        recorder=recorder
        or FakeAudioRecorder(tmp_path / "voice.wav"),
        enabled=enabled,
    )
    presenter = AgentOutputPresenter(
        speech_service=SpeechService(
            provider=speech_provider,
            enabled=True,
        ),
        output=output,
    )
    controller = VoiceConversationController(
        recognition=recognition,
        conversation=conversation or conversation_service_factory(),
        presenter=presenter,
        output=output,
        on_state_change=on_state_change or (
            lambda _previous, current: observed_states.append(current)
        ),
    )

    return controller, output, observed_states, speech_provider


def test_controller_can_start_turn_only_when_idle():
    controller = VoiceConversationController(
        recognition=SpeechRecognitionService(
            provider=RecordingRecognitionProvider(),
            recorder=FailingAudioRecorder(),
            enabled=True,
        ),
        conversation=RaisingConversationService(),
        presenter=AgentOutputPresenter(
            speech_service=SpeechService(
                provider=RecordingSpeechProvider(),
                enabled=False,
            ),
            output=StringIO(),
        ),
        output=StringIO(),
    )

    assert controller.can_start_turn() is True

    controller.state = VoiceState.SPEAKING

    assert controller.is_busy is True
    assert controller.can_start_turn() is False

    controller.state = VoiceState.LISTENING

    assert controller.can_start_turn() is False


def test_voice_turn_follows_idle_listening_transcribing_thinking_speaking_idle(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    states_during = {}

    def capture_listening():
        states_during["listening"] = controller.state

    def capture_transcribing():
        states_during["transcribing"] = controller.state

    def capture_thinking():
        states_during["thinking"] = controller.state

    def capture_speaking():
        states_during["speaking"] = controller.state
        states_during["listening_while_speaking"] = (
            controller.state is VoiceState.LISTENING
        )

    conversation = conversation_service_factory(
        ai_client=fake_ai_client
    )
    original_handle = conversation.handle_message

    def handle_and_capture(message: str) -> str:
        capture_thinking()
        return original_handle(message)

    conversation.handle_message = handle_and_capture
    controller, output, observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            recorder=FakeAudioRecorder(
                tmp_path / "voice.wav",
                on_record=capture_listening,
            ),
            recognition_provider=RecordingRecognitionProvider(
                transcription="How was your day?",
                on_transcribe=capture_transcribing,
            ),
            speech_provider=RecordingSpeechProvider(
                on_speak=capture_speaking,
            ),
            conversation=conversation,
        )
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.transcription == "How was your day?"
    assert result.response == "Fake response for: How was your day?"
    assert observed_states == [
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.THINKING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]
    assert states_during["listening"] is VoiceState.LISTENING
    assert states_during["transcribing"] is VoiceState.TRANSCRIBING
    assert states_during["thinking"] is VoiceState.THINKING
    assert states_during["speaking"] is VoiceState.SPEAKING
    assert states_during["listening_while_speaking"] is False
    assert controller.state is VoiceState.IDLE
    assert "Listening..." in output.getvalue()
    assert "You: How was your day?" in output.getvalue()
    assert "Agent: Fake response for: How was your day?" in (
        output.getvalue()
    )
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert not (tmp_path / "voice.wav").exists()


def test_capture_error_returns_to_idle(
    tmp_path,
    conversation_service_factory,
):
    controller, output, observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            recorder=FailingAudioRecorder(),
        )
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.transcription is None
    assert result.response is None
    assert observed_states == [
        VoiceState.LISTENING,
        VoiceState.IDLE,
    ]
    assert controller.state is VoiceState.IDLE
    assert "I couldn't hear anything usable." in output.getvalue()
    assert speech_provider.spoken_texts == []


def test_transcription_error_returns_to_idle(
    tmp_path,
    conversation_service_factory,
):
    controller, output, observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            recognition_provider=FailingRecognitionProvider(),
        )
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.response is None
    assert observed_states == [
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.IDLE,
    ]
    assert controller.state is VoiceState.IDLE
    assert "I couldn't hear anything usable." in output.getvalue()
    assert speech_provider.spoken_texts == []
    assert not (tmp_path / "voice.wav").exists()


def test_conversation_error_returns_to_idle(
    tmp_path,
    conversation_service_factory,
):
    controller, output, observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            conversation=RaisingConversationService(),
        )
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.response is None
    assert observed_states == [
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.THINKING,
        VoiceState.IDLE,
    ]
    assert controller.state is VoiceState.IDLE
    assert speech_provider.spoken_texts == []


def test_tts_error_returns_to_idle(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    controller, output, observed_states, _speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            speech_provider=FailingSpeechProvider(),
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
        )
    )

    result = controller.handle_voice_turn()

    assert result.accepted is True
    assert result.response == (
        "Fake response for: How was your day?"
    )
    assert observed_states == [
        VoiceState.LISTENING,
        VoiceState.TRANSCRIBING,
        VoiceState.THINKING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
    ]
    assert controller.state is VoiceState.IDLE
    assert "Agent: Fake response for: How was your day?" in (
        output.getvalue()
    )


def test_second_voice_session_is_rejected_while_busy(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    second_result = {}

    def try_second_session():
        second_result["value"] = controller.handle_voice_turn()
        second_result["state"] = controller.state

    controller, output, _observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            recorder=FakeAudioRecorder(
                tmp_path / "voice.wav",
                on_record=try_second_session,
            ),
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
        )
    )

    first_result = controller.handle_voice_turn()

    assert first_result.accepted is True
    assert second_result["value"].accepted is False
    assert second_result["state"] is VoiceState.LISTENING
    assert "Please wait until I finish speaking." in (
        output.getvalue()
    )
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert controller.state is VoiceState.IDLE


def test_concurrent_voice_turns_do_not_listen_together(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    started = Event()
    release = Event()
    accepted = []

    def block_while_listening():
        started.set()
        release.wait(timeout=1)

    controller, _output, _observed_states, speech_provider = (
        _build_controller(
            tmp_path,
            conversation_service_factory,
            recorder=FakeAudioRecorder(
                tmp_path / "voice.wav",
                on_record=block_while_listening,
            ),
            conversation=conversation_service_factory(
                ai_client=fake_ai_client
            ),
        )
    )

    first_thread = Thread(
        target=lambda: accepted.append(controller.handle_voice_turn())
    )
    first_thread.start()
    assert started.wait(timeout=1)

    second_result = controller.handle_voice_turn()
    release.set()
    first_thread.join(timeout=1)

    assert second_result.accepted is False
    assert accepted[0].accepted is True
    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]
    assert controller.state is VoiceState.IDLE
