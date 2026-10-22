import csv
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dashboard
import kalshi_api
import live_execution


def trade(**overrides):
    row = {field: "" for field in live_execution.FIELDNAMES}
    row.update({
        "timestamp": "2026-10-17T01:00:00+00:00",
        "trade_id": "live-test",
        "ticker": "KXBTC15M-TEST",
        "side": "YES",
        "entry_price": "0.9000",
        "contracts": "1",
        "submitted_count": "1",
        "filled_count": "0.00",
        "order_id": "order-test",
    })
    row.update(overrides)
    return row


def fill(**overrides):
    row = {
        "fill_id": "fill-test",
        "order_id": "order-test",
        "ticker": "KXBTC15M-TEST",
        "count_fp": "1.00",
        "yes_price_dollars": "0.8000",
        "no_price_dollars": "0.2000",
        "fee_cost": "0.0200",
    }
    row.update(overrides)
    return row


class LiveReportingTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.path = Path(self.tmpdir.name) / "live_trades.csv"
        patcher = patch.object(live_execution, "LIVE_TRADE_FILE", str(self.path))
        patcher.start()
        self.addCleanup(patcher.stop)

    def reconcile(self, rows, fills, result="YES"):
        live_execution.write_live_trade_rows(rows)
        count = live_execution.update_live_trade_results(
            lambda ticker: result,
            get_fills_fn=lambda order_id, **kwargs: fills,
        )
        return count, live_execution.read_live_trade_rows()

    def test_verified_profit_uses_fill_price_and_fees_instead_of_limit(self):
        count, rows = self.reconcile([trade()], [fill()])
        self.assertEqual(1, count)
        self.assertEqual("0.1800", rows[0]["profit_loss"])
        self.assertEqual("0.8000", rows[0]["fill_cost"])
        self.assertEqual("0.0200", rows[0]["fees_paid"])
        self.assertEqual("ACTUAL", rows[0]["pnl_basis"])

    def test_no_loss_uses_actual_partial_fill_cost_and_fees(self):
        count, rows = self.reconcile(
            [trade(side="NO")],
            [fill(count_fp="0.25", no_price_dollars="0.7000", fee_cost="0.0100")],
        )
        self.assertEqual(1, count)
        self.assertEqual("0.25", rows[0]["filled_count"])
        self.assertEqual("PARTIAL", rows[0]["fill_status"])
        self.assertEqual("-0.1850", rows[0]["profit_loss"])

    def test_multiple_fills_are_summed_at_each_execution_price(self):
        count, rows = self.reconcile([trade()], [
            fill(fill_id="first", count_fp="0.50", yes_price_dollars="0.7800", fee_cost="0.0100"),
            fill(fill_id="second", count_fp="0.50", yes_price_dollars="0.8000", fee_cost="0.0100"),
        ])
        self.assertEqual(1, count)
        self.assertEqual("0.7900", rows[0]["fill_cost"])
        self.assertEqual("0.1900", rows[0]["profit_loss"])

    def test_unfilled_orders_have_zero_cashflow_and_no_win_or_loss(self):
        live_execution.write_live_trade_rows([trade()])
        result_lookup = Mock()
        self.assertEqual(0, live_execution.update_live_trade_results(
            result_lookup, get_fills_fn=lambda order_id, **kwargs: [],
        ))
        row = live_execution.read_live_trade_rows()[0]
        self.assertEqual("UNFILLED", row["fill_status"])
        self.assertEqual("0.0000", row["profit_loss"])
        self.assertEqual("", row["actual_result"])
        self.assertEqual("", row["correct"])
        result_lookup.assert_not_called()

    def test_missing_fee_does_not_produce_guessed_net_profit(self):
        count, rows = self.reconcile([trade()], [fill(fee_cost=None)])
        self.assertEqual(0, count)
        self.assertEqual("FILLED", rows[0]["fill_status"])
        self.assertEqual("", rows[0]["profit_loss"])
        self.assertIn("fees unavailable", rows[0]["sync_error"])

    def test_pending_market_keeps_pnl_blank_and_can_settle_on_later_check(self):
        count, rows = self.reconcile([trade()], [fill()], result=None)
        self.assertEqual(0, count)
        self.assertEqual("", rows[0]["profit_loss"])
        count, rows = self.reconcile(rows, [fill()])
        self.assertEqual(1, count)
        self.assertEqual("0.1800", rows[0]["profit_loss"])

    def test_lookup_failure_keeps_existing_fill_information(self):
        row = trade(filled_count="1", status="executed")
        live_execution.write_live_trade_rows([row])
        with redirect_stdout(io.StringIO()):
            count = live_execution.update_live_trade_results(
                lambda ticker: "YES", get_fills_fn=Mock(side_effect=TimeoutError("lookup failed")),
            )
        self.assertEqual(0, count)
        result = live_execution.read_live_trade_rows()[0]
        self.assertEqual("1", result["filled_count"])
        self.assertEqual("", result["profit_loss"])
        self.assertEqual("lookup failed", result["sync_error"])

    def test_missing_history_does_not_erase_a_previously_recorded_fill(self):
        with redirect_stdout(io.StringIO()):
            count, rows = self.reconcile([trade(filled_count="1")], [])
        self.assertEqual(0, count)
        self.assertEqual("1", rows[0]["filled_count"])
        self.assertEqual("", rows[0]["profit_loss"])
        self.assertIn("unverified", rows[0]["sync_error"])

    def test_reconciliation_preserves_order_appended_during_lookup(self):
        live_execution.write_live_trade_rows([trade()])

        def get_fills(order_id, **kwargs):
            live_execution.append_live_trade_row(trade(trade_id="live-new", order_id="order-new"))
            return [fill()]

        live_execution.update_live_trade_results(lambda ticker: "YES", get_fills_fn=get_fills)
        rows = live_execution.read_live_trade_rows()
        self.assertEqual(["live-test", "live-new"], [row["trade_id"] for row in rows])
        self.assertEqual("0.1800", rows[0]["profit_loss"])

    def test_legacy_csv_migration_preserves_original_backup_including_bad_rows(self):
        old_fields = [field for field in live_execution.FIELDNAMES if field not in (
            "trade_id", "fill_cost", "fees_paid", "pnl_basis", "sync_error",
        )]
        with self.path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=old_fields)
            writer.writeheader()
            writer.writerow({key: value for key, value in trade().items() if key in old_fields})
            file.write("broken,row\n")
        original = self.path.read_bytes()
        rows = live_execution.read_live_trade_rows()
        backups = list(self.path.parent.glob("live_trades.csv.backup-*"))
        self.assertEqual(1, len(backups))
        self.assertEqual(original, backups[0].read_bytes())
        self.assertEqual(2, len(rows))
        self.assertTrue(rows[1]["error"])

    def test_dashboard_counts_filled_trades_and_keeps_other_orders_in_history(self):
        rows = [
            trade(trade_id="filled", filled_count="1", actual_result="YES", profit_loss="0.1800", fill_cost="0.8000"),
            trade(trade_id="unfilled", actual_result="YES", profit_loss="0.0000"),
            trade(trade_id="unknown", filled_count=""),
            trade(trade_id="rejected", error="bad request"),
        ]
        stats = dashboard.live_trade_stats(rows)
        self.assertEqual(1, stats["total"])
        self.assertEqual(1, stats["settled"])
        self.assertEqual(100, stats["winRate"])
        self.assertEqual("0.1800", stats["profitLoss"])
        self.assertEqual("0.8000", stats["totalInvested"])
        self.assertEqual(4, len(stats["recent"]))


class FillHistoryTests(unittest.TestCase):
    def test_fixed_point_counts_are_recognized_and_unknown_is_not_assumed_filled(self):
        self.assertEqual("0.25", live_execution.normalize_filled_count({"fill_count_fp": "0.25"}, 1))
        self.assertEqual("", live_execution.normalize_filled_count({"order_id": "order-test"}, 1))

    def test_fill_history_paginates_both_sources_and_filters_unrelated_orders(self):
        expected = fill()
        with patch("kalshi_api.request", side_effect=[
            {"fills": [expected], "cursor": "page2"},
            {"fills": [], "cursor": ""},
            {"fills": [expected, fill(fill_id="unrelated", order_id="other")], "cursor": ""},
        ]) as request:
            rows = kalshi_api.get_order_fills("order-test", ticker="KXBTC15M-TEST")
        self.assertEqual([expected], rows)
        self.assertEqual(3, request.call_count)
        self.assertTrue(all(item.args[0] == "GET" for item in request.call_args_list))
        self.assertEqual("page2", request.call_args_list[1].kwargs["params"]["cursor"])
        self.assertNotIn("order_id", request.call_args_list[2].kwargs["params"])


if __name__ == "__main__":
    unittest.main()
