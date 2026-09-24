import os
import sys
from threading import Event, Thread
from typing import Callable, Protocol, TextIO

from app.voice.controller import VoiceConversationController
from app.voice.session import VoiceConversationSession


DEFAULT_WAKE_WORD = "pran"
DEFAULT_WAKE_WORD_PROVIDER = "openwakeword"
DEFAULT_WAKE_WORD_THRESHOLD = 0.5


class AudioFrameSource(Protocol):
    def start(self) -> None:
        """Open the microphone stream."""

    def read(self, nbytes: int) -> bytes | None:
        """Return the next PCM chunk, or None when the stream ends."""

    def stop(self) -> None:
        """Release the microphone stream."""


class WakeWordDetector(Protocol):
    def wait(self, stop_event: Event) -> bool:
        """Block until a wake word is detected or stop_event is set."""

    def close(self) -> None:
        """Release microphone and model resources."""


class NullWakeWordDetector:
    def wait(self, stop_event: Event) -> bool:
        stop_event.wait()
        return False

    def close(self) -> None:
        return None


class WakeWordService:
    """Listens for a local wake word and starts a voice session when idle."""

    def __init__(
        self,
        controller: VoiceConversationController,
        detector: WakeWordDetector | None = None,
        session: VoiceConversationSession | None = None,
        enabled: bool = False,
        wake_word: str = DEFAULT_WAKE_WORD,
        error_handler: Callable[[Exception], None] | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.controller = controller
        self.detector = detector or NullWakeWordDetector()
        self.session = session
        self.enabled = enabled
        self.wake_word = wake_word
        self.error_handler = error_handler or self._default_error_handler
        self.output = output
        self._stop_event = Event()
        self._thread: Thread | None = None

    @classmethod
    def from_env(
        cls,
        controller: VoiceConversationController,
        detector: WakeWordDetector | None = None,
        session: VoiceConversationSession | None = None,
        error_handler: Callable[[Exception], None] | None = None,
        output: TextIO | None = None,
    ) -> "WakeWordService":
        enabled = _env_flag("ENGLISH_AGENT_WAKE_WORD_ENABLED")
        wake_word = os.getenv(
            "ENGLISH_AGENT_WAKE_WORD",
            DEFAULT_WAKE_WORD,
        ).strip() or DEFAULT_WAKE_WORD

        if not enabled:
            return cls(
                controller=controller,
                detector=detector or NullWakeWordDetector(),
                session=session,
                enabled=False,
                wake_word=wake_word,
                error_handler=error_handler,
                output=output,
            )

        selected_detector = detector
        detector_error = None

        if selected_detector is None:
            try:
                selected_detector = _provider_from_env(wake_word)
            except Exception as error:
                detector_error = error
                selected_detector = NullWakeWordDetector()
                enabled = False

        service = cls(
            controller=controller,
            detector=selected_detector,
            session=session,
            enabled=enabled,
            wake_word=wake_word,
            error_handler=error_handler,
            output=output,
        )

        if detector_error is not None:
            service.error_handler(detector_error)

        return service

    def start(self) -> None:
        if not self.enabled:
            return

        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self.session is not None:
            self.session.stop()

        self.detector.close()

        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                detected = self.detector.wait(self._stop_event)
            except Exception as error:
                self.error_handler(error)

                if self._stop_event.wait(0.5):
                    return

                continue

            if not detected or self._stop_event.is_set():
                continue

            try:
                self._start_conversation()
            except Exception as error:
                self.error_handler(error)

    def _start_conversation(self) -> None:
        if self.session is not None:
            if not self.session.can_start():
                return

            self.session.run()
            return

        if not self.controller.can_start_turn():
            return

        self.controller.handle_voice_turn()

    def _default_error_handler(self, error: Exception) -> None:
        print(
            f"Wake word error: {error}",
            file=sys.stderr,
        )


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _provider_from_env(wake_word: str) -> WakeWordDetector:
    provider_name = os.getenv(
        "ENGLISH_AGENT_WAKE_WORD_PROVIDER",
        DEFAULT_WAKE_WORD_PROVIDER,
    ).strip().lower()

    if provider_name == "openwakeword":
        from app.voice.wake_word_providers.openwakeword import (
            OpenWakeWordDetector,
        )

        return OpenWakeWordDetector.from_env(wake_word=wake_word)

    return NullWakeWordDetector()
