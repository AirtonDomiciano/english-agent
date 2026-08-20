from threading import Lock

from app.chat.service import ConversationService
from app.daily import DailyScheduler, DailySchedulerRunner
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
    scheduler = DailyScheduler()
    conversation_lock = Lock()

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

    def print_daily_result(result) -> None:
        print(f"\nAgent: {result.response}")

    daily_runner = DailySchedulerRunner(
        scheduler=scheduler,
        conversation_service=conversation,
        on_result=print_daily_result,
        lock=conversation_lock,
    )

    daily_results = daily_runner.run_once()

    if not daily_results:
        print("Agent: I'm here when you want to practice.")

    daily_runner.start(run_immediately=False)

    try:
        while True:
            message = input("\nYou: ").strip()
            normalized_message = message.lower()

            if normalized_message in EXIT_COMMANDS:
                print("\nAgent: See you later, Airton!")
                break

            if normalized_message in CLEAR_COMMANDS:
                with conversation_lock:
                    conversation.clear_history()

                print("\nAgent: Conversation history cleared.")
                continue

            if (
                normalized_message == MODE_COMMAND
                or normalized_message.startswith(f"{MODE_COMMAND} ")
            ):
                mode_name = message[len(MODE_COMMAND):].strip()

                if not mode_name:
                    with conversation_lock:
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
                    with conversation_lock:
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

            with conversation_lock:
                response = conversation.handle_message(message)

            print(f"\nAgent: {response}")

    except KeyboardInterrupt:
        print("\n\nAgent: See you later, Airton!")
    finally:
        daily_runner.stop()


if __name__ == "__main__":
    main()
