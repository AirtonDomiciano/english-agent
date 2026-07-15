from app.ai.openai_client import OpenAIClient
from app.prompts.system_prompt import SYSTEM_PROMPT


class ConversationService:
    def __init__(self, ai_client: OpenAIClient | None = None) -> None:
        self.ai_client = ai_client or OpenAIClient()

    def handle_message(self, message: str) -> str:
        cleaned_message = message.strip()

        if not cleaned_message:
            return "Please say something so I can help you practice English."

        try:
            return self.ai_client.generate_response(
                message=cleaned_message,
                instructions=SYSTEM_PROMPT,
            )
        except Exception as error:
            return f"I couldn't answer right now. Error: {error}"