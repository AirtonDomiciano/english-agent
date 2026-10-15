from threading import Event
from time import monotonic
from typing import Callable, TextIO
import sys

from config import WakeWordExperimentConfig, missing_model_message


class WakeWordMicrophoneProbe:
    """Isolated loop to score a custom openWakeWord ONNX model."""

    def __init__(
        self,
        config: WakeWordExperimentConfig,
        predictor: Callable[[bytes], object] | None = None,
        frame_source=None,
        clock: Callable[[], float] | None = None,
        output: TextIO | None = None,
    ) -> None:
        self.config = config
        self.predictor = predictor
        self.frame_source = frame_source
        self._clock = clock or monotonic
        self.output = output or sys.stdout
        self._latched = False
        self._last_detection_at = -config.cooldown_seconds
        self._last_printed_score: float | None = None
        self._last_score_print_at = 0.0
        self.detections = 0

    def run(self, stop_event: Event | None = None) -> int:
        stop_event = stop_event or Event()
        frame_source = self.frame_source or _default_frame_source(
            self.config
        )
        predictor = self.predictor or _openwakeword_predictor(
            self.config.model_path
        )

        try:
            self._print("🎤 Listening...")
            frame_source.start()

            while not stop_event.is_set():
                raw = frame_source.read(self.config.frame_bytes)

                if raw is None or len(raw) < self.config.frame_bytes:
                    if stop_event.wait(0.01):
                        break

                    continue

                self._handle_score(peak_score(predictor(raw)))
        except KeyboardInterrupt:
            self._print("\nStopped.")
        finally:
            frame_source.stop()

        return 0

    def _handle_score(self, score: float) -> None:
        now = self._clock()
        detected = score >= self.config.threshold

        if detected:
            cooled_down = (
                now - self._last_detection_at
                >= self.config.cooldown_seconds
            )

            if not self._latched and cooled_down:
                self._latched = True
                self._last_detection_at = now
                self.detections += 1
                self._print(f"score={score:.2f}")
                self._print("🔥 WAKE WORD DETECTED")
                return
        else:
            self._latched = False

        if self._should_print_score(score, now):
            self._last_printed_score = score
            self._last_score_print_at = now
            self._print(f"score={score:.2f}")

    def _should_print_score(self, score: float, now: float) -> bool:
        if score < self.config.score_print_threshold:
            return False

        if self._last_printed_score is None:
            return True

        if abs(score - self._last_printed_score) >= 0.1:
            return True

        return now - self._last_score_print_at >= 0.5

    def _print(self, message: str) -> None:
        print(message, file=self.output, flush=True)


def peak_score(prediction) -> float:
    if isinstance(prediction, dict):
        if not prediction:
            return 0.0

        return max(float(score) for score in prediction.values())

    return float(prediction)


def ensure_model_exists(model_path) -> str | None:
    if model_path.exists():
        return None

    return missing_model_message(model_path)


def _default_frame_source(config: WakeWordExperimentConfig):
    from app.voice.wake_word_providers.openwakeword import (
        ArecordFrameSource,
    )

    return ArecordFrameSource(
        sample_rate=config.sample_rate,
        channels=config.channels,
    )


def _openwakeword_predictor(model_path):
    import numpy as np
    from openwakeword.model import Model

    model = Model(
        wakeword_models=[str(model_path)],
        inference_framework="onnx",
    )

    def predict(raw: bytes):
        frame = np.frombuffer(raw, dtype=np.int16)

        return model.predict(frame)

    return predict
