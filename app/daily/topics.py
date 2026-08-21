import random
from dataclasses import dataclass
from typing import Protocol


DEFAULT_TOPICS = (
    "League of Legends",
    "MMORPG",
    "games",
    "artificial intelligence",
    "software development",
    "Angular",
    "technology",
)


@dataclass(frozen=True, eq=False)
class DailyTopic:
    category: str
    title: str
    short_summary: str
    source_name: str
    source_url: str
    published_at: str | None = None

    @classmethod
    def local(cls, category: str) -> "DailyTopic":
        return cls(
            category=category,
            title=category,
            short_summary=(
                "A light everyday conversation starter about "
                f"{category}."
            ),
            source_name="local",
            source_url="",
        )

    @classmethod
    def from_value(cls, value: "DailyTopic | str") -> "DailyTopic":
        if isinstance(value, DailyTopic):
            return value

        return cls.local(value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.category == other

        if not isinstance(other, DailyTopic):
            return False

        return (
            self.category == other.category
            and self.title == other.title
            and self.short_summary == other.short_summary
            and self.source_name == other.source_name
            and self.source_url == other.source_url
            and self.published_at == other.published_at
        )

    def __str__(self) -> str:
        return self.category


class TopicProviderProtocol(Protocol):
    def choose_topic(self) -> DailyTopic | str:
        """Choose a topic from any source."""


class TopicProvider:
    """Chooses local conversation topics without external data."""

    def __init__(
        self,
        topics: tuple[str, ...] = DEFAULT_TOPICS,
        randomizer: random.Random | None = None,
    ) -> None:
        if not topics:
            raise ValueError("TopicProvider requires at least one topic.")

        self.topics = topics
        self.randomizer = randomizer or random.Random()

    def choose_topic(self) -> str:
        return self.randomizer.choice(self.topics)
