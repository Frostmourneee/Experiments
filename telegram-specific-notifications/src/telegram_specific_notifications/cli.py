import argparse

from .config import ConfigurationError
from .discovery import list_chats
from .listener import run_listener


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="telegram-specific-notifications",
        description="Show Ubuntu notifications for selected Telegram chats.",
    )

    subcommands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subcommands.add_parser(
        "run",
        help="Listen for allowed chats and show Ubuntu notifications.",
    )
    subcommands.add_parser(
        "list-chats",
        help="List Telegram chats and their IDs.",
    )

    return parser


def main() -> None:
    parser = _create_parser()
    arguments = parser.parse_args()

    try:
        if arguments.command == "run":
            run_listener()
        elif arguments.command == "list-chats":
            list_chats()
    except ConfigurationError as error:
        parser.error(str(error))
