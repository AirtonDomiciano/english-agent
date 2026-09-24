import os
from enum import Enum
from threading import Event, Lock
from time import monotonic
from typing import Callable, TextIO

from app.voice.controller import VoiceConversationController


DEFAULT_VOICE_SESSION_TIMEOUT_SECONDS = 15.0


class VoiceSessionState(str, Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"


class VoiceConversationSession:
    """Runs repeated voice turns until silence, farewell, or shutdown."""

    def __init__(
        self,
        controller: VoiceConversationController,
        timeout_seconds: float = DEFAULT_VOICE_SESSION_TIMEOUT_SECONDS,
        clock: Callable[[], float] | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.controller = controller
        self.timeout_seconds = max(1.0, timeout_seconds)
        self._clock = clock or monotonic
        self.output = output
        self.state = VoiceSessionState.INACTIVE
        self._lock = Lock()
        self._stop_event = Event()
        self._last_activity_at: float | None = None

    @classmethod
    def from_env(
        cls,
        controller: VoiceConversationController,
        output: TextIO | None = None,
    ) -> "VoiceConversationSession":
        return cls(
            controller=controller,
            timeout_seconds=_env_float(
                "ENGLISH_AGENT_VOICE_SESSION_TIMEOUT_SECONDS",
                DEFAULT_VOICE_SESSION_TIMEOUT_SECONDS,
            ),
            output=output,
        )

    @property
    def is_active(self) -> bool:
        return self.state is VoiceSessionState.ACTIVE

    def can_start(self) -> bool:
        return (
            self.state is VoiceSessionState.INACTIVE
            and not self._lock.locked()
        )

    def run(self) -> None:
        if not self._lock.acquire(blocking=False):
            return

        self._stop_event.clear()
        self.state = VoiceSessionState.ACTIVE
        self._last_activity_at = self._clock()

        try:
            while not self._stop_event.is_set():
                result = self.controller.handle_voice_turn(
                    announce_empty=False
                )

                if not result.accepted:
                    break

                if result.ended_session:
                    self._print("\nAgent: See you later.")
                    break

                if result.heard_user:
                    self._last_activity_at = self._clock()
                    continue

                if (
                    self._clock() - (self._last_activity_at or 0)
                    >= self.timeout_seconds
                ):
                    self._print(
                        "\nAgent: I'll wait until you say "
                        "the wake word."
                    )
                    break
        finally:
            self.state = VoiceSessionState.INACTIVE
            self._last_activity_at = None
            self._lock.release()

    def stop(self) -> None:
        self._stop_event.set()

    def _print(self, message: str) -> None:
        print(
            message,
            file=self.output or getattr(self.controller, "output", None),
        )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
