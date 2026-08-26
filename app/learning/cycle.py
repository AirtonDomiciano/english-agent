import json
import random
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"


class LearningStage(str, Enum):
    COMPREHENSION = "COMPREHENSION"
    VOCABULARY = "VOCABULARY"
    WRITING = "WRITING"
    CONVERSATION = "CONVERSATION"
    MASTERED = "MASTERED"


DEFAULT_PROGRESS: dict[str, int] = {
    "comprehension": 0,
    "vocabulary": 0,
    "writing": 0,
    "conversation": 0,
}


@dataclass(frozen=True)
class LearningTopic:
    id: str
    name: str
    cefr_level: CEFRLevel
    description: str
    suggested_duration_days: int
    learning_stages: tuple[LearningStage, ...]


DEFAULT_TOPIC_STAGES = (
    LearningStage.COMPREHENSION,
    LearningStage.VOCABULARY,
    LearningStage.WRITING,
    LearningStage.CONVERSATION,
    LearningStage.MASTERED,
)


DEFAULT_LEARNING_TOPICS: tuple[LearningTopic, ...] = (
    LearningTopic(
        id="greetings-introductions",
        name="Greetings and Introductions",
        cefr_level=CEFRLevel.A1,
        description=(
            "Say hello, introduce yourself and ask simple personal "
            "questions."
        ),
        suggested_duration_days=15,
        learning_stages=DEFAULT_TOPIC_STAGES,
    ),
    LearningTopic(
        id="daily-routine",
        name="Daily Routine",
        cefr_level=CEFRLevel.A1,
        description=(
            "Talk about everyday habits, schedule and simple routines."
        ),
        suggested_duration_days=15,
        learning_stages=DEFAULT_TOPIC_STAGES,
    ),
    LearningTopic(
        id="work-profession",
        name="Work and Profession",
        cefr_level=CEFRLevel.A2,
        description=(
            "Describe your job, responsibilities and professional "
            "context."
        ),
        suggested_duration_days=20,
        learning_stages=DEFAULT_TOPIC_STAGES,
    ),
    LearningTopic(
        id="simple-present",
        name="Simple Present",
        cefr_level=CEFRLevel.A1,
        description=(
            "Use simple present to describe habits, facts and routines."
        ),
        suggested_duration_days=15,
        learning_stages=DEFAULT_TOPIC_STAGES,
    ),
    LearningTopic(
        id="simple-past",
        name="Simple Past",
        cefr_level=CEFRLevel.A2,
        description=(
            "Talk about completed actions and past experiences."
        ),
        suggested_duration_days=20,
        learning_stages=DEFAULT_TOPIC_STAGES,
    ),
)


def parse_cefr_level(value: CEFRLevel | str) -> CEFRLevel:
    if isinstance(value, CEFRLevel):
        return value

    return CEFRLevel(str(value).upper())


def parse_learning_stage(
    value: LearningStage | str,
) -> LearningStage:
    if isinstance(value, LearningStage):
        return value

    return LearningStage(str(value).upper())


class LearningTopicCatalog:
    def __init__(
        self,
        topics: tuple[LearningTopic, ...] = DEFAULT_LEARNING_TOPICS,
    ) -> None:
        if not topics:
            raise ValueError("LearningTopicCatalog requires topics.")

        self._topics = {
            topic.id: topic
            for topic in topics
        }

    def first_topic_for_level(
        self,
        level: CEFRLevel | str,
    ) -> LearningTopic:
        resolved_level = parse_cefr_level(level)

        for topic in self._topics.values():
            if topic.cefr_level == resolved_level:
                return topic

        return next(iter(self._topics.values()))

    def get(self, topic_id: str) -> LearningTopic:
        return self._topics[topic_id]

    def find(self, topic_id: str) -> LearningTopic | None:
        return self._topics.get(topic_id)

    def all(self) -> list[LearningTopic]:
        return list(self._topics.values())


@dataclass
class LearningFocusState:
    current_topic: str
    current_level: CEFRLevel
    current_stage: LearningStage
    start_date: str
    target_days: int
    progress: dict[str, int] = field(
        default_factory=lambda: deepcopy(DEFAULT_PROGRESS)
    )
    completed_topics: list[str] = field(default_factory=list)
    topics_to_review: list[str] = field(default_factory=list)
    last_review_dates: dict[str, str] = field(default_factory=dict)


class LearningCycleStore:
    """Persists adaptive learning state in local JSON."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        catalog: LearningTopicCatalog | None = None,
        default_level: CEFRLevel | str = CEFRLevel.A1,
        today_provider: Callable[[], date] | None = None,
    ) -> None:
        self.storage_path = Path(
            storage_path or "data/learning_cycle.json"
        )
        self.catalog = catalog or LearningTopicCatalog()
        self.default_level = parse_cefr_level(default_level)
        self.today_provider = today_provider or date.today
        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self.save(self.create_initial_state())

    def create_initial_state(self) -> LearningFocusState:
        topic = self.catalog.first_topic_for_level(
            self.default_level
        )

        return LearningFocusState(
            current_topic=topic.id,
            current_level=topic.cefr_level,
            current_stage=topic.learning_stages[0],
            start_date=self.today_provider().isoformat(),
            target_days=topic.suggested_duration_days,
        )

    def load(self) -> LearningFocusState:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8",
            )
            data = json.loads(content)

            if not isinstance(data, dict):
                return self.create_initial_state()

            return self._state_from_data(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return self.create_initial_state()

    def save(self, state: LearningFocusState) -> None:
        data = asdict(state)
        data["current_level"] = state.current_level.value
        data["current_stage"] = state.current_stage.value

        self.storage_path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _state_from_data(
        self,
        data: dict[str, Any],
    ) -> LearningFocusState:
        initial_state = self.create_initial_state()
        merged = {
            **asdict(initial_state),
            **data,
        }
        progress = {
            **deepcopy(DEFAULT_PROGRESS),
            **(
                merged.get("progress")
                if isinstance(merged.get("progress"), dict)
                else {}
            ),
        }

        return LearningFocusState(
            current_topic=str(merged["current_topic"]),
            current_level=parse_cefr_level(merged["current_level"]),
            current_stage=parse_learning_stage(
                merged["current_stage"]
            ),
            start_date=str(merged["start_date"]),
            target_days=int(merged["target_days"]),
            progress={
                metric: self._clamp_score(value)
                for metric, value in progress.items()
            },
            completed_topics=list(merged.get("completed_topics", [])),
            topics_to_review=list(merged.get("topics_to_review", [])),
            last_review_dates=dict(
                merged.get("last_review_dates", {})
            ),
        )

    def _clamp_score(self, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0

        return max(0, min(100, parsed))


class LearningCycle:
    """Coordinates learning focus, progress and review state."""

    def __init__(
        self,
        store: LearningCycleStore | None = None,
        catalog: LearningTopicCatalog | None = None,
        randomizer: random.Random | None = None,
    ) -> None:
        self.catalog = catalog or (
            store.catalog
            if store
            else LearningTopicCatalog()
        )
        self.store = store or LearningCycleStore(
            catalog=self.catalog
        )
        self.randomizer = randomizer or random.Random()

    def current_state(self) -> LearningFocusState:
        return self.store.load()

    def current_topic(self) -> LearningTopic:
        state = self.current_state()
        topic = self.catalog.find(state.current_topic)

        if topic:
            return topic

        return self.catalog.first_topic_for_level(
            state.current_level
        )

    def change_stage(
        self,
        stage: LearningStage | str,
    ) -> LearningFocusState:
        state = self.current_state()
        state.current_stage = parse_learning_stage(stage)
        self.store.save(state)

        return state

    def update_progress(
        self,
        metric: str,
        score: int,
    ) -> LearningFocusState:
        state = self.current_state()

        if metric not in DEFAULT_PROGRESS:
            raise ValueError(f"Unknown progress metric: {metric}.")

        state.progress[metric] = max(0, min(100, int(score)))
        self.store.save(state)

        return state

    def complete_current_topic(self) -> LearningFocusState:
        state = self.current_state()

        if state.current_topic not in state.completed_topics:
            state.completed_topics.append(state.current_topic)

        state.current_stage = LearningStage.MASTERED
        self.store.save(state)

        return state

    def mark_for_review(self, topic_id: str) -> LearningFocusState:
        state = self.current_state()

        if topic_id not in state.topics_to_review:
            state.topics_to_review.append(topic_id)

        self.store.save(state)

        return state

    def record_review(
        self,
        topic_id: str,
        reviewed_on: date | None = None,
    ) -> LearningFocusState:
        state = self.current_state()
        review_date = reviewed_on or date.today()
        state.last_review_dates[topic_id] = review_date.isoformat()
        self.store.save(state)

        return state

    def choose_warm_up_topic(self) -> LearningTopic | None:
        state = self.current_state()
        reviewable_topics = [
            topic_id
            for topic_id in state.topics_to_review
            if topic_id != state.current_topic
            and self.catalog.find(topic_id)
        ]

        if not reviewable_topics:
            return None

        reviewable_topics.sort(
            key=lambda topic_id: state.last_review_dates.get(
                topic_id,
                "",
            )
        )

        return self.catalog.get(reviewable_topics[0])

    def to_prompt_context(self) -> str:
        state = self.current_state()
        current_topic = self.current_topic()
        warm_up_topic = self.choose_warm_up_topic()

        context = {
            "current_level": state.current_level.value,
            "current_topic": current_topic.name,
            "current_stage": state.current_stage.value,
            "started_on": state.start_date,
            "target_days": state.target_days,
            "progress": state.progress,
            "completed_topics": [
                self.catalog.get(topic_id).name
                for topic_id in state.completed_topics
                if self.catalog.find(topic_id)
            ],
            "needs_review": [
                self.catalog.get(topic_id).name
                for topic_id in state.topics_to_review
                if self.catalog.find(topic_id)
            ],
            "warm_up_candidate": (
                warm_up_topic.name
                if warm_up_topic
                else None
            ),
        }

        return (
            "Adaptive Learning Cycle context:\n"
            f"{json.dumps(context, indent=2, ensure_ascii=False)}\n"
            "Use this as background context only. Do not force every "
            "conversation into a lesson."
        )


class WritingPracticeProvider:
    """Creates short writing prompts from the current learning focus."""

    def __init__(
        self,
        learning_cycle: LearningCycle,
    ) -> None:
        self.learning_cycle = learning_cycle

    def create_prompt(self) -> str:
        state = self.learning_cycle.current_state()
        topic = self.learning_cycle.current_topic()

        if state.current_stage == LearningStage.CONVERSATION:
            return (
                "Imagine this is a natural conversation. Write a short "
                f"answer using {topic.name}."
            )

        if state.current_stage == LearningStage.WRITING:
            return (
                f"Write 4-5 simple sentences about {topic.name}. "
                f"Keep it appropriate for level {state.current_level.value}."
            )

        return (
            f"Write 2-3 simple sentences related to {topic.name}. "
            f"Level: {state.current_level.value}. "
            f"Stage: {state.current_stage.value}."
        )

    def build_review_message(self, user_response: str) -> str:
        state = self.learning_cycle.current_state()
        topic = self.learning_cycle.current_topic()

        return (
            "Review this short writing practice response.\n"
            f"CEFR level: {state.current_level.value}\n"
            f"Current topic: {topic.name}\n"
            f"Current stage: {state.current_stage.value}\n"
            "Be gentle and practical. Correct the most important "
            "mistakes, show a more natural version, and invite one "
            "small follow-up.\n"
            f"User response: {user_response.strip()}"
        )
