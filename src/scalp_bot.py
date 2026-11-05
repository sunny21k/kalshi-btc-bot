import os
import ssl
import time
from collections import defaultdict, deque
from decimal import Decimal

from requests.exceptions import RequestException
from websocket import WebSocketException

from bot import get_current_market, get_seconds_remaining, get_yes_quote
from btc_feed import get_btc_price
from bot_telemetry import BotTelemetry
from entry_prices import entry_price_range_from_env, serialize_entry_price_range
from entry_rules import entry_rules_from_env, filter_scalp_entry
from kalshi_api import get_orderbook
from run_lock import RunLock
from scalp_execution import close_position, initialize_scalp_file, open_position
from scalp_strategy import (
    build_candle,
    choose_scalp_entry,
    choose_scalp_exit,
)


POLL_SECONDS = Decimal(os.getenv("SCALP_POLL_SECONDS", "1"))
CONTRACTS = int(os.getenv("SCALP_CONTRACTS", "1"))
ALLOWED_SIDES = tuple(
    side.strip().upper()
    for side in os.getenv("SCALP_ALLOWED_SIDES", "YES,NO").split(",")
    if side.strip()
)
COOLDOWN_SECONDS = Decimal(os.getenv("SCALP_COOLDOWN_SECONDS", "30"))
MIN_SECONDS_REMAINING = Decimal(os.getenv("SCALP_MIN_SECONDS_REMAINING", "90"))
TRAILING_ACTIVATION = Decimal(os.getenv("SCALP_TRAILING_ACTIVATION_DOLLARS", "0.03"))
TRAILING_GIVEBACK = Decimal(
    os.getenv(
        "SCALP_TRAILING_GIVEBACK_DOLLARS",
        os.getenv("SCALP_TRAILING_FLOOR_DOLLARS", "0.01"),
    )
)
STOP_LOSS = Decimal(os.getenv("SCALP_STOP_LOSS_DOLLARS", "0.03"))
MAX_RETRY_SECONDS = 30


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
    entry_price_range = entry_price_range_from_env()
    entry_rules = entry_rules_from_env('scalp_paper')
    initialize_scalp_file()
    telemetry = BotTelemetry("scalp_paper", poll_seconds=POLL_SECONDS, settings={
        'entryPriceRange': serialize_entry_price_range(entry_price_range), 'entryRules': entry_rules, 'scalp': {
        'POLL_SECONDS': POLL_SECONDS, 'CONTRACTS': CONTRACTS, 'ALLOWED_SIDES': ALLOWED_SIDES,
        'COOLDOWN_SECONDS': COOLDOWN_SECONDS, 'MIN_SECONDS_REMAINING': MIN_SECONDS_REMAINING,
        'TRAILING_ACTIVATION': TRAILING_ACTIVATION, 'TRAILING_GIVEBACK': TRAILING_GIVEBACK,
        'STOP_LOSS': STOP_LOSS,
    }})

    print("Starting PAPER scalp bot...")
    print("This bot does not place live orders.")
    print(f"Contracts: {CONTRACTS}")
    print(f"Allowed sides: {', '.join(ALLOWED_SIDES)}")
    print(f"Cooldown: {COOLDOWN_SECONDS}s")
    print(f"Minimum time remaining: {MIN_SECONDS_REMAINING}s")
    print(f"Trailing activation: ${TRAILING_ACTIVATION}")
    print(f"Trailing giveback: ${TRAILING_GIVEBACK}")
    print(f"Stop loss: ${STOP_LOSS}")
    if entry_price_range:
        print(f"Custom entry prices: {entry_price_range['min'] * 100:g}%–{entry_price_range['max'] * 100:g}%")

    tick_store = {
        5: defaultdict(list),
        15: defaultdict(list),
    }
    position = None
    recent_btc_prices = deque(maxlen=4)
    cooldown_until = Decimal("0")
    retry_delay = 1

    while True:
        source = "BTC feed"
        try:
            try:
                telemetry.stage("Fetching BTC price")
                btc_price = Decimal(str(get_btc_price()))
                recent_btc_prices.append(btc_price)
                telemetry.price(btc_price)
                source = "Kalshi"
                telemetry.stage("Fetching market and order book")
                market = get_current_market()
                orderbook = get_orderbook(market["ticker"]) if market is not None else None
            except (
                RequestException,
                WebSocketException,
                ConnectionError,
                TimeoutError,
                ssl.SSLError,
            ) as exc:
                telemetry.failure(exc, source=source, api=True)
                print(
                    f"Market data error: {type(exc).__name__}: {exc} | "
                    f"retrying in {retry_delay}s",
                    flush=True,
                )
                # New entries need fresh candles after a data gap; keep the position.
                for buckets in tick_store.values():
                    buckets.clear()
                recent_btc_prices.clear()
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, MAX_RETRY_SECONDS)
                continue

            if retry_delay > 1:
                print("Market data connection restored.", flush=True)
            retry_delay = 1

            now = Decimal(str(time.time()))
            append_tick(tick_store, now, btc_price)

            if market is None:
                telemetry.market(ticker=None)
                telemetry.decide("WAIT", "No active market found")
                print("No active market.")
                time.sleep(float(POLL_SECONDS))
                continue

            ticker = market["ticker"]
            yes_bid, yes_ask, no_bid, no_ask, spread = get_yes_quote(orderbook, market)
            seconds_remaining = get_seconds_remaining(market)
            target = market.get("floor_strike")
            telemetry.market(
                ticker=ticker, closeAt=market.get("close_time"), secondsRemaining=seconds_remaining,
                targetPrice=target,
                priceDifference=(btc_price - Decimal(str(target)) if target not in (None, "") else None),
                yesAsk=yes_ask, noAsk=no_ask, spread=spread,
            )
            source = "Bot"
            candles_5s = closed_candles(tick_store, now=now, seconds=5)
            candles_15s = closed_candles(tick_store, now=now, seconds=15)

            print()
            print("=" * 72)
            print(f"SCALP BOT | {ticker}")
            print(f"BTC: ${btc_price:,.2f}")
            if seconds_remaining is not None:
                print(f"Time left: {int(seconds_remaining)}s")

            if yes_bid is None:
                telemetry.decide("WAIT", "Order book quote unavailable")
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
                    trailing_giveback=TRAILING_GIVEBACK,
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
                cooldown_until = now + COOLDOWN_SECONDS

            if position is None:
                if now < cooldown_until:
                    entry = {
                        "decision": "WAIT",
                        "reason": "cooldown after exit",
                    }
                elif (
                    seconds_remaining is not None
                    and Decimal(str(seconds_remaining)) < MIN_SECONDS_REMAINING
                ):
                    entry = {
                        "decision": "WAIT",
                        "reason": "inside final scalp cutoff",
                    }
                else:
                    entry = choose_scalp_entry(
                        candles_5s,
                        candles_15s,
                        yes_ask=yes_ask,
                        no_ask=no_ask,
                        spread=spread,
                        allowed_sides=ALLOWED_SIDES,
                        entry_price_range=entry_price_range or ({'min': '.0001', 'max': '.9999'} if entry_rules else None),
                    )
                    entry = filter_scalp_entry(entry, entry_rules, btc_price=btc_price, target_price=target,
                        seconds_remaining=seconds_remaining, recent_prices=recent_btc_prices, entry_price_range=entry_price_range)
                print(f"Decision: {entry['decision']} | {entry['reason']}")
                telemetry.decide(entry["decision"], entry["reason"], side=entry.get("side", ""))

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
                    telemetry.decide("OPEN", "Paper position opened; monitoring exits", side=position["side"])
            else:
                exit_signal = choose_scalp_exit(
                    position,
                    candles_5s,
                    yes_bid=yes_bid,
                    no_bid=no_bid,
                    trailing_activation=TRAILING_ACTIVATION,
                    trailing_giveback=TRAILING_GIVEBACK,
                    stop_loss=STOP_LOSS,
                )
                position["peak_profit"] = exit_signal["peak_profit"]
                telemetry.decide("HOLD", exit_signal["reason"], side=position["side"])
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
                    telemetry.decide("CLOSED", exit_signal["reason"], side=position["side"])
                    position = None
                    cooldown_until = now + COOLDOWN_SECONDS

            time.sleep(float(POLL_SECONDS))

        except KeyboardInterrupt:
            telemetry.stop()
            print("\nScalp bot stopped.")
            break
        except Exception as exc:
            telemetry.failure(exc, source=source)
            raise


if __name__ == "__main__":
    try:
        with RunLock("scalp_paper_bot"):
            main()
    except RuntimeError as exc:
        print(f"Scalp bot already running: {exc}")
