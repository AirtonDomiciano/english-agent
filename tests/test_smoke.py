from app.chat.service import ConversationService
from app.memory.conversation_memory import ConversationMemory
from app.startup.bootstrap import bootstrap_app


class FakeAIClient:
    def generate_response(
        self,
        messages: list[dict],
        instructions: str,
    ) -> str:
        last_message = messages[-1]["content"]

        return f"Fake response for: {last_message}"


def test_conversation_service_returns_response(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
    )

    reply = service.handle_message(
        "Hello, I want to practice English"
    )

    assert reply == (
        "Fake response for: "
        "Hello, I want to practice English"
    )


def test_conversation_service_saves_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
    )

    service.handle_message("Hello")

    history = memory.load()

    assert len(history) == 2
    assert history[0] == {
        "role": "user",
        "content": "Hello",
    }
    assert history[1] == {
        "role": "assistant",
        "content": "Fake response for: Hello",
    }


def test_memory_can_clear_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")
    memory.clear()

    assert memory.load() == []


def test_bootstrap_creates_expected_structure(tmp_path):
    app = bootstrap_app(data_dir=tmp_path)

    assert app["data_dir"].exists()
    assert app["memory_path"].exists()
    assert app["phase"] == "phase-1"