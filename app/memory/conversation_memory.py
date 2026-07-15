import json
from pathlib import Path
from typing import Any


class ConversationMemory:
    """Persist conversation history as JSON."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path or "data/conversation_history.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.write_text("[]", encoding="utf-8")

    def load(self) -> list[dict[str, Any]]:
        return json.loads(self.storage_path.read_text(encoding="utf-8"))

    def append(self, entry: dict[str, Any]) -> None:
        history = self.load()
        history.append(entry)
        self.storage_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
