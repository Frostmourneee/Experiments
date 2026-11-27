import importlib.machinery
import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "vps-status-monitor"
LOADER = importlib.machinery.SourceFileLoader("vps_status_monitor", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
LOADER.exec_module(monitor)


class PingResultTests(unittest.TestCase):
    target = monitor.Target("test", "192.0.2.1")

    def test_all_replies_is_up(self):
        result = monitor.interpret_ping_result(
            self.target,
            0,
            "3 packets transmitted, 3 received, 0% packet loss\n"
            "rtt min/avg/max/mdev = 10.000/12.500/15.000/2.000 ms\n",
            "",
        )
        self.assertEqual(result.status, "up")
        self.assertEqual(result.packets_received, 3)
        self.assertEqual(result.avg_rtt_ms, 12.5)

    def test_partial_loss_is_still_up(self):
        result = monitor.interpret_ping_result(
            self.target,
            0,
            "3 packets transmitted, 1 received, 66.6667% packet loss\n"
            "rtt min/avg/max/mdev = 11.000/11.000/11.000/0.000 ms\n",
            "",
        )
        self.assertEqual(result.status, "up")
        self.assertEqual(result.packets_received, 1)

    def test_all_three_lost_is_down(self):
        result = monitor.interpret_ping_result(
            self.target,
            1,
            "3 packets transmitted, 0 received, 100% packet loss\n",
            "",
        )
        self.assertEqual(result.status, "down")

    def test_local_ping_error_is_unknown_not_down(self):
        result = monitor.interpret_ping_result(
            self.target, 2, "", "ping: socket: Operation not permitted"
        )
        self.assertEqual(result.status, "unknown")

    def test_incomplete_attempt_is_unknown(self):
        result = monitor.interpret_ping_result(
            self.target,
            1,
            "2 packets transmitted, 0 received, 100% packet loss\n",
            "",
        )
        self.assertEqual(result.status, "unknown")


class RouteTests(unittest.TestCase):
    def test_selects_lowest_metric_main_default(self):
        output = (
            "default via 192.168.1.1 dev wlan0 metric 600\n"
            "default via 192.168.31.1 dev enp34s0 metric 100\n"
        )
        self.assertEqual(monitor.parse_base_interface(output), "enp34s0")

    def test_no_default_route_returns_none(self):
        self.assertIsNone(monitor.parse_base_interface("192.168.31.0/24 dev enp34s0\n"))


class OutageTests(unittest.TestCase):
    def rows(self, values):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE events (target TEXT, checked_at INTEGER, status TEXT)"
        )
        connection.executemany("INSERT INTO events VALUES (?, ?, ?)", values)
        return list(connection.execute("SELECT * FROM events ORDER BY target, checked_at"))

    def test_consecutive_failures_become_one_interval(self):
        rows = self.rows(
            [
                ("amsterdam", 100, "up"),
                ("amsterdam", 160, "down"),
                ("amsterdam", 220, "down"),
                ("amsterdam", 280, "up"),
            ]
        )
        outages = monitor.build_outages(rows, now=300)
        self.assertEqual(len(outages), 1)
        self.assertEqual(outages[0].started_at, 160)
        self.assertEqual(outages[0].ended_at, 280)
        self.assertEqual(outages[0].end_reason, "recovered")

    def test_missing_monitor_data_does_not_extend_outage(self):
        rows = self.rows(
            [
                ("ltv", 100, "down"),
                ("ltv", 160, "down"),
                ("ltv", 1000, "up"),
            ]
        )
        outages = monitor.build_outages(rows, now=1010)
        self.assertEqual(len(outages), 1)
        self.assertIsNone(outages[0].ended_at)
        self.assertEqual(outages[0].last_down_at, 160)
        self.assertEqual(outages[0].end_reason, "data gap")


if __name__ == "__main__":
    unittest.main()
