import json
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable

from app.chat.service import ConversationService
from app.daily import DailyTopic, SessionWindow, TopicProvider
from app.daily.companion_prompt import COMPANION_PERSONALITY_PROMPT
from app.daily.topics import TopicProviderProtocol
from app.learning import LearningCycle


class CompanionInteractionType(str, Enum):
    SOCIAL = "SOCIAL"
    RANDOM_TOPIC = "RANDOM_TOPIC"
    MINI_QUIZ = "MINI_QUIZ"
    LEARNING_RECALL = "LEARNING_RECALL"
    QUICK_CHALLENGE = "QUICK_CHALLENGE"
    LEARNING_COMMITMENT = "LEARNING_COMMITMENT"


COMMITMENT_FOLLOW_UP_DELAYS = (
    timedelta(minutes=10),
    timedelta(minutes=30),
    timedelta(minutes=45),
    timedelta(hours=1),
)


@dataclass(frozen=True)
class CompanionInteractionResult:
    interaction_type: CompanionInteractionType
    prompt: str
    response: str


@dataclass
class LearningCommitmentState:
    date: str
    status: str = "pending"
    prompts_sent: int = 0
    next_follow_up_at: str | None = None


@dataclass
class CompanionInteractionState:
    last_interaction_at: str | None = None
    last_response_at: str | None = None
    ignored_interactions: int = 0
    learning_commitment: LearningCommitmentState | None = None
    pending_follow_ups: list[dict] = field(default_factory=list)
    daily_interaction_counts: dict[str, int] = field(
        default_factory=dict
    )
    familiarity: int = 0
    preferred_topics: list[str] = field(default_factory=list)
    accepted_invites: int = 0
    ignored_invites: int = 0
    streak_days: int = 0


class CompanionInteractionStore:
    """Persists the minimum state needed for companion initiative."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
    ) -> None:
        self.storage_path = Path(
            storage_path or "data/companion_interactions.json"
        )
        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self.save(CompanionInteractionState())

    def load(self) -> CompanionInteractionState:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8",
            )
            data = json.loads(content)

            if not isinstance(data, dict):
                return CompanionInteractionState()

            return self._state_from_data(data)
        except (json.JSONDecodeError, OSError):
            return CompanionInteractionState()

    def save(self, state: CompanionInteractionState) -> None:
        data = asdict(state)

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
        data: dict,
    ) -> CompanionInteractionState:
        commitment = data.get("learning_commitment")

        if isinstance(commitment, dict):
            commitment_state = LearningCommitmentState(
                date=str(commitment.get("date", "")),
                status=str(commitment.get("status", "pending")),
                prompts_sent=int(
                    commitment.get("prompts_sent", 0)
                ),
                next_follow_up_at=commitment.get(
                    "next_follow_up_at"
                ),
            )
        else:
            commitment_state = None

        return CompanionInteractionState(
            last_interaction_at=data.get("last_interaction_at"),
            last_response_at=data.get("last_response_at"),
            ignored_interactions=int(
                data.get("ignored_interactions", 0)
            ),
            learning_commitment=commitment_state,
            pending_follow_ups=list(
                data.get("pending_follow_ups", [])
                if isinstance(data.get("pending_follow_ups"), list)
                else []
            ),
            daily_interaction_counts=dict(
                data.get("daily_interaction_counts", {})
                if isinstance(data.get("daily_interaction_counts"), dict)
                else {}
            ),
            familiarity=int(data.get("familiarity", 0)),
            preferred_topics=list(
                data.get("preferred_topics", [])
                if isinstance(data.get("preferred_topics"), list)
                else []
            ),
            accepted_invites=int(data.get("accepted_invites", 0)),
            ignored_invites=int(data.get("ignored_invites", 0)),
            streak_days=int(data.get("streak_days", 0)),
        )


class CompanionInteractionEngine:
    """Creates spontaneous companion interactions without owning chat."""

    def __init__(
        self,
        store: CompanionInteractionStore | None = None,
        learning_cycle: LearningCycle | None = None,
        topic_provider: TopicProviderProtocol | None = None,
        commitment_window: SessionWindow | None = None,
        now_provider: Callable[[], datetime] | None = None,
        interaction_selector: Callable[
            [list[CompanionInteractionType]],
            CompanionInteractionType,
        ] | None = None,
        randomizer: random.Random | None = None,
        quiet_minutes: int = 45,
        max_daily_interactions: int = 6,
    ) -> None:
        self.store = store or CompanionInteractionStore()
        self.learning_cycle = learning_cycle or LearningCycle()
        self.topic_provider = topic_provider or TopicProvider()
        self.commitment_window = commitment_window or SessionWindow(
            start=time(hour=14, minute=45),
            end=time(hour=15, minute=30),
        )
        self.now_provider = now_provider or datetime.now
        self.randomizer = randomizer or random.Random()
        self.interaction_selector = (
            interaction_selector or self.randomizer.choice
        )
        self.quiet_minutes = quiet_minutes
        self.max_daily_interactions = max_daily_interactions

    def select_interaction(
        self,
        current_datetime: datetime | None = None,
    ) -> CompanionInteractionType | None:
        now = current_datetime or self.now_provider()
        state = self.store.load()

        if self._commitment_follow_up_due(state, now):
            return CompanionInteractionType.LEARNING_COMMITMENT

        if self._commitment_should_start(state, now):
            return CompanionInteractionType.LEARNING_COMMITMENT

        if self._should_stay_quiet(state, now):
            return None

        candidates = [
            CompanionInteractionType.SOCIAL,
            CompanionInteractionType.RANDOM_TOPIC,
            CompanionInteractionType.MINI_QUIZ,
            CompanionInteractionType.QUICK_CHALLENGE,
        ]

        if self.learning_cycle.choose_warm_up_topic():
            candidates.append(
                CompanionInteractionType.LEARNING_RECALL
            )

        return self.interaction_selector(candidates)

    def start_interaction(
        self,
        conversation_service: ConversationService,
        interaction_type: CompanionInteractionType | str | None = None,
        current_datetime: datetime | None = None,
    ) -> CompanionInteractionResult | None:
        now = current_datetime or self.now_provider()
        selected_type = (
            self._parse_interaction_type(interaction_type)
            if interaction_type
            else self.select_interaction(now)
        )

        if not selected_type:
            return None

        prompt = self._build_prompt(selected_type, now)
        response = conversation_service.handle_message(
            message=prompt,
            additional_instructions=COMPANION_PERSONALITY_PROMPT,
            save_user_message=False,
            raise_on_error=True,
        )
        self._record_interaction(selected_type, now)

        return CompanionInteractionResult(
            interaction_type=selected_type,
            prompt=prompt,
            response=response,
        )

    def register_user_response(
        self,
        current_datetime: datetime | None = None,
    ) -> CompanionInteractionState:
        now = current_datetime or self.now_provider()
        state = self.store.load()
        state.last_response_at = now.isoformat()
        state.accepted_invites += 1

        if (
            state.learning_commitment
            and state.learning_commitment.date == _day_key(now)
            and state.learning_commitment.status == "pending"
        ):
            state.learning_commitment.status = "completed"
            state.learning_commitment.next_follow_up_at = None

        state.pending_follow_ups = []
        self.store.save(state)

        return state

    def mark_interaction_ignored(
        self,
    ) -> CompanionInteractionState:
        state = self.store.load()
        state.ignored_interactions += 1
        state.ignored_invites += 1
        self.store.save(state)

        return state

    def _record_interaction(
        self,
        interaction_type: CompanionInteractionType,
        now: datetime,
    ) -> None:
        state = self.store.load()
        day_key = _day_key(now)
        state.last_interaction_at = now.isoformat()
        state.daily_interaction_counts[day_key] = (
            state.daily_interaction_counts.get(day_key, 0) + 1
        )

        if interaction_type == (
            CompanionInteractionType.LEARNING_COMMITMENT
        ):
            self._record_learning_commitment(state, now)

        self.store.save(state)

    def _record_learning_commitment(
        self,
        state: CompanionInteractionState,
        now: datetime,
    ) -> None:
        day_key = _day_key(now)
        commitment = state.learning_commitment

        if (
            not commitment
            or commitment.date != day_key
            or commitment.status != "pending"
        ):
            commitment = LearningCommitmentState(date=day_key)
            state.learning_commitment = commitment

        commitment.prompts_sent += 1
        next_delay_index = commitment.prompts_sent - 1

        if next_delay_index < len(COMMITMENT_FOLLOW_UP_DELAYS):
            next_time = now + COMMITMENT_FOLLOW_UP_DELAYS[
                next_delay_index
            ]
            commitment.next_follow_up_at = next_time.isoformat()
            state.pending_follow_ups = [{
                "interaction_type": (
                    CompanionInteractionType.LEARNING_COMMITMENT.value
                ),
                "due_at": commitment.next_follow_up_at,
            }]
            return

        commitment.status = "closed"
        commitment.next_follow_up_at = None
        state.pending_follow_ups = []

    def _build_prompt(
        self,
        interaction_type: CompanionInteractionType,
        now: datetime,
    ) -> str:
        builders = {
            CompanionInteractionType.SOCIAL: (
                self._build_social_prompt
            ),
            CompanionInteractionType.RANDOM_TOPIC: (
                self._build_random_topic_prompt
            ),
            CompanionInteractionType.MINI_QUIZ: (
                self._build_mini_quiz_prompt
            ),
            CompanionInteractionType.LEARNING_RECALL: (
                self._build_learning_recall_prompt
            ),
            CompanionInteractionType.QUICK_CHALLENGE: (
                self._build_quick_challenge_prompt
            ),
            CompanionInteractionType.LEARNING_COMMITMENT: (
                self._build_learning_commitment_prompt
            ),
        }

        return builders[interaction_type](now)

    def _build_social_prompt(self, now: datetime) -> str:
        return (
            "Start a spontaneous companion interaction.\n"
            "Type: SOCIAL\n"
            f"Time: {now.isoformat()}\n"
            "Goal: just socialize naturally. Ask how the day is going, "
            "how the user slept, or make one light comment.\n"
            "Do not make this an explicit lesson, quiz or challenge.\n"
            "Use one familiar playful opening when it fits."
        )

    def _build_random_topic_prompt(self, now: datetime) -> str:
        topic = DailyTopic.from_value(
            self.topic_provider.choose_topic()
        )

        return (
            "Start a spontaneous companion interaction.\n"
            "Type: RANDOM_TOPIC\n"
            f"Time: {now.isoformat()}\n"
            f"Category: {topic.category}\n"
            f"Title: {topic.title}\n"
            f"Short summary: {topic.short_summary}\n"
            "Use the topic as a natural conversation starter. Keep it "
            "short, curious and friendly. Do not read it like news."
        )

    def _build_mini_quiz_prompt(self, now: datetime) -> str:
        state = self.learning_cycle.current_state()
        topic = self.learning_cycle.current_topic()

        return (
            "Start a spontaneous companion interaction.\n"
            "Type: MINI_QUIZ\n"
            f"Time: {now.isoformat()}\n"
            f"Current topic: {topic.name}\n"
            f"Current stage: {state.current_stage.value}\n"
            "Ask one tiny question related to the current learning "
            "topic. Keep it playful and do not turn it into a class."
        )

    def _build_learning_recall_prompt(self, now: datetime) -> str:
        warm_up_topic = self.learning_cycle.choose_warm_up_topic()
        topic = warm_up_topic or self.learning_cycle.current_topic()

        return (
            "Start a spontaneous companion interaction.\n"
            "Type: LEARNING_RECALL\n"
            f"Time: {now.isoformat()}\n"
            f"Review topic: {topic.name}\n"
            "Bring this back as a quick warm-up in a natural situation. "
            "Ask only one easy question."
        )

    def _build_quick_challenge_prompt(self, now: datetime) -> str:
        state = self.learning_cycle.current_state()
        topic = self.learning_cycle.current_topic()

        return (
            "Start a spontaneous companion interaction.\n"
            "Type: QUICK_CHALLENGE\n"
            f"Time: {now.isoformat()}\n"
            f"Current topic: {topic.name}\n"
            f"Current level: {state.current_level.value}\n"
            "Give one quick English challenge: a short translation, a "
            "phrase correction, or a tiny answer prompt."
        )

    def _build_learning_commitment_prompt(
        self,
        now: datetime,
    ) -> str:
        state = self.learning_cycle.current_state()
        topic = self.learning_cycle.current_topic()
        commitment = self.store.load().learning_commitment
        prompt_number = (
            commitment.prompts_sent + 1
            if commitment and commitment.date == _day_key(now)
            else 1
        )

        return (
            "Start a companion learning commitment interaction.\n"
            "Type: LEARNING_COMMITMENT\n"
            f"Time: {now.isoformat()}\n"
            f"Prompt number today: {prompt_number}\n"
            f"Current level: {state.current_level.value}\n"
            f"Current topic: {topic.name}\n"
            f"Current stage: {state.current_stage.value}\n"
            "Invite the user into the main English practice of the day. "
            "Sound familiar and motivating, not like a notification. "
            "Ask for a small yes/no or short response to begin."
        )

    def _commitment_should_start(
        self,
        state: CompanionInteractionState,
        now: datetime,
    ) -> bool:
        commitment = state.learning_commitment

        if not self.commitment_window.contains(now.time()):
            return False

        return (
            not commitment
            or commitment.date != _day_key(now)
        )

    def _commitment_follow_up_due(
        self,
        state: CompanionInteractionState,
        now: datetime,
    ) -> bool:
        commitment = state.learning_commitment

        if (
            not commitment
            or commitment.date != _day_key(now)
            or commitment.status != "pending"
            or not commitment.next_follow_up_at
        ):
            return False

        due_at = _parse_datetime(commitment.next_follow_up_at)

        return due_at is not None and now >= due_at

    def _should_stay_quiet(
        self,
        state: CompanionInteractionState,
        now: datetime,
    ) -> bool:
        day_key = _day_key(now)

        if (
            state.daily_interaction_counts.get(day_key, 0)
            >= self.max_daily_interactions
        ):
            return True

        if not state.last_interaction_at:
            return False

        last_interaction_at = _parse_datetime(
            state.last_interaction_at
        )

        if not last_interaction_at:
            return False

        quiet_until = last_interaction_at + timedelta(
            minutes=self.quiet_minutes
        )

        return now < quiet_until

    def _parse_interaction_type(
        self,
        interaction_type: CompanionInteractionType | str,
    ) -> CompanionInteractionType:
        if isinstance(interaction_type, CompanionInteractionType):
            return interaction_type

        return CompanionInteractionType(
            str(interaction_type).upper()
        )


def _day_key(value: datetime) -> str:
    return value.date().isoformat()


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
