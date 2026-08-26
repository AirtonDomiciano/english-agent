from app.memory.conversation_memory import ConversationMemory
from app.startup.bootstrap import bootstrap_app


def test_memory_can_clear_history(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")
    memory.clear()

    assert memory.load() == []


def test_memory_load_recent_returns_last_messages_in_order(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    for index in range(5):
        memory.append("user", f"Message {index}")

    recent_messages = memory.load_recent(limit=3)

    assert recent_messages == [
        {
            "role": "user",
            "content": "Message 2",
        },
        {
            "role": "user",
            "content": "Message 3",
        },
        {
            "role": "user",
            "content": "Message 4",
        },
    ]
    assert len(memory.load()) == 5


def test_memory_load_recent_returns_empty_for_zero_limit(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")

    assert memory.load_recent(limit=0) == []
    assert len(memory.load()) == 1


def test_memory_load_recent_returns_empty_for_negative_limit(tmp_path):
    memory = ConversationMemory(
        storage_path=tmp_path / "history.json"
    )

    memory.append("user", "Hello")

    assert memory.load_recent(limit=-1) == []
    assert len(memory.load()) == 1


def test_bootstrap_creates_expected_structure(tmp_path):
    app = bootstrap_app(data_dir=tmp_path)

    assert app["data_dir"].exists()
    assert app["memory_path"].exists()
    assert app["phase"] == "phase-1"
