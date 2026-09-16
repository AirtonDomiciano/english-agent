import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_OPENAI_TRANSCRIPTION_MODEL = "whisper-1"
DEFAULT_OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS = 30


class OpenAITranscriptionProvider:
    """Speech-to-text provider backed by OpenAI audio transcription."""

    def __init__(
        self,
        client=None,
        model: str = DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
        client_factory=None,
    ) -> None:
        self.client = client
        self.model = model
        self.client_factory = client_factory or _openai_client_from_env

    @classmethod
    def from_env(cls) -> "OpenAITranscriptionProvider":
        return cls(
            model=os.getenv(
                "ENGLISH_AGENT_STT_MODEL",
                DEFAULT_OPENAI_TRANSCRIPTION_MODEL,
            )
        )

    def transcribe(self, audio_path: Path, language: str) -> str:
        client = self._client()

        with audio_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                language=language,
            )

        text = getattr(transcription, "text", None)

        if text is None and isinstance(transcription, dict):
            text = transcription.get("text")

        return str(text or "")

    def _client(self):
        if self.client is None:
            self.client = self.client_factory()

        return self.client


def _openai_client_from_env():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY não encontrada no arquivo .env."
        )

    return OpenAI(
        api_key=api_key,
        timeout=_env_float(
            "ENGLISH_AGENT_STT_TIMEOUT",
            DEFAULT_OPENAI_TRANSCRIPTION_TIMEOUT_SECONDS,
        ),
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
