from app.context.personal_context import PersonalContext


def test_personal_context_creates_default_file(
    personal_context_factory,
):
    context = personal_context_factory()

    saved_context = context.load()

    assert saved_context["name"] == "Airton"
    assert saved_context["english_level"] == "B1"
    assert saved_context["learning_mode"] == "DAILY"
    assert saved_context["learning_preferences"] == {
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
    }


def test_personal_context_can_be_updated(personal_context_factory):
    context = personal_context_factory()

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


def test_personal_context_adds_missing_default_values(tmp_path):
    storage_path = tmp_path / "personal_context.json"
    storage_path.write_text(
        '{"name": "Airton"}',
        encoding="utf-8",
    )

    context = PersonalContext(storage_path=storage_path)
    saved_context = context.load()

    assert saved_context["name"] == "Airton"
    assert saved_context["learning_mode"] == "DAILY"
    assert saved_context["english_level"] == "B1"
