from datetime import datetime

from app.chat.service import ConversationService
from app.learning import (
    CEFRLevel,
    LearningCycle,
    LearningCycleStore,
    LearningMode,
    LearningStage,
    WritingPracticeProvider,
)
from app.memory.conversation_memory import ConversationMemory


def test_learning_cycle_creates_initial_state(
    learning_cycle_factory,
):
    cycle = learning_cycle_factory(default_level=CEFRLevel.A1)

    state = cycle.current_state()
    topic = cycle.current_topic()

    assert state.current_level == CEFRLevel.A1
    assert state.current_topic == "greetings-introductions"
    assert topic.name == "Greetings and Introductions"
    assert state.current_stage == LearningStage.COMPREHENSION
    assert state.target_days == 15
    assert state.progress == {
        "comprehension": 0,
        "vocabulary": 0,
        "writing": 0,
        "conversation": 0,
    }


def test_learning_cycle_changes_stage(learning_cycle_factory):
    cycle = learning_cycle_factory()

    state = cycle.change_stage(LearningStage.WRITING)

    assert state.current_stage == LearningStage.WRITING
    assert cycle.current_state().current_stage == (
        LearningStage.WRITING
    )


def test_learning_cycle_updates_progress(learning_cycle_factory):
    cycle = learning_cycle_factory()

    state = cycle.update_progress(
        metric="conversation",
        score=45,
    )

    assert state.progress["conversation"] == 45


def test_learning_cycle_clamps_progress(learning_cycle_factory):
    cycle = learning_cycle_factory()

    state = cycle.update_progress(
        metric="writing",
        score=150,
    )

    assert state.progress["writing"] == 100


def test_learning_cycle_marks_current_topic_completed(
    learning_cycle_factory,
):
    cycle = learning_cycle_factory()

    state = cycle.complete_current_topic()

    assert "greetings-introductions" in state.completed_topics
    assert state.current_stage == LearningStage.MASTERED


def test_learning_cycle_marks_topic_for_review(
    learning_cycle_factory,
):
    cycle = learning_cycle_factory()

    state = cycle.mark_for_review("simple-present")

    assert state.topics_to_review == ["simple-present"]


def test_learning_cycle_selects_warm_up_topic(
    learning_cycle_factory,
):
    cycle = learning_cycle_factory()
    cycle.mark_for_review("simple-present")
    cycle.mark_for_review("daily-routine")
    cycle.record_review(
        topic_id="daily-routine",
        reviewed_on=datetime(2026, 8, 20).date(),
    )

    warm_up = cycle.choose_warm_up_topic()

    assert warm_up is not None
    assert warm_up.id == "simple-present"


def test_learning_cycle_persists_state(tmp_path):
    storage_path = tmp_path / "learning_cycle.json"
    first_cycle = LearningCycle(
        store=LearningCycleStore(storage_path=storage_path)
    )
    first_cycle.change_stage("VOCABULARY")
    first_cycle.update_progress("vocabulary", 80)

    second_cycle = LearningCycle(
        store=LearningCycleStore(storage_path=storage_path)
    )
    state = second_cycle.current_state()

    assert state.current_stage == LearningStage.VOCABULARY
    assert state.progress["vocabulary"] == 80


def test_learning_cycle_loads_old_data_without_cycle_fields(
    tmp_path,
):
    storage_path = tmp_path / "learning_cycle.json"
    storage_path.write_text(
        '{"current_level": "B1"}',
        encoding="utf-8",
    )
    cycle = LearningCycle(
        store=LearningCycleStore(storage_path=storage_path)
    )

    state = cycle.current_state()

    assert state.current_level == CEFRLevel.B1
    assert state.current_topic == "greetings-introductions"
    assert state.current_stage == LearningStage.COMPREHENSION
    assert state.progress["conversation"] == 0


def test_writing_practice_uses_current_learning_focus(
    learning_cycle_factory,
):
    cycle = learning_cycle_factory()
    cycle.change_stage(LearningStage.WRITING)
    provider = WritingPracticeProvider(cycle)

    prompt = provider.create_prompt()

    assert "Greetings and Introductions" in prompt
    assert "level A1" in prompt
    assert "4-5 simple sentences" in prompt


def test_writing_practice_can_use_conversation_service(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    learning_cycle = learning_cycle_factory()
    learning_cycle.change_stage(LearningStage.WRITING)
    practice = WritingPracticeProvider(learning_cycle)
    service = ConversationService(
        ai_client=inspectable_ai_client,
        memory=memory,
        personal_context=personal_context_factory(),
        learning_cycle=learning_cycle,
    )

    service.handle_message(
        practice.build_review_message("My name is Airton.")
    )

    assert "Review this short writing practice response" in (
        inspectable_ai_client.messages[-1]["content"]
    )
    assert "Current topic: Greetings and Introductions" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_conversation_service_adds_learning_cycle_context(
    tmp_path,
    personal_context_factory,
    learning_cycle_factory,
    inspectable_ai_client,
):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    learning_cycle = learning_cycle_factory()
    learning_cycle.change_stage(LearningStage.WRITING)
    learning_cycle.update_progress("writing", 70)

    service = ConversationService(
        ai_client=inspectable_ai_client,
        memory=memory,
        personal_context=personal_context_factory(),
        learning_cycle=learning_cycle,
    )

    service.handle_message("Hello")

    assert "Adaptive Learning Cycle context" in (
        inspectable_ai_client.instructions
    )
    assert '"current_level": "A1"' in (
        inspectable_ai_client.instructions
    )
    assert (
        '"current_topic": "Greetings and Introductions"'
        in inspectable_ai_client.instructions
    )
    assert '"current_stage": "WRITING"' in (
        inspectable_ai_client.instructions
    )
    assert '"writing": 70' in inspectable_ai_client.instructions


def test_learning_cycle_context_keeps_learning_modes(
    conversation_service_factory,
    inspectable_ai_client,
):
    service = conversation_service_factory(
        ai_client=inspectable_ai_client,
        learning_mode=LearningMode.TEACHER,
    )

    service.handle_message("Teach me")

    assert "Active learning mode: TEACHER" in (
        inspectable_ai_client.instructions
    )
    assert "Adaptive Learning Cycle context" in (
        inspectable_ai_client.instructions
    )
