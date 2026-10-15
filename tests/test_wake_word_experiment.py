import sys
from io import StringIO
from pathlib import Path
from threading import Event

EXPERIMENT_DIR = (
    Path(__file__).resolve().parents[1] / "experiments" / "wake-word"
)

if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

from config import (
    WakeWordExperimentConfig,
    load_config,
    missing_model_message,
)
from listener import (
    WakeWordMicrophoneProbe,
    ensure_model_exists,
    peak_score,
)
from test_microphone import main as experiment_main


class FakeFrameSource:
    def __init__(self, frames: list[bytes] | None = None) -> None:
        self.frames = list(frames or [])
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def read(self, nbytes: int) -> bytes | None:
        if not self.frames:
            return None

        return self.frames.pop(0)

    def stop(self) -> None:
        self.stopped += 1


class FakeClock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _frame(config: WakeWordExperimentConfig) -> bytes:
    return b"\x00" * config.frame_bytes


def test_missing_model_message_is_clear(tmp_path):
    model_path = tmp_path / "hey_pran.onnx"

    message = ensure_model_exists(model_path)

    assert message is not None
    assert "Wake word model not found:" in message
    assert "hey_pran.onnx" in message


def test_experiment_main_exits_without_stack_trace_when_model_missing(
    monkeypatch,
    tmp_path,
    capsys,
):
    model_path = tmp_path / "hey_pran.onnx"
    monkeypatch.setenv("WAKE_WORD_MODEL", str(model_path))

    assert experiment_main() == 1

    captured = capsys.readouterr()
    assert "Wake word model not found:" in captured.err
    assert "hey_pran.onnx" in captured.err
    assert "Traceback" not in captured.err


def test_load_config_reads_threshold_from_env(monkeypatch, tmp_path):
    model_path = tmp_path / "hey_pran.onnx"
    monkeypatch.setenv("WAKE_WORD_MODEL", str(model_path))
    monkeypatch.setenv("WAKE_WORD_THRESHOLD", "0.75")
    monkeypatch.setenv("WAKE_WORD_COOLDOWN_SECONDS", "3")

    config = load_config()

    assert config.threshold == 0.75
    assert config.cooldown_seconds == 3.0
    assert config.model_path == model_path.resolve()
    assert config.sample_rate == 16000
    assert config.channels == 1
    assert config.frame_samples == 1280


def test_peak_score_reads_openwakeword_dict():
    assert peak_score({"hey_pran": 0.87}) == 0.87
    assert peak_score({}) == 0.0
    assert peak_score(0.41) == 0.41


def test_probe_prints_detection_once_and_keeps_listening():
    config = WakeWordExperimentConfig(threshold=0.5, cooldown_seconds=2.0)
    scores = [0.23, 0.41, 0.87, 0.91, 0.12, 0.88]
    output = StringIO()
    clock = FakeClock(0.0)
    source = FakeFrameSource([_frame(config)] * len(scores))
    stop_event = Event()

    def predictor(_raw: bytes):
        score = scores.pop(0)
        clock.now += 0.08

        if not scores:
            stop_event.set()

        return {"hey_pran": score}

    probe = WakeWordMicrophoneProbe(
        config=config,
        predictor=predictor,
        frame_source=source,
        clock=clock,
        output=output,
    )

    assert probe.run(stop_event) == 0

    text = output.getvalue()
    assert "🎤 Listening..." in text
    assert text.count("🔥 WAKE WORD DETECTED") == 1
    assert "score=0.23" in text
    assert "score=0.41" in text
    assert probe.detections == 1
    assert source.started == 1
    assert source.stopped == 1


def test_cooldown_and_latch_suppress_repeat_detections():
    config = WakeWordExperimentConfig(threshold=0.7, cooldown_seconds=2.0)
    output = StringIO()
    clock = FakeClock(0.0)
    source = FakeFrameSource([_frame(config)] * 4)
    stop_event = Event()
    remaining = [0.95, 0.96, 0.97, 0.10]

    def predictor(_raw: bytes):
        score = remaining.pop(0)
        clock.now += 0.08

        if not remaining:
            stop_event.set()

        return {"hey_pran": score}

    probe = WakeWordMicrophoneProbe(
        config=config,
        predictor=predictor,
        frame_source=source,
        clock=clock,
        output=output,
    )

    probe.run(stop_event)

    assert probe.detections == 1
    assert output.getvalue().count("🔥 WAKE WORD DETECTED") == 1


def test_second_utterance_after_cooldown_is_detected():
    config = WakeWordExperimentConfig(threshold=0.7, cooldown_seconds=2.0)
    output = StringIO()
    clock = FakeClock(0.0)
    frames = [
        (0.9, 0.0),
        (0.1, 2.1),
        (0.92, 2.2),
    ]
    source = FakeFrameSource([_frame(config)] * len(frames))
    stop_event = Event()
    remaining = list(frames)

    def predictor(_raw: bytes):
        score, now = remaining.pop(0)
        clock.now = now

        if not remaining:
            stop_event.set()

        return {"hey_pran": score}

    probe = WakeWordMicrophoneProbe(
        config=config,
        predictor=predictor,
        frame_source=source,
        clock=clock,
        output=output,
    )

    probe.run(stop_event)

    assert probe.detections == 2
    assert output.getvalue().count("🔥 WAKE WORD DETECTED") == 2


def test_low_scores_are_not_printed():
    config = WakeWordExperimentConfig(
        threshold=0.5,
        score_print_threshold=0.2,
    )
    output = StringIO()
    stop_event = Event()
    source = FakeFrameSource([_frame(config), _frame(config)])
    remaining = [0.01, 0.04]

    def predictor(_raw: bytes):
        score = remaining.pop(0)

        if not remaining:
            stop_event.set()

        return {"hey_pran": score}

    probe = WakeWordMicrophoneProbe(
        config=config,
        predictor=predictor,
        frame_source=source,
        output=output,
    )

    probe.run(stop_event)

    assert "score=" not in output.getvalue()
    assert "🔥 WAKE WORD DETECTED" not in output.getvalue()


def test_ctrl_c_stops_frame_source():
    config = WakeWordExperimentConfig()
    source = FakeFrameSource()
    source.read = lambda nbytes: (_ for _ in ()).throw(KeyboardInterrupt())
    output = StringIO()

    probe = WakeWordMicrophoneProbe(
        config=config,
        predictor=lambda _raw: {"hey_pran": 0.0},
        frame_source=source,
        output=output,
    )

    assert probe.run() == 0
    assert source.stopped == 1
    assert "Stopped." in output.getvalue()


def test_missing_model_helper_uses_repo_relative_path():
    message = missing_model_message(
        EXPERIMENT_DIR / "models" / "hey_pran.onnx"
    )

    assert message == (
        "Wake word model not found:\n"
        "experiments/wake-word/models/hey_pran.onnx"
    )


def test_experiment_default_model_uses_repo_onnx():
    from config import DEFAULT_MODEL_PATH

    assert DEFAULT_MODEL_PATH.name == "hey_pran.onnx"
    assert DEFAULT_MODEL_PATH.parent.name == "models"
    assert "hey_pran_work" not in str(DEFAULT_MODEL_PATH)
