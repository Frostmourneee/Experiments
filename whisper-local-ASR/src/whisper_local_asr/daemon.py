"""Long-lived local recording and Whisper transcription daemon."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .core import load_model, transcribe, warm_up
from .protocol import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, socket_path


class State(StrEnum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


@dataclass
class Recording:
    recording_id: str
    path: Path
    process: subprocess.Popen[bytes]
    error_log: BinaryIO


def _brief_error(error: object) -> str:
    text = " ".join(str(error).split())
    return text[:240] or "unknown error"


def notify(summary: str, body: str, urgency: str = "normal") -> None:
    """Send a best-effort desktop notification."""
    executable = shutil.which("notify-send")
    if not executable:
        return

    try:
        subprocess.run(
            [executable, "--urgency", urgency, summary, body],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return


class DictationController:
    """Own exactly one sequential record/transcribe cycle."""

    def __init__(
        self,
        model: Any,
        recording_dir: Path,
        *,
        transcriber: Callable[[Any, Any], str] = transcribe,
        ffmpeg: str | None = None,
    ) -> None:
        self.model = model
        self.recording_dir = recording_dir
        self.transcriber = transcriber
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or ""
        self.state = State.IDLE
        self.recording: Recording | None = None
        self.lock = threading.Lock()

        if not self.ffmpeg:
            raise RuntimeError("ffmpeg was not found on PATH")

        self.recording_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.recording_dir, 0o700)
        self._remove_stale_recordings()

    def _remove_stale_recordings(self) -> None:
        for path in self.recording_dir.glob("recording-*.wav"):
            if path.is_file() and not path.is_symlink():
                try:
                    path.unlink()
                except OSError:
                    pass

    def _read_error_log(self, recording: Recording) -> str:
        try:
            recording.error_log.flush()
            recording.error_log.seek(0)
            raw = recording.error_log.read(16 * 1024)
            return _brief_error(raw.decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            return ""

    def _start_ffmpeg(self) -> Recording:
        recording_id = uuid.uuid4().hex
        path = self.recording_dir / f"recording-{recording_id}.wav"
        error_log = tempfile.TemporaryFile(mode="w+b")
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "alsa",
            "-i",
            "default",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(path),
        ]

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=error_log,
                start_new_session=True,
            )
        except OSError:
            error_log.close()
            raise

        recording = Recording(recording_id, path, process, error_log)
        time.sleep(0.15)
        if process.poll() is not None:
            message = self._read_error_log(recording) or "ffmpeg exited immediately"
            error_log.close()
            path.unlink(missing_ok=True)
            raise RuntimeError(message)
        return recording

    def _finish_ffmpeg(self, recording: Recording) -> None:
        process = recording.process
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        if not recording.path.is_file() or recording.path.stat().st_size <= 44:
            message = self._read_error_log(recording) or "recording is empty"
            raise RuntimeError(message)

    def _close_recording(self, recording: Recording) -> None:
        try:
            recording.error_log.close()
        except OSError:
            pass
        try:
            recording.path.unlink(missing_ok=True)
        except OSError:
            pass

    def _error_response(self, message: str) -> dict[str, Any]:
        return {
            "ok": False,
            "state": self.state.value,
            "error": _brief_error(message),
        }

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("version") != PROTOCOL_VERSION:
            return self._error_response("unsupported protocol version")

        command = request.get("command")
        if command == "start":
            return self._handle_start()
        if command == "stop":
            return self._handle_stop(request.get("recording_id"))
        if command == "cancel":
            return self._handle_cancel(request.get("recording_id"))
        return self._error_response("unknown command")

    def _handle_start(self) -> dict[str, Any]:
        with self.lock:
            if self.state is not State.IDLE:
                return self._error_response("ASR is already active")

            try:
                recording = self._start_ffmpeg()
            except Exception as exc:  # noqa: BLE001 - returned to the local client.
                return self._error_response(f"unable to start recording: {exc}")

            self.recording = recording
            self.state = State.RECORDING
            return {
                "ok": True,
                "state": self.state.value,
                "recording_id": recording.recording_id,
            }

    def _matching_recording(self, recording_id: object) -> Recording | None:
        recording = self.recording
        if (
            not isinstance(recording_id, str)
            or not recording_id
            or recording is None
            or recording.recording_id != recording_id
        ):
            return None
        return recording

    def _handle_stop(self, recording_id: object) -> dict[str, Any]:
        with self.lock:
            if self.state is not State.RECORDING:
                return self._error_response("ASR is not recording")
            recording = self._matching_recording(recording_id)
            if recording is None:
                return self._error_response("recording is owned by another client")

            self.state = State.TRANSCRIBING
            self.recording = None

        try:
            self._finish_ffmpeg(recording)
            text = self.transcriber(self.model, str(recording.path))
            return {
                "ok": True,
                "state": State.IDLE.value,
                "text": text,
            }
        except Exception as exc:  # noqa: BLE001 - returned to the local client.
            return {
                "ok": False,
                "state": State.IDLE.value,
                "error": _brief_error(f"transcription failed: {exc}"),
            }
        finally:
            self._close_recording(recording)
            with self.lock:
                self.state = State.IDLE

    def _handle_cancel(self, recording_id: object) -> dict[str, Any]:
        with self.lock:
            if self.state is not State.RECORDING:
                return self._error_response("ASR is not recording")
            recording = self._matching_recording(recording_id)
            if recording is None:
                return self._error_response("recording is owned by another client")

            self.recording = None
            self.state = State.IDLE

        try:
            process = recording.process
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            self._close_recording(recording)

        return {"ok": True, "state": State.IDLE.value}

    def shutdown(self) -> None:
        with self.lock:
            recording = self.recording
            self.recording = None
            if self.state is State.RECORDING:
                self.state = State.IDLE

        if recording is not None:
            try:
                process = recording.process
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            finally:
                self._close_recording(recording)


class RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
        controller: DictationController = self.server.controller  # type: ignore[attr-defined]
        if not raw or len(raw) > MAX_MESSAGE_BYTES:
            response = {
                "ok": False,
                "state": controller.state.value,
                "error": "invalid request size",
            }
        else:
            try:
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict):
                    raise ValueError("request must be a JSON object")
                response = controller.handle(request)
            except (UnicodeError, ValueError) as exc:
                response = {
                    "ok": False,
                    "state": controller.state.value,
                    "error": _brief_error(exc),
                }

        try:
            self.wfile.write(
                json.dumps(
                    response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
        except (BrokenPipeError, ConnectionResetError):
            return


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False
    request_queue_size = 8

    def __init__(self, path: Path, controller: DictationController) -> None:
        self.controller = controller
        super().__init__(str(path), RequestHandler)


def _prepare_socket(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        return

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            connection.connect(str(path))
    except OSError:
        path.unlink(missing_ok=True)
        return
    raise RuntimeError(f"ASR daemon is already listening on {path}")


def _recording_directory() -> Path:
    cache_home = os.environ.get("XDG_CACHE_HOME")
    root = Path(cache_home) if cache_home else Path.home() / ".cache"
    return root / "whisper-local-asr" / "recordings"


def run() -> int:
    path = socket_path()
    server: ThreadingUnixServer | None = None
    controller: DictationController | None = None

    try:
        _prepare_socket(path)
        model = load_model()
        warm_up(model)
        controller = DictationController(model, _recording_directory())
        old_umask = os.umask(0o077)
        try:
            server = ThreadingUnixServer(path, controller)
        finally:
            os.umask(old_umask)
        os.chmod(path, 0o600)
    except Exception as exc:  # noqa: BLE001 - daemon startup boundary.
        if server is not None:
            server.server_close()
            path.unlink(missing_ok=True)
        message = _brief_error(exc)
        notify("Whisper ASR", f"Error: {message}", urgency="critical")
        print(f"Whisper ASR startup failed: {message}", flush=True)
        return 1

    stopped = threading.Event()

    def request_shutdown(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.25},
        name="whisper-asr-socket",
        daemon=True,
    )
    thread.start()
    notify("Whisper ASR", "Model loaded successfully")

    try:
        stopped.wait()
    finally:
        server.shutdown()
        server.server_close()
        controller.shutdown()
        path.unlink(missing_ok=True)
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
