from datetime import datetime, timezone

from app.daily import DailyTopic, LiveTopicProvider, TopicProvider


def test_topic_provider_chooses_configured_topic():
    topic_provider = TopicProvider(
        topics=("Angular",),
    )

    assert topic_provider.choose_topic() == "Angular"


def test_live_topic_provider_returns_valid_topic(
    live_topic_cache_factory,
    rss_feed_builder,
):
    feed = rss_feed_builder({
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
        cache=live_topic_cache_factory(),
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
    live_topic_cache_factory,
):
    def fetcher(url, timeout_seconds):
        raise RuntimeError("network down")

    provider = LiveTopicProvider(
        categories=("artificial intelligence",),
        cache=live_topic_cache_factory(),
        fetcher=fetcher,
        fallback_provider=TopicProvider(
            topics=("games",),
        ),
        max_live_attempts=1,
    )

    topic = provider.choose_topic()

    assert topic.category == "games"
    assert topic.source_name == "local"


def test_live_topic_provider_uses_timeout_for_fetcher(
    live_topic_cache_factory,
):
    requested_timeouts = []

    def fetcher(url, timeout_seconds):
        requested_timeouts.append(timeout_seconds)
        raise TimeoutError("too slow")

    provider = LiveTopicProvider(
        categories=("technology",),
        cache=live_topic_cache_factory(),
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
    live_topic_cache_factory,
    rss_feed_builder,
):
    feed = rss_feed_builder(
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
        cache=live_topic_cache_factory(),
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
    live_topic_cache_factory,
    rss_feed_builder,
):
    feed = rss_feed_builder(
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

    first_topic = provider.choose_topic()
    second_topic = provider.choose_topic()

    assert first_topic.title == (
        "League patch changes jungle balance"
    )
    assert second_topic.title == (
        "League adds a new ranked experiment"
    )
