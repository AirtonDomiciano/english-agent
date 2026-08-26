from app.chat.service import ConversationService
from app.learning import LearningMode
from app.memory.conversation_memory import ConversationMemory


def test_conversation_service_returns_response(
    conversation_service_factory,
    fake_ai_client,
):
    service = conversation_service_factory(ai_client=fake_ai_client)

    reply = service.handle_message(
        "Hello, I want to practice English"
    )

    assert reply == (
        "Fake response for: "
        "Hello, I want to practice English"
    )


def test_conversation_service_saves_history(
    conversation_service_factory,
    fake_ai_client,
):
    service = conversation_service_factory(ai_client=fake_ai_client)

    service.handle_message("Hello")

    history = service.memory.load()

    assert history == [
        {
            "role": "user",
            "content": "Hello",
        },
        {
            "role": "assistant",
            "content": "Fake response for: Hello",
        },
    ]


def test_conversation_service_adds_personal_context(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    service.handle_message("Hello")

    assert "Airton" in inspectable_ai_client.instructions
    assert '"english_level": "B1"' in (
        inspectable_ai_client.instructions
    )


def test_conversation_service_sends_configured_context_window(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = personal_context_factory()

    for index in range(5):
        memory.append("user", f"Old message {index}")

    service = ConversationService(
        ai_client=inspectable_ai_client,
        memory=memory,
        personal_context=personal_context,
        learning_cycle=learning_cycle_factory(),
        context_window_size=2,
    )

    service.handle_message("Current message")

    assert inspectable_ai_client.messages == [
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


def test_conversation_service_treats_negative_context_window_as_zero(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    memory.append("user", "Earlier message")

    service = ConversationService(
        ai_client=inspectable_ai_client,
        memory=memory,
        personal_context=personal_context_factory(),
        learning_cycle=learning_cycle_factory(),
        context_window_size=-5,
    )

    service.handle_message("Current message")

    assert inspectable_ai_client.messages == [
        {
            "role": "user",
            "content": "Current message",
        },
    ]


def test_conversation_service_adds_current_message_after_history(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    memory.append("user", "Earlier message")

    service = ConversationService(
        ai_client=inspectable_ai_client,
        memory=memory,
        personal_context=personal_context_factory(),
        learning_cycle=learning_cycle_factory(),
        context_window_size=1,
    )

    service.handle_message("Current message")

    assert inspectable_ai_client.messages[-1] == {
        "role": "user",
        "content": "Current message",
    }


def test_conversation_service_keeps_full_history_saved(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    fake_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    for index in range(5):
        memory.append("user", f"Old message {index}")

    service = ConversationService(
        ai_client=fake_ai_client,
        memory=memory,
        personal_context=personal_context_factory(),
        learning_cycle=learning_cycle_factory(),
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


def test_conversation_service_keeps_manual_error_response(
    conversation_service_factory,
    failing_ai_client,
):
    service = conversation_service_factory(ai_client=failing_ai_client)

    reply = service.handle_message("Hello")

    assert reply == (
        "I couldn't answer right now. "
        "Error: OpenAI unavailable"
    )
    assert service.memory.load() == []


def test_set_learning_mode_persists_selected_mode(
    conversation_service_factory,
    fake_ai_client,
):
    service = conversation_service_factory(ai_client=fake_ai_client)

    selected_mode = service.set_learning_mode("teacher")

    assert selected_mode == LearningMode.TEACHER
    assert service.personal_context.load()["learning_mode"] == "TEACHER"


def test_set_learning_mode_rejects_unknown_mode(
    conversation_service_factory,
    fake_ai_client,
):
    service = conversation_service_factory(ai_client=fake_ai_client)

    try:
        service.set_learning_mode("unknown")
    except ValueError as error:
        assert "Available modes" in str(error)
    else:
        raise AssertionError("Expected ValueError")
