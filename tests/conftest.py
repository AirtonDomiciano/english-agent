import pytest

from app.chat.service import ConversationService
from app.context.personal_context import PersonalContext
from app.daily import LiveTopicCache
from app.learning import CEFRLevel, LearningCycle, LearningCycleStore
from app.memory.conversation_memory import ConversationMemory


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


@pytest.fixture
def fake_ai_client():
    return FakeAIClient()


@pytest.fixture
def inspectable_ai_client():
    return InspectableFakeAIClient()


@pytest.fixture
def failing_ai_client():
    return FailingAIClient()


@pytest.fixture
def personal_context_factory(tmp_path):
    counter = 0

    def create(namespace: str | None = None) -> PersonalContext:
        nonlocal counter
        counter += 1
        base_path = tmp_path / (namespace or f"personal_{counter}")

        return PersonalContext(
            storage_path=base_path / "personal_context.json"
        )

    return create


@pytest.fixture
def learning_cycle_factory(tmp_path):
    counter = 0

    def create(
        default_level: CEFRLevel = CEFRLevel.A1,
        namespace: str | None = None,
    ) -> LearningCycle:
        nonlocal counter
        counter += 1
        base_path = tmp_path / (namespace or f"learning_{counter}")

        return LearningCycle(
            store=LearningCycleStore(
                storage_path=base_path / "learning_cycle.json",
                default_level=default_level,
            )
        )

    return create


@pytest.fixture
def conversation_service_factory(tmp_path):
    counter = 0

    def create(
        ai_client=None,
        learning_mode=None,
        context_window_size: int = 20,
        namespace: str | None = None,
    ) -> ConversationService:
        nonlocal counter
        counter += 1
        base_path = tmp_path / (namespace or f"conversation_{counter}")

        return ConversationService(
            ai_client=ai_client or InspectableFakeAIClient(),
            memory=ConversationMemory(
                storage_path=base_path / "history.json"
            ),
            personal_context=PersonalContext(
                storage_path=base_path / "personal_context.json"
            ),
            learning_mode=learning_mode,
            learning_cycle=LearningCycle(
                store=LearningCycleStore(
                    storage_path=base_path / "learning_cycle.json"
                )
            ),
            context_window_size=context_window_size,
        )

    return create


@pytest.fixture
def live_topic_cache_factory(tmp_path):
    counter = 0

    def create(namespace: str | None = None) -> LiveTopicCache:
        nonlocal counter
        counter += 1
        base_path = tmp_path / (namespace or f"live_topics_{counter}")

        return LiveTopicCache(
            storage_path=base_path / "live_topic_cache.json"
        )

    return create


@pytest.fixture
def rss_feed_builder():
    def build(*items):
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

    return build
