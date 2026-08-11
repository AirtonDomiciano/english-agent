import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

from app.chat.service import ConversationService
from app.daily.companion_prompt import COMPANION_PERSONALITY_PROMPT
from app.daily.topics import TopicProvider


@dataclass(frozen=True)
class SessionWindow:
    start: time
    end: time

    def contains(self, current_time: time) -> bool:
        return self.start <= current_time <= self.end


@dataclass(frozen=True)
class DailySessionResult:
    session_id: str
    topic: str
    response: str


class DailySessionStore:
    """Persists only which sessions were triggered on each day."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
    ) -> None:
        self.storage_path = Path(
            storage_path or "data/daily_sessions.json"
        )
        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self.storage_path.write_text(
                "{}",
                encoding="utf-8",
            )

    def load(self) -> dict[str, list[str]]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8",
            )
            records = json.loads(content)

            if not isinstance(records, dict):
                return {}

            return {
                day: sessions
                for day, sessions in records.items()
                if isinstance(day, str)
                and isinstance(sessions, list)
            }
        except (json.JSONDecodeError, OSError):
            return {}

    def was_triggered(
        self,
        session_id: str,
        current_date: date,
    ) -> bool:
        records = self.load()
        sessions = records.get(current_date.isoformat(), [])

        return session_id in sessions

    def mark_triggered(
        self,
        session_id: str,
        current_date: date,
    ) -> None:
        records = self.load()
        day_key = current_date.isoformat()
        sessions = records.setdefault(day_key, [])

        if session_id not in sessions:
            sessions.append(session_id)

        self.storage_path.write_text(
            json.dumps(
                records,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class DailySession:
    session_id: str
    window: SessionWindow

    def should_trigger(
        self,
        current_datetime: datetime,
        store: DailySessionStore,
    ) -> bool:
        if not self.window.contains(current_datetime.time()):
            return False

        return not store.was_triggered(
            session_id=self.session_id,
            current_date=current_datetime.date(),
        )

    def start(
        self,
        conversation_service: ConversationService,
        topic_provider: TopicProvider,
        store: DailySessionStore,
        current_datetime: datetime,
    ) -> DailySessionResult | None:
        if not self.should_trigger(
            current_datetime=current_datetime,
            store=store,
        ):
            return None

        topic = topic_provider.choose_topic()
        response = conversation_service.handle_message(
            message=self._build_start_message(topic),
            additional_instructions=COMPANION_PERSONALITY_PROMPT,
            save_user_message=False,
        )

        store.mark_triggered(
            session_id=self.session_id,
            current_date=current_datetime.date(),
        )

        return DailySessionResult(
            session_id=self.session_id,
            topic=topic,
            response=response,
        )

    def _build_start_message(self, topic: str) -> str:
        return (
            "Start a daily companion conversation now.\n"
            f"Session: {self.session_id}\n"
            f"Topic: {topic}\n"
            "Open with one short, natural message in English. "
            "Sound like a friendly companion who remembered something "
            "interesting, not like a teacher starting a class. "
            "Invite the user to answer with one question."
        )


def create_default_daily_sessions() -> tuple[DailySession, ...]:
    return (
        DailySession(
            session_id="morning",
            window=SessionWindow(
                start=time(hour=8, minute=30),
                end=time(hour=9, minute=0),
            ),
        ),
        DailySession(
            session_id="afternoon",
            window=SessionWindow(
                start=time(hour=14, minute=0),
                end=time(hour=14, minute=30),
            ),
        ),
    )
