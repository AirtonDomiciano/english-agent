from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Callable, TextIO

from app.chat.service import ConversationService
from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService
from app.voice.self_voice import SelfVoiceDetector


class VoiceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"


_ALLOWED_TRANSITIONS = {
    VoiceState.IDLE: {VoiceState.LISTENING},
    VoiceState.LISTENING: {VoiceState.TRANSCRIBING, VoiceState.IDLE},
    VoiceState.TRANSCRIBING: {VoiceState.THINKING, VoiceState.IDLE},
    VoiceState.THINKING: {VoiceState.SPEAKING, VoiceState.IDLE},
    VoiceState.SPEAKING: {VoiceState.IDLE},
}


@dataclass(frozen=True)
class VoiceTurnResult:
    accepted: bool
    transcription: str | None = None
    response: str | None = None


class VoiceConversationController:
    """Orchestrates one push-to-talk voice turn and its exclusive state."""

    def __init__(
        self,
        recognition: SpeechRecognitionService,
        conversation: ConversationService,
        presenter: AgentOutputPresenter,
        conversation_lock: Lock | None = None,
        output: TextIO | None = None,
        on_state_change: (
            Callable[[VoiceState, VoiceState], None] | None
        ) = None,
        self_voice_detector: SelfVoiceDetector | None = None,
    ) -> None:
        self.recognition = recognition
        self.conversation = conversation
        self.presenter = presenter
        self.conversation_lock = conversation_lock
        self.output = output
        self.on_state_change = on_state_change
        self.self_voice_detector = self_voice_detector
        self.state = VoiceState.IDLE
        self._session_lock = Lock()

    @property
    def is_busy(self) -> bool:
        return self.state is not VoiceState.IDLE

    def can_start_turn(self) -> bool:
        """Whether a new voice turn may start.

        Future self-voice or echo detection can extend this gate
        without changing wake-word or STT services.
        """
        return (
            self.state is VoiceState.IDLE
            and not self._session_lock.locked()
        )

    def handle_voice_turn(self) -> VoiceTurnResult:
        if not self._session_lock.acquire(blocking=False):
            self._print(
                "\nAgent: Please wait until I finish speaking."
            )
            return VoiceTurnResult(accepted=False)

        try:
            return self._run_turn()
        finally:
            try:
                self._set_state(VoiceState.IDLE)
            finally:
                self._session_lock.release()

    def _run_turn(self) -> VoiceTurnResult:
        audio_path = None

        try:
            self._set_state(VoiceState.LISTENING)
            self._print("\nListening...")
            audio_path = self.recognition.capture_audio()

            if not audio_path:
                self._print_unusable_audio()
                return VoiceTurnResult(accepted=True)

            self._set_state(VoiceState.TRANSCRIBING)
            transcription = self.recognition.transcribe_audio(
                audio_path
            )

            if not transcription:
                self._print_unusable_audio()
                return VoiceTurnResult(accepted=True)

            if (
                self.self_voice_detector is not None
                and self.self_voice_detector.is_probable_self_voice(
                    transcription
                )
            ):
                return VoiceTurnResult(
                    accepted=True,
                    transcription=transcription,
                )

            self._print(f"\nYou: {transcription}")
            self._set_state(VoiceState.THINKING)

            conversation_guard = (
                self.conversation_lock
                if self.conversation_lock is not None
                else nullcontext()
            )

            with conversation_guard:
                response = self.conversation.handle_message(
                    transcription
                )

            self._set_state(VoiceState.SPEAKING)
            self.presenter.show_agent_response(response)

            return VoiceTurnResult(
                accepted=True,
                transcription=transcription,
                response=response,
            )
        except Exception:
            return VoiceTurnResult(accepted=True)
        finally:
            if audio_path:
                Path(audio_path).unlink(missing_ok=True)

    def _set_state(self, new_state: VoiceState) -> None:
        if (
            new_state is not VoiceState.IDLE
            and new_state not in _ALLOWED_TRANSITIONS[self.state]
        ):
            raise RuntimeError(
                "Invalid voice state transition: "
                f"{self.state.value} -> {new_state.value}"
            )

        previous_state = self.state
        self.state = new_state

        if self.on_state_change and previous_state is not new_state:
            self.on_state_change(previous_state, new_state)

    def _print_unusable_audio(self) -> None:
        self._print(
            "\nAgent: I couldn't hear anything usable. "
            "You can keep typing normally."
        )

    def _print(self, message: str) -> None:
        print(message, file=self.output)
