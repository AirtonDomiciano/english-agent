import os
import shlex
import subprocess


DEFAULT_ESPEAK_COMMAND = "espeak"
DEFAULT_ESPEAK_TIMEOUT_SECONDS = 30


class EspeakSpeechProvider:
    """Local Debian-friendly TTS provider using espeak."""

    def __init__(
        self,
        command: tuple[str, ...] | None = None,
        timeout_seconds: int = DEFAULT_ESPEAK_TIMEOUT_SECONDS,
    ) -> None:
        self.command = command or (DEFAULT_ESPEAK_COMMAND,)
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "EspeakSpeechProvider":
        command = tuple(
            shlex.split(
                os.getenv(
                    "ENGLISH_AGENT_TTS_COMMAND",
                    DEFAULT_ESPEAK_COMMAND,
                )
            )
        )
        timeout_seconds = _env_int(
            "ENGLISH_AGENT_TTS_TIMEOUT",
            DEFAULT_ESPEAK_TIMEOUT_SECONDS,
        )

        return cls(
            command=command,
            timeout_seconds=timeout_seconds,
        )

    def speak(self, text: str) -> None:
        subprocess.run(
            [
                *self.command,
                text,
            ],
            check=True,
            timeout=self.timeout_seconds,
        )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
