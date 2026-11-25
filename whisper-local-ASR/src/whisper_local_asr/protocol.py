"""Local Unix-socket protocol shared by the daemon and client."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
SOCKET_NAME = "whisper-local-asr.sock"


def socket_path() -> Path:
    """Return a per-user socket path available to every Neovim instance."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        root = Path(runtime_dir)
    else:
        conventional = Path("/run/user") / str(os.getuid())
        root = conventional if conventional.is_dir() else Path(tempfile.gettempdir())

    return root / SOCKET_NAME
