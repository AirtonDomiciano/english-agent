from pathlib import Path

from app.memory.conversation_memory import ConversationMemory


def bootstrap_app(data_dir: str | Path | None = None) -> dict[str, object]:
    """Create the initial application structure for phase 1."""
    root = Path(data_dir or "data")
    root.mkdir(parents=True, exist_ok=True)

    memory_path = root / "conversation_history.json"
    if not memory_path.exists():
        memory_path.write_text("[]", encoding="utf-8")

    ConversationMemory(storage_path=memory_path)

    return {
        "data_dir": root,
        "memory_path": memory_path,
        "phase": "phase-1",
    }
