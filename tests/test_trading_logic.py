import csv
import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import paper_execution
import prediction_tracker
from bot import get_yes_quote
from strategy import calculate_edge, estimate_probability, make_decision


class PaperExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_trade_file = paper_execution.TRADE_FILE
        paper_execution.TRADE_FILE = os.path.join(self.tmpdir.name, "paper_trades.csv")
        self.addCleanup(setattr, paper_execution, "TRADE_FILE", self.original_trade_file)

    def read_rows(self):
        with open(paper_execution.TRADE_FILE, "r", newline="") as file:
            return list(csv.DictReader(file))

    def test_record_paper_trade_uses_canonical_schema_and_prevents_duplicates(self):
        recorded = paper_execution.record_paper_trade(
            ticker="KXBTC15M-TEST",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.58"),
            model_probability=Decimal("0.6596"),
            edge=Decimal("0.0796"),
            contracts=1,
        )
        duplicate = paper_execution.record_paper_trade(
            ticker="KXBTC15M-TEST",
            side="YES",
            prediction="UP",
            entry_price=Decimal("0.58"),
            model_probability=Decimal("0.6596"),
            edge=Decimal("0.0796"),
            contracts=1,
        )

        rows = self.read_rows()
        self.assertTrue(recorded)
        self.assertFalse(duplicate)
        self.assertEqual(1, len(rows))
        self.assertEqual(paper_execution.FIELDNAMES, list(rows[0].keys()))
        self.assertEqual("YES", rows[0]["side"])
        self.assertEqual("0.5800", rows[0]["entry_price"])
        self.assertEqual("0.5800", rows[0]["cost"])
        self.assertEqual("", rows[0]["actual_result"])
        self.assertEqual("", rows[0]["profit_loss"])
        self.assertEqual("", rows[0]["correct"])

    def test_settlement_updates_only_unsettled_rows_and_uses_purchased_side(self):
        paper_execution.write_trade_rows([
            {
                "timestamp": "t1",
                "ticker": "YES-WIN",
                "side": "YES",
                "prediction": "UP",
                "entry_price": "0.5800",
                "model_probability": "0.6596",
                "edge": "0.0796",
                "contracts": "1",
                "cost": "0.5800",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
            },
            {
                "timestamp": "t2",
                "ticker": "NO-WIN",
                "side": "NO",
                "prediction": "DOWN",
                "entry_price": "0.4600",
                "model_probability": "0.5416",
                "edge": "0.0816",
                "contracts": "1",
                "cost": "0.4600",
                "actual_result": "",
                "profit_loss": "",
                "correct": "",
            },
            {
                "timestamp": "t3",
                "ticker": "ALREADY",
                "side": "YES",
                "prediction": "UP",
                "entry_price": "0.2500",
                "model_probability": "0.7000",
                "edge": "0.4500",
                "contracts": "1",
                "cost": "0.2500",
                "actual_result": "NO",
                "profit_loss": "-0.2500",
                "correct": "False",
            },
        ])

        updated = paper_execution.update_paper_trade_results(
            lambda ticker: {"YES-WIN": "YES", "NO-WIN": "NO"}.get(ticker)
        )

        rows = {row["ticker"]: row for row in self.read_rows()}
        self.assertEqual(2, updated)
        self.assertEqual("0.4200", rows["YES-WIN"]["profit_loss"])
        self.assertEqual("True", rows["YES-WIN"]["correct"])
        self.assertEqual("0.5400", rows["NO-WIN"]["profit_loss"])
        self.assertEqual("True", rows["NO-WIN"]["correct"])
        self.assertEqual("-0.2500", rows["ALREADY"]["profit_loss"])


class StrategyTests(unittest.TestCase):
    def test_orderbook_quotes_use_dollar_probability_units(self):
        quote = get_yes_quote({
            "orderbook_fp": {
                "yes_dollars": [["0.42", 10]],
                "no_dollars": [["0.54", 10]],
            }
        })

        self.assertEqual(
            (
                Decimal("0.42"),
                Decimal("0.46"),
                Decimal("0.54"),
                Decimal("0.58"),
                Decimal("0.04"),
            ),
            quote,
        )

    def test_edge_uses_dollar_probability_units(self):
        self.assertEqual(
            Decimal("0.0796"),
            calculate_edge(Decimal("0.6596"), Decimal("0.58")),
        )

    def test_down_probability_increases_with_movement_and_can_buy_no(self):
        probability = estimate_probability("DOWN", Decimal("-0.0408"))
        self.assertEqual(Decimal("0.5816"), probability)
        self.assertEqual(
            "BUY NO",
            make_decision("DOWN", probability, Decimal("0.60"), Decimal("0.46")),
        )


class PredictionTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.original_data_file = prediction_tracker.DATA_FILE
        prediction_tracker.DATA_FILE = os.path.join(self.tmpdir.name, "market_data.csv")
        self.addCleanup(setattr, prediction_tracker, "DATA_FILE", self.original_data_file)

    def test_completed_predictions_keep_first_actionable_signal_per_ticker(self):
        with open(prediction_tracker.DATA_FILE, "w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["timestamp", "ticker", "signal"])
            writer.writeheader()
            writer.writerow({"timestamp": "1", "ticker": "T1", "signal": "NEUTRAL"})
            writer.writerow({"timestamp": "2", "ticker": "T1", "signal": "UP"})
            writer.writerow({"timestamp": "3", "ticker": "T1", "signal": "DOWN"})
            writer.writerow({"timestamp": "4", "ticker": "T2", "signal": "DOWN"})

        self.assertEqual(
            {"T1": "UP", "T2": "DOWN"},
            prediction_tracker.get_completed_predictions(),
        )


if __name__ == "__main__":
    unittest.main()
