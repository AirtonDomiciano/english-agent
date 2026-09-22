import subprocess
from pathlib import Path
from types import SimpleNamespace

from app.speech.audio import AudioFilePlayer
from app.speech.providers.openai_tts import OpenAISpeechProvider
from app.speech.service import SpeechService


class RecordingAudioPlayer:
    def __init__(self) -> None:
        self.played_paths = []
        self.played_payloads = []
        self.existed_during_play = []

    def play(self, audio_path: Path) -> None:
        path = Path(audio_path)
        self.played_paths.append(path)
        self.existed_during_play.append(path.exists())
        self.played_payloads.append(
            path.read_bytes() if path.exists() else b""
        )


class FailingAudioPlayer:
    def __init__(self) -> None:
        self.played_paths = []

    def play(self, audio_path: Path) -> None:
        self.played_paths.append(Path(audio_path))
        raise RuntimeError("player unavailable")


class FakeSpeechAPI:
    def __init__(
        self,
        content: bytes = b"RIFF-audio",
        error: Exception | None = None,
    ) -> None:
        self.calls = []
        self.content = content
        self.error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)

        if self.error is not None:
            raise self.error

        return SimpleNamespace(content=self.content)


class FakeOpenAIClient:
    def __init__(self, speech_api: FakeSpeechAPI) -> None:
        self.audio = SimpleNamespace(speech=speech_api)


def test_openai_provider_generates_and_plays_speech(tmp_path):
    speech_api = FakeSpeechAPI(content=b"neural-wav")
    player = RecordingAudioPlayer()
    provider = OpenAISpeechProvider(
        client=FakeOpenAIClient(speech_api),
        player=player,
        model="gpt-4o-mini-tts",
        voice="coral",
        audio_dir=tmp_path,
    )

    provider.speak("Hello Airton")

    assert speech_api.calls == [
        {
            "model": "gpt-4o-mini-tts",
            "voice": "coral",
            "input": "Hello Airton",
            "response_format": "wav",
        }
    ]
    assert player.existed_during_play == [True]
    assert player.played_payloads == [b"neural-wav"]
    assert list(tmp_path.glob("*.wav")) == []


def test_openai_provider_cleans_up_temp_file_when_playback_fails(tmp_path):
    player = FailingAudioPlayer()
    provider = OpenAISpeechProvider(
        client=FakeOpenAIClient(FakeSpeechAPI()),
        player=player,
        audio_dir=tmp_path,
    )

    try:
        provider.speak("Cleanup after play error")
    except RuntimeError as error:
        assert str(error) == "player unavailable"

    assert player.played_paths
    assert not player.played_paths[0].exists()
    assert list(tmp_path.glob("*.wav")) == []


def test_openai_generation_failure_does_not_leave_temp_files(tmp_path):
    player = RecordingAudioPlayer()
    provider = OpenAISpeechProvider(
        client=FakeOpenAIClient(
            FakeSpeechAPI(error=RuntimeError("generation unavailable"))
        ),
        player=player,
        audio_dir=tmp_path,
    )

    try:
        provider.speak("Do not keep this file")
    except RuntimeError as error:
        assert str(error) == "generation unavailable"

    assert player.played_paths == []
    assert list(tmp_path.iterdir()) == []


def test_openai_provider_unavailable_without_api_key(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    errors = []
    provider = OpenAISpeechProvider(
        player=RecordingAudioPlayer(),
        audio_dir=tmp_path,
    )
    service = SpeechService(
        provider=provider,
        enabled=True,
        error_handler=errors.append,
    )

    spoken = service.speak("Keep showing the reply")

    assert spoken is False
    assert len(errors) == 1
    assert "OPENAI_API_KEY" in str(errors[0])
    assert list(tmp_path.iterdir()) == []


def test_openai_empty_audio_is_a_generation_failure(tmp_path):
    player = RecordingAudioPlayer()
    provider = OpenAISpeechProvider(
        client=FakeOpenAIClient(FakeSpeechAPI(content=b"")),
        player=player,
        audio_dir=tmp_path,
    )

    try:
        provider.speak("Empty audio")
    except RuntimeError as error:
        assert str(error) == "OpenAI TTS returned empty audio."

    assert player.played_paths == []
    assert list(tmp_path.iterdir()) == []


def test_audio_file_player_uses_default_device_command(
    tmp_path,
    monkeypatch,
):
    played = {}

    def fake_run(command, check, timeout, stdout=None, stderr=None):
        played["command"] = command
        played["check"] = check
        played["timeout"] = timeout
        played["stdout"] = stdout
        played["stderr"] = stderr

    monkeypatch.setattr("app.speech.audio.subprocess.run", fake_run)
    audio_path = tmp_path / "speech.wav"
    audio_path.write_bytes(b"wav")
    player = AudioFilePlayer(
        command=("aplay", "-q"),
        timeout_seconds=12,
    )

    player.play(audio_path)

    assert played["command"] == ["aplay", "-q", str(audio_path)]
    assert "-D" not in played["command"]
    assert played["check"] is True
    assert played["timeout"] == 12
    assert played["stdout"] is subprocess.DEVNULL
    assert played["stderr"] is subprocess.DEVNULL


def test_openai_from_env_reads_voice_and_model(monkeypatch):
    monkeypatch.setenv("ENGLISH_AGENT_TTS_MODEL", "tts-1-hd")
    monkeypatch.setenv("ENGLISH_AGENT_TTS_VOICE", "sage")
    monkeypatch.setenv("ENGLISH_AGENT_TTS_PLAY_COMMAND", "aplay -q")

    provider = OpenAISpeechProvider.from_env()

    assert provider.model == "tts-1-hd"
    assert provider.voice == "sage"
    assert provider.player.command == ("aplay", "-q")
