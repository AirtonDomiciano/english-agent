import json
from pathlib import Path
from typing import Any


class ConversationMemory:
    """Persiste o histórico da conversa em um arquivo JSON."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(
            storage_path or "data/conversation_history.json"
        )

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.storage_path.exists():
            self.clear()

    def load(self) -> list[dict[str, Any]]:
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            history = json.loads(content)

            if not isinstance(history, list):
                return []

            return history
        except (json.JSONDecodeError, OSError):
            return []

    def load_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        history = self.load()

        return history[-limit:]

    def append(self, role: str, content: str) -> None:
        history = self.load()

        history.append({
            "role": role,
            "content": content,
        })

        self.storage_path.write_text(
            json.dumps(
                history,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.storage_path.write_text(
            "[]",
            encoding="utf-8",
        )
