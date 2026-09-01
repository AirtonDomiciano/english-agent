from typing import TextIO

from app.speech import SpeechService


class AgentOutputPresenter:
    """Centralizes visible and spoken agent responses."""

    def __init__(
        self,
        speech_service: SpeechService | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.speech_service = speech_service or SpeechService.from_env()
        self.output = output

    def show_agent_response(self, response: str) -> None:
        print(
            f"\nAgent: {response}",
            file=self.output,
        )
        self.speech_service.speak(response)
