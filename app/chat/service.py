from app.ai.openai_client import OpenAIClient
from app.context.personal_context import PersonalContext
from app.memory.conversation_memory import ConversationMemory
from app.prompts.system_prompt import SYSTEM_PROMPT


class ConversationService:
    def __init__(
        self,
        ai_client: OpenAIClient | None = None,
        memory: ConversationMemory | None = None,
        personal_context: PersonalContext | None = None,
    ) -> None:
        self.ai_client = ai_client or OpenAIClient()
        self.memory = memory or ConversationMemory()
        self.personal_context = (
            personal_context or PersonalContext()
        )

    def handle_message(self, message: str) -> str:
        cleaned_message = message.strip()

        if not cleaned_message:
            return (
                "Please say something so I can help you "
                "practice English."
            )

        history = self.memory.load()

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

    def _build_instructions(self) -> str:
        personal_context = self.personal_context.to_prompt()

        return (
            f"{SYSTEM_PROMPT.strip()}\n\n"
            f"{personal_context}"
        )
