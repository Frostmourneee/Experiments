#!/usr/bin/env bash

set -euo pipefail

project_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config_directory="$HOME/.config/telegram-specific-notifications"
state_directory="$HOME/.local/state/telegram-specific-notifications"
environment_file="$config_directory/.env"
executable="$HOME/.local/bin/telegram-specific-notifications"
service="$HOME/.config/systemd/user/telegram-specific-notifications.service"

if ! command -v uv >/dev/null; then
    echo "uv is required: https://docs.astral.sh/uv/" >&2
    exit 1
fi

if ! command -v notify-send >/dev/null; then
    echo "notify-send is required (Ubuntu package: libnotify-bin)." >&2
    exit 1
fi

uv sync --locked --directory "$project_directory"

install -d -m 700 "$config_directory" "$state_directory"
install -d -m 755 "$HOME/.local/bin" "$HOME/.config/systemd/user"

if [[ ! -e "$environment_file" ]]; then
    install -m 600 "$project_directory/.env.example" "$environment_file"
fi

ln -sfn \
    "$project_directory/.venv/bin/telegram-specific-notifications" \
    "$executable"
ln -sfn \
    "$project_directory/systemd/telegram-specific-notifications.service" \
    "$service"

systemctl --user daemon-reload

echo "Installed. Configure $environment_file before starting the service."
