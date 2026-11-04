import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import kalshi_api
import live_execution


class LiveBlockerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = Path(self.tmpdir.name) / "live.csv"
        patcher = patch.object(live_execution, "LIVE_TRADE_FILE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.now = datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc)

    def row(self, **overrides):
        row = {key: "" for key in live_execution.FIELDNAMES}
        row.update({
            "timestamp": self.now.isoformat(),
            "trade_id": "live-existing",
            "ticker": "KXBTC15M-EXISTING",
            "side": "YES",
            "prediction": "UP",
            "contracts": "1",
            "submitted_count": "1",
            "entry_price": "0.8000",
            "filled_count": "0.00",
            "status": "",
        })
        row.update(overrides)
        return row

    def test_quarantined_non_order_fragments_do_not_break_risk_checks_or_change_csv(self):
        live_execution.write_live_trade_rows([
            self.row(),
            self.row(timestamp="e", ticker="error", side="", contracts="", submitted_count="", filled_count="", error="Malformed legacy row; see CSV backup"),
            self.row(timestamp="", ticker="live-old-fragment", side="", contracts="", submitted_count="", filled_count="", error="Malformed legacy row; see CSV backup"),
        ])
        original = self.path.read_bytes()
        with self.assertWarnsRegex(RuntimeWarning, "2 quarantined non-order fragments"):
            self.assertEqual(1, live_execution.live_trade_count_today(now=self.now))
        self.assertEqual(original, self.path.read_bytes())

    def test_suspicious_order_dates_still_block_instead_of_bypassing_limits(self):
        for timestamp in ("e", "", "2026-10-28T01:00:00"):
            with self.subTest(timestamp=timestamp):
                live_execution.write_live_trade_rows([self.row(timestamp=timestamp, order_id="real-order")])
                with self.assertRaisesRegex(RuntimeError, "invalid timestamp"):
                    live_execution.live_trade_count_today(now=self.now)
                create = Mock()
                with self.assertRaisesRegex(RuntimeError, "invalid timestamp"):
                    live_execution.place_live_trade(
                        ticker="NEW", side="YES", prediction="UP", entry_price="0.80", create_order_fn=create,
                    )
                create.assert_not_called()

    def test_date_is_normalized_to_utc_for_daily_cap(self):
        live_execution.write_live_trade_rows([self.row(timestamp="2026-10-27T21:00:00-04:00")])
        self.assertEqual(1, live_execution.live_trade_count_today(now=self.now))

    def test_shifted_quarantined_order_counts_as_attempt_but_not_guessed_pnl(self):
        live_execution.write_live_trade_rows([self.row(
            ticker="live-old-id", side="KXBTC15M-OLD", profit_loss="YES",
            error="Malformed legacy row; see CSV backup",
        )])
        self.assertEqual(1, live_execution.live_trade_count_today(now=self.now))
        self.assertEqual(0, live_execution.realized_live_profit_loss_today(now=self.now))

    def test_invalid_real_order_pnl_remains_a_blocker(self):
        for profit in ("NaN", "Infinity", "not-money"):
            with self.subTest(profit=profit):
                live_execution.write_live_trade_rows([self.row(profit_loss=profit)])
                with self.assertRaisesRegex(RuntimeError, "invalid recorded P/L"):
                    live_execution.realized_live_profit_loss_today(now=self.now)

    def test_duplicate_prints_existing_outcome_without_retrying_order(self):
        live_execution.write_live_trade_rows([self.row(bot_id="btc15_live")])
        create = Mock()
        output = io.StringIO()
        with redirect_stdout(output):
            result = live_execution.place_live_trade(
                ticker="KXBTC15M-EXISTING", side="NO", prediction="DOWN", entry_price="0.80",
                bot_id="btc15_dual_live", create_order_fn=create,
            )
        self.assertFalse(result)
        self.assertIn("LIVE ENTRY SKIPPED", output.getvalue())
        self.assertIn("btc15_live | UNFILLED", output.getvalue())
        create.assert_not_called()

    def test_zero_fill_is_explicit_in_log_and_never_claimed_as_purchase(self):
        create = Mock(return_value={"order_id": "order-zero", "fill_count": "0.00", "remaining_count": "0.00"})
        output = io.StringIO()
        with redirect_stdout(output):
            live_execution.place_live_trade(
                ticker="ZERO", side="YES", prediction="UP", entry_price="0.80", create_order_fn=create,
            )
        self.assertIn("LIVE ORDER UNFILLED", output.getvalue())
        self.assertIn("filled=0.00", output.getvalue())
        self.assertEqual("UNFILLED", live_execution.read_live_trade_rows()[0]["fill_status"])

    def test_known_http_rejection_is_distinguished_from_uncertain_timeout(self):
        response = requests.Response()
        response.status_code = 400
        error = requests.HTTPError("invalid request", response=response)
        with self.assertRaises(requests.HTTPError):
            live_execution.place_live_trade(
                ticker="REJECT", side="YES", prediction="UP", entry_price="0.80",
                create_order_fn=Mock(side_effect=error),
            )
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("REJECTED", row["status"])
        self.assertEqual("REJECTED", row["fill_status"])


class ApiErrorDetailsTests(unittest.TestCase):
    def test_error_includes_exchange_validation_message_not_auth_headers(self):
        for nested in (True, False):
            body = {"code": "invalid_parameters", "message": "invalid price increment", "details": "price"}
            response = requests.Response()
            response.status_code = 400
            response.url = "https://external-api.kalshi.com/trade-api/v2/portfolio/events/orders"
            response._content = json.dumps({"error": body} if nested else body).encode()
            with (
                self.subTest(nested=nested),
                patch("kalshi_api.get_headers", return_value={"KALSHI-ACCESS-KEY": "secret-test-key"}),
                patch("kalshi_api.requests.request", return_value=response) as transport,
                self.assertRaises(requests.HTTPError) as caught,
            ):
                kalshi_api.request("POST", "/trade-api/v2/portfolio/events/orders", json={"ticker": "TEST"})
            self.assertIn("invalid price increment", str(caught.exception))
            self.assertIn("invalid_parameters", str(caught.exception))
            self.assertNotIn("secret-test-key", str(caught.exception))
            transport.assert_called_once()


if __name__ == "__main__":
    unittest.main()
