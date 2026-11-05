import csv
import os
from datetime import datetime, timezone

from outcome_tracker import get_market_result, prediction_was_correct
from live_execution import update_live_trade_results
from paper_execution import DIRECTION_TRADE_FILE, DUAL_TRADE_FILE, update_paper_trade_results
from run_lock import RunLock


DATA_FILE = "data/market_data.csv"
RESULTS_FILE = "data/prediction_results.csv"


def initialize_results_file():
    os.makedirs("data", exist_ok=True)

    if os.path.exists(RESULTS_FILE):
        return

    with open(RESULTS_FILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "timestamp",
            "ticker",
            "prediction",
            "actual_result",
            "correct",
        ])


def get_completed_predictions(*, should_stop=None):
    if not os.path.exists(DATA_FILE):
        return {}

    predictions = {}

    with open(DATA_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            if should_stop is not None and should_stop():
                break
            signal = row["signal"]
            ticker = row["ticker"]

            if signal not in ["UP", "DOWN"]:
                continue

            if ticker not in predictions:
                predictions[ticker] = signal

    return predictions


def get_already_tracked():
    if not os.path.exists(RESULTS_FILE):
        return set()

    tracked = set()

    with open(RESULTS_FILE, "r", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            tracked.add(row["ticker"])

    return tracked


def track_completed_markets(*, get_result_fn=None, on_error=None, should_stop=None, on_progress=None):
    initialize_results_file()

    predictions = get_completed_predictions(should_stop=should_stop)
    already_tracked = get_already_tracked()

    new_results = 0
    get_result_fn = get_result_fn or get_market_result

    for ticker, prediction in predictions.items():
        if should_stop is not None and should_stop():
            break

        if ticker in already_tracked:
            continue

        try:
            result = get_result_fn(ticker)
        except Exception as e:
            message = f"Could not check {ticker}: {e}"
            print(message, flush=True)
            if on_error is not None:
                on_error(message)
            if on_progress is not None:
                on_progress(0)
            continue

        if result not in ["YES", "NO"]:
            if on_progress is not None:
                on_progress(0)
            continue

        correct = prediction_was_correct(prediction, result)

        with open(RESULTS_FILE, "a", newline="") as file:
            writer = csv.writer(file)

            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                ticker,
                prediction,
                result,
                correct,
            ])

        print(
            f"{ticker} | "
            f"Prediction: {prediction} | "
            f"Result: {result} | "
            f"{'CORRECT' if correct else 'INCORRECT'}",
            flush=True,
        )

        new_results += 1
        if on_progress is not None:
            on_progress(1)

    return new_results


def refresh_results(*, should_stop=None, on_progress=None):
    summary = {
        "paperSettled": 0,
        "dualPaperSettled": 0,
        "directionPaperSettled": 0,
        "liveSettled": 0,
        "predictionsRecorded": 0,
        "errors": [],
        "errorCount": 0,
        "checked": 0,
        "stopped": False,
    }
    results = {}

    def publish():
        if on_progress is not None:
            on_progress({**summary, "errors": list(summary["errors"])})

    def progress(stage, settled):
        summary[stage] += settled
        summary["checked"] += 1
        publish()

    def get_result(ticker):
        if ticker not in results:
            try:
                results[ticker] = get_market_result(ticker)
            except Exception as exc:
                results[ticker] = exc
        result = results[ticker]
        if isinstance(result, Exception):
            raise result
        return result

    def report_error(stage, message):
        summary["errorCount"] += 1
        if len(summary["errors"]) < 50:
            summary["errors"].append({"stage": stage, "message": str(message)[:1000]})
        publish()

    # The CLI and dashboard share this lock, independently of all bot locks.
    with RunLock("prediction_tracker"):
        tasks = (
            ("liveSettled", lambda **kwargs: update_live_trade_results(get_result, **kwargs)),
            ("paperSettled", lambda **kwargs: update_paper_trade_results(get_result, **kwargs)),
            ("dualPaperSettled", lambda **kwargs: update_paper_trade_results(get_result, trade_file=DUAL_TRADE_FILE, **kwargs)),
            ("directionPaperSettled", lambda **kwargs: update_paper_trade_results(get_result, trade_file=DIRECTION_TRADE_FILE, **kwargs)),
            ("predictionsRecorded", lambda **kwargs: track_completed_markets(get_result_fn=get_result, **kwargs)),
        )
        try:
            for stage, task in tasks:
                if should_stop is not None and should_stop():
                    break
                try:
                    summary[stage] = task(
                        on_error=lambda message: report_error(stage, message),
                        should_stop=should_stop,
                        on_progress=lambda settled: progress(stage, settled),
                    )
                except Exception as exc:
                    report_error(stage, exc)
                    print(f"Could not refresh {stage}: {exc}", flush=True)
        except KeyboardInterrupt:
            summary["stopped"] = True
        if should_stop is not None and should_stop():
            summary["stopped"] = True
        publish()

    return summary


def main():
    print("Updating fills, fees, and completed BTC markets...", flush=True)
    try:
        summary = refresh_results()
    except RuntimeError as exc:
        print(f"Refresh not started: {exc}", flush=True)
        return 1

    print()
    print(f"Paper trades settled: {summary['paperSettled']}")
    print(f"YES/NO paper trades settled: {summary['dualPaperSettled']}")
    print(f"Direction paper trades settled: {summary.get('directionPaperSettled', 0)}")
    print(f"Live trades settled: {summary['liveSettled']}")
    print(f"New results recorded: {summary['predictionsRecorded']}")
    print(f"Checks needing attention: {summary['errorCount']}")
    if summary["stopped"]:
        print("Refresh stopped. Saved updates were kept; unchecked trades are unchanged.", flush=True)
        return 130
    return 1 if summary["errorCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
