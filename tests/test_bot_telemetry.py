import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import DEFAULT, patch

from requests.exceptions import ReadTimeout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import bot
import bot_telemetry as telemetry
import dashboard


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        patcher = patch.object(telemetry, "STATUS_DIR", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = datetime(2026, 11, 4, 20, tzinfo=timezone.utc)
        patcher = patch.object(telemetry, "timestamp", return_value=self.now.isoformat())
        patcher.start()
        self.addCleanup(patcher.stop)

    def ready(self, bot_id="btc15_paper"):
        reporter = telemetry.BotTelemetry(bot_id)
        reporter.stage("Fetching BTC price")
        reporter.price(Decimal("82550.27"))
        reporter.market(ticker="TEST", secondsRemaining=180, spread=Decimal("0.02"))
        reporter.decide("WAIT", "price threshold not confirmed for 3 polls")
        return reporter

    def view(self, reporter, **overrides):
        return telemetry.runtime_status(
            reporter.data["botId"], running=True, pid=reporter.data["pid"], managed=True,
            now=overrides.pop("now", self.now), **overrides,
        )

    def test_snapshot_preserves_decimal_values_and_true_data_receipt_time(self):
        reporter = self.ready()
        reporter.stage("Fetching order book")
        view = self.view(reporter)
        self.assertEqual("healthy", view["state"])
        self.assertEqual("82550.27", view["price"]["value"])
        self.assertEqual(self.now.isoformat(), view["price"]["at"])
        self.assertEqual("0.02", view["market"]["spread"])
        self.assertEqual(0, view["heartbeatAgeSeconds"])
        self.assertEqual([reporter.path], list(self.path.iterdir()))

    def test_new_poll_heartbeat_does_not_make_an_old_price_fresh(self):
        reporter = self.ready()
        later = self.now + timedelta(seconds=60)
        with patch.object(telemetry, "timestamp", return_value=later.isoformat()):
            reporter.stage("Fetching BTC price")
        view = self.view(reporter, now=later)
        self.assertEqual("stale", view["state"])
        self.assertEqual(0, view["heartbeatAgeSeconds"])
        self.assertEqual(60, view["priceAgeSeconds"])

    def test_alive_process_with_old_heartbeat_is_not_reported_healthy(self):
        reporter = self.ready()
        self.assertEqual("stale", self.view(reporter, now=self.now + timedelta(seconds=46))["state"])

    def test_api_error_is_retained_after_matching_feed_recovers(self):
        reporter = self.ready()
        reporter.failure(ReadTimeout("order book timed out"), source="Kalshi", api=True)
        self.assertEqual("degraded", self.view(reporter)["state"])
        reporter.price("82551")
        self.assertTrue(self.view(reporter)["lastApiError"]["active"])
        reporter.market(ticker="TEST")
        reporter.decide("WAIT", "more than 5 minutes left")
        view = self.view(reporter)
        self.assertEqual("healthy", view["state"])
        self.assertFalse(view["lastApiError"]["active"])
        self.assertEqual("order book timed out", view["lastApiError"]["message"])
        self.assertIsNotNone(view["lastApiError"]["recoveredAt"])

    def test_stop_is_explicit_and_last_observation_is_preserved(self):
        reporter = self.ready()
        reporter.stop()
        with patch.object(telemetry, "process_alive", return_value=True):
            view = telemetry.runtime_status("btc15_paper", now=self.now)
        self.assertEqual("stopped", view["state"])
        self.assertEqual("TEST", view["market"]["ticker"])
        self.assertFalse(view["processAlive"])

    def test_restarted_pid_cannot_inherit_previous_runs_decision(self):
        reporter = self.ready()
        view = telemetry.runtime_status("btc15_paper", running=True, managed=True, pid=reporter.data["pid"] + 1, now=self.now)
        self.assertEqual("starting", view["state"])
        self.assertNotIn("decision", view)

    def test_independent_bot_files_and_terminal_process_detection(self):
        first = self.ready()
        second = self.ready("btc15_dual_paper")
        second.decide("WAIT", "spread wider than 3 cents")
        with patch.object(telemetry, "process_alive", return_value=True):
            view = telemetry.runtime_status("btc15_dual_paper", now=self.now)
        self.assertEqual("spread wider than 3 cents", view["decision"]["reason"])
        self.assertFalse(view["managed"])
        self.assertTrue(view["processAlive"])
        self.assertNotEqual(first.path, second.path)
        self.assertNotEqual(first.data["decision"], second.data["decision"])

    def test_unwritable_status_disk_does_not_raise_or_leave_partial_files(self):
        with patch.object(telemetry.os, "replace", side_effect=PermissionError("disk unavailable")):
            reporter = telemetry.BotTelemetry("btc15_paper")
            reporter.price("82500")
            reporter.failure(ValueError("test"), source="Bot")
            reporter.stop()
        self.assertEqual([], list(self.path.iterdir()))

    def test_corrupt_or_wrong_bot_snapshot_is_ignored(self):
        path = self.path / "btc15_paper.json"
        for value in ("{", json.dumps({"botId": "btc15_live"}), json.dumps({"botId": "btc15_paper", "price": "invalid"})):
            with self.subTest(value=value):
                path.write_text(value)
                self.assertIsNone(telemetry.read_snapshot("btc15_paper"))

    def test_future_or_naive_clock_does_not_appear_fresh(self):
        reporter = self.ready()
        for value in ((self.now + timedelta(hours=1)).isoformat(), "2026-11-04T20:00:00"):
            reporter.data["heartbeatAt"] = value
            reporter.save()
            self.assertEqual("starting", self.view(reporter)["state"])

    def test_cap_counts_both_live_bots_and_rejected_attempts_by_utc_date(self):
        reporter = self.ready("btc15_dual_live")
        reporter.data["settings"] = {"dailyLimit": 2}
        reporter.save()
        rows = [
            {"timestamp": "2026-11-04T01:00:00Z", "ticker": "OLD1", "bot_id": "btc15_live", "status": "REJECTED"},
            {"timestamp": "2026-11-04T02:00:00Z", "ticker": "TEST", "bot_id": "btc15_dual_live", "fill_status": "UNFILLED"},
            {"timestamp": "2026-11-03T23:59:59Z", "ticker": "YESTERDAY"},
        ]
        original = json.dumps(rows)
        result = dashboard.entry_diagnostics(self.view(reporter), rows, live=True, daily_limit=30, now=self.now)
        self.assertEqual(2, result["dailyAttempts"])
        self.assertIn("Daily live cap reached: 2/2 attempts (UTC)", result["blockers"])
        self.assertTrue(any("UNFILLED" in reason for reason in result["blockers"]))
        self.assertEqual(original, json.dumps(rows))

    def test_disabled_cap_still_shows_shared_attempt_count(self):
        result = dashboard.entry_diagnostics(self.view(self.ready()), [{"timestamp": self.now.isoformat()}], live=True, daily_limit=0, now=self.now)
        self.assertEqual(1, result["dailyAttempts"])
        self.assertFalse(any("cap reached" in reason for reason in result["blockers"]))

    def test_invalid_ledger_does_not_fabricate_daily_count(self):
        result = dashboard.entry_diagnostics(self.view(self.ready()), [{"timestamp": "broken", "ticker": "ORDER"}], live=True, daily_limit=30, now=self.now)
        self.assertIsNone(result["dailyAttempts"])
        self.assertTrue(any("cannot be verified" in reason for reason in result["blockers"]))

    def test_stopped_bot_does_not_show_historical_wait_as_current_blocker(self):
        reporter = self.ready()
        reporter.stop()
        result = dashboard.entry_diagnostics({**self.view(reporter), "state": "stopped"}, [])
        self.assertEqual(["Bot is stopped. Start it to evaluate new entries."], result["blockers"])

    def test_observing_strategy_and_duplicate_execution_does_not_add_orders(self):
        with (
            patch.multiple(bot, get_btc_price=DEFAULT, get_current_market=DEFAULT, get_seconds_remaining=DEFAULT,
                           get_orderbook=DEFAULT, log_market_data=DEFAULT, log_shadow_signal=DEFAULT,
                           place_live_trade=DEFAULT, record_paper_trade=DEFAULT) as mocks,
            patch("bot.time.sleep", side_effect=[None, None, KeyboardInterrupt]),
            redirect_stdout(io.StringIO()),
        ):
            mocks["get_btc_price"].side_effect = [82305, 82304, 82303]
            mocks["get_current_market"].return_value = {"ticker": "TEST", "floor_strike": "82323"}
            mocks["get_seconds_remaining"].return_value = 180
            mocks["get_orderbook"].return_value = {"orderbook_fp": {"yes_dollars": [["0.20", 10]], "no_dollars": [["0.78", 10]]}}
            mocks["record_paper_trade"].return_value = False
            bot.main(live_enabled=False, trade_budget="1")
        snapshot = telemetry.read_snapshot("btc15_paper")
        self.assertEqual("BLOCKED", snapshot["decision"]["action"])
        self.assertIn("Already entered", snapshot["decision"]["reason"])
        self.assertIsNotNone(snapshot["stoppedAt"])
        mocks["record_paper_trade"].assert_called_once()
        mocks["place_live_trade"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
