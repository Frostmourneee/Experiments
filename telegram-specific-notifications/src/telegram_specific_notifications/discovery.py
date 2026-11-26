import asyncio
from pathlib import Path

from telethon import TelegramClient

from .config import load_client_settings


def _secure_session_file(session_path: Path) -> None:
    if session_path.exists():
        session_path.chmod(0o600)


def _dialog_kind(dialog: object) -> str:
    if getattr(dialog, "is_user", False):
        return "private"

    if getattr(dialog, "is_group", False):
        return "group"

    if getattr(dialog, "is_channel", False):
        return "channel"

    return "other"


async def _list_chats_async() -> None:
    settings = load_client_settings()

    client = TelegramClient(
        session=str(settings.session_path),
        api_id=settings.api_id,
        api_hash=settings.api_hash,
        device_model="Selective Notifications",
        system_version="Ubuntu",
        app_version="0.1.0",
    )

    try:
        await client.start()
        _secure_session_file(settings.session_path)

        current_user = await client.get_me()

        if current_user is None:
            raise RuntimeError("Telegram authentication failed.")

        display_name = " ".join(
            part
            for part in (current_user.first_name, current_user.last_name)
            if part
        )

        print(f"\nAuthenticated as {display_name} ({current_user.id})\n")
        print(f"{'CHAT ID':>16}  {'TYPE':<8}  NAME")
        print("-" * 70)

        async for dialog in client.iter_dialogs():
            name = " ".join((dialog.name or "<unnamed>").split())
            print(f"{dialog.id:>16}  {_dialog_kind(dialog):<8}  {name}")
    finally:
        if client.is_connected():
            await client.disconnect()

        _secure_session_file(settings.session_path)


def list_chats() -> None:
    asyncio.run(_list_chats_async())
