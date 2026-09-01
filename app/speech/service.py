import os
import sys
from threading import Lock
from typing import Callable, Protocol


class SpeechProvider(Protocol):
    def speak(self, text: str) -> None:
        """Speak text using a concrete TTS provider."""


class SpeechService:
    """Serializes optional text-to-speech playback."""

    def __init__(
        self,
        provider: SpeechProvider,
        enabled: bool = False,
        error_handler: Callable[[Exception], None] | None = None,
    ) -> None:
        self.provider = provider
        self.enabled = enabled
        self.error_handler = error_handler or self._default_error_handler
        self._lock = Lock()

    @classmethod
    def from_env(
        cls,
        provider: SpeechProvider | None = None,
        error_handler: Callable[[Exception], None] | None = None,
    ) -> "SpeechService":
        enabled = _env_flag("ENGLISH_AGENT_TTS_ENABLED")
        selected_provider = provider or _provider_from_env()

        return cls(
            provider=selected_provider,
            enabled=enabled,
            error_handler=error_handler,
        )

    def speak(self, text: str) -> bool:
        cleaned_text = text.strip()

        if not self.enabled or not cleaned_text:
            return False

        try:
            with self._lock:
                self.provider.speak(cleaned_text)

            return True
        except Exception as error:
            self.error_handler(error)

            return False

    def _default_error_handler(self, error: Exception) -> None:
        print(
            f"TTS error: {error}",
            file=sys.stderr,
        )


class NullSpeechProvider:
    def speak(self, text: str) -> None:
        return None


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _provider_from_env() -> SpeechProvider:
    provider_name = os.getenv(
        "ENGLISH_AGENT_TTS_PROVIDER",
        "espeak",
    ).strip().lower()

    if provider_name == "espeak":
        from app.speech.providers.espeak import EspeakSpeechProvider

        return EspeakSpeechProvider.from_env()

    return NullSpeechProvider()
