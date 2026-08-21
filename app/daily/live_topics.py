import json
import os
import random
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus

import httpx

from app.daily.topics import (
    DEFAULT_TOPICS,
    DailyTopic,
    TopicProvider,
    TopicProviderProtocol,
)


DEFAULT_CACHE_PATH = "data/live_topic_cache.json"
DEFAULT_SEARCH_URL_TEMPLATE = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=en-US&gl=US&ceid=US:en"
)
DEFAULT_TIMEOUT_SECONDS = 4.0
DEFAULT_CACHE_TTL_SECONDS = 30 * 60
DEFAULT_RECENT_LIMIT = 8
DEFAULT_MAX_LIVE_ATTEMPTS = 3
DEFAULT_MAX_TOPIC_AGE_DAYS = 14

TopicFetcher = Callable[[str, float], str]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _default_fetcher(url: str, timeout_seconds: float) -> str:
    response = httpx.get(url, timeout=timeout_seconds)
    response.raise_for_status()

    return response.text


class LiveTopicCache:
    """Stores short topic metadata and recent titles locally."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
    ) -> None:
        self.storage_path = Path(storage_path or DEFAULT_CACHE_PATH)
        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self._write({
                "topics_by_category": {},
                "recent_titles": [],
            })

    def get_candidates(
        self,
        category: str,
        now: datetime,
        ttl_seconds: int,
    ) -> list[DailyTopic] | None:
        records = self._load()
        category_records = records.get(
            "topics_by_category",
            {},
        )
        cached = category_records.get(category)

        if not isinstance(cached, dict):
            return None

        cached_at = self._parse_datetime(cached.get("cached_at"))

        if not cached_at:
            return None

        if now - cached_at > timedelta(seconds=ttl_seconds):
            return None

        topics = cached.get("topics", [])

        if not isinstance(topics, list):
            return None

        candidates = [
            self._topic_from_record(record)
            for record in topics
            if isinstance(record, dict)
        ]

        return [
            topic
            for topic in candidates
            if topic is not None
        ]

    def set_candidates(
        self,
        category: str,
        topics: list[DailyTopic],
        now: datetime,
    ) -> None:
        records = self._load()
        category_records = records.setdefault(
            "topics_by_category",
            {},
        )
        category_records[category] = {
            "cached_at": now.isoformat(),
            "topics": [
                asdict(topic)
                for topic in topics
            ],
        }

        self._write(records)

    def recent_titles(self) -> list[str]:
        records = self._load()
        recent_titles = records.get("recent_titles", [])

        if not isinstance(recent_titles, list):
            return []

        return [
            title
            for title in recent_titles
            if isinstance(title, str)
        ]

    def remember_topic(
        self,
        topic: DailyTopic,
        limit: int = DEFAULT_RECENT_LIMIT,
    ) -> None:
        records = self._load()
        recent_titles = self.recent_titles()
        title_key = topic.title.strip()

        if not title_key:
            return

        recent_titles = [
            title
            for title in recent_titles
            if title.lower() != title_key.lower()
        ]
        records["recent_titles"] = [
            title_key,
            *recent_titles,
        ][:limit]

        self._write(records)

    def _load(self) -> dict:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8",
            )
            records = json.loads(content)

            if isinstance(records, dict):
                return records
        except (json.JSONDecodeError, OSError):
            pass

        return {
            "topics_by_category": {},
            "recent_titles": [],
        }

    def _write(self, records: dict) -> None:
        self.storage_path.write_text(
            json.dumps(
                records,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _topic_from_record(
        self,
        record: dict,
    ) -> DailyTopic | None:
        try:
            return DailyTopic(
                category=record["category"],
                title=record["title"],
                short_summary=record["short_summary"],
                source_name=record["source_name"],
                source_url=record["source_url"],
                published_at=record.get("published_at"),
            )
        except KeyError:
            return None

    def _parse_datetime(
        self,
        value: object,
    ) -> datetime | None:
        if not isinstance(value, str):
            return None

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None

        return _ensure_utc(parsed)


class LiveTopicProvider:
    """Chooses recent live topics and falls back to local topics."""

    def __init__(
        self,
        categories: tuple[str, ...] = DEFAULT_TOPICS,
        fallback_provider: TopicProviderProtocol | None = None,
        cache: LiveTopicCache | None = None,
        fetcher: TopicFetcher | None = None,
        search_url_template: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: int | None = None,
        recent_limit: int = DEFAULT_RECENT_LIMIT,
        max_live_attempts: int | None = None,
        max_topic_age_days: int = DEFAULT_MAX_TOPIC_AGE_DAYS,
        randomizer: random.Random | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if not categories:
            raise ValueError(
                "LiveTopicProvider requires at least one category."
            )

        self.categories = categories
        self.fallback_provider = fallback_provider or TopicProvider()
        self.cache = cache or LiveTopicCache(
            storage_path=os.getenv(
                "ENGLISH_AGENT_LIVE_TOPIC_CACHE",
                DEFAULT_CACHE_PATH,
            )
        )
        self.fetcher = fetcher or _default_fetcher
        self.search_url_template = (
            search_url_template
            or os.getenv(
                "ENGLISH_AGENT_NEWS_SEARCH_URL_TEMPLATE",
                DEFAULT_SEARCH_URL_TEMPLATE,
            )
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _env_float(
                "ENGLISH_AGENT_LIVE_TOPIC_TIMEOUT",
                DEFAULT_TIMEOUT_SECONDS,
            )
        )
        self.cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else _env_int(
                "ENGLISH_AGENT_LIVE_TOPIC_CACHE_TTL",
                DEFAULT_CACHE_TTL_SECONDS,
            )
        )
        self.recent_limit = recent_limit
        self.max_live_attempts = (
            max_live_attempts
            if max_live_attempts is not None
            else _env_int(
                "ENGLISH_AGENT_MAX_LIVE_TOPIC_ATTEMPTS",
                DEFAULT_MAX_LIVE_ATTEMPTS,
            )
        )
        self.max_topic_age_days = max_topic_age_days
        self.randomizer = randomizer or random.Random()
        self.now_provider = now_provider or datetime.now

    def choose_topic(self) -> DailyTopic:
        categories = list(self.categories)
        self.randomizer.shuffle(categories)
        now = _ensure_utc(self.now_provider())

        for category in categories[:self.max_live_attempts]:
            try:
                candidates = self._get_candidates(
                    category=category,
                    now=now,
                )
                topic = self._choose_non_repeated(candidates)

                if topic:
                    self._remember_topic(
                        topic,
                        limit=self.recent_limit,
                    )

                    return topic
            except Exception:
                continue

        fallback_topic = DailyTopic.from_value(
            self.fallback_provider.choose_topic()
        )
        self._remember_topic(
            fallback_topic,
            limit=self.recent_limit,
        )

        return fallback_topic

    def _remember_topic(
        self,
        topic: DailyTopic,
        limit: int,
    ) -> None:
        try:
            self.cache.remember_topic(
                topic,
                limit=limit,
            )
        except OSError:
            pass

    def _get_candidates(
        self,
        category: str,
        now: datetime,
    ) -> list[DailyTopic]:
        cached_candidates = self.cache.get_candidates(
            category=category,
            now=now,
            ttl_seconds=self.cache_ttl_seconds,
        )

        if cached_candidates:
            return cached_candidates

        feed_content = self.fetcher(
            self._build_search_url(category),
            self.timeout_seconds,
        )
        candidates = self._parse_feed(
            feed_content=feed_content,
            category=category,
            now=now,
        )

        if candidates:
            self.cache.set_candidates(
                category=category,
                topics=candidates,
                now=now,
            )

        return candidates

    def _choose_non_repeated(
        self,
        candidates: list[DailyTopic],
    ) -> DailyTopic | None:
        if not candidates:
            return None

        recent_titles = {
            title.lower()
            for title in self.cache.recent_titles()
        }
        alternatives = [
            candidate
            for candidate in candidates
            if candidate.title.lower() not in recent_titles
        ]

        return (alternatives or candidates)[0]

    def _build_search_url(self, category: str) -> str:
        query = quote_plus(f"{category} news")

        return self.search_url_template.format(query=query)

    def _parse_feed(
        self,
        feed_content: str,
        category: str,
        now: datetime,
    ) -> list[DailyTopic]:
        root = ET.fromstring(feed_content)
        candidates = []

        for item in root.findall(".//item"):
            title = _node_text(item, "title")
            link = _node_text(item, "link")

            if not title or not link:
                continue

            description = _shorten(
                _strip_html(_node_text(item, "description") or title)
            )
            published_at = _parse_published_at(
                _node_text(item, "pubDate")
            )
            source_node = item.find("source")
            source_name = (
                source_node.text.strip()
                if source_node is not None
                and source_node.text
                else "live source"
            )

            candidates.append(
                DailyTopic(
                    category=category,
                    title=_shorten(_strip_html(title), max_chars=140),
                    short_summary=description,
                    source_name=source_name,
                    source_url=link,
                    published_at=(
                        published_at.isoformat()
                        if published_at
                        else None
                    ),
                )
            )

        return self._prioritize_recent(
            topics=candidates,
            now=now,
        )

    def _prioritize_recent(
        self,
        topics: list[DailyTopic],
        now: datetime,
    ) -> list[DailyTopic]:
        fresh_topics = [
            topic
            for topic in topics
            if _topic_age_days(topic, now) <= self.max_topic_age_days
        ]

        return sorted(
            fresh_topics or topics,
            key=_published_sort_key,
            reverse=True,
        )


def _node_text(item: ET.Element, tag_name: str) -> str:
    node = item.find(tag_name)

    if node is None or node.text is None:
        return ""

    return node.text.strip()


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    collapsed = re.sub(r"\s+", " ", without_tags)

    return unescape(collapsed).strip()


def _shorten(value: str, max_chars: int = 220) -> str:
    if len(value) <= max_chars:
        return value

    return value[: max_chars - 3].rstrip() + "..."


def _parse_published_at(value: str) -> datetime | None:
    if not value:
        return None

    try:
        return _ensure_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _published_sort_key(topic: DailyTopic) -> datetime:
    if not topic.published_at:
        return datetime.min.replace(tzinfo=timezone.utc)

    try:
        return _ensure_utc(datetime.fromisoformat(topic.published_at))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _topic_age_days(topic: DailyTopic, now: datetime) -> int:
    published_at = _published_sort_key(topic)

    if published_at == datetime.min.replace(tzinfo=timezone.utc):
        return 0

    return max(0, (now - published_at).days)
