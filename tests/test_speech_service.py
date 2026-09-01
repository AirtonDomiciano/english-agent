import time
from io import StringIO
from threading import Thread

from app.companion import (
    CompanionInteractionEngine,
    CompanionInteractionStore,
    CompanionInteractionType,
)
from app.daily import TopicProvider
from app.presentation import AgentOutputPresenter
from app.speech import SpeechService


class RecordingSpeechProvider:
    def __init__(self) -> None:
        self.spoken_texts = []

    def speak(self, text: str) -> None:
        self.spoken_texts.append(text)


class FailingSpeechProvider:
    def speak(self, text: str) -> None:
        raise RuntimeError("speaker unavailable")


class SlowSpeechProvider:
    def __init__(self) -> None:
        self.active_calls = 0
        self.max_active_calls = 0
        self.spoken_texts = []

    def speak(self, text: str) -> None:
        self.active_calls += 1
        self.max_active_calls = max(
            self.max_active_calls,
            self.active_calls,
        )
        time.sleep(0.01)
        self.spoken_texts.append(text)
        self.active_calls -= 1


def test_tts_enabled_speaks_response(monkeypatch):
    provider = RecordingSpeechProvider()
    monkeypatch.setenv("ENGLISH_AGENT_TTS_ENABLED", "true")

    service = SpeechService.from_env(provider=provider)

    spoken = service.speak("Hey Airton!")

    assert spoken is True
    assert provider.spoken_texts == ["Hey Airton!"]


def test_tts_disabled_does_not_speak(monkeypatch):
    provider = RecordingSpeechProvider()
    monkeypatch.setenv("ENGLISH_AGENT_TTS_ENABLED", "false")

    service = SpeechService.from_env(provider=provider)

    spoken = service.speak("Quiet mode")

    assert spoken is False
    assert provider.spoken_texts == []


def test_tts_provider_failure_does_not_break_conversation():
    errors = []
    service = SpeechService(
        provider=FailingSpeechProvider(),
        enabled=True,
        error_handler=errors.append,
    )

    spoken = service.speak("Still show this text")

    assert spoken is False
    assert len(errors) == 1
    assert str(errors[0]) == "speaker unavailable"


def test_multiple_responses_are_not_spoken_simultaneously():
    provider = SlowSpeechProvider()
    service = SpeechService(
        provider=provider,
        enabled=True,
    )
    threads = [
        Thread(target=service.speak, args=(f"Message {index}",))
        for index in range(5)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert provider.max_active_calls == 1
    assert len(provider.spoken_texts) == 5


def test_presenter_speaks_manual_response(
    conversation_service_factory,
    fake_ai_client,
):
    provider = RecordingSpeechProvider()
    speech_service = SpeechService(
        provider=provider,
        enabled=True,
    )
    output = StringIO()
    presenter = AgentOutputPresenter(
        speech_service=speech_service,
        output=output,
    )
    conversation = conversation_service_factory(
        ai_client=fake_ai_client
    )

    response = conversation.handle_message("Manual hello")
    presenter.show_agent_response(response)

    assert "Agent: Fake response for: Manual hello" in (
        output.getvalue()
    )
    assert provider.spoken_texts == [
        "Fake response for: Manual hello"
    ]


def test_presenter_speaks_companion_interaction(
    tmp_path,
    conversation_service_factory,
    learning_cycle_factory,
):
    provider = RecordingSpeechProvider()
    presenter = AgentOutputPresenter(
        speech_service=SpeechService(
            provider=provider,
            enabled=True,
        ),
        output=StringIO(),
    )
    engine = CompanionInteractionEngine(
        store=CompanionInteractionStore(
            storage_path=tmp_path / "companion_state.json"
        ),
        learning_cycle=learning_cycle_factory(),
        topic_provider=TopicProvider(topics=("technology",)),
    )
    conversation = conversation_service_factory()

    result = engine.start_interaction(
        conversation_service=conversation,
        interaction_type=CompanionInteractionType.SOCIAL,
    )
    presenter.show_agent_response(result.response)

    assert provider.spoken_texts == ["Fake response"]
