from app.ai.openai_client import OpenAIClient
from app.context.personal_context import PersonalContext
from app.learning import LearningMode, LearningModeRegistry
from app.memory.conversation_memory import ConversationMemory
from app.prompts.system_prompt import SYSTEM_PROMPT


DEFAULT_CONTEXT_WINDOW_SIZE = 20


class ConversationService:
    def __init__(
        self,
        ai_client: OpenAIClient | None = None,
        memory: ConversationMemory | None = None,
        personal_context: PersonalContext | None = None,
        learning_mode: LearningMode | str | None = None,
        learning_modes: LearningModeRegistry | None = None,
        context_window_size: int = DEFAULT_CONTEXT_WINDOW_SIZE,
    ) -> None:
        self.ai_client = ai_client or OpenAIClient()
        self.memory = memory or ConversationMemory()
        self.personal_context = (
            personal_context or PersonalContext()
        )
        self.learning_modes = (
            learning_modes or LearningModeRegistry()
        )
        self.learning_mode = learning_mode
        self.context_window_size = max(0, context_window_size)

    def handle_message(self, message: str) -> str:
        cleaned_message = message.strip()

        if not cleaned_message:
            return (
                "Please say something so I can help you "
                "practice English."
            )

        history = self.memory.load_recent(
            limit=self.context_window_size
        )

        messages = [
            *history,
            {
                "role": "user",
                "content": cleaned_message,
            },
        ]

        instructions = self._build_instructions()

        try:
            response = self.ai_client.generate_response(
                messages=messages,
                instructions=instructions,
            )

            self.memory.append(
                role="user",
                content=cleaned_message,
            )

            self.memory.append(
                role="assistant",
                content=response,
            )

            return response

        except Exception as error:
            return (
                "I couldn't answer right now. "
                f"Error: {error}"
            )

    def clear_history(self) -> None:
        self.memory.clear()

    def current_learning_mode(self) -> LearningMode:
        return self.learning_modes.resolve(
            self.learning_mode
            or self.personal_context.get_learning_mode()
        )

    def set_learning_mode(
        self,
        learning_mode: LearningMode | str,
    ) -> LearningMode:
        resolved_mode = self.learning_modes.find(learning_mode)

        if not resolved_mode:
            available_modes = ", ".join(
                self.learning_modes.available_modes()
            )
            raise ValueError(
                "Unknown learning mode. Available modes: "
                f"{available_modes}."
            )

        self.learning_mode = resolved_mode
        self.personal_context.update({
            "learning_mode": resolved_mode.value,
        })

        return resolved_mode

    def _build_instructions(self) -> str:
        personal_context = self.personal_context.to_prompt()
        learning_mode_instructions = (
            self.learning_modes.get_instructions(
                self.current_learning_mode()
            )
        )

        return (
            f"{SYSTEM_PROMPT.strip()}\n\n"
            f"{learning_mode_instructions}\n\n"
            f"{personal_context}"
        )
