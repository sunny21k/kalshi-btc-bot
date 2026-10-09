import os
import time
from collections import defaultdict
from decimal import Decimal

from bot import get_current_market, get_seconds_remaining, get_yes_quote
from btc_feed import get_btc_price
from kalshi_api import get_orderbook
from scalp_execution import close_position, open_position
from scalp_strategy import (
    build_candle,
    choose_scalp_entry,
    choose_scalp_exit,
)


POLL_SECONDS = Decimal(os.getenv("SCALP_POLL_SECONDS", "1"))
CONTRACTS = int(os.getenv("SCALP_CONTRACTS", "1"))
TRAILING_ACTIVATION = Decimal(os.getenv("SCALP_TRAILING_ACTIVATION_DOLLARS", "50"))
TRAILING_FLOOR = Decimal(os.getenv("SCALP_TRAILING_FLOOR_DOLLARS", "35"))
STOP_LOSS = Decimal(os.getenv("SCALP_STOP_LOSS_DOLLARS", "20"))


def candle_bucket(timestamp, seconds):
    return int(timestamp // seconds) * seconds


def append_tick(tick_store, timestamp, price):
    tick_store[5][candle_bucket(timestamp, 5)].append(price)
    tick_store[15][candle_bucket(timestamp, 15)].append(price)


def closed_candles(tick_store, *, now, seconds, limit=20):
    current_bucket = candle_bucket(now, seconds)
    candles = []

    for start_ts in sorted(tick_store[seconds]):
        if start_ts >= current_bucket:
            continue
        prices = tick_store[seconds][start_ts]
        if prices:
            candles.append(build_candle(start_ts, prices))

    return candles[-limit:]


def main():
    print("Starting PAPER scalp bot...")
    print("This bot does not place live orders.")
    print(f"Contracts: {CONTRACTS}")
    print(f"Trailing activation: ${TRAILING_ACTIVATION}")
    print(f"Trailing floor: ${TRAILING_FLOOR}")
    print(f"Stop loss: ${STOP_LOSS}")

    tick_store = {
        5: defaultdict(list),
        15: defaultdict(list),
    }
    position = None

    while True:
        try:
            now = Decimal(str(time.time()))
            btc_price = Decimal(str(get_btc_price()))
            append_tick(tick_store, now, btc_price)

            market = get_current_market()
            if market is None:
                print("No active market.")
                time.sleep(float(POLL_SECONDS))
                continue

            ticker = market["ticker"]
            orderbook = get_orderbook(ticker)
            yes_bid, yes_ask, no_bid, no_ask, spread = get_yes_quote(orderbook, market)
            seconds_remaining = get_seconds_remaining(market)
            candles_5s = closed_candles(tick_store, now=now, seconds=5)
            candles_15s = closed_candles(tick_store, now=now, seconds=15)

            print()
            print("=" * 72)
            print(f"SCALP BOT | {ticker}")
            print(f"BTC: ${btc_price:,.2f}")
            if seconds_remaining is not None:
                print(f"Time left: {int(seconds_remaining)}s")

            if yes_bid is None:
                print("Quote unavailable.")
                time.sleep(float(POLL_SECONDS))
                continue

            print(
                f"YES {yes_bid * 100:.1f}/{yes_ask * 100:.1f}c | "
                f"NO {no_bid * 100:.1f}/{no_ask * 100:.1f}c | "
                f"spread {spread * 100:.1f}c"
            )

            if position is not None and position["ticker"] != ticker:
                exit_signal = choose_scalp_exit(
                    position,
                    candles_5s,
                    yes_bid=yes_bid,
                    no_bid=no_bid,
                    trailing_activation=TRAILING_ACTIVATION,
                    trailing_floor=TRAILING_FLOOR,
                    stop_loss=STOP_LOSS,
                )
                close_position(
                    position,
                    exit_price=exit_signal["exit_price"],
                    profit_loss=exit_signal["current_profit"],
                    peak_profit=exit_signal["peak_profit"],
                    reason="market changed",
                )
                print("Closed position because market changed.")
                position = None

            if position is None:
                entry = choose_scalp_entry(
                    candles_5s,
                    candles_15s,
                    yes_ask=yes_ask,
                    no_ask=no_ask,
                    spread=spread,
                )
                print(f"Decision: {entry['decision']} | {entry['reason']}")

                if entry["decision"] in ("BUY YES", "BUY NO"):
                    position = open_position(
                        ticker=ticker,
                        side=entry["side"],
                        prediction=entry["prediction"],
                        entry_price=entry["entry_price"],
                        contracts=CONTRACTS,
                        reason=entry["reason"],
                    )
                    print(
                        f"OPEN {position['side']} x{CONTRACTS} "
                        f"@ ${position['entry_price']:.4f}"
                    )
            else:
                exit_signal = choose_scalp_exit(
                    position,
                    candles_5s,
                    yes_bid=yes_bid,
                    no_bid=no_bid,
                    trailing_activation=TRAILING_ACTIVATION,
                    trailing_floor=TRAILING_FLOOR,
                    stop_loss=STOP_LOSS,
                )
                position["peak_profit"] = exit_signal["peak_profit"]
                print(
                    f"Position: {position['side']} x{position['contracts']} "
                    f"entry ${position['entry_price']:.4f} | "
                    f"P/L ${exit_signal['current_profit']:.4f} | "
                    f"peak ${exit_signal['peak_profit']:.4f} | "
                    f"{exit_signal['reason']}"
                )

                if exit_signal["decision"] == "SELL":
                    close_position(
                        position,
                        exit_price=exit_signal["exit_price"],
                        profit_loss=exit_signal["current_profit"],
                        peak_profit=exit_signal["peak_profit"],
                        reason=exit_signal["reason"],
                    )
                    print("CLOSED position.")
                    position = None

            time.sleep(float(POLL_SECONDS))

        except KeyboardInterrupt:
            print("\nScalp bot stopped.")
            break


if __name__ == "__main__":
    main()
