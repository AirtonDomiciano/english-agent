class ConversationService:
    """Minimal conversational service used by the initial scaffold."""

    def handle_message(self, message: str) -> str:
        cleaned = message.strip()
        if not cleaned:
            return "Please say something so I can help you practice English."

        return (
            f"I can help you practice English. You said: {cleaned}. "
            "We can expand this into a full personal assistant later."
        )
