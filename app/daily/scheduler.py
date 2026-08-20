from contextlib import AbstractContextManager, nullcontext
from datetime import datetime
from threading import Event, Thread
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


class DailySchedulerRunner:
    """Keeps the daily scheduler active while the app is running."""

    def __init__(
        self,
        scheduler: DailyScheduler,
        conversation_service: ConversationService,
        on_result: Callable[[DailySessionResult], None],
        poll_interval_seconds: float = 60.0,
        lock: AbstractContextManager | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.conversation_service = conversation_service
        self.on_result = on_result
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.lock = lock or nullcontext()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def run_once(self) -> list[DailySessionResult]:
        with self.lock:
            results = self.scheduler.run_pending(
                self.conversation_service
            )

        for result in results:
            self.on_result(result)

        return results

    def start(self, run_immediately: bool = True) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = Thread(
            target=self._run,
            args=(run_immediately,),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=2)

    def _run(self, run_immediately: bool) -> None:
        if run_immediately:
            self.run_once()

        while not self._stop_event.wait(
            self.poll_interval_seconds
        ):
            self.run_once()
