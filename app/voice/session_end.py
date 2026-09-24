import re


VOICE_SESSION_END_PHRASES = (
    "bye",
    "goodbye",
    "see you later",
    "thats all",
    "that is all",
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")


def is_voice_session_end(text: str) -> bool:
    normalized = _normalize(text)

    if not normalized:
        return False

    return any(
        normalized == phrase or normalized.startswith(f"{phrase} ")
        for phrase in VOICE_SESSION_END_PHRASES
    )


def _normalize(text: str) -> str:
    normalized = _NON_ALNUM_RE.sub(
        " ",
        text.casefold().replace("'", "").replace("’", ""),
    )

    return " ".join(normalized.split())
