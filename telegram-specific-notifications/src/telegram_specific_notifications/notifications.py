import asyncio
import html
import shutil
import subprocess


class NotificationError(RuntimeError):
    """Raised when an Ubuntu desktop notification cannot be delivered."""


def ensure_notifications_available() -> None:
    if shutil.which("notify-send") is None:
        raise NotificationError(
            "notify-send is unavailable; install the libnotify-bin package."
        )


async def show_notification(title: str, body: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "notify-send",
        "--app-name=Selective Notifications",
        "--icon=telegram",
        "--category=im.received",
        "--urgency=normal",
        html.escape(title),
        html.escape(body),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    _, standard_error = await process.communicate()

    if process.returncode != 0:
        error_message = standard_error.decode(errors="replace").strip()
        details = f": {error_message}" if error_message else ""

        raise NotificationError(
            f"notify-send exited with status {process.returncode}{details}"
        )
