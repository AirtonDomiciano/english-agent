import os
import shlex
import subprocess
from pathlib import Path
from threading import Event

from app.voice.wake_word import (
    DEFAULT_WAKE_WORD,
    DEFAULT_WAKE_WORD_THRESHOLD,
    AudioFrameSource,
)


DEFAULT_WAKE_WORD_RECORD_COMMAND = "arecord"
DEFAULT_WAKE_WORD_SAMPLE_RATE = 16000
DEFAULT_WAKE_WORD_CHANNELS = 1
DEFAULT_WAKE_WORD_FRAME_SAMPLES = 1280
PRETRAINED_WAKE_WORDS = {
    "alexa": "alexa",
    "hey jarvis": "hey_jarvis",
    "hey_jarvis": "hey_jarvis",
    "hey mycroft": "hey_mycroft",
    "hey_mycroft": "hey_mycroft",
    "hey rhasspy": "hey_rhasspy",
    "hey_rhasspy": "hey_rhasspy",
}


class ArecordFrameSource:
    """Streams raw PCM from arecord without selecting an output device."""

    def __init__(
        self,
        command: tuple[str, ...] | None = None,
        sample_rate: int = DEFAULT_WAKE_WORD_SAMPLE_RATE,
        channels: int = DEFAULT_WAKE_WORD_CHANNELS,
    ) -> None:
        self.command = command or (DEFAULT_WAKE_WORD_RECORD_COMMAND,)
        self.sample_rate = sample_rate
        self.channels = channels
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        self.stop()
        self.process = subprocess.Popen(
            [
                *self.command,
                "-q",
                "-f",
                "S16_LE",
                "-r",
                str(self.sample_rate),
                "-c",
                str(self.channels),
                "-t",
                "raw",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def read(self, nbytes: int) -> bytes | None:
        if self.process is None or self.process.stdout is None:
            return None

        data = self.process.stdout.read(nbytes)

        if not data:
            return None

        return data

    def stop(self) -> None:
        process = self.process
        self.process = None

        if process is None:
            return

        process.terminate()

        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1)


class OpenWakeWordDetector:
    """Local wake-word detector backed by openWakeWord ONNX models."""

    def __init__(
        self,
        wake_word: str = DEFAULT_WAKE_WORD,
        threshold: float = DEFAULT_WAKE_WORD_THRESHOLD,
        model_name: str | None = None,
        frame_source: AudioFrameSource | None = None,
        predictor=None,
        model_factory=None,
        frame_samples: int = DEFAULT_WAKE_WORD_FRAME_SAMPLES,
    ) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.model_name = model_name or _resolve_wake_word_model(wake_word)
        self.frame_source = frame_source or ArecordFrameSource()
        self.predictor = predictor
        self.model_factory = model_factory or _openwakeword_model_from_env
        self.frame_samples = frame_samples
        self.frame_bytes = frame_samples * 2
        self._model = None

    @classmethod
    def from_env(
        cls,
        wake_word: str = DEFAULT_WAKE_WORD,
    ) -> "OpenWakeWordDetector":
        model_path = os.getenv("ENGLISH_AGENT_WAKE_WORD_MODEL", "").strip()
        command = tuple(
            shlex.split(
                os.getenv(
                    "ENGLISH_AGENT_WAKE_WORD_RECORD_COMMAND",
                    DEFAULT_WAKE_WORD_RECORD_COMMAND,
                )
            )
        )

        return cls(
            wake_word=wake_word,
            threshold=_env_float(
                "ENGLISH_AGENT_WAKE_WORD_THRESHOLD",
                DEFAULT_WAKE_WORD_THRESHOLD,
            ),
            model_name=_resolve_wake_word_model(wake_word, model_path),
            frame_source=ArecordFrameSource(command=command),
        )

    def wait(self, stop_event: Event) -> bool:
        try:
            self.frame_source.start()

            while not stop_event.is_set():
                raw = self.frame_source.read(self.frame_bytes)

                if raw is None or len(raw) < self.frame_bytes:
                    if stop_event.wait(0.01):
                        return False

                    continue

                if self._is_detected(self._predict(raw)):
                    return True

            return False
        finally:
            self.frame_source.stop()

    def close(self) -> None:
        self.frame_source.stop()

    def _predict(self, raw: bytes):
        if self.predictor is not None:
            return self.predictor(raw)

        import numpy as np

        frame = np.frombuffer(raw, dtype=np.int16)
        model = self._get_model()

        return model.predict(frame)

    def _get_model(self):
        if self._model is None:
            self._model = self.model_factory(self.model_name)

        return self._model

    def _is_detected(self, prediction) -> bool:
        if isinstance(prediction, dict):
            return any(
                float(score) >= self.threshold
                for score in prediction.values()
            )

        return float(prediction) >= self.threshold


def _resolve_wake_word_model(
    wake_word: str,
    model_path: str = "",
) -> str:
    if model_path:
        resolved_path = Path(model_path)

        if not resolved_path.exists():
            raise RuntimeError(
                "Wake word model not found: "
                f"{model_path}. Train an openWakeWord ONNX model "
                "for this phrase and set "
                "ENGLISH_AGENT_WAKE_WORD_MODEL."
            )

        return str(resolved_path)

    if Path(wake_word).exists():
        return wake_word

    normalized = " ".join(wake_word.strip().lower().split())
    pretrained = PRETRAINED_WAKE_WORDS.get(normalized)

    if pretrained:
        return pretrained

    raise RuntimeError(
        f'openWakeWord has no pretrained model for "{wake_word}". '
        "A custom phrase needs a trained ONNX or TFLite model. "
        "Set ENGLISH_AGENT_WAKE_WORD_MODEL to that file path."
    )


def _openwakeword_model_from_env(model_name: str):
    import openwakeword
    from openwakeword.model import Model

    if Path(model_name).exists():
        return Model(
            wakeword_models=[model_name],
            inference_framework="onnx",
        )

    openwakeword.utils.download_models(model_names=[model_name])

    return Model(
        wakeword_models=[model_name],
        inference_framework="onnx",
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
