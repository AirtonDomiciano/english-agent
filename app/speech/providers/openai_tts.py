import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from app.speech.audio import AudioFilePlayer, AudioPlayer


DEFAULT_OPENAI_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENAI_TTS_VOICE = "coral"
DEFAULT_OPENAI_TTS_FORMAT = "wav"
DEFAULT_OPENAI_TTS_TIMEOUT_SECONDS = 30


class OpenAISpeechProvider:
    """Neural text-to-speech provider backed by OpenAI TTS."""

    def __init__(
        self,
        client=None,
        player: AudioPlayer | None = None,
        model: str = DEFAULT_OPENAI_TTS_MODEL,
        voice: str = DEFAULT_OPENAI_TTS_VOICE,
        response_format: str = DEFAULT_OPENAI_TTS_FORMAT,
        client_factory=None,
        audio_dir: Path | None = None,
    ) -> None:
        self.client = client
        self.player = player or AudioFilePlayer()
        self.model = model
        self.voice = voice
        self.response_format = response_format
        self.client_factory = client_factory or _openai_client_from_env
        self.audio_dir = audio_dir

    @classmethod
    def from_env(cls) -> "OpenAISpeechProvider":
        audio_dir_value = os.getenv("ENGLISH_AGENT_TTS_AUDIO_DIR")
        audio_dir = Path(audio_dir_value) if audio_dir_value else None

        return cls(
            player=AudioFilePlayer.from_env(),
            model=os.getenv(
                "ENGLISH_AGENT_TTS_MODEL",
                DEFAULT_OPENAI_TTS_MODEL,
            ),
            voice=os.getenv(
                "ENGLISH_AGENT_TTS_VOICE",
                DEFAULT_OPENAI_TTS_VOICE,
            ),
            audio_dir=audio_dir,
        )

    def speak(self, text: str) -> None:
        audio_path = None

        try:
            audio_path = self._write_speech_file(text)
            self.player.play(audio_path)
        finally:
            if audio_path is not None:
                Path(audio_path).unlink(missing_ok=True)

    def _write_speech_file(self, text: str) -> Path:
        if self.audio_dir:
            self.audio_dir.mkdir(parents=True, exist_ok=True)

        audio_bytes = self._generate_audio(text)
        audio_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f".{self.response_format}",
            dir=self.audio_dir,
        )
        audio_path = Path(audio_file.name)
        audio_file.close()

        try:
            audio_path.write_bytes(audio_bytes)

            return audio_path
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise

    def _generate_audio(self, text: str) -> bytes:
        client = self._client()
        response = client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
            response_format=self.response_format,
        )
        audio_bytes = getattr(response, "content", None)

        if not audio_bytes:
            raise RuntimeError("OpenAI TTS returned empty audio.")

        return bytes(audio_bytes)

    def _client(self):
        if self.client is None:
            self.client = self.client_factory()

        return self.client


def _openai_client_from_env():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY não encontrada no arquivo .env."
        )

    return OpenAI(
        api_key=api_key,
        timeout=_env_float(
            "ENGLISH_AGENT_TTS_TIMEOUT",
            DEFAULT_OPENAI_TTS_TIMEOUT_SECONDS,
        ),
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
