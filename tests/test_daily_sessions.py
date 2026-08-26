from datetime import datetime, timezone

from app.daily import (
    DailyScheduler,
    DailySessionStore,
    LiveTopicProvider,
    TopicProvider,
    create_default_daily_sessions,
)


def test_default_daily_sessions_include_morning_and_afternoon():
    sessions = create_default_daily_sessions()

    assert [
        session.session_id
        for session in sessions
    ] == [
        "morning",
        "afternoon",
    ]


def test_daily_session_uses_live_topic_details(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
    live_topic_cache_factory,
    rss_feed_builder,
):
    feed = rss_feed_builder({
        "title": "New MMORPG focuses on large-scale PvP",
        "link": "https://example.com/mmorpg-pvp",
        "description": (
            "The game is leaning into castle sieges and big guild "
            "battles."
        ),
        "published_at": "Fri, 21 Aug 2026 11:30:00 GMT",
        "source_name": "Example MMO",
    })
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    provider = LiveTopicProvider(
        categories=("MMORPG",),
        cache=live_topic_cache_factory(),
        fetcher=lambda url, timeout_seconds: feed,
        max_live_attempts=1,
        now_provider=lambda: datetime(
            2026,
            8,
            21,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    )
    scheduler = DailyScheduler(
        store=DailySessionStore(
            storage_path=tmp_path / "daily_sessions.json"
        ),
        topic_provider=provider,
    )

    results = scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 21, 8, 45),
    )

    message = inspectable_ai_client.messages[-1]["content"]

    assert len(results) == 1
    assert results[0].topic.category == "MMORPG"
    assert "Category: MMORPG" in message
    assert "Title: New MMORPG focuses on large-scale PvP" in message
    assert (
        "Short summary: The game is leaning into castle sieges"
        in message
    )
    assert "https://example.com/mmorpg-pvp" not in message


def test_daily_session_uses_conversation_service_without_user_memory(
    tmp_path,
    conversation_service_factory,
    inspectable_ai_client,
):
    conversation = conversation_service_factory(
        ai_client=inspectable_ai_client
    )
    scheduler = DailyScheduler(
        store=DailySessionStore(
            storage_path=tmp_path / "daily_sessions.json"
        ),
        topic_provider=TopicProvider(
            topics=("artificial intelligence",),
        ),
    )

    scheduler.run_pending(
        conversation_service=conversation,
        current_datetime=datetime(2026, 8, 11, 8, 45),
    )

    history = conversation.memory.load()

    assert history == [
        {
            "role": "assistant",
            "content": "Fake response",
        },
    ]
    assert "artificial intelligence" in (
        inspectable_ai_client.messages[-1]["content"]
    )
