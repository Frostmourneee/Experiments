#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
user_home_dir=${HOME:?HOME is not set}
binary_dir="$user_home_dir/.local/bin"
unit_dir="$user_home_dir/.config/systemd/user"
state_dir="${XDG_STATE_HOME:-$user_home_dir/.local/state}/vps-status-monitor"

command -v python3 >/dev/null 2>&1 || {
    echo "python3 is required" >&2
    exit 1
}
command -v ping >/dev/null 2>&1 || {
    echo "ping is required (usually provided by iputils-ping)" >&2
    exit 1
}
command -v systemctl >/dev/null 2>&1 || {
    echo "systemctl is required" >&2
    exit 1
}

install -d "$binary_dir" "$unit_dir" "$state_dir"
install -m 0755 "$project_dir/vps-status-monitor" "$binary_dir/vps-status-monitor"
install -m 0644 \
    "$project_dir/systemd/vps-status-monitor.service" \
    "$unit_dir/vps-status-monitor.service"
install -m 0644 \
    "$project_dir/systemd/vps-status-monitor.timer" \
    "$unit_dir/vps-status-monitor.timer"

systemctl --user daemon-reload
systemctl --user enable --now vps-status-monitor.timer

echo "Installed and started vps-status-monitor.timer"
echo "Run a first check now with: $binary_dir/vps-status-monitor check"
echo "Inspect the schedule with: systemctl --user list-timers vps-status-monitor.timer"

case ":${PATH:-}:" in
    *":$binary_dir:"*) ;;
    *) echo "Note: add $binary_dir to PATH to run vps-status-monitor by name." ;;
esac
