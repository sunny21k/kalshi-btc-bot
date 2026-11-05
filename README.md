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

## Direction Paper Bot

`src/direction_paper_bot.py` is a separate paper experiment. It keeps the
4-minute/$10 rule. Its 5-minute/$50 rule additionally requires **three
consecutive BTC moves in the bought side's direction**: all rising for YES,
all falling for NO. Flat moves, a reversal inside that four-price window, or
insufficient observations block the strong rule. These are BTC price polls,
normally five seconds apart, rather than exchange contract prices or candles.
The existing price bands, spread filter, confirmations, final-30-second cutoff,
and one-entry-per-market rule still apply. The strong rule takes priority even
inside four minutes; it cannot bypass the direction check via the late rule.

```sh
PYTHONPATH=src python src/direction_paper_bot.py
```

It is forced to paper mode even if live trading is enabled in the environment.
The default budget is $100 before fees, with the usual editable paper budget.
Trades go to `data/direction_paper_trades.csv`, observations to
`data/direction_market_data.csv`, and dashboard output to
`data/bot_logs/btc15_direction_paper.log`. It has its own process lock and can
run alongside the other bots. Restart the dashboard to register it, then
choose **15m Direction**. The existing result-refresh button and performance
CLI include this bot's settlements and independent statistics.

### Inspect entry directions

New entries made by the updated runner save the BTC observations used at the
paper-entry or live-order decision in `<trade ledger>.entries.jsonl`, keyed by
trade ID. The main trade CSV schema and old rows stay intact. Click a trade
row or its ID to open details, including the BTC price, previous price, dollar
and percentage movement, source confidence, and saved price window when
available. Rising/falling refers to the BTC price movement; the purchased
YES/NO contract and final outcome are shown separately. Historical inferred
previous prices are reconstructed from the recorded BTC price and percent
change and are labeled as estimates. Live snapshots describe the decision,
not the exact exchange fill time. Existing bot processes must restart to
load observation recording.

Dashboard dollar amounts display two decimal places. Internal calculations,
CSV records, and execution prices retain their precision. Tiny nonzero chart
values can be marked below one cent rather than being presented as zero.

To inspect historical paper trades and filled live orders:

```sh
PYTHONPATH=src python src/trade_direction_audit.py
```

This writes `data/trade_direction_audit.csv` and does not edit input ledgers
or submit orders. It streams the market logs once and matches the ticker,
entry quote, and countdown where recorded. Only observations at most two
seconds **before** the entry are eligible. It uses `btc_change`, not the
strategy prediction, to infer movement. Interleaved logs lack a bot ID, so
historical directions are labeled **Inferred**. Conflicting matches are
**Uncertain**; absent evidence remains **Unknown**. Old logs cannot prove the
entire three-move window or reconstruct whether the new strategy would trade.
Saved entry observations take precedence and are labeled **Recorded**.

The dashboard reads this small report on its normal refresh instead of
scanning the full market log each time. Rerun the audit to include later old
entries. Use `--trades path/to/trades.csv`, repeatable `--market-data`, or
`--output` to choose other inputs and a report location. Unfilled or rejected
live attempts are excluded from purchases.

### Backtest the direction bot offline

Replay the recorded observations using a $100 entry budget:

```sh
PYTHONPATH=src python src/backtest_direction.py
```

Outputs are separate from all trading ledgers:

- `data/backtests/direction/report.md`: original versus direction-filtered rules,
  with counts, P/L, ROI, and breakdowns by rule and side.
- `data/backtests/direction/trades.csv`: every simulated entry and its price window.
- `data/backtests/direction/summary.json`: full results, source metadata, and exclusions.

This command is entirely offline and cannot place orders. It runs the current
YES/NO strategy and the new direction variant on the same reconstructed
5-second observation stream. It freezes input copies before replay, so running
bots may continue writing their logs. Snapshot sizes and hashes are recorded
with the results. It reads historical outcomes only for settlement,
sizes each entry from its recorded ask, and allows one entry per market per
variant. A missing outcome stays pending rather than becoming a win or loss.

Historical logs combine multiple bots and omit per-bot IDs, so this is an
**approximate replay**, not an exact reconstruction of the original processes.
Targets are recovered from earlier matching shadow observations and carried
forward only after becoming known. The backtest never fills in an earlier
target from a later observation. Conflicting target markets are excluded;
gaps over 30 seconds reset history and confirmation counters. Rows before
target observations became available cannot produce entries.

Gross P/L excludes fees and assumes the entire order fills at the quoted ask;
historical depth and actual slippage are unavailable. The report also shows
a hypothetical one-cent cost per contract, which is not an exchange fee quote.
Previously observed data is not an independent forward test.

Options include `--budget`, `--sample-seconds`, `--max-gap-seconds`, and an
explicit assumed total `--cost-per-contract`. Use `--output-dir` for separate
experiments, repeat `--market-data` and `--results` for custom inputs, or choose
the shadow file with `--shadow-data`. For example:

```sh
PYTHONPATH=src python src/backtest_direction.py --budget 100 --cost-per-contract 0.01 --output-dir data/backtests/direction_cost_test
```

## YES/NO Live Bot

`src/dual_live_bot.py` uses `late_4m_10` at **75–85¢** and `strong_5m_50` at
**80–92¢**, retaining the existing momentum, confirmation, spread, and chase
checks. The strong rule takes priority when both rules match, so a 75–79¢
strong-rule entry cannot fall back to the late rule. The 9-minute rule stays
disabled. Paper bots and the original live bot retain their own entry bands.
It is real trading. Its default entry budget is **$1 per trade**, separate from
the $100 paper default. Both budgets can be changed before starting a bot.
It holds filled contracts to settlement; there is no scalp exit or stop-loss order.

Compare the old 75¢ strong-rule minimum with the 80¢ minimum offline:

```sh
PYTHONPATH=src python src/backtest_direction.py --compare strong-min-80
```

The default $100-budget comparison is saved separately in
`data/backtests/live_80c/`. It uses the same approximate observation replay
and cost limitations described above. This comparison changes only the
strong-rule minimum, without adding the direction-paper bot's three-move filter.

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

The shared limits are the chosen entry budget per order excluding fees and
a configurable live order attempt cap per UTC day (default 30). There is no
daily loss stop; `KALSHI_MAX_DAILY_LIVE_LOSS` is no longer read and existing
values have no effect. Failed attempts count toward the daily
cap too. Logging happens before submission; uncertain submissions are not
automatically retried. Check the exchange using the logged `client_order_id`
if an order remains unverified without an `order_id`.

Run `src/prediction_tracker.py` or `src/live_execution.py` to reconcile actual
fills, fees, and settled P/L for both live bots. Recorded losses are retained
for reporting but do not block later orders. Invalid ledger timestamps or P/L
still require reconciliation before trading. Order
transport follows the [Kalshi V2 order API](https://docs.kalshi.com/api-reference/orders/create-order-v2).

## Performance Charts And Calendar

Each paper, live, and scalp bot has its own performance section above trade
history. Switch between daily bars and a cumulative P/L curve, and choose
Month, 7D, 30D, or All. Cumulative P/L is calculated within the selected
range. The monthly calendar highlights profit and loss days; select a date
for its P/L, profitable/losing/flat trade counts, and actual settled live fees.
Month arrows change both the calendar and the chart range.

Additional range statistics include average P/L per trade, profit factor,
best/worst day, and settled fees or paper ROI.
Fees are already included in live net P/L and are not subtracted twice.

All dates use `America/New_York`, including daylight-saving transitions.
The 15-minute ledgers are grouped by entry date because settlement timestamps
are not recorded. Scalp results use close date. Live charts include only
positive filled quantities with verified actual P/L and fees; pending,
rejected, and unfilled orders are not plotted as profits. Paper charts use
settled results. Invalid dates/P&L and duplicate records are excluded and
reported. Pending counts refer to the bot's full history. Charts read all
eligible history, not just the recent-trades table, without modifying any CSV.

The layout uses a full-width analytics section, stacks chart/calendar on
narrow screens, and keeps trade tables horizontally scrollable. The chart
bundle is lazy-loaded separately from the bot controls.

Run analytics tests with `python -m unittest discover -s tests` and, from
`dashboard`, `npm test`. Rebuild the frontend with `npm run build` after changes.
See [the frontend guide](dashboard/README.md) for the component structure and
where to make dashboard changes.

The header includes an **Info & FAQ** page with a bot guide, searchable
questions, and release history. A subtle footer link shows the version.
Changed frontend builds advance the patch version automatically; rebuilding
unchanged source keeps the same version. See the frontend guide for release
notes and larger version bumps.

## Entry Reasons And Bot Health

Each bot's control panel includes **Why no trade?** and **Bot health**. Entry
reasons come from the bot's actual latest strategy evaluation. The dashboard
also checks the local ledger for an existing entry in that market and the
shared live attempt cap (including rejected and unfilled attempts, by UTC day).
Scalp observations show candle-history waits, cooldowns, and open-position exits.
The context row shows time left, BTC distance from target, asks, and spread.

Health shows the process, heartbeat, last received BTC price and its age, current
activity, and the latest API error. Recovered errors remain available to inspect.
A running process with an old heartbeat or price is marked stale, and old
decisions are labelled as historical. Diagnostics are local atomic snapshots in
`data/bot_status/`; they do not change strategy rules, make exchange requests,
or modify trade ledgers. A failed snapshot write does not stop trading.
Bots started in a terminal report health too; stop those in their own terminal.

After installing this feature, **restart the dashboard and each bot once** to
load the new code. Refreshing the browser alone cannot enable bot telemetry.

## Refresh Results

Click **Update results** in the dashboard header to check actual live fills,
exchange fees, net P/L, both 15-minute paper ledgers, and completed predictions.
This runs the same refresh pipeline as `PYTHONPATH=src python src/prediction_tracker.py`,
in the background without stopping or restarting any bots. It never submits,
retries, or cancels orders. Each completed check is saved immediately, so the
dashboard's normal polling can display new fees and P/L during the scan.

The button shows **Updating...** and a running check count while active.
Use **Stop refresh** to stop only this dashboard refresh after the current
check finishes and saves. Already saved updates are kept; unchecked trades are
unchanged. The dashboard reloads stats after stopping or completing the job.
A completion message reports
new settlements; **Refresh errors** lists failed checks. Missing fees or
unfinalized markets keep net P/L pending rather than estimating it. A failed
check does not prevent other trades from updating. Repeated clicks reuse the
active job, and the CLI and dashboard share a tracker lock.

For terminal refreshes, Ctrl+C also keeps results saved so far and releases the
tracker lock. Stopping early does not mean all trades have been refreshed.

Paper and live settlement writes merge into their latest ledgers under file
locks, preserving entries appended during exchange lookups. After installing
this update, restart the dashboard and any older bot processes once to load
the new code. Subsequent results refreshes do not require a bot restart.
Normal five-second dashboard polling only reads local stats; it does not
start exchange reconciliation on its own.

## Trade Budgets

Each 15-minute bot has an **Entry budget ($, before fees)** input above Start.
Enter the maximum entry cost for each trade, then start the bot. Live starts
require confirmation of that amount. Stop a running bot before changing its
budget; editing settings never resizes an existing position or changes old CSV
rows. The scalp bot's sizing is unchanged.

Sizing rounds down to whole contracts: $1 at $0.80 buys 1 contract for $0.80;
$100 at $0.80 buys 125 for $100; $100 at $0.83 buys 120 for $99.60. Exchange fees
are additional. Immediate-or-cancel live orders can fill fewer contracts or none.
The daily order cap does not increase when you increase the budget. Without a
daily loss stop, losses across multiple entries are not limited by a daily P/L threshold.

For terminal starts, set `KALSHI_LIVE_TRADE_BUDGET` (default `1.00`) or
`KALSHI_PAPER_TRADE_BUDGET` (default `100.00`). For example:

```sh
KALSHI_LIVE_TRADING=true KALSHI_LIVE_TRADE_BUDGET=100 PYTHONPATH=src python src/dual_live_bot.py
```

## Daily Live Order Limit

Stop the live bot, change **Daily order limit (UTC)** in its dashboard controls,
then start it again. Select **No daily cap** to disable only the attempt cap.
The live-start confirmation displays the selected limit, including when disabled.
The default is 30; invalid, negative, or fractional limits are rejected.

For terminal starts or a dashboard default, set `KALSHI_MAX_LIVE_TRADES_PER_DAY`
in `.env` or the process environment: a positive whole number sets the cap,
and `0` disables it. Restart the dashboard and bots after changing `.env`.
For example, this changes the cap to 60 for this terminal launch:

```sh
KALSHI_LIVE_TRADING=true KALSHI_MAX_LIVE_TRADES_PER_DAY=60 PYTHONPATH=src python src/dual_live_bot.py
```

Attempts already logged today still count across both live bots; restarting or
switching bots does not reset the count. Failed and unfilled orders count too.
The counter resets at midnight UTC, not local midnight. Changing or disabling
the cap does not change the entry budget, one attempt per market, price checks,
or uncertain-submission protection. Disabling the cap allows more total
spending, with no daily trade-count or daily P/L limit.

## Live Entry Troubleshooting

Paper entries are simulated; a live signal is not proof of a filled order.
The live log now reports `LIVE ORDER FILLED`, `PARTIAL`, `UNFILLED`, or `UNKNOWN`.
`LIVE ENTRY SKIPPED` identifies an earlier attempt and its bot/outcome; it does
not automatically retry rejected, unfilled, or uncertain submissions.

Kalshi HTTP errors include the exchange's validation message when available.
Already-quarantined non-order fragments remain in the CSV but do not break date
checks. A real order with an invalid date or P/L still blocks trading until it
is reconciled. Dated malformed rows still count toward the daily attempt cap.

Stop and restart a bot after code updates to load the new code. Old orphaned
processes started before process locking was added may still run outside the
dashboard controls; stop those separately before starting the current live bot.
