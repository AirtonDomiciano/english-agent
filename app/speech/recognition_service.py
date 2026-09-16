import os
import sys
from pathlib import Path
from typing import Callable, Protocol

from app.speech.audio import (
    ArecordMicrophoneRecorder,
    AudioRecorder,
    NullAudioRecorder,
)


class SpeechRecognitionProvider(Protocol):
    def transcribe(self, audio_path: Path, language: str) -> str:
        """Return text transcribed from an audio file."""


class SpeechRecognitionService:
    """Captures one spoken phrase and transcribes it into user text."""

    def __init__(
        self,
        provider: SpeechRecognitionProvider,
        recorder: AudioRecorder,
        enabled: bool = False,
        language: str = "en",
        error_handler: Callable[[Exception], None] | None = None,
    ) -> None:
        self.provider = provider
        self.recorder = recorder
        self.enabled = enabled
        self.language = language or "en"
        self.error_handler = error_handler or self._default_error_handler

    @classmethod
    def from_env(
        cls,
        provider: SpeechRecognitionProvider | None = None,
        recorder: AudioRecorder | None = None,
        error_handler: Callable[[Exception], None] | None = None,
    ) -> "SpeechRecognitionService":
        enabled = _env_flag("ENGLISH_AGENT_STT_ENABLED")
        language = os.getenv(
            "ENGLISH_AGENT_STT_LANGUAGE",
            "en",
        ).strip() or "en"

        selected_provider = (
            provider
            or (
                _provider_from_env()
                if enabled
                else NullSpeechRecognitionProvider()
            )
        )
        selected_recorder = (
            recorder
            or (
                ArecordMicrophoneRecorder.from_env()
                if enabled
                else NullAudioRecorder()
            )
        )

        return cls(
            provider=selected_provider,
            recorder=selected_recorder,
            enabled=enabled,
            language=language,
            error_handler=error_handler,
        )

    def listen_once(self) -> str | None:
        if not self.enabled:
            return None

        audio_path = None

        try:
            audio_path = self.recorder.record()

            if not audio_path:
                return None

            audio_path = Path(audio_path)

            if (
                not audio_path.exists()
                or audio_path.stat().st_size == 0
            ):
                return None

            transcription = self.provider.transcribe(
                audio_path=audio_path,
                language=self.language,
            )
            cleaned_transcription = str(transcription or "").strip()

            return cleaned_transcription or None
        except Exception as error:
            self.error_handler(error)

            return None
        finally:
            if audio_path:
                Path(audio_path).unlink(missing_ok=True)

    def _default_error_handler(self, error: Exception) -> None:
        print(
            f"STT error: {error}",
            file=sys.stderr,
        )


class NullSpeechRecognitionProvider:
    def transcribe(self, audio_path: Path, language: str) -> str:
        return ""


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _provider_from_env() -> SpeechRecognitionProvider:
    provider_name = os.getenv(
        "ENGLISH_AGENT_STT_PROVIDER",
        "openai",
    ).strip().lower()

    if provider_name == "openai":
        from app.speech.recognition_providers.openai_transcription import (
            OpenAITranscriptionProvider,
        )

        return OpenAITranscriptionProvider.from_env()

    return NullSpeechRecognitionProvider()
