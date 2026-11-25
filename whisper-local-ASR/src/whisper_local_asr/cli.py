"""One-shot command-line transcription interface."""

from __future__ import annotations

import argparse
from pathlib import Path

from .core import load_model, transcribe


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a local English audio file with faster-whisper."
    )
    parser.add_argument("audio", type=Path, help="Path to a local audio file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audio_path = args.audio.expanduser().resolve()
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = load_model()
    print(transcribe(model, str(audio_path)))
