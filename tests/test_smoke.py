import json
import tempfile
from pathlib import Path

from app.chat.service import ConversationService
from app.memory.conversation_memory import ConversationMemory
from app.startup.bootstrap import bootstrap_app


def test_conversation_service_returns_response():
    service = ConversationService()
    reply = service.handle_message("Hello, I want to practice English")

    assert isinstance(reply, str)
    assert len(reply) > 0


def test_memory_can_persist_history(tmp_path):
    memory = ConversationMemory(storage_path=tmp_path / "history.json")
    memory.append({"role": "user", "content": "Hello"})
    memory.append({"role": "assistant", "content": "Hi"})

    saved = memory.load()
    assert len(saved) == 2
    assert saved[0]["content"] == "Hello"


def test_bootstrap_creates_expected_structure(tmp_path):
    app = bootstrap_app(data_dir=tmp_path)

    assert app["data_dir"].exists()
    assert app["memory_path"].exists()
    assert app["phase"] == "phase-1"
