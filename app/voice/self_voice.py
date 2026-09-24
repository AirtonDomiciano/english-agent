import os
import re
from difflib import SequenceMatcher
from threading import Lock
from time import monotonic
from typing import Callable


DEFAULT_SELF_VOICE_WINDOW_SECONDS = 8.0
DEFAULT_SELF_VOICE_SIMILARITY_THRESHOLD = 0.85
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")


class SelfVoiceDetector:
    """Detects likely echo of the agent's last spoken text."""

    def __init__(
        self,
        window_seconds: float = DEFAULT_SELF_VOICE_WINDOW_SECONDS,
        similarity_threshold: float = (
            DEFAULT_SELF_VOICE_SIMILARITY_THRESHOLD
        ),
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.window_seconds = max(0.0, window_seconds)
        self.similarity_threshold = min(
            1.0,
            max(0.0, similarity_threshold),
        )
        self._clock = clock or monotonic
        self._lock = Lock()
        self._spoken_text = ""
        self._spoken_at: float | None = None

    @classmethod
    def from_env(cls) -> "SelfVoiceDetector":
        return cls(
            window_seconds=_env_float(
                "ENGLISH_AGENT_SELF_VOICE_WINDOW_SECONDS",
                DEFAULT_SELF_VOICE_WINDOW_SECONDS,
            ),
            similarity_threshold=_env_float(
                "ENGLISH_AGENT_SELF_VOICE_SIMILARITY_THRESHOLD",
                DEFAULT_SELF_VOICE_SIMILARITY_THRESHOLD,
            ),
        )

    def remember_agent_speech(
        self,
        text: str,
        spoken_at: float | None = None,
    ) -> None:
        cleaned_text = text.strip()

        if not cleaned_text:
            return

        with self._lock:
            self._spoken_text = cleaned_text
            self._spoken_at = (
                spoken_at if spoken_at is not None else self._clock()
            )

    def is_probable_self_voice(
        self,
        transcription: str,
        now: float | None = None,
    ) -> bool:
        cleaned_transcription = transcription.strip()

        if not cleaned_transcription:
            return False

        with self._lock:
            spoken_text = self._spoken_text
            spoken_at = self._spoken_at

        if not spoken_text or spoken_at is None:
            return False

        current_time = now if now is not None else self._clock()

        if current_time - spoken_at > self.window_seconds:
            return False

        return (
            _similarity(spoken_text, cleaned_transcription)
            >= self.similarity_threshold
        )


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(
        None,
        _normalize(left),
        _normalize(right),
    ).ratio()


def _normalize(text: str) -> str:
    normalized = _NON_ALNUM_RE.sub(" ", text.casefold())

    return " ".join(normalized.split())


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
