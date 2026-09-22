import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol


DEFAULT_ARECORD_COMMAND = "arecord"
DEFAULT_APLAY_COMMAND = "aplay -q"
DEFAULT_STT_DURATION_SECONDS = 5
DEFAULT_STT_SAMPLE_RATE = 16000
DEFAULT_STT_CHANNELS = 1
DEFAULT_TTS_PLAY_TIMEOUT_SECONDS = 30


class AudioRecorder(Protocol):
    def record(self) -> Path | None:
        """Capture one audio sample and return its local file path."""


class ArecordMicrophoneRecorder:
    """Debian-friendly microphone recorder using arecord."""

    def __init__(
        self,
        command: tuple[str, ...] | None = None,
        duration_seconds: int = DEFAULT_STT_DURATION_SECONDS,
        sample_rate: int = DEFAULT_STT_SAMPLE_RATE,
        channels: int = DEFAULT_STT_CHANNELS,
        audio_dir: Path | None = None,
    ) -> None:
        self.command = command or (DEFAULT_ARECORD_COMMAND,)
        self.duration_seconds = max(1, duration_seconds)
        self.sample_rate = max(8000, sample_rate)
        self.channels = max(1, channels)
        self.audio_dir = audio_dir

    @classmethod
    def from_env(cls) -> "ArecordMicrophoneRecorder":
        command = tuple(
            shlex.split(
                os.getenv(
                    "ENGLISH_AGENT_STT_RECORD_COMMAND",
                    DEFAULT_ARECORD_COMMAND,
                )
            )
        )
        audio_dir_value = os.getenv("ENGLISH_AGENT_STT_AUDIO_DIR")
        audio_dir = Path(audio_dir_value) if audio_dir_value else None

        return cls(
            command=command,
            duration_seconds=_env_int(
                "ENGLISH_AGENT_STT_DURATION_SECONDS",
                DEFAULT_STT_DURATION_SECONDS,
            ),
            sample_rate=_env_int(
                "ENGLISH_AGENT_STT_SAMPLE_RATE",
                DEFAULT_STT_SAMPLE_RATE,
            ),
            channels=_env_int(
                "ENGLISH_AGENT_STT_CHANNELS",
                DEFAULT_STT_CHANNELS,
            ),
            audio_dir=audio_dir,
        )

    def record(self) -> Path:
        if self.audio_dir:
            self.audio_dir.mkdir(parents=True, exist_ok=True)
        audio_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".wav",
            dir=self.audio_dir,
        )
        audio_path = Path(audio_file.name)
        audio_file.close()

        try:
            subprocess.run(
                [
                    *self.command,
                    "-q",
                    "-f",
                    "S16_LE",
                    "-r",
                    str(self.sample_rate),
                    "-c",
                    str(self.channels),
                    "-d",
                    str(self.duration_seconds),
                    str(audio_path),
                ],
                check=True,
                timeout=self.duration_seconds + 5,
            )

            return audio_path
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise


class NullAudioRecorder:
    def record(self) -> Path | None:
        return None


class AudioPlayer(Protocol):
    def play(self, audio_path: Path) -> None:
        """Play a local audio file on the default output device."""


class AudioFilePlayer:
    """Plays generated speech files without selecting an output device."""

    def __init__(
        self,
        command: tuple[str, ...] | None = None,
        timeout_seconds: int = DEFAULT_TTS_PLAY_TIMEOUT_SECONDS,
    ) -> None:
        self.command = command or (DEFAULT_APLAY_COMMAND,)
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "AudioFilePlayer":
        command = tuple(
            shlex.split(
                os.getenv(
                    "ENGLISH_AGENT_TTS_PLAY_COMMAND",
                    DEFAULT_APLAY_COMMAND,
                )
            )
        )

        return cls(
            command=command,
            timeout_seconds=_env_int(
                "ENGLISH_AGENT_TTS_TIMEOUT",
                DEFAULT_TTS_PLAY_TIMEOUT_SECONDS,
            ),
        )

    def play(self, audio_path: Path) -> None:
        subprocess.run(
            [
                *self.command,
                str(audio_path),
            ],
            check=True,
            timeout=self.timeout_seconds,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
