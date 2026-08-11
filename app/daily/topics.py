import random


DEFAULT_TOPICS = (
    "League of Legends",
    "MMORPG",
    "games",
    "artificial intelligence",
    "software development",
    "Angular",
    "technology",
)


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
