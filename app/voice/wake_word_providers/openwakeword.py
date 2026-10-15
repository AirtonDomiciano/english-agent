import os
import shlex
import subprocess
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable, TextIO

from app.voice.wake_word import (
    DEFAULT_WAKE_WORD,
    DEFAULT_WAKE_WORD_THRESHOLD,
    AudioFrameSource,
)


DEFAULT_WAKE_WORD_RECORD_COMMAND = "arecord"
DEFAULT_WAKE_WORD_SAMPLE_RATE = 16000
DEFAULT_WAKE_WORD_CHANNELS = 1
DEFAULT_WAKE_WORD_FRAME_SAMPLES = 1280
DEFAULT_WAKE_WORD_COOLDOWN_SECONDS = 2.0
DEFAULT_WAKE_WORD_SCORE_PRINT_THRESHOLD = 0.2
DEFAULT_WAKE_WORD_MODEL = "models/hey_pran.onnx"
MELSPECTROGRAM_MODEL = "models/melspectrogram.onnx"
EMBEDDING_MODEL = "models/embedding_model.onnx"
PRETRAINED_WAKE_WORDS = {
    "alexa": "alexa",
    "hey jarvis": "hey_jarvis",
    "hey_jarvis": "hey_jarvis",
    "hey mycroft": "hey_mycroft",
    "hey_mycroft": "hey_mycroft",
    "hey rhasspy": "hey_rhasspy",
    "hey_rhasspy": "hey_rhasspy",
}
BUNDLED_WAKE_WORDS = {
    "hey pran": DEFAULT_WAKE_WORD_MODEL,
    "hey_pran": DEFAULT_WAKE_WORD_MODEL,
    "pran": DEFAULT_WAKE_WORD_MODEL,
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
        cooldown_seconds: float = DEFAULT_WAKE_WORD_COOLDOWN_SECONDS,
        debug: bool = False,
        pause_check: Callable[[], bool] | None = None,
        clock: Callable[[], float] | None = None,
        output: TextIO | None = None,
        score_print_threshold: float = (
            DEFAULT_WAKE_WORD_SCORE_PRINT_THRESHOLD
        ),
    ) -> None:
        self.wake_word = wake_word
        self.threshold = threshold
        self.model_name = model_name or _resolve_wake_word_model(wake_word)
        self.frame_source = frame_source or ArecordFrameSource()
        self.predictor = predictor
        self.model_factory = model_factory or _openwakeword_model_from_env
        self.frame_samples = frame_samples
        self.frame_bytes = frame_samples * 2
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.debug = debug
        self.pause_check = pause_check
        self._clock = clock or monotonic
        self.output = output
        self.score_print_threshold = score_print_threshold
        self._model = None
        self._latched = False
        self._last_detection_at = -self.cooldown_seconds
        self._last_printed_score: float | None = None
        self._last_score_print_at = 0.0

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
            cooldown_seconds=_env_float(
                "ENGLISH_AGENT_WAKE_WORD_COOLDOWN_SECONDS",
                DEFAULT_WAKE_WORD_COOLDOWN_SECONDS,
            ),
            debug=_env_flag("ENGLISH_AGENT_WAKE_WORD_DEBUG"),
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

                if self.pause_check and self.pause_check():
                    self._latched = True
                    continue

                score = peak_score(self._predict(raw))
                self._maybe_print_score(score)

                if self._accept_detection(score):
                    return True

            return False
        finally:
            self.frame_source.stop()

    def close(self) -> None:
        self.frame_source.stop()

    def _accept_detection(self, score: float) -> bool:
        if score < self.threshold:
            self._latched = False
            return False

        now = self._clock()
        cooled_down = now - self._last_detection_at >= self.cooldown_seconds

        if self._latched or not cooled_down:
            return False

        self._latched = True
        self._last_detection_at = now
        return True

    def _maybe_print_score(self, score: float) -> None:
        if not self.debug or not self._should_print_score(score):
            return

        now = self._clock()
        self._last_printed_score = score
        self._last_score_print_at = now
        print(f"Wake word score={score:.2f}", file=self.output, flush=True)

    def _should_print_score(self, score: float) -> bool:
        if score < self.score_print_threshold:
            return False

        if self._last_printed_score is None:
            return True

        if abs(score - self._last_printed_score) >= 0.1:
            return True

        return self._clock() - self._last_score_print_at >= 0.5

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


def peak_score(prediction) -> float:
    if isinstance(prediction, dict):
        if not prediction:
            return 0.0

        return max(float(score) for score in prediction.values())

    return float(prediction)


def _project_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        if (parent / "main.py").exists() and (parent / "app").is_dir():
            return parent

    return current.parents[3]


def _resolve_repo_path(path: str) -> Path:
    candidate = Path(path).expanduser()

    if not candidate.is_absolute():
        candidate = _project_root() / candidate

    return candidate.resolve()


def _resolve_wake_word_model(
    wake_word: str,
    model_path: str = "",
) -> str:
    if model_path:
        resolved_path = _resolve_repo_path(model_path)

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
    bundled = BUNDLED_WAKE_WORDS.get(normalized)

    if bundled:
        bundled_path = _resolve_repo_path(bundled)

        if bundled_path.exists():
            return str(bundled_path)

    pretrained = PRETRAINED_WAKE_WORDS.get(normalized)

    if pretrained:
        return pretrained

    raise RuntimeError(
        f'openWakeWord has no pretrained model for "{wake_word}". '
        "A custom phrase needs a trained ONNX or TFLite model. "
        "Set ENGLISH_AGENT_WAKE_WORD_MODEL to that file path."
    )


def _ensure_feature_models() -> tuple[str, str]:
    melspec = _resolve_repo_path(MELSPECTROGRAM_MODEL)
    embedding = _resolve_repo_path(EMBEDDING_MODEL)

    if melspec.exists() and embedding.exists():
        return str(melspec), str(embedding)

    raise RuntimeError(
        "openWakeWord feature models are missing. "
        f"Expected {MELSPECTROGRAM_MODEL} and {EMBEDDING_MODEL} "
        "next to the wake word model."
    )


def _openwakeword_model_from_env(model_name: str):
    import openwakeword
    from openwakeword.model import Model

    melspec_path, embedding_path = _ensure_feature_models()

    if Path(model_name).exists():
        return Model(
            wakeword_models=[model_name],
            inference_framework="onnx",
            melspec_model_path=melspec_path,
            embedding_model_path=embedding_path,
        )

    openwakeword.utils.download_models(model_names=[model_name])

    return Model(
        wakeword_models=[model_name],
        inference_framework="onnx",
        melspec_model_path=melspec_path,
        embedding_model_path=embedding_path,
    )


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
