from datetime import datetime, timezone
from threading import Event

from app.context.personal_context import PersonalContext
from app.chat.service import ConversationService
from app.daily import (
    DailyTopic,
    DailyScheduler,
    DailySchedulerRunner,
    DailySessionStore,
    LiveTopicCache,
    LiveTopicProvider,
    TopicProvider,
    create_default_daily_sessions,
)
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


class FailingAIClient:
    def generate_response(
        self,
        messages: list[dict],
        instructions: str,
    ) -> str:
        raise RuntimeError("OpenAI unavailable")


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


def test_conversation_service_keeps_manual_error_response(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    service = ConversationService(
        ai_client=FailingAIClient(),
        memory=memory,
        personal_context=personal_context,
    )

    reply = service.handle_message("Hello")

    assert reply == (
        "I couldn't answer right now. "
        "Error: OpenAI unavailable"
    )
    assert memory.load() == []


def create_daily_service(tmp_path, ai_client=None):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    return ConversationService(
        ai_client=ai_client or InspectableFakeAIClient(),
        memory=memory,
        personal_context=personal_context,
    )


def build_rss_feed(*items):
    rss_items = "\n".join(
        (
            "<item>"
            f"<title>{item['title']}</title>"
            f"<link>{item['link']}</link>"
            f"<description>{item['description']}</description>"
            f"<pubDate>{item['published_at']}</pubDate>"
            f"<source>{item['source_name']}</source>"
            "</item>"
        )
        for item in items
    )

    return f"<rss><channel>{rss_items}</channel></rss>"


def live_topic_cache(tmp_path):
    return LiveTopicCache(
        storage_path=tmp_path / "live_topic_cache.json"
    )


def test_topic_provider_chooses_configured_topic():
    topic_provider = TopicProvider(
        topics=("Angular",),
    )

    assert topic_provider.choose_topic() == "Angular"


def test_live_topic_provider_returns_valid_topic(tmp_path):
    feed = build_rss_feed({
        "title": "Angular releases a new developer preview",
        "link": "https://example.com/angular-preview",
        "description": (
            "Angular is testing a smaller build pipeline for apps."
        ),
        "published_at": "Fri, 21 Aug 2026 11:00:00 GMT",
        "source_name": "Example Tech",
    })
    requested = {}

    def fetcher(url, timeout_seconds):
        requested["url"] = url
        requested["timeout_seconds"] = timeout_seconds

        return feed

    provider = LiveTopicProvider(
        categories=("Angular",),
        cache=live_topic_cache(tmp_path),
        fetcher=fetcher,
        timeout_seconds=1.5,
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

    topic = provider.choose_topic()

    assert topic == DailyTopic(
        category="Angular",
        title="Angular releases a new developer preview",
        short_summary=(
            "Angular is testing a smaller build pipeline for apps."
        ),
        source_name="Example Tech",
        source_url="https://example.com/angular-preview",
        published_at="2026-08-21T11:00:00+00:00",
    )
    assert "Angular+news" in requested["url"]
    assert requested["timeout_seconds"] == 1.5


def test_live_topic_provider_falls_back_when_source_fails(
    tmp_path,
):
    def fetcher(url, timeout_seconds):
        raise RuntimeError("network down")

    provider = LiveTopicProvider(
        categories=("artificial intelligence",),
        cache=live_topic_cache(tmp_path),
        fetcher=fetcher,
        fallback_provider=TopicProvider(
            topics=("games",),
        ),
        max_live_attempts=1,
    )

    topic = provider.choose_topic()

    assert topic.category == "games"
    assert topic.source_name == "local"


def test_live_topic_provider_uses_timeout_for_fetcher(tmp_path):
    requested_timeouts = []

    def fetcher(url, timeout_seconds):
        requested_timeouts.append(timeout_seconds)
        raise TimeoutError("too slow")

    provider = LiveTopicProvider(
        categories=("technology",),
        cache=live_topic_cache(tmp_path),
        fetcher=fetcher,
        fallback_provider=TopicProvider(
            topics=("technology",),
        ),
        timeout_seconds=0.25,
        max_live_attempts=1,
    )

    topic = provider.choose_topic()

    assert topic.category == "technology"
    assert requested_timeouts == [0.25]


def test_live_topic_provider_uses_cache_without_refetching(
    tmp_path,
):
    feed = build_rss_feed(
        {
            "title": "First cached games topic",
            "link": "https://example.com/games-1",
            "description": "A short games update.",
            "published_at": "Fri, 21 Aug 2026 10:00:00 GMT",
            "source_name": "Example Games",
        },
        {
            "title": "Second cached games topic",
            "link": "https://example.com/games-2",
            "description": "Another short games update.",
            "published_at": "Fri, 21 Aug 2026 09:00:00 GMT",
            "source_name": "Example Games",
        },
    )
    fetch_count = {
        "value": 0,
    }

    def fetcher(url, timeout_seconds):
        fetch_count["value"] += 1

        return feed

    provider = LiveTopicProvider(
        categories=("games",),
        cache=live_topic_cache(tmp_path),
        fetcher=fetcher,
        cache_ttl_seconds=3600,
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

    first_topic = provider.choose_topic()
    second_topic = provider.choose_topic()

    assert fetch_count["value"] == 1
    assert first_topic.title != second_topic.title


def test_live_topic_provider_avoids_simple_repetition(
    tmp_path,
):
    feed = build_rss_feed(
        {
            "title": "League patch changes jungle balance",
            "link": "https://example.com/lol-1",
            "description": "The patch focuses on jungle pacing.",
            "published_at": "Fri, 21 Aug 2026 10:00:00 GMT",
            "source_name": "Example Esports",
        },
        {
            "title": "League adds a new ranked experiment",
            "link": "https://example.com/lol-2",
            "description": "Riot is testing ranked queue changes.",
            "published_at": "Fri, 21 Aug 2026 09:00:00 GMT",
            "source_name": "Example Esports",
        },
    )
    provider = LiveTopicProvider(
        categories=("League of Legends",),
        cache=live_topic_cache(tmp_path),
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

    first_topic = provider.choose_topic()
    second_topic = provider.choose_topic()

    assert first_topic.title == (
        "League patch changes jungle balance"
    )
    assert second_topic.title == (
        "League adds a new ranked experiment"
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


def test_daily_scheduler_triggers_morning_inside_window(tmp_path):
    ai_client = InspectableFakeAIClient()
    conversation = create_daily_service(
        tmp_path,
        ai_client=ai_client,
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
        ai_client.instructions
    )
    assert "Active learning mode: DAILY" in ai_client.instructions
    assert "Category: MMORPG" in ai_client.messages[-1]["content"]


def test_daily_scheduler_does_not_trigger_after_window(tmp_path):
    conversation = create_daily_service(tmp_path)
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


def test_daily_scheduler_does_not_trigger_twice_same_day(tmp_path):
    conversation = create_daily_service(tmp_path)
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
):
    conversation = create_daily_service(tmp_path)
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
):
    failing_conversation = create_daily_service(
        tmp_path,
        ai_client=FailingAIClient(),
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

    retry_conversation = create_daily_service(
        tmp_path,
        ai_client=InspectableFakeAIClient(),
    )
    retry_results = scheduler.run_pending(
        conversation_service=retry_conversation,
        current_datetime=current_datetime,
    )

    assert failed_results == []
    assert failing_conversation.memory.load() == []
    assert len(retry_results) == 1
    assert store.was_triggered(
        session_id="morning",
        current_date=current_datetime.date(),
    )


def test_daily_session_uses_live_topic_details(tmp_path):
    feed = build_rss_feed({
        "title": "New MMORPG focuses on large-scale PvP",
        "link": "https://example.com/mmorpg-pvp",
        "description": (
            "The game is leaning into castle sieges and big guild "
            "battles."
        ),
        "published_at": "Fri, 21 Aug 2026 11:30:00 GMT",
        "source_name": "Example MMO",
    })
    ai_client = InspectableFakeAIClient()
    conversation = create_daily_service(
        tmp_path,
        ai_client=ai_client,
    )
    provider = LiveTopicProvider(
        categories=("MMORPG",),
        cache=live_topic_cache(tmp_path),
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

    message = ai_client.messages[-1]["content"]

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
):
    ai_client = InspectableFakeAIClient()
    conversation = create_daily_service(
        tmp_path,
        ai_client=ai_client,
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
        ai_client.messages[-1]["content"]
    )


def test_manual_conversation_still_works_after_daily_scheduler(
    tmp_path,
):
    conversation = create_daily_service(
        tmp_path,
        ai_client=FakeAIClient(),
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


def test_bootstrap_creates_expected_structure(tmp_path):
    app = bootstrap_app(data_dir=tmp_path)

    assert app["data_dir"].exists()
    assert app["memory_path"].exists()
    assert app["phase"] == "phase-1"
