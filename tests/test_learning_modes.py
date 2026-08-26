from app.learning import LearningMode


def test_default_daily_learning_mode_is_added_to_instructions(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    service.handle_message("Hello")

    assert "Active learning mode: DAILY" in (
        inspectable_ai_client.instructions
    )
    assert (
        "Do not turn every interaction into a formal lesson"
        in inspectable_ai_client.instructions
    )


def test_learning_mode_from_personal_context_is_used(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    service.personal_context.update({
        "learning_mode": "TEACHER",
    })

    service.handle_message("Teach me something")

    assert "Active learning mode: TEACHER" in (
        inspectable_ai_client.instructions
    )
    assert "Teach one concept at a time" in (
        inspectable_ai_client.instructions
    )


def test_explicit_learning_mode_overrides_personal_context(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client,
        learning_mode="conversation",
    )
    service.personal_context.update({
        "learning_mode": "TEACHER",
    })

    service.handle_message("Let's chat")

    assert "Active learning mode: CONVERSATION" in (
        inspectable_ai_client.instructions
    )
    assert "original sentence" in inspectable_ai_client.instructions
    assert "Active learning mode: TEACHER" not in (
        inspectable_ai_client.instructions
    )


def test_vocabulary_learning_mode_instructions_are_available(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client,
        learning_mode=LearningMode.VOCABULARY,
    )

    service.handle_message("I need new words")

    assert "Active learning mode: VOCABULARY" in (
        inspectable_ai_client.instructions
    )
    assert "Software development" in inspectable_ai_client.instructions
    assert "Finish each vocabulary group with a short test" in (
        inspectable_ai_client.instructions
    )


def test_invalid_context_learning_mode_falls_back_to_daily(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    service.personal_context.update({
        "learning_mode": "UNKNOWN",
    })

    service.handle_message("Hello")

    assert service.current_learning_mode() == LearningMode.DAILY
    assert "Active learning mode: DAILY" in (
        inspectable_ai_client.instructions
    )
