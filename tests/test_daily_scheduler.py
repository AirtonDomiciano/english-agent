from datetime import datetime
from threading import Event

from app.daily import DailyScheduler, DailySessionStore, TopicProvider


def test_daily_scheduler_triggers_morning_inside_window(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    store = DailySessionStore(
        storage_path=tmp_path / "daily_sessions.json"
    )
    scheduler = DailyScheduler(
        store=store,
        topic_provider=TopicProvider(
            topics=("MMORPG",),
        ),
    )

    results = scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 11, 8, 45),
    )

    assert len(results) == 1
    assert results[0].session_id == "morning"
    assert results[0].topic == "MMORPG"
    assert "Companion personality instructions" in (
        inspectable_ai_client.instructions
    )
    assert "Active learning mode: DAILY" in (
        inspectable_ai_client.instructions
    )
    assert "Adaptive Learning Cycle context" in (
        inspectable_ai_client.instructions
    )
    assert "Category: MMORPG" in (
        inspectable_ai_client.messages[-1]["content"]
    )


def test_daily_scheduler_does_not_trigger_after_window(
    tmp_path,
    conversation_service_factory,
):
    conversation = conversation_service_factory()
    store = DailySessionStore(
        storage_path=tmp_path / "daily_sessions.json"
    )
    scheduler = DailyScheduler(
        store=store,
        topic_provider=TopicProvider(
            topics=("Angular",),
        ),
    )

    results = scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 11, 9, 1),
    )

    assert results == []
    assert conversation.memory.load() == []
    assert store.load() == {}


def test_daily_scheduler_does_not_trigger_twice_same_day(
    tmp_path,
    conversation_service_factory,
):
    conversation = conversation_service_factory()
    store = DailySessionStore(
        storage_path=tmp_path / "daily_sessions.json"
    )
    scheduler = DailyScheduler(
        store=store,
        topic_provider=TopicProvider(
            topics=("games",),
        ),
    )
    current_datetime = datetime(2026, 8, 11, 8, 45)

    first_results = scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=current_datetime,
    )
    second_results = scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=current_datetime,
    )

    assert len(first_results) == 1
    assert second_results == []
    assert store.was_triggered(
        session_id="morning",
        current_date=current_datetime.date(),
    )
    assert len(conversation.memory.load()) == 1


def test_daily_scheduler_runner_keeps_checking_until_window(
    tmp_path,
    conversation_service_factory,
):
    from app.daily import DailySchedulerRunner

    conversation = conversation_service_factory()
    store = DailySessionStore(
        storage_path=tmp_path / "daily_sessions.json"
    )
    current_times = iter([
        datetime(2026, 8, 11, 8, 0),
        datetime(2026, 8, 11, 8, 45),
    ])
    scheduler = DailyScheduler(
        store=store,
        topic_provider=TopicProvider(
            topics=("Angular",),
        ),
        now_provider=lambda: next(
            current_times,
            datetime(2026, 8, 11, 8, 45),
        ),
    )
    received_results = []
    result_received = Event()

    runner = DailySchedulerRunner(
        scheduler=scheduler,
        conversation_service=conversation,
        on_result=lambda result: (
            received_results.append(result),
            result_received.set(),
        ),
        poll_interval_seconds=0.1,
    )

    runner.start()

    try:
        assert result_received.wait(timeout=1)
    finally:
        runner.stop()

    assert len(received_results) == 1
    assert received_results[0].session_id == "morning"
    assert received_results[0].topic == "Angular"


def test_daily_scheduler_does_not_mark_triggered_when_ai_fails(
    tmp_path,
    conversation_service_factory,
    failing_ai_client,
    inspectable_ai_client,
):
    failing_conversation = conversation_service_factory(
        ai_client=failing_ai_client,
        namespace="failing_conversation",
    )
    store = DailySessionStore(
        storage_path=tmp_path / "daily_sessions.json"
    )
    scheduler = DailyScheduler(
        store=store,
        topic_provider=TopicProvider(
            topics=("technology",),
        ),
    )
    current_datetime = datetime(2026, 8, 11, 8, 45)

    failed_results = scheduler.run_pending(
        conversation_service=failing_conversation,
        current_datetime=current_datetime,
    )

    retry_conversation = conversation_service_factory(
        ai_client=inspectable_ai_client,
        namespace="retry_conversation",
    )
    retry_results = scheduler.run_pending(
        conversation_service=retry_conversation,
        current_datetime=current_datetime,
    )

    assert failed_results == []
    assert failing_conversation.memory.load() == []
    assert retry_conversation.memory.load() == [
        {
            "role": "assistant",
            "content": "Fake response",
        },
    ]
    assert len(retry_results) == 1
    assert store.was_triggered(
        session_id="morning",
        current_date=current_datetime.date(),
    )


def test_manual_conversation_still_works_after_daily_scheduler(
    tmp_path,
    conversation_service_factory,
    fake_ai_client,
):
    conversation = conversation_service_factory(
        ai_client=fake_ai_client
    )
    scheduler = DailyScheduler(
        store=DailySessionStore(
            storage_path=tmp_path / "daily_sessions.json"
        ),
        topic_provider=TopicProvider(
            topics=("technology",),
        ),
    )

    scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 11, 9, 1),
    )
    reply = conversation.handle_message("Manual hello")

    assert reply == "Fake response for: Manual hello"
    assert conversation.memory.load() == [
        {
            "role": "user",
            "content": "Manual hello",
        },
        {
            "role": "assistant",
            "content": "Fake response for: Manual hello",
        },
    ]
