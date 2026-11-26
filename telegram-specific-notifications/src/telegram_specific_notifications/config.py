import os
from dataclasses import dataclass, field
from pathlib import Path

APPLICATION_NAME = "telegram-specific-notifications"


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ClientSettings:
    api_id: int
    api_hash: str = field(repr=False)
    session_path: Path


@dataclass(frozen=True, slots=True)
class Settings(ClientSettings):
    allowed_chat_ids: frozenset[int]


def _read_env_var(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise ConfigurationError(f"Required environment variable {name} is not set.")

    return value


def _read_chat_ids(name: str) -> frozenset[int]:
    raw_value = _read_env_var(name)
    values = [value.strip() for value in raw_value.split(",")]

    if any(not value for value in values):
        raise ConfigurationError(
            f"{name} must be a comma-separated list of integers."
        )

    try:
        chat_ids = frozenset(int(value) for value in values)
    except ValueError as error:
        raise ConfigurationError(
            f"{name} must be a comma-separated list of integers."
        ) from error

    if 0 in chat_ids:
        raise ConfigurationError(f"{name} cannot contain zero.")

    return chat_ids


def _state_home() -> Path:
    return Path.home() / ".local" / "state"


def load_client_settings() -> ClientSettings:
    raw_api_id = _read_env_var("API_ID")
    api_hash = _read_env_var("API_HASH")

    try:
        api_id = int(raw_api_id)
    except ValueError as error:
        raise ConfigurationError("API_ID must be an integer") from error

    if api_id <= 0:
        raise ConfigurationError("API_ID must be positive.")

    state_directory = _state_home() / APPLICATION_NAME
    state_directory.mkdir(parents=True, exist_ok=True)
    state_directory.chmod(0o700)

    return ClientSettings(
        api_id=api_id,
        api_hash=api_hash,
        session_path=state_directory / "account.session",
    )


def load_settings() -> Settings:
    client_settings = load_client_settings()

    return Settings(
        api_id=client_settings.api_id,
        api_hash=client_settings.api_hash,
        session_path=client_settings.session_path,
        allowed_chat_ids=_read_chat_ids("ALLOWED_CHAT_IDS"),
    )
