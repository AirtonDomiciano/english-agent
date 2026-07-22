from app.context.personal_context import PersonalContext
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


class InspectableFakeAIClient:
    def __init__(self) -> None:
        self.instructions = ""

    def generate_response(
        self,
        messages: list[dict],
        instructions: str,
    ) -> str:
        self.instructions = instructions

        return "Fake response"


def create_personal_context(tmp_path):
    return PersonalContext(
        storage_path=tmp_path / "personal_context.json"
    )


def test_conversation_service_returns_response(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
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
    personal_context = create_personal_context(tmp_path)

    service = ConversationService(
        ai_client=FakeAIClient(),
        memory=memory,
        personal_context=personal_context,
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


def test_personal_context_creates_default_file(tmp_path):
    context = create_personal_context(tmp_path)

    saved_context = context.load()

    assert saved_context["name"] == "Airton"
    assert saved_context["english_level"] == "B1"


def test_personal_context_can_be_updated(tmp_path):
    context = create_personal_context(tmp_path)

    context.update({
        "english_level": "B2",
    })

    saved_context = context.load()

    assert saved_context["english_level"] == "B2"


def test_personal_context_handles_invalid_json(tmp_path):
    storage_path = tmp_path / "personal_context.json"
    storage_path.write_text("{invalid", encoding="utf-8")

    context = PersonalContext(storage_path=storage_path)

    assert context.load()["name"] == "Airton"


def test_personal_context_is_added_to_instructions(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )
    personal_context = create_personal_context(tmp_path)
    ai_client = InspectableFakeAIClient()

    service = ConversationService(
        ai_client=ai_client,
        memory=memory,
        personal_context=personal_context,
    )

    service.handle_message("Hello")

    assert "Airton" in ai_client.instructions
    assert '"english_level": "B1"' in ai_client.instructions


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
