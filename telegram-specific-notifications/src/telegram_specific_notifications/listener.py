import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient, events
from telethon.utils import get_display_name

from .config import load_settings
from .notifications import (
    NotificationError,
    ensure_notifications_available,
    show_notification,
)

MAX_PREVIEW_LENGTH = 300


def _secure_session_file(session_path: Path) -> None:
    if session_path.exists():
        session_path.chmod(0o600)


def _entity_name(entity: object | None) -> str:
    if entity is None:
        return "Telegram"

    return get_display_name(entity) or "Telegram"


def _message_preview(raw_text: str) -> str:
    text = " ".join(raw_text.replace("\x00", "").split())

    if not text:
        return "New media message"

    if len(text) <= MAX_PREVIEW_LENGTH:
        return text

    return f"{text[: MAX_PREVIEW_LENGTH - 1]}…"


async def _run_listener_async() -> None:
    settings = load_settings()
    ensure_notifications_available()

    client = TelegramClient(
        session=str(settings.session_path),
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        device_model="Selective Notifications",
        system_version="Ubuntu",
        app_version="0.1.0",
    )

    @client.on(events.NewMessage(incoming=True))
    async def handle_new_message(event: events.NewMessage.Event) -> None:
        if event.chat_id not in settings.allowed_chat_ids:
            return

        chat = await event.get_chat()
        title = _entity_name(chat)
        body = _message_preview(event.raw_text)

        if event.is_group:
            sender = await event.get_sender()
            sender_name = _entity_name(sender)
            body = f"{sender_name}: {body}"

        try:
            await show_notification(title, body)
        except NotificationError as error:
            print(f"Notification failed: {error}", file=sys.stderr)

    try:
        await client.start()
        _secure_session_file(settings.session_path)

        print(
            "Listening for messages from "
            f"{len(settings.allowed_chat_ids)} allowed chat(s). "
            "Press Ctrl+C to stop."
        )

        await client.run_until_disconnected()
    finally:
        if client.is_connected():
            await client.disconnect()

        _secure_session_file(settings.session_path)


def run_listener() -> None:
    try:
        asyncio.run(_run_listener_async())
    except KeyboardInterrupt:
        pass
