from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService, SpeechService
from app.speech.recognition_providers.openai_transcription import (
    OpenAITranscriptionProvider,
)


class FakeAudioRecorder:
    def __init__(
        self,
        audio_path: Path,
        payload: bytes = b"audio",
    ) -> None:
        self.audio_path = audio_path
        self.payload = payload
        self.calls = 0

    def record(self) -> Path:
        self.calls += 1
        self.audio_path.parent.mkdir(parents=True, exist_ok=True)
        self.audio_path.write_bytes(self.payload)

        return self.audio_path


class RecordingRecognitionProvider:
    def __init__(self, transcription: str = "How was your day?") -> None:
        self.transcription = transcription
        self.calls = []

    def transcribe(self, audio_path: Path, language: str) -> str:
        self.calls.append(
            {
                "audio_path": audio_path,
                "language": language,
                "exists": audio_path.exists(),
            }
        )

        return self.transcription


class FailingRecognitionProvider:
    def transcribe(self, audio_path: Path, language: str) -> str:
        raise RuntimeError("transcription unavailable")


class FailingAudioRecorder:
    def record(self) -> Path:
        raise RuntimeError("microphone unavailable")


class RecordingSpeechProvider:
    def __init__(self) -> None:
        self.spoken_texts = []

    def speak(self, text: str) -> None:
        self.spoken_texts.append(text)


class FakeOpenAITranscriptions:
    def __init__(self) -> None:
        self.calls = []

    def create(self, model, file, language):
        self.calls.append(
            {
                "model": model,
                "filename": file.name,
                "language": language,
            }
        )

        return SimpleNamespace(text="Transcribed by OpenAI")


def test_stt_enabled_returns_transcription(tmp_path):
    recorder = FakeAudioRecorder(tmp_path / "voice.wav")
    provider = RecordingRecognitionProvider(
        transcription="Hey Nova, let's practice."
    )
    service = SpeechRecognitionService(
        provider=provider,
        recorder=recorder,
        enabled=True,
        language="en",
    )

    transcription = service.listen_once()

    assert transcription == "Hey Nova, let's practice."
    assert recorder.calls == 1
    assert provider.calls == [
        {
            "audio_path": tmp_path / "voice.wav",
            "language": "en",
            "exists": True,
        }
    ]


def test_stt_disabled_does_not_capture_audio(tmp_path):
    recorder = FakeAudioRecorder(tmp_path / "voice.wav")
    provider = RecordingRecognitionProvider()
    service = SpeechRecognitionService(
        provider=provider,
        recorder=recorder,
        enabled=False,
    )

    transcription = service.listen_once()

    assert transcription is None
    assert recorder.calls == 0
    assert provider.calls == []


def test_stt_from_env_reads_enabled_and_language(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ENGLISH_AGENT_STT_ENABLED", "true")
    monkeypatch.setenv("ENGLISH_AGENT_STT_LANGUAGE", "pt")
    recorder = FakeAudioRecorder(tmp_path / "voice.wav")
    provider = RecordingRecognitionProvider(
        transcription="Olá, Nova."
    )

    service = SpeechRecognitionService.from_env(
        provider=provider,
        recorder=recorder,
    )
    transcription = service.listen_once()

    assert transcription == "Olá, Nova."
    assert provider.calls[0]["language"] == "pt"


def test_stt_from_env_with_missing_openai_key_does_not_crash_app(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("ENGLISH_AGENT_STT_ENABLED", "true")
    monkeypatch.setenv("ENGLISH_AGENT_STT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    errors = []
    service = SpeechRecognitionService.from_env(
        recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
        error_handler=errors.append,
    )

    transcription = service.listen_once()

    assert transcription is None
    assert len(errors) == 1
    assert "OPENAI_API_KEY" in str(errors[0])


def test_stt_provider_error_returns_none_without_crashing(tmp_path):
    errors = []
    service = SpeechRecognitionService(
        provider=FailingRecognitionProvider(),
        recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
        enabled=True,
        error_handler=errors.append,
    )

    transcription = service.listen_once()

    assert transcription is None
    assert len(errors) == 1
    assert str(errors[0]) == "transcription unavailable"


def test_stt_microphone_error_returns_none_without_crashing():
    errors = []
    service = SpeechRecognitionService(
        provider=RecordingRecognitionProvider(),
        recorder=FailingAudioRecorder(),
        enabled=True,
        error_handler=errors.append,
    )

    transcription = service.listen_once()

    assert transcription is None
    assert len(errors) == 1
    assert str(errors[0]) == "microphone unavailable"


def test_capture_audio_leaves_file_for_the_caller(tmp_path):
    audio_path = tmp_path / "voice.wav"
    service = SpeechRecognitionService(
        provider=RecordingRecognitionProvider(),
        recorder=FakeAudioRecorder(audio_path),
        enabled=True,
    )

    captured_path = service.capture_audio()

    assert captured_path == audio_path
    assert captured_path.exists()
    assert service.provider.calls == []


def test_stt_empty_audio_does_not_call_provider(tmp_path):
    provider = RecordingRecognitionProvider()
    service = SpeechRecognitionService(
        provider=provider,
        recorder=FakeAudioRecorder(
            audio_path=tmp_path / "empty.wav",
            payload=b"",
        ),
        enabled=True,
    )

    transcription = service.listen_once()

    assert transcription is None
    assert provider.calls == []


def test_stt_blank_transcription_does_not_create_user_text(tmp_path):
    service = SpeechRecognitionService(
        provider=RecordingRecognitionProvider(transcription="   "),
        recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
        enabled=True,
    )

    transcription = service.listen_once()

    assert transcription is None


def test_stt_transcription_is_sent_to_conversation_service(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    service = SpeechRecognitionService(
        provider=RecordingRecognitionProvider(
            transcription="What did I learn yesterday?"
        ),
        recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
        enabled=True,
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    transcription = service.listen_once()
    response = conversation.handle_message(transcription)

    assert response == "Fake response"
    assert inspectable_ai_client.messages[-1]["content"] == (
        "What did I learn yesterday?"
    )


def test_stt_response_uses_presenter_and_tts(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    speech_provider = RecordingSpeechProvider()
    presenter = AgentOutputPresenter(
        speech_service=SpeechService(
            provider=speech_provider,
            enabled=True,
        ),
        output=StringIO(),
    )
    recognition = SpeechRecognitionService(
        provider=RecordingRecognitionProvider(
            transcription="How was your day?"
        ),
        recorder=FakeAudioRecorder(tmp_path / "voice.wav"),
        enabled=True,
    )
    conversation = conversation_service_factory(
        ai_client=fake_ai_client
    )

    transcription = recognition.listen_once()
    response = conversation.handle_message(transcription)
    presenter.show_agent_response(response)

    assert speech_provider.spoken_texts == [
        "Fake response for: How was your day?"
    ]


def test_openai_transcription_provider_uses_configured_model(tmp_path):
    transcriptions = FakeOpenAITranscriptions()
    fake_client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=transcriptions)
    )
    provider = OpenAITranscriptionProvider(
        client=fake_client,
        model="whisper-test",
    )
    audio_path = tmp_path / "voice.wav"
    audio_path.write_bytes(b"audio")

    transcription = provider.transcribe(
        audio_path=audio_path,
        language="en",
    )

    assert transcription == "Transcribed by OpenAI"
    assert transcriptions.calls == [
        {
            "model": "whisper-test",
            "filename": str(audio_path),
            "language": "en",
        }
    ]
