import copy
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dashboard
from performance_analytics import build_performance


NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def trade(identity="one", **overrides):
    row = dict(
        trade_id=identity, timestamp="2026-11-04T14:00:00+00:00", ticker="BTC-TEST",
        side="YES", actual_result="YES", profit_loss="0.1800", cost="0.8000",
        filled_count="1.00", fill_cost="0.8000", fees_paid="0.0200", pnl_basis="ACTUAL",
    )
    row.update(overrides)
    return row


class PerformanceAnalyticsTests(unittest.TestCase):
    def test_decimal_daily_totals_are_exact_and_inputs_are_unchanged(self):
        rows = [trade("a", profit_loss="0.1"), trade("b", profit_loss="0.2"),
                trade("c", profit_loss="-0.15"), trade("d", profit_loss="0")]
        original = copy.deepcopy(rows)
        result = build_performance(rows, now=NOW)
        day = result["days"][0]
        self.assertEqual("0.1500", day["profitLoss"])
        self.assertEqual("0.3000", day["grossProfit"])
        self.assertEqual("0.1500", day["grossLoss"])
        self.assertEqual((2, 1, 1), (day["profitable"], day["losing"], day["flat"]))
        self.assertEqual(4, day["trades"])
        self.assertIsNone(day["fees"])
        self.assertEqual(original, rows)

    def test_new_york_dates_do_not_use_utc_midnight(self):
        result = build_performance([
            trade("a", timestamp="2026-11-04T00:30:00Z", profit_loss="1"),
            trade("b", timestamp="2026-11-04T14:00:00Z", profit_loss="2"),
        ], now=NOW)
        self.assertEqual(["2026-11-03", "2026-11-04"], [day["date"] for day in result["days"]])
        self.assertEqual(["1.0000", "3.0000"], [day["cumulative"] for day in result["days"]])
        self.assertEqual("America/New_York", result["timezone"])

    def test_dst_repeated_hour_stays_on_one_calendar_day(self):
        result = build_performance([
            trade("a", timestamp="2026-11-01T01:30:00-04:00", profit_loss="1"),
            trade("b", timestamp="2026-11-01T01:30:00-05:00", profit_loss="2"),
        ], now=NOW)
        self.assertEqual(1, len(result["days"]))
        self.assertEqual("2026-11-01", result["days"][0]["date"])
        self.assertEqual(2, result["days"][0]["trades"])

    def test_intraday_extremes_and_drawdown_follow_trade_order_not_csv_order(self):
        result = build_performance([
            trade("c", timestamp="2026-11-04T16:00:00Z", profit_loss="-40"),
            trade("a", timestamp="2026-11-04T14:00:00Z", profit_loss="-20"),
            trade("b", timestamp="2026-11-04T15:00:00Z", profit_loss="50"),
        ], now=NOW)
        day = result["days"][0]
        self.assertEqual("-10.0000", day["profitLoss"])
        self.assertEqual("30.0000", day["peak"])
        self.assertEqual("-20.0000", day["trough"])
        self.assertEqual("40.0000", day["drawdown"])

    def test_live_uses_verified_net_pnl_without_subtracting_fees_twice(self):
        result = build_performance([trade()], kind="live", now=NOW)
        self.assertEqual("0.1800", result["days"][0]["profitLoss"])
        self.assertEqual("0.0200", result["days"][0]["fees"])
        self.assertEqual("0.8000", result["days"][0]["invested"])

    def test_pending_unfilled_rejected_and_estimated_live_rows_are_not_profits(self):
        rows = [
            trade("good"), trade("unfilled", filled_count="0", profit_loss="100"),
            trade("rejected", error="rejected", profit_loss="100"),
            trade("open", actual_result="", profit_loss=""),
            trade("missing-fees", fees_paid="", profit_loss="100"),
            trade("estimated", pnl_basis="", profit_loss="100"),
        ]
        result = build_performance(rows, kind="live", now=NOW)
        self.assertEqual(1, result["days"][0]["trades"])
        self.assertEqual("0.1800", result["days"][0]["profitLoss"])
        self.assertEqual(3, result["pending"])

    def test_duplicate_live_order_id_is_counted_once(self):
        result = build_performance([
            trade("a", order_id="same"), trade("b", order_id="same"),
        ], kind="live", now=NOW)
        self.assertEqual(1, result["days"][0]["trades"])
        self.assertEqual(1, result["excluded"]["duplicates"])

    def test_older_pending_copy_does_not_hide_verified_result(self):
        result = build_performance([
            trade("a", order_id="same", actual_result="", profit_loss=""),
            trade("b", order_id="same"),
        ], kind="live", now=NOW)
        self.assertEqual(1, result["days"][0]["trades"])
        self.assertEqual(0, result["pending"])

    def test_bad_dates_and_nonfinite_pnl_are_reported_not_graphed_as_zero(self):
        rows = [trade("bad-date", timestamp="bad"), trade("naive", timestamp="2026-11-04T12:00:00"),
                trade("future", timestamp="2026-11-10T14:00:00Z"),
                trade("nan", profit_loss="NaN"), trade("inf", profit_loss="Infinity"),
                trade("missing", profit_loss="")]
        result = build_performance(rows, now=NOW)
        self.assertEqual([], result["days"])
        self.assertEqual(3, result["excluded"]["invalidDate"])
        self.assertEqual(3, result["excluded"]["invalidProfitLoss"])

    def test_missing_cost_preserves_pnl_but_does_not_invent_roi_basis(self):
        result = build_performance([trade(cost="")], now=NOW)
        self.assertEqual("0.1800", result["days"][0]["profitLoss"])
        self.assertIsNone(result["days"][0]["invested"])

    def test_scalp_counts_closed_positions_on_close_date_not_open_events(self):
        result = build_performance([
            trade("scalp-1", event="OPEN", timestamp="2026-11-03T14:00:00Z", profit_loss=""),
            trade("scalp-1", event="CLOSE", opened_at="2026-11-03T14:00:00Z", closed_at="2026-11-04T14:00:00Z", profit_loss="0.25"),
            trade("scalp-1", event="CLOSE", closed_at="2026-11-04T14:00:00Z", profit_loss="0.25"),
            trade("scalp-open", event="OPEN", profit_loss=""),
            trade("junk", event="OPEN", profit_loss=""),
        ], kind="scalp", now=NOW)
        self.assertEqual("close", result["dateBasis"])
        self.assertEqual("2026-11-04", result["days"][0]["date"])
        self.assertEqual("0.2500", result["days"][0]["profitLoss"])
        self.assertEqual(1, result["pending"])
        self.assertEqual(1, result["excluded"]["duplicates"])

    def test_live_bot_analytics_remain_isolated(self):
        rows = [trade("a", bot_id="btc15_live"), trade("b", bot_id="btc15_dual_live", profit_loss="20")]
        first = dashboard.live_trade_stats(rows, bot_id="btc15_live")["performance"]
        second = dashboard.live_trade_stats(rows, bot_id="btc15_dual_live")["performance"]
        self.assertEqual("0.1800", first["days"][0]["profitLoss"])
        self.assertEqual("20.0000", second["days"][0]["profitLoss"])

    def test_every_bot_payload_includes_independent_analytics_even_without_data(self):
        with patch.object(dashboard, "read_csv", return_value=[]):
            result = dashboard.build_payload()
        for name in ("paper", "dualPaper", "live", "dualLive", "scalp"):
            self.assertEqual([], result[name]["performance"]["days"])
        self.assertEqual("live", result["dualLive"]["performance"]["kind"])


if __name__ == "__main__":
    unittest.main()
