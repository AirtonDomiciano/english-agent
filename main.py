from app.chat.service import ConversationService
from app.startup.bootstrap import bootstrap_app


EXIT_COMMANDS = {
    "exit",
    "quit",
    "sair",
}

CLEAR_COMMANDS = {
    "/clear",
    "/limpar",
}


def main() -> None:
    app = bootstrap_app()
    conversation = ConversationService()

    print(
        f"English Agent initialized in phase: "
        f"{app['phase']}"
    )

    print("Type 'exit' to finish.")
    print("Type '/clear' to clear the conversation.\n")

    print(
        "Agent: Good morning, Airton! "
        "How are you feeling today?"
    )

    while True:
        try:
            message = input("\nYou: ").strip()

            if message.lower() in EXIT_COMMANDS:
                print("\nAgent: See you later, Airton!")
                break

            if message.lower() in CLEAR_COMMANDS:
                conversation.clear_history()
                print("\nAgent: Conversation history cleared.")
                continue

            response = conversation.handle_message(message)

            print(f"\nAgent: {response}")

        except KeyboardInterrupt:
            print("\n\nAgent: See you later, Airton!")
            break


if __name__ == "__main__":
    main()