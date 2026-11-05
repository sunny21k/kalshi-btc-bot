import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import paper_execution
from entry_context import make_entry_context
from trade_direction_audit import audit_trades, write_report


class DirectionAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.trades = self.root / "trades.csv"
        self.market = self.root / "market.csv"
        self.trade = dict(timestamp="2026-11-05T20:00:01+00:00", trade_id="paper-1", ticker="TEST", side="NO", entry_price="0.80", seconds_remaining="180.1234")
        self.sample = dict(timestamp="2026-11-05T20:00:00+00:00", ticker="TEST", btc_price="90000", btc_change="0.01", signal="DOWN", yes_bid="0.20", yes_ask="0.22", seconds_remaining="180.12342")

    def write(self, path, rows):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with path.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def audit(self, samples, trades=None):
        self.write(self.trades, trades or [self.trade])
        self.write(self.market, samples)
        before = {path: path.read_bytes() for path in (self.trades, self.market)}
        report = audit_trades([self.trades], [self.market])
        for path, contents in before.items():
            self.assertEqual(contents, path.read_bytes())
        return report

    def test_uses_observed_btc_change_not_prediction_and_marks_inference(self):
        row = self.audit([self.sample])[0]
        self.assertEqual("UP", row["entry_direction"])
        self.assertEqual("INFERRED", row["entry_direction_basis"])
        self.assertEqual("OPPOSITE", row["entry_direction_match"])
        self.assertEqual("1.0000", row["match_offset_seconds"])

    def test_conflicting_shared_observations_are_uncertain(self):
        row = self.audit([self.sample, {**self.sample, "btc_change": "-0.01"}])[0]
        self.assertEqual("AMBIGUOUS", row["entry_direction_basis"])
        self.assertEqual("UNKNOWN", row["entry_direction"])

    def test_future_stale_wrong_quote_and_wrong_countdown_rows_cannot_be_used(self):
        for changes in ({"timestamp": "2026-11-05T20:00:02+00:00"},
                        {"timestamp": "2026-11-05T19:59:58+00:00"},
                        {"yes_bid": "0.21"}, {"seconds_remaining": "180.5"}, {"btc_change": "NaN"}):
            self.assertEqual("UNKNOWN", self.audit([{**self.sample, **changes}])[0]["entry_direction_basis"])

    def test_flat_is_not_falsely_classified_as_a_match_and_unfilled_orders_are_skipped(self):
        row = self.audit([{**self.sample, "btc_change": "0"}])[0]
        self.assertEqual("FLAT", row["entry_direction_match"])
        rows = self.audit([self.sample], trades=[{**self.trade, "filled_count": "0"}])
        self.assertEqual([], rows)

    def test_recorded_snapshot_overrides_inference_and_survives_settlement(self):
        context = make_entry_context([940, 938, 936, 934], side="NO", bot_id="btc15_direction_paper", observed_at=self.sample["timestamp"])
        paper_execution.record_paper_trade(ticker="TEST", side="NO", prediction="DOWN", entry_price="0.80", model_probability="0.8", edge="0", trade_file=self.trades, entry_context=context)
        paper_execution.update_paper_trade_results(lambda _: "NO", trade_file=self.trades)
        self.write(self.market, [self.sample])
        row = audit_trades([self.trades], [self.market])[0]
        self.assertEqual("RECORDED", row["entry_direction_basis"])
        self.assertEqual("DOWN", row["entry_direction"])
        self.assertEqual("MATCH", row["entry_direction_match"])
        output = self.root / "report.csv"
        write_report([row], output)
        with output.open(newline="") as file:
            self.assertEqual("RECORDED", next(csv.DictReader(file))["entry_direction_basis"])


if __name__ == "__main__":
    unittest.main()
