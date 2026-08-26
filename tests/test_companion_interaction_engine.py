from datetime import datetime, time

from app.companion import (
    CompanionInteractionEngine,
    CompanionInteractionStore,
    CompanionInteractionType,
)
from app.daily import SessionWindow, TopicProvider
from app.learning import LearningStage


def create_engine(
    tmp_path,
    learning_cycle,
    topic_provider=None,
    interaction_selector=None,
    commitment_window=None,
    quiet_minutes=45,
):
    return CompanionInteractionEngine(
        store=CompanionInteractionStore(
            storage_path=tmp_path / "companion_state.json"
        ),
        learning_cycle=learning_cycle,
        topic_provider=topic_provider or TopicProvider(
            topics=("technology",),
        ),
        interaction_selector=interaction_selector,
        commitment_window=commitment_window,
        quiet_minutes=quiet_minutes,
    )


def test_interaction_engine_selects_type(
    tmp_path,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
        interaction_selector=lambda candidates: (
            CompanionInteractionType.MINI_QUIZ
        ),
    )

    selected = engine.select_interaction(
        datetime(2026, 8, 26, 10, 0)
    )

    assert selected == CompanionInteractionType.MINI_QUIZ


def test_social_interaction_has_no_explicit_learning_goal(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    result = engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.SOCIAL,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    assert result is not None
    assert result.interaction_type == CompanionInteractionType.SOCIAL
    assert "Type: SOCIAL" in inspectable_ai_client.messages[-1][
        "content"
    ]
    assert "Do not make this an explicit lesson" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_mini_quiz_uses_current_learning_topic(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    learning_cycle = learning_cycle_factory()
    engine = create_engine(tmp_path, learning_cycle=learning_cycle)
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.MINI_QUIZ,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    assert "Type: MINI_QUIZ" in inspectable_ai_client.messages[-1][
        "content"
    ]
    assert "Current topic: Greetings and Introductions" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_learning_recall_uses_warm_up_topic(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    learning_cycle = learning_cycle_factory()
    learning_cycle.mark_for_review("simple-present")
    engine = create_engine(tmp_path, learning_cycle=learning_cycle)
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.LEARNING_RECALL,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    assert "Type: LEARNING_RECALL" in (
        inspectable_ai_client.messages[-1]["content"]
    )
    assert "Review topic: Simple Present" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_random_topic_uses_topic_provider(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
        topic_provider=TopicProvider(topics=("MMORPG",)),
    )
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.RANDOM_TOPIC,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    assert "Type: RANDOM_TOPIC" in (
        inspectable_ai_client.messages[-1]["content"]
    )
    assert "Category: MMORPG" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_quick_challenge_uses_current_topic_and_level(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    learning_cycle = learning_cycle_factory()
    learning_cycle.change_stage(LearningStage.WRITING)
    engine = create_engine(tmp_path, learning_cycle=learning_cycle)
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )

    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.QUICK_CHALLENGE,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    assert "Type: QUICK_CHALLENGE" in (
        inspectable_ai_client.messages[-1]["content"]
    )
    assert "Current topic: Greetings and Introductions" in (
        inspectable_ai_client.messages[-1]["content"]
    )
    assert "Current level: A1" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_learning_commitment_starts_near_15h(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
        commitment_window=SessionWindow(
            start=time(hour=14, minute=45),
            end=time(hour=15, minute=30),
        ),
    )
    conversation = conversation_service_factory()

    result = engine.start_interaction(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 26, 15, 0),
    )
    state = engine.store.load()

    assert result is not None
    assert result.interaction_type == (
        CompanionInteractionType.LEARNING_COMMITMENT
    )
    assert state.learning_commitment is not None
    assert state.learning_commitment.status == "pending"
    assert state.learning_commitment.prompts_sent == 1
    assert state.learning_commitment.next_follow_up_at == (
        "2026-08-26T15:10:00"
    )


def test_learning_commitment_follow_ups_use_10_30_45_60_minutes(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
        quiet_minutes=0,
    )
    conversation = conversation_service_factory()

    sent_times = [
        datetime(2026, 8, 26, 15, 0),
        datetime(2026, 8, 26, 15, 10),
        datetime(2026, 8, 26, 15, 40),
        datetime(2026, 8, 26, 16, 25),
        datetime(2026, 8, 26, 17, 25),
    ]

    for sent_time in sent_times:
        result = engine.start_interaction(
            conversation_service=conversation,
            current_datetime=sent_time,
        )
        assert result is not None
        assert result.interaction_type == (
            CompanionInteractionType.LEARNING_COMMITMENT
        )

    state = engine.store.load()

    assert state.learning_commitment is not None
    assert state.learning_commitment.prompts_sent == 5
    assert state.learning_commitment.status == "closed"
    assert state.learning_commitment.next_follow_up_at is None
    assert state.pending_follow_ups == []


def test_learning_commitment_cancels_follow_ups_after_response(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
    )
    conversation = conversation_service_factory()
    engine.start_interaction(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 26, 15, 0),
    )

    state = engine.register_user_response(
        datetime(2026, 8, 26, 15, 5)
    )
    selected = engine.select_interaction(
        datetime(2026, 8, 26, 15, 10)
    )

    assert state.learning_commitment is not None
    assert state.learning_commitment.status == "completed"
    assert state.learning_commitment.next_follow_up_at is None
    assert state.pending_follow_ups == []
    assert selected is None


def test_spontaneous_interactions_do_not_create_follow_ups(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
    )
    conversation = conversation_service_factory()

    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.RANDOM_TOPIC,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )
    state = engine.mark_interaction_ignored()

    assert state.ignored_interactions == 1
    assert state.learning_commitment is None
    assert state.pending_follow_ups == []


def test_engine_stays_quiet_after_recent_interaction(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    engine = create_engine(
        tmp_path,
        learning_cycle=learning_cycle_factory(),
    )
    conversation = conversation_service_factory()
    engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.SOCIAL,
        current_datetime=datetime(2026, 8, 26, 10, 0),
    )

    selected = engine.select_interaction(
        datetime(2026, 8, 26, 10, 10)
    )

    assert selected is None
