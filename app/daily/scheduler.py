from datetime import datetime
from typing import Callable

from app.chat.service import ConversationService
from app.daily.sessions import (
    DailySession,
    DailySessionResult,
    DailySessionStore,
    create_default_daily_sessions,
)
from app.daily.topics import TopicProvider


class DailyScheduler:
    """Runs configured daily sessions when their windows are active."""

    def __init__(
        self,
        sessions: tuple[
            DailySession,
            ...,
        ] | None = None,
        store: DailySessionStore | None = None,
        topic_provider: TopicProvider | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self.sessions = sessions or create_default_daily_sessions()
        self.store = store or DailySessionStore()
        self.topic_provider = topic_provider or TopicProvider()
        self.now_provider = now_provider or datetime.now

    def run_pending(
        self,
        conversation_service: ConversationService,
        current_datetime: datetime | None = None,
    ) -> list[DailySessionResult]:
        now = current_datetime or self.now_provider()
        results: list[DailySessionResult] = []

        for session in self.sessions:
            result = session.start(
                conversation_service=conversation_service,
                topic_provider=self.topic_provider,
                store=self.store,
                current_datetime=now,
            )

            if result:
                results.append(result)

        return results
