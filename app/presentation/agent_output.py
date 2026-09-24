from typing import Protocol, TextIO

from app.speech import SpeechService


class AgentSpeechMemory(Protocol):
    def remember_agent_speech(self, text: str) -> None:
        """Remember text that was effectively spoken by the agent."""


class AgentOutputPresenter:
    """Centralizes visible and spoken agent responses."""

    def __init__(
        self,
        speech_service: SpeechService | None = None,
        output: TextIO | None = None,
        self_voice_detector: AgentSpeechMemory | None = None,
    ) -> None:
        self.speech_service = speech_service or SpeechService.from_env()
        self.output = output
        self.self_voice_detector = self_voice_detector

    def show_agent_response(self, response: str) -> None:
        print(
            f"\nAgent: {response}",
            file=self.output,
        )
        spoken = self.speech_service.speak(response)

        if spoken and self.self_voice_detector is not None:
            self.self_voice_detector.remember_agent_speech(response)
