import os
from dataclasses import dataclass, field
from pathlib import Path

APPLICATION_NAME = "telegram-specific-notifications"


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    api_id: int
    api_hash: str = field(repr=False)
    session_path: Path


def _read_env_var(name: str) -> str:
    value = os.environ.get(name, "").strip()

    if not value:
        raise ConfigurationError(f"Required environment variable {name} is not set.")

    return value


def _state_home() -> Path:
    return Path.home() / ".local" / "state"


def load_settings() -> Settings:
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

    return Settings(
        api_id=api_id,
        api_hash=api_hash,
        session_path=state_directory / "account.session",
    )
