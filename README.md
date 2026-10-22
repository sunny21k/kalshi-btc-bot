# kalshi-btc-bot

## YES/NO Paper Bot

Run from the project root with the virtual environment active:

```sh
PYTHONPATH=src python src/dual_paper_bot.py
```

This separate paper-only bot buys YES above the BTC target or NO below it:

- Within 4 minutes of close, at least $10 from the target.
- Within 5 minutes of close, at least $50 from the target.

It keeps the existing confirmation, momentum, spread, and entry-price checks,
skips the final 30 seconds, and makes at most one trade per market. Both
15-minute paper bots use a $100 budget per trade, rounded down to whole
contracts: at $0.80, that buys 125 contracts for $100; at $0.83, it buys 120
contracts for $99.60. Live and scalp sizing are unchanged. Existing trades
keep their original quantities and P/L. Restart the paper bots to use the
new sizing. The
5-minute/$50 rule takes priority when both rules match. The 9-minute rule is
disabled. It cannot submit live orders, even with live trading enabled in the
environment.

Trades are stored in `data/dual_paper_trades.csv`. The original NO-only paper
bot and scalp bot can run alongside it with their own trade histories.

Restart `src/dashboard.py` and choose **15m YES / NO** to start or stop it and
see its independent stats. To settle completed trades and print performance:

```sh
PYTHONPATH=src python src/prediction_tracker.py
PYTHONPATH=src python src/performance.py
```
