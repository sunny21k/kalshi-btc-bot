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
15-minute paper bots default to a $100 budget per trade, rounded down to whole
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

## YES/NO Live Bot

`src/dual_live_bot.py` uses the same `late_4m_10` and `strong_5m_50` rules
and entry filters as the YES/NO paper bot. The 9-minute rule stays disabled.
It is real trading. Its default entry budget is **$1 per trade**, separate from
the $100 paper default. Both budgets can be changed before starting a bot.
It holds filled contracts to settlement; there is no scalp exit or stop-loss order.

Restart the dashboard, choose **YES / NO Live**, and use **Start** to enable it.
The dashboard asks for confirmation before starting real-money trading. To
start it from the terminal instead, with your Kalshi API credentials configured:

```sh
KALSHI_LIVE_TRADING=true PYTHONPATH=src python src/dual_live_bot.py
```

Without `KALSHI_LIVE_TRADING=true`, this entry point refuses to start. The
original live bot and this bot share a process lock, so only one can run at
a time. Paper bots can continue running alongside either live bot.

All live orders remain in `data/live_trades.csv`; `bot_id=btc15_dual_live`
identifies this bot. Older rows belong to `btc15_live`. The dashboard and
`src/performance.py` report them separately. Live schema upgrades keep a backup
of the original CSV. Runtime output is in `data/bot_logs/btc15_dual_live.log`
when started from the dashboard.

The shared limits are the chosen entry budget per order excluding fees,
30 live order attempts per UTC day, and a realized daily loss stop from
`KALSHI_MAX_DAILY_LIVE_LOSS` (default $10). Failed attempts count toward the daily
cap too. Logging happens before submission; uncertain submissions are not
automatically retried. Check the exchange using the logged `client_order_id`
if an order remains unverified without an `order_id`.

Run `src/prediction_tracker.py` or `src/live_execution.py` to reconcile actual
fills, fees, and settled P/L for both live bots. Keep reconciliation current:
the daily loss stop uses recorded realized P/L, not unsettled exposure. Order
transport follows the [Kalshi V2 order API](https://docs.kalshi.com/api-reference/orders/create-order-v2).

## Trade Budgets

Each 15-minute bot has an **Entry budget ($, before fees)** input above Start.
Enter the maximum entry cost for each trade, then start the bot. Live starts
require confirmation of that amount. Stop a running bot before changing its
budget; editing settings never resizes an existing position or changes old CSV
rows. The scalp bot's sizing is unchanged.

Sizing rounds down to whole contracts: $1 at $0.80 buys 1 contract for $0.80;
$100 at $0.80 buys 125 for $100; $100 at $0.83 buys 120 for $99.60. Exchange fees
are additional. Immediate-or-cancel live orders can fill fewer contracts or none.
The 30-order daily cap and configured daily loss stop do not increase when you
increase the budget.

For terminal starts, set `KALSHI_LIVE_TRADE_BUDGET` (default `1.00`) or
`KALSHI_PAPER_TRADE_BUDGET` (default `100.00`). For example:

```sh
KALSHI_LIVE_TRADING=true KALSHI_LIVE_TRADE_BUDGET=100 PYTHONPATH=src python src/dual_live_bot.py
```
