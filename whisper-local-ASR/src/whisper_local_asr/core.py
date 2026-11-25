"""Shared model configuration and transcription helpers."""

from __future__ import annotations

import ctypes
import site
from importlib.resources import as_file, files
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from faster_whisper import WhisperModel


MODEL_NAME = "large-v3"
DEVICE = "cuda"
COMPUTE_TYPE = "int8_float16"

INITIAL_PROMPT = """
        This is a software-engineering prompt for an AI coding assistant.
        It may mention many terms like Linux, Ubuntu, Bash, Git, GitHub, Go, SQL, APIs, JSON, YAML, Docker, Neovim, Neovide, OpenAI, and Codex.
        """


def preload_cuda_libraries() -> None:
    """Expose CUDA libraries installed as Python packages to CTranslate2."""
    library_names = (
        ("cublas", "libcublasLt.so.12"),
        ("cublas", "libcublas.so.12"),
        ("cudnn", "libcudnn.so.9"),
    )

    roots = [Path(path) for path in site.getsitepackages()]
    user_site = site.getusersitepackages()
    if user_site:
        roots.append(Path(user_site))

    missing: list[str] = []
    for package, library_name in library_names:
        candidates = [
            root / "nvidia" / package / "lib" / library_name for root in roots
        ]
        library = next((path for path in candidates if path.is_file()), None)
        if library is None:
            missing.append(library_name)
            continue
        ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)

    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"Missing CUDA runtime libraries: {names}. Run `uv sync` first."
        )


def load_model() -> WhisperModel:
    """Load the configured Whisper model into GPU memory."""
    preload_cuda_libraries()

    from faster_whisper import WhisperModel

    return WhisperModel(
        MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        num_workers=1,
    )


def transcribe(model: WhisperModel, audio: Any) -> str:
    """Transcribe English technical dictation with the shared settings."""
    segments, _ = model.transcribe(
        audio,
        language="en",
        task="transcribe",
        beam_size=5,
        vad_filter=True,
        without_timestamps=True,
        initial_prompt=INITIAL_PROMPT,
    )
    return "".join(segment.text for segment in segments).strip()


def warm_up(model: WhisperModel) -> None:
    resource = files("whisper_local_asr").joinpath("resources", "warmup.wav")

    with as_file(resource) as audio:
        segments, _ = model.transcribe(
            str(audio),
            language="en",
            task="transcribe",
            beam_size=1,
            vad_filter=False,
            without_timestamps=True,
            initial_prompt=INITIAL_PROMPT,
        )
        # faster-whisper is lazy; consuming the generator performs inference.
        list(segments)
