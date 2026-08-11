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

MODE_COMMAND = "/mode"


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
        "Type '/mode daily|teacher|conversation|vocabulary' "
        "to change learning mode.\n"
    )

    print(
        "Agent: Good morning, Airton! "
        "How are you feeling today?"
    )

    while True:
        try:
            message = input("\nYou: ").strip()
            normalized_message = message.lower()

            if normalized_message in EXIT_COMMANDS:
                print("\nAgent: See you later, Airton!")
                break

            if normalized_message in CLEAR_COMMANDS:
                conversation.clear_history()
                print("\nAgent: Conversation history cleared.")
                continue

            if (
                normalized_message == MODE_COMMAND
                or normalized_message.startswith(f"{MODE_COMMAND} ")
            ):
                mode_name = message[len(MODE_COMMAND):].strip()

                if not mode_name:
                    current_mode = (
                        conversation.current_learning_mode().value
                    )
                    available_modes = ", ".join(
                        conversation.learning_modes.available_modes()
                    )
                    print(
                        "\nAgent: Current learning mode is "
                        f"{current_mode}. Available modes: "
                        f"{available_modes}."
                    )
                    continue

                try:
                    selected_mode = conversation.set_learning_mode(
                        mode_name
                    )
                    print(
                        "\nAgent: Learning mode changed to "
                        f"{selected_mode.value}."
                    )
                except ValueError as error:
                    print(f"\nAgent: {error}")

                continue

            response = conversation.handle_message(message)

            print(f"\nAgent: {response}")

        except KeyboardInterrupt:
            print("\n\nAgent: See you later, Airton!")
            break


if __name__ == "__main__":
    main()
