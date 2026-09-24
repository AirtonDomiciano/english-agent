from threading import Lock

from app.chat.service import ConversationService
from app.daily import DailyScheduler, DailySchedulerRunner
from app.presentation import AgentOutputPresenter
from app.speech import SpeechRecognitionService
from app.startup.bootstrap import bootstrap_app
from app.voice import (
    SelfVoiceDetector,
    VoiceConversationController,
    WakeWordService,
)


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
VOICE_COMMAND = "/voice"


def main() -> None:
    app = bootstrap_app()
    conversation = ConversationService()
    scheduler = DailyScheduler()
    self_voice_detector = SelfVoiceDetector.from_env()
    presenter = AgentOutputPresenter(
        self_voice_detector=self_voice_detector,
    )
    speech_recognition = SpeechRecognitionService.from_env()
    conversation_lock = Lock()
    voice_conversation = VoiceConversationController(
        recognition=speech_recognition,
        conversation=conversation,
        presenter=presenter,
        conversation_lock=conversation_lock,
        self_voice_detector=self_voice_detector,
    )
    wake_word_service = WakeWordService.from_env(
        controller=voice_conversation,
    )

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
    if wake_word_service.enabled:
        print(
            f'Say "{wake_word_service.wake_word}" or type /voice '
            "to speak one message.\n"
        )
    else:
        print("Type '/voice' to speak one message.\n")

    def print_daily_result(result) -> None:
        presenter.show_agent_response(result.response)

    daily_runner = DailySchedulerRunner(
        scheduler=scheduler,
        conversation_service=conversation,
        on_result=print_daily_result,
        lock=conversation_lock,
    )

    daily_results = daily_runner.run_once()

    if not daily_results:
        presenter.show_agent_response(
            "I'm here when you want to practice."
        )

    daily_runner.start(run_immediately=False)
    wake_word_service.start()

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

            if normalized_message == VOICE_COMMAND:
                voice_conversation.handle_voice_turn()
                continue

            with conversation_lock:
                response = conversation.handle_message(message)

            presenter.show_agent_response(response)

    except KeyboardInterrupt:
        print("\n\nAgent: See you later, Airton!")
    finally:
        wake_word_service.stop()
        daily_runner.stop()


if __name__ == "__main__":
    main()
