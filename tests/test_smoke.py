from app.context.personal_context import PersonalContext
from app.chat.service import ConversationService
from app.learning import LearningMode
from app.memory.conversation_memory import ConversationMemory
from app.startup.bootstrap import bootstrap_app


class FakeAIClient:
    def generate_response(
        self,
        messages: list[dict],
        instructions: str,
    ) -> str:
        last_message = messages[-1]["content"]

        return f"Fake response for: {last_message}"


class InspectableFakeAIClient:
    def __init__(self) -> None:
        self.instructions = ""
        self.messages = []

    def generate_response(
        self,
        messages: list[dict],
        instructions: str,
    ) -> str:
        self.instructions = instructions
        self.messages = messages

        return "Fake response"


def create_personal_context(tmp_path):
    return PersonalContext(
        storage_path=tmp_path / "personal_context.json"
    )


def test_conversation_service_returns_response(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
    )

    reply = service.handle_message(
        "Hello, I want to practice English"
    )

    assert reply == (
        "Fake response for: "
        "Hello, I want to practice English"
    )


def test_conversation_service_saves_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Hello")

    history = memory.load()

    assert len(history) == 2
    assert history[0] == {
        "role": "user",
        "content": "Hello",
    }
    assert history[1] == {
        "role": "assistant",
        "content": "Fake response for: Hello",
    }


def test_personal_context_creates_default_file(tmp_path):
    context = create_personal_context(tmp_path)

    saved_context = context.load()

    assert saved_context["name"] == "Airton"
    assert saved_context["english_level"] == "B1"
    assert saved_context["learning_mode"] == "DAILY"
    assert saved_context["learning_preferences"] == {
        "correction_style": "gentle",
        "preferred_language": "English",
        "explanation_language": "Portuguese when necessary",
        "conversation_topics": [
            "software development",
            "daily routine",
            "gym",
            "violin",
            "games",
        ],
    }


def test_personal_context_can_be_updated(tmp_path):
    context = create_personal_context(tmp_path)

    context.update({
        "english_level": "B2",
    })

    saved_context = context.load()

    assert saved_context["english_level"] == "B2"


def test_personal_context_handles_invalid_json(tmp_path):
    storage_path = tmp_path / "personal_context.json"
    storage_path.write_text("{invalid", encoding="utf-8")

    context = PersonalContext(storage_path=storage_path)

    assert context.load()["name"] == "Airton"


def test_personal_context_adds_missing_default_values(tmp_path):
    storage_path = tmp_path / "personal_context.json"
    storage_path.write_text(
        '{"name": "Airton"}',
        encoding="utf-8",
    )

    context = PersonalContext(storage_path=storage_path)
    saved_context = context.load()

    assert saved_context["name"] == "Airton"
    assert saved_context["learning_mode"] == "DAILY"
    assert saved_context["english_level"] == "B1"


def test_personal_context_is_added_to_instructions(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Hello")

    assert "Airton" in ai_client.instructions
    assert '"english_level": "B1"' in ai_client.instructions


def test_default_daily_learning_mode_is_added_to_instructions(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Hello")

    assert "Active learning mode: DAILY" in ai_client.instructions
    assert (
        "Do not turn every interaction into a formal lesson"
        in ai_client.instructions
    )


def test_learning_mode_from_personal_context_is_used(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    personal_context.update({
        "learning_mode": "TEACHER",
    })
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Teach me something")

    assert "Active learning mode: TEACHER" in ai_client.instructions
    assert "Teach one concept at a time" in ai_client.instructions


def test_explicit_learning_mode_overrides_personal_context(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    personal_context.update({
        "learning_mode": "TEACHER",
    })
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
        learning_mode="conversation",
    )

    service.handle_message("Let's chat")

    assert "Active learning mode: CONVERSATION" in ai_client.instructions
    assert "original sentence" in ai_client.instructions
    assert "Active learning mode: TEACHER" not in ai_client.instructions


def test_vocabulary_learning_mode_instructions_are_available(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
        learning_mode=LearningMode.VOCABULARY,
    )

    service.handle_message("I need new words")

    assert "Active learning mode: VOCABULARY" in ai_client.instructions
    assert "Software development" in ai_client.instructions
    assert "Finish each vocabulary group with a short test" in (
        ai_client.instructions
    )


def test_invalid_context_learning_mode_falls_back_to_daily(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    personal_context.update({
        "learning_mode": "UNKNOWN",
    })
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Hello")

    assert service.current_learning_mode() == LearningMode.DAILY
    assert "Active learning mode: DAILY" in ai_client.instructions


def test_set_learning_mode_persists_selected_mode(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
    )

    selected_mode = service.set_learning_mode("teacher")

    assert selected_mode == LearningMode.TEACHER
    assert personal_context.load()["learning_mode"] == "TEACHER"


def test_set_learning_mode_rejects_unknown_mode(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
    )

    try:
        service.set_learning_mode("unknown")
    except ValueError as error:
        assert "Available modes" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_memory_can_clear_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")
    memory.clear()

    assert memory.load() == []


def test_memory_load_recent_returns_last_messages_in_order(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    for index in range(5):
        memory.append("user", f"Message {index}")

    recent_messages = memory.load_recent(limit=3)

    assert recent_messages == [
        {
            "role": "user",
            "content": "Message 2",
        },
        {
            "role": "user",
            "content": "Message 3",
        },
        {
            "role": "user",
            "content": "Message 4",
        },
    ]
    assert len(memory.load()) == 5


def test_memory_load_recent_returns_empty_for_zero_limit(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")

    assert memory.load_recent(limit=0) == []
    assert len(memory.load()) == 1


def test_memory_load_recent_returns_empty_for_negative_limit(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")

    assert memory.load_recent(limit=-1) == []
    assert len(memory.load()) == 1


def test_conversation_service_sends_configured_context_window(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    for index in range(5):
        memory.append("user", f"Old message {index}")

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
        context_window_size=2,
    )

    service.handle_message("Current message")

    assert ai_client.messages == [
        {
            "role": "user",
            "content": "Old message 3",
        },
        {
            "role": "user",
            "content": "Old message 4",
        },
        {
            "role": "user",
            "content": "Current message",
        },
    ]


def test_conversation_service_treats_negative_context_window_as_zero(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    memory.append("user", "Earlier message")

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
        context_window_size=-5,
    )

    service.handle_message("Current message")

    assert ai_client.messages == [
        {
            "role": "user",
            "content": "Current message",
        },
    ]


def test_conversation_service_adds_current_message_after_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    memory.append("user", "Earlier message")

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
        context_window_size=1,
    )

    service.handle_message("Current message")

    assert ai_client.messages[-1] == {
        "role": "user",
        "content": "Current message",
    }


def test_conversation_service_keeps_full_history_saved(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    for index in range(5):
        memory.append("user", f"Old message {index}")

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
        context_window_size=2,
    )

    service.handle_message("Current message")

    history = memory.load()

    assert len(history) == 7
    assert history[-2] == {
        "role": "user",
        "content": "Current message",
    }
    assert history[-1] == {
        "role": "assistant",
        "content": "Fake response for: Current message",
    }


def test_bootstrap_creates_expected_structure(tmp_path):
    app = bootstrap_app(data_dir=tmp_path)

    assert app["data_dir"].exists()
    assert app["memory_path"].exists()
    assert app["phase"] == "phase-1"
