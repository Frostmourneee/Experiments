# Telegram Specific Notifications

A small Ubuntu service that shows desktop notifications only for selected
Telegram chats. Telegram itself may remain closed: Telethon keeps a lightweight
connection to your account, filters incoming messages by chat ID, and sends
matching messages to Ubuntu through `notify-send`.

## Quick start

Clone the repository and run the setup script:

```bash
git clone https://github.com/Frostmourneee/Experiments.git && cd Experiments/telegram-specific-notifications
./setup.sh
```

Open the generated configuration and fill in `API_ID` and `API_HASH` from
[my.telegram.org](https://my.telegram.org/apps). Leave `ALLOWED_CHAT_IDS` empty
for now:

```bash
$EDITOR ~/.config/telegram-specific-notifications/.env
```

Load the configuration into your current terminal and list the available
chats:

```bash
set -a
source ~/.config/telegram-specific-notifications/.env
set +a
telegram-specific-notifications list-chats
```

The first connection asks for your phone number, login code, and
two-step-verification password when enabled. Copy the desired chat IDs into
`ALLOWED_CHAT_IDS` as a comma-separated list, then start the service:

```bash
$EDITOR ~/.config/telegram-specific-notifications/.env
systemctl --user enable --now telegram-specific-notifications.service
```

Check its status or restart it after changing the configuration:

```bash
systemctl --user status telegram-specific-notifications.service
systemctl --user restart telegram-specific-notifications.service
```

## What it uses

- Python 3.12+, [uv](https://docs.astral.sh/uv/) and
  [Telethon](https://docs.telethon.dev/)
- Ubuntu `notify-send` (`libnotify-bin`)
- A systemd user service
- Telegram `api_id` and `api_hash`
