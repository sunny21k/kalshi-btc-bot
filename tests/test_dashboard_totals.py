import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import dashboard


class DashboardTradedTotalTests(unittest.TestCase):
    def test_paper_total_includes_old_and_new_sizes_and_unsettled_entries(self):
        stats = dashboard.trade_stats([
            {"side": "YES", "cost": "100.0000", "contracts": "125", "actual_result": "YES", "profit_loss": "25.0000"},
            {"side": "NO", "cost": "99.6000", "contracts": "120", "actual_result": "", "profit_loss": ""},
            {"side": "NO", "cost": "0.8000", "contracts": "1", "actual_result": "NO", "profit_loss": "0.2000"},
            {"cost": "1000.0000", "error": "invalid row"},
        ], cost_field="cost")

        self.assertEqual("200.4000", stats["totalTraded"])
        self.assertEqual("100.8000", stats["totalInvested"])
        self.assertEqual("25.2000", stats["profitLoss"])
        self.assertEqual(25, stats["roi"])
        self.assertEqual(3, stats["total"])

    def test_unsettled_entries_count_as_traded_without_creating_settled_roi(self):
        stats = dashboard.trade_stats([
            {"cost": "99.6000", "actual_result": ""},
        ], cost_field="cost")
        self.assertEqual("99.6000", stats["totalTraded"])
        self.assertEqual("0.0000", stats["totalInvested"])
        self.assertIsNone(stats["roi"])

    def test_empty_history_has_zero_total(self):
        self.assertEqual("0.0000", dashboard.trade_stats([], cost_field="cost")["totalTraded"])
        self.assertEqual("0.0000", dashboard.live_trade_stats([])["totalTraded"])
        self.assertEqual("0.0000", dashboard.scalp_stats([])["totalInvested"])

    def test_live_total_uses_fill_cost_including_partial_unsettled_orders(self):
        stats = dashboard.live_trade_stats([
            {"side": "YES", "filled_count": "1", "fill_cost": "0.8000", "max_cost": "0.9000", "actual_result": "YES", "profit_loss": "0.1800"},
            {"side": "NO", "filled_count": "0.25", "fill_cost": "0.1750", "max_cost": "0.8000", "actual_result": ""},
            {"side": "YES", "filled_count": "0", "max_cost": "100.0000"},
            {"side": "NO", "filled_count": "", "max_cost": "100.0000"},
            {"side": "YES", "filled_count": "1", "fill_cost": "100.0000", "error": "rejected"},
        ])

        self.assertEqual("0.9750", stats["totalTraded"])
        self.assertEqual("0.8000", stats["totalInvested"])
        self.assertEqual(2, stats["total"])

    def test_scalp_total_counts_entry_cost_once_not_again_at_close(self):
        stats = dashboard.scalp_stats([
            {"trade_id": "scalp-closed", "event": "OPEN", "cost": "100.0000"},
            {"trade_id": "scalp-closed", "event": "CLOSE", "cost": "100.0000", "profit_loss": "1.0000"},
            {"trade_id": "scalp-open", "event": "OPEN", "cost": "99.6000"},
            {"trade_id": "broken", "event": "OPEN", "cost": "1000.0000"},
            {"trade_id": "scalp-invalid", "event": "OPEN", "cost": "1000.0000", "error": "invalid row"},
        ])

        self.assertEqual("199.6000", stats["totalInvested"])
        self.assertEqual(2, stats["total"])
        self.assertEqual(1, stats["open"])


if __name__ == "__main__":
    unittest.main()
