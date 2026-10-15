import os
from dataclasses import dataclass
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = EXPERIMENT_DIR.parents[1] / "models" / "hey_pran.onnx"
DEFAULT_THRESHOLD = 0.5
DEFAULT_COOLDOWN_SECONDS = 2.0
DEFAULT_SCORE_PRINT_THRESHOLD = 0.2
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_FRAME_SAMPLES = 1280
WAKE_PHRASE = "Hey Pran"


@dataclass(frozen=True)
class WakeWordExperimentConfig:
    model_path: Path = DEFAULT_MODEL_PATH
    threshold: float = DEFAULT_THRESHOLD
    cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS
    score_print_threshold: float = DEFAULT_SCORE_PRINT_THRESHOLD
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    frame_samples: int = DEFAULT_FRAME_SAMPLES
    wake_phrase: str = WAKE_PHRASE

    @property
    def frame_bytes(self) -> int:
        return self.frame_samples * 2


def load_config() -> WakeWordExperimentConfig:
    model_path = Path(
        os.getenv("WAKE_WORD_MODEL", DEFAULT_MODEL_PATH)
    ).expanduser()

    if not model_path.is_absolute():
        model_path = (Path.cwd() / model_path).resolve()

    return WakeWordExperimentConfig(
        model_path=model_path,
        threshold=_env_float("WAKE_WORD_THRESHOLD", DEFAULT_THRESHOLD),
        cooldown_seconds=_env_float(
            "WAKE_WORD_COOLDOWN_SECONDS",
            DEFAULT_COOLDOWN_SECONDS,
        ),
        score_print_threshold=_env_float(
            "WAKE_WORD_SCORE_PRINT_THRESHOLD",
            DEFAULT_SCORE_PRINT_THRESHOLD,
        ),
    )


def missing_model_message(model_path: Path) -> str:
    try:
        display_path = model_path.relative_to(EXPERIMENT_DIR.parents[1])
    except ValueError:
        display_path = model_path

    return f"Wake word model not found:\n{display_path}"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default
