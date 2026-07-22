import json
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_PERSONAL_CONTEXT: dict[str, Any] = {
    "name": "Airton",
    "english_level": "B1",
    "primary_goal": (
        "Improve English through natural daily conversations, "
        "especially speaking, vocabulary and writing."
    ),
    "interests": [
        "software development",
        "artificial intelligence",
        "personal projects",
        "gym",
        "violin",
        "games",
    ],
    "professional_context": {
        "role": "Full-stack developer",
        "main_technologies": [
            "Angular",
            "NestJS",
            "GraphQL",
            "SQL Server",
            "Python",
        ],
    },
    "learning_preferences": {
        "correction_style": "gentle",
        "preferred_language": "English",
        "explanation_language": "Portuguese when necessary",
        "conversation_topics": [
            "software development",
            "daily routine",
            "gym",
            "violin",
            "games",
        ],
    },
}


class PersonalContext:
    """Persiste informações permanentes sobre o usuário."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
    ) -> None:
        self.storage_path = Path(
            storage_path or "data/personal_context.json"
        )

        self.storage_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.storage_path.exists():
            self.save(DEFAULT_PERSONAL_CONTEXT)

    def load(self) -> dict[str, Any]:
        try:
            content = self.storage_path.read_text(
                encoding="utf-8",
            )
            context = json.loads(content)

            if not isinstance(context, dict):
                return deepcopy(DEFAULT_PERSONAL_CONTEXT)

            return context
        except (json.JSONDecodeError, OSError):
            return deepcopy(DEFAULT_PERSONAL_CONTEXT)

    def save(self, context: dict[str, Any]) -> None:
        self.storage_path.write_text(
            json.dumps(
                context,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def update(self, values: dict[str, Any]) -> None:
        context = self.load()
        context.update(values)
        self.save(context)

    def to_prompt(self) -> str:
        context = self.load()

        return (
            "Personal context about the user:\n"
            f"{json.dumps(context, indent=2, ensure_ascii=False)}"
        )
