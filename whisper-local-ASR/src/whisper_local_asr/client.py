"""Command-line clients for Neovim and system-wide clipboard dictation."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .protocol import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, socket_path

SERVICE_NAME = "whisper-local-asr.service"
GLOBAL_RECORDING_FILE = "whisper-local-asr-global-recording-id"
GLOBAL_LOCK_FILE = "whisper-local-asr-global.lock"
DAEMON_START_TIMEOUT_SECONDS = 60.0


def send_request(request: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Send one request and wait for its single JSON response."""
    target = path or socket_path()
    payload = json.dumps(
        request,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(3)
        connection.connect(str(target))
        connection.sendall(payload)
        # A stop request can legitimately wait for a long transcription.
        connection.settimeout(None)

        chunks = bytearray()
        while True:
            chunk = connection.recv(64 * 1024)
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > MAX_MESSAGE_BYTES:
                raise RuntimeError("ASR daemon response is too large")
            if b"\n" in chunk:
                break

    raw = bytes(chunks).split(b"\n", 1)[0]
    if not raw:
        raise RuntimeError("ASR daemon closed the connection without a response")

    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError("ASR daemon returned an invalid response")
    return response


def _runtime_path(name: str) -> Path:
    return socket_path().parent / name


def _daemon_accepts_connections(path: Path | None = None) -> bool:
    """Return whether a daemon is listening, without leaving a connection open."""
    target = path or socket_path()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            connection.connect(str(target))
    except OSError:
        return False
    return True


def _ensure_daemon_ready(timeout: float = DAEMON_START_TIMEOUT_SECONDS) -> None:
    """Start the user service when needed and wait for its warmed socket."""
    if _daemon_accepts_connections():
        return

    try:
        result = subprocess.run(
            ["systemctl", "--user", "start", SERVICE_NAME],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"unable to start {SERVICE_NAME}: {exc}") from exc

    if result.returncode != 0:
        message = " ".join((result.stderr or result.stdout).split())
        raise RuntimeError(
            message or f"systemctl could not start {SERVICE_NAME}"
        )

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _daemon_accepts_connections():
            return
        time.sleep(0.1)

    raise RuntimeError(
        f"{SERVICE_NAME} did not finish model warm-up within {timeout:g} seconds"
    )


def _read_recording_id(path: Path) -> str | None:
    try:
        recording_id = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"unable to read global dictation state: {exc}") from exc

    if recording_id:
        return recording_id
    path.unlink(missing_ok=True)
    return None


def _write_recording_id(path: Path, recording_id: str) -> None:
    """Atomically persist the active global recording with private permissions."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(recording_id + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


@contextmanager
def _toggle_lock(path: Path) -> Iterator[bool]:
    """Serialize toggle presses without queuing another stop during transcription."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        os.close(descriptor)


def _clipboard_command() -> list[str]:
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        return ["wl-copy"]
    if shutil.which("xclip"):
        return ["xclip", "-selection", "clipboard", "-in"]
    if shutil.which("wl-copy"):
        return ["wl-copy"]
    raise RuntimeError("neither xclip nor wl-copy was found")


def _copy_to_clipboard(text: str) -> None:
    if not text:
        raise RuntimeError("transcription returned empty text; clipboard was unchanged")

    try:
        result = subprocess.run(
            _clipboard_command(),
            input=text.encode("utf-8"),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"unable to copy transcription to clipboard: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"clipboard command exited with status {result.returncode}"
        )


def _notify_error(message: str) -> None:
    executable = shutil.which("notify-send")
    if not executable:
        return
    try:
        subprocess.run(
            [executable, "--urgency", "critical", "Whisper ASR", message],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return


def toggle_clipboard(
    *,
    state_path: Path | None = None,
    lock_path: Path | None = None,
) -> dict[str, Any]:
    """Start global recording, or stop it and put the transcript on the clipboard."""
    state_path = state_path or _runtime_path(GLOBAL_RECORDING_FILE)
    lock_path = lock_path or _runtime_path(GLOBAL_LOCK_FILE)

    with _toggle_lock(lock_path) as acquired:
        if not acquired:
            return {
                "ok": False,
                "state": "busy",
                "error": "global dictation toggle is already processing",
            }

        _ensure_daemon_ready()
        recording_id = _read_recording_id(state_path)
        if recording_id is None:
            response = send_request(
                {"version": PROTOCOL_VERSION, "command": "start"}
            )
            if (
                response.get("ok") is True
                and response.get("state") == "recording"
                and isinstance(response.get("recording_id"), str)
                and response["recording_id"]
            ):
                try:
                    _write_recording_id(state_path, response["recording_id"])
                except OSError:
                    try:
                        send_request(
                            {
                                "version": PROTOCOL_VERSION,
                                "command": "cancel",
                                "recording_id": response["recording_id"],
                            }
                        )
                    except (OSError, UnicodeError, ValueError, RuntimeError):
                        pass
                    raise
            return response

        try:
            response = send_request(
                {
                    "version": PROTOCOL_VERSION,
                    "command": "stop",
                    "recording_id": recording_id,
                }
            )
        finally:
            state_path.unlink(missing_ok=True)

        text = response.get("text")
        if response.get("ok") is True and isinstance(text, str):
            _copy_to_clipboard(text)
            response = {**response, "clipboard": True}
        return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control the local Whisper daemon")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start recording")
    subparsers.add_parser(
        "toggle-clipboard",
        help="Start global recording, or stop and copy its transcript",
    )

    for command in ("stop", "cancel"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("recording_id")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "toggle-clipboard":
        try:
            response = toggle_clipboard()
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            message = str(exc)
            print(f"Global dictation failed: {message}", file=sys.stderr)
            _notify_error(message)
            raise SystemExit(1) from exc

        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
        if response.get("ok") is not True and response.get("state") != "busy":
            message = str(response.get("error") or "global dictation failed")
            _notify_error(message)
            raise SystemExit(1)
        return

    request: dict[str, Any] = {
        "version": PROTOCOL_VERSION,
        "command": args.command,
    }
    if args.command in {"stop", "cancel"}:
        request["recording_id"] = args.recording_id

    try:
        response = send_request(request)
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(f"Unable to contact Whisper daemon: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
