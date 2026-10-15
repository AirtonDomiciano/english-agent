#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = Path(__file__).resolve().parent

for path in (ROOT, EXPERIMENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from config import load_config
from listener import WakeWordMicrophoneProbe, ensure_model_exists


def main() -> int:
    config = load_config()
    missing = ensure_model_exists(config.model_path)

    if missing:
        print(missing, file=sys.stderr)
        return 1

    print(f"Model: {config.model_path}")
    print(f"Phrase: {config.wake_phrase}")
    print(f"Threshold: {config.threshold}")
    print(f"Cooldown: {config.cooldown_seconds}s")
    print(
        "Audio: "
        f"{config.sample_rate} Hz, "
        f"{config.channels} channel, "
        f"S16_LE, {config.frame_samples} samples/frame"
    )
    print("Ctrl+C to stop.\n")

    try:
        return WakeWordMicrophoneProbe(config).run()
    except FileNotFoundError as error:
        print(f"Microphone capture failed: {error}", file=sys.stderr)
        return 1
    except ImportError as error:
        print(
            "openWakeWord is not available. Install with:\n"
            "pip install openwakeword==0.6.0 --no-deps\n"
            f"Original error: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
