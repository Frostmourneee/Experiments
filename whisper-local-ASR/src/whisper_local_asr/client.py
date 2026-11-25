"""Small command-line client used asynchronously by Neovim."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

from .protocol import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, socket_path


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control the local Whisper daemon")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Start recording")

    for command in ("stop", "cancel"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("recording_id")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
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
