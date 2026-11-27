# vps-status-monitor

A small, dependency-free ICMP monitor for configured IP targets.

Every check sends three ICMP echo requests to each VPS. A VPS is recorded as
unreachable only if all three requests are lost. Partial loss remains reachable
and is retained in the database.

Pings are explicitly bound to the ordinary Internet interface. By default the
checker discovers it from the IPv4 default route in Linux routing table `main`.
This bypasses policy-routed global VPN connections.
## Install

Run this as the user who should own the monitor:

```bash
./install.sh
vps-status-monitor check
```

The installer creates:

```text
~/.local/bin/vps-status-monitor
~/.config/systemd/user/vps-status-monitor.service
~/.config/systemd/user/vps-status-monitor.timer
~/.local/state/vps-status-monitor/monitor.db
```

It also enables and starts the user timer. No root privileges or Python packages
are required.
## Commands

```bash
vps-status-monitor status
vps-status-monitor outages --since 7d
vps-status-monitor outages --target amsterdam --since 30d
vps-status-monitor chart --since 24h
vps-status-monitor chart --target ltv --since 6h --width 72
vps-status-monitor check --interface enp34s0
```

Durations accept `s`, `m`, `h`, `d`, or `w`. Times are displayed in the local
timezone; SQLite stores Unix timestamps. The default database location follows
`$XDG_STATE_HOME` when it is set.

Use `--interface NAME` on `check`, or set `VPS_STATUS_MONITOR_INTERFACE`, to
override automatic base-interface discovery. If discovery fails, the checker
records `UNKNOWN` rather than silently sending probes through the VPN. The
selected interface is stored with every sample and displayed by `status`.

The terminal chart uses:

```text
. reachable
! reachable with partial packet loss
X unreachable (all three packets lost)
E local ping/check error
? no recorded data
```

Outage boundaries have approximately one-minute resolution. Missing monitor
data is never counted as downtime. The latest status is labelled `STALE` if no
sample has arrived recently.

## Operations

```bash
systemctl --user status vps-status-monitor.timer
systemctl --user list-timers vps-status-monitor.timer
journalctl --user -u vps-status-monitor.service
systemctl --user disable --now vps-status-monitor.timer
```

The service uses `check --quiet`, so normal successful samples do not fill the
journal. Outages, partial loss, and local check errors are logged.

This monitor measures reachability from the machine on which it runs. Install it
on the always-on device whose network path you want to observe.
