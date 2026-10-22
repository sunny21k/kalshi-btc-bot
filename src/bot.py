import os
import time
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal

from btc_feed import get_btc_price
from kalshi_api import get_markets_for_series, get_orderbook
from strategy import (
    calculate_btc_change,
    make_late_momentum_decision,
)
from data_logger import log_market_data
from live_execution import place_live_trade
from paper_execution import (
    PAPER_TRADE_BUDGET,
    contracts_for_budget,
    initialize_trade_file,
    record_paper_trade,
)
from run_lock import RunLock
from shadow_logger import log_shadow_signal


SERIES = "KXBTC15M"
POLL_SECONDS = 5
LIVE_TRADING_ENABLED = os.getenv("KALSHI_LIVE_TRADING", "").lower() == "true"


def parse_close_time(market):
    raw = market.get("close_time")

    if not raw:
        return None

    return datetime.fromisoformat(
        raw.replace("Z", "+00:00")
    )


def get_seconds_remaining(market):
    close_time = parse_close_time(market)

    if close_time is None:
        return None

    return (
        close_time - datetime.now(timezone.utc)
    ).total_seconds()


def get_current_market():
    data = get_markets_for_series(SERIES)

    markets = data.get("markets", [])

    if not markets:
        return None

    now = datetime.now(timezone.utc)

    valid_markets = []

    for market in markets:
        close_time = parse_close_time(market)

        if close_time and close_time > now:
            valid_markets.append(market)

    if not valid_markets:
        return None

    valid_markets.sort(
        key=lambda market: parse_close_time(market)
    )

    return valid_markets[0]


def price_to_probability(price):
    price = Decimal(str(price))

    if price <= Decimal("1"):
        return price

    return price / Decimal("100")


def level_price(level):
    if isinstance(level, dict):
        return level.get("price")

    return level[0]


def market_price(market, key):
    value = market.get(key)
    if value in (None, ""):
        return None
    return price_to_probability(value)


def get_yes_quote(orderbook, market=None):
    orderbook_fp = orderbook.get("orderbook_fp", {})
    legacy_orderbook = orderbook.get("orderbook") or orderbook

    yes_levels = orderbook_fp.get("yes_dollars") or legacy_orderbook.get("yes") or []
    no_levels = orderbook_fp.get("no_dollars") or legacy_orderbook.get("no") or []

    yes_prices = [
        price_to_probability(level_price(level))
        for level in yes_levels
        if level_price(level) is not None
    ]
    no_prices = [
        price_to_probability(level_price(level))
        for level in no_levels
        if level_price(level) is not None
    ]

    if not yes_prices or not no_prices:
        if market is None:
            return None, None, None, None, None

        yes_bid = market_price(market, "yes_bid_dollars")
        yes_ask = market_price(market, "yes_ask_dollars")
        no_bid = market_price(market, "no_bid_dollars")
        no_ask = market_price(market, "no_ask_dollars")
        if None in (yes_bid, yes_ask, no_bid, no_ask):
            return None, None, None, None, None

        return yes_bid, yes_ask, no_bid, no_ask, yes_ask - yes_bid

    yes_bid = max(yes_prices)
    no_bid = max(no_prices)

    yes_ask = Decimal("1.00") - no_bid
    no_ask = Decimal("1.00") - yes_bid

    spread = yes_ask - yes_bid

    return yes_bid, yes_ask, no_bid, no_ask, spread


def main(
    *,
    live_enabled=None,
    paper_sides=("NO",),
    paper_trade_file=None,
    enable_early_up=True,
    bot_name="BTC 15M BOT",
):
    if live_enabled is None:
        live_enabled = LIVE_TRADING_ENABLED

    print(f"Starting {bot_name}...")
    print("Mode: LIVE MONEY" if live_enabled else "Mode: PAPER")
    if not live_enabled:
        print(f"Paper test: {'/'.join(paper_sides)} trades only")
        print(f"Paper budget: ${PAPER_TRADE_BUDGET:.2f} per trade (whole contracts)")
        if paper_trade_file is not None:
            initialize_trade_file(trade_file=paper_trade_file)
            print(f"Trade log: {paper_trade_file}")

    previous_btc_price = None
    recent_btc_prices = deque(maxlen=4)
    confirmation_counts = {}
    previous_entry_prices = {}

    while True:

        try:

            btc_price = Decimal(
                str(get_btc_price())
            )
            recent_btc_prices.append(btc_price)

            market = get_current_market()

            if market is None:
                print("No active market found.")
                time.sleep(POLL_SECONDS)
                continue

            ticker = market["ticker"]

            orderbook = get_orderbook(ticker)

            (
                yes_bid,
                yes_ask,
                no_bid,
                no_ask,
                spread,
            ) = get_yes_quote(orderbook, market)

            if previous_btc_price is None:

                price_change = Decimal("0")

            else:

                price_change = calculate_btc_change(
                    btc_price,
                    previous_btc_price
                )

            seconds_remaining = get_seconds_remaining(
                market
            )

            target_price = market.get("floor_strike")
            price_difference_for_confirmation = None
            confirmation_key = None

            if target_price not in (None, ""):
                price_difference_for_confirmation = (
                    btc_price - Decimal(str(target_price))
                )
                if abs(price_difference_for_confirmation) >= Decimal("10"):
                    confirmation_side = (
                        "YES"
                        if price_difference_for_confirmation > 0
                        else "NO"
                    )
                    confirmation_key = (ticker, confirmation_side)
                    confirmation_counts[confirmation_key] = (
                        confirmation_counts.get(confirmation_key, 0) + 1
                    )
                else:
                    confirmation_counts[(ticker, "YES")] = 0
                    confirmation_counts[(ticker, "NO")] = 0

            trade_signal = make_late_momentum_decision(
                btc_price=btc_price,
                target_price=target_price,
                seconds_remaining=seconds_remaining,
                yes_ask=yes_ask,
                no_ask=no_ask,
                spread=spread,
                recent_prices=recent_btc_prices,
                previous_entry_price=(
                    previous_entry_prices.get(confirmation_key)
                    if confirmation_key is not None
                    else None
                ),
                confirmation_count=(
                    confirmation_counts.get(confirmation_key, 0)
                    if confirmation_key is not None
                    else 0
                ),
                enable_early_up=enable_early_up,
            )
            if (
                not live_enabled
                and trade_signal["decision"] in ("BUY YES", "BUY NO")
                and trade_signal["side"] not in paper_sides
            ):
                trade_signal = {
                    **trade_signal,
                    "decision": "WAIT",
                    "reason": f"15m paper test is {'/'.join(paper_sides)}-only",
                }
            if decision_key := trade_signal.get("side"):
                previous_entry_prices[(ticker, decision_key)] = (
                    trade_signal.get("entry_price")
                )

            log_shadow_signal(
                ticker=ticker,
                live_enabled=live_enabled,
                trade_signal=trade_signal,
                seconds_remaining=seconds_remaining,
            )
            signal = trade_signal["prediction"]
            decision = trade_signal["decision"]
            entry_price = trade_signal["entry_price"]
            price_difference = trade_signal["price_difference"]
            model_probability = entry_price or Decimal("0.50")
            edge = Decimal("0")

            log_market_data(
                ticker=ticker,
                btc_price=btc_price,
                btc_change=price_change,
                signal=signal,
                model_probability=model_probability,
                yes_bid=yes_bid,
                yes_ask=yes_ask,
                spread=spread,
                edge=edge,
                seconds_remaining=seconds_remaining,
            )

            print()
            print("=" * 60)
            print(bot_name)
            print("=" * 60)

            print(
                f"BTC Price: ${btc_price:,.2f}"
            )

            print(
                f"BTC Change: {price_change:.4f}%"
            )

            if target_price is not None:

                print(
                    f"Target Price: ${Decimal(str(target_price)):,.2f}"
                )

            if price_difference is not None:

                print(
                    f"BTC Difference: ${price_difference:,.2f}"
                )

            print(
                f"Signal: {signal}"
            )

            print(
                f"Model Probability: "
                f"{model_probability * 100:.1f}%"
            )

            print()

            print(
                f"Market: {ticker}"
            )

            print(
                f"Close: {market.get('close_time')}"
            )

            if seconds_remaining is not None:

                minutes = int(
                    max(seconds_remaining, 0) // 60
                )

                seconds = int(
                    max(seconds_remaining, 0) % 60
                )

                print(
                    f"Time Remaining: "
                    f"{minutes}m {seconds}s"
                )

            print()

            if yes_bid is not None:

                print(
                    f"YES Bid: {yes_bid * Decimal('100'):.1f}c"
                )

                print(
                    f"YES Ask: {yes_ask * Decimal('100'):.1f}c"
                )

                print(
                    f"NO Bid: {no_bid * Decimal('100'):.1f}c"
                )

                print(
                    f"NO Ask: {no_ask * Decimal('100'):.1f}c"
                )

                print(
                    f"Spread: {spread * Decimal('100'):.1f}c"
                )

                if edge is not None:

                    print(
                        f"Edge: {edge * 100:.1f}%"
                    )

                print(
                    f"Decision: {decision}"
                )

                print(
                    f"Reason: {trade_signal['reason']}"
                )

                if decision in ("BUY YES", "BUY NO"):
                    side = trade_signal["side"]

                    if live_enabled:

                        contracts = 1
                        trade_recorded = place_live_trade(
                            ticker=ticker,
                            side=side,
                            prediction=signal,
                            entry_price=entry_price,
                            strategy_name=trade_signal.get("strategy_name", ""),
                            seconds_remaining=seconds_remaining,
                            contracts=1,
                            exchange_index=market.get("exchange_index"),
                        )

                    else:

                        contracts = contracts_for_budget(entry_price)
                        trade_recorded = record_paper_trade(
                            ticker=ticker,
                            side=side,
                            prediction=signal,
                            entry_price=entry_price,
                            model_probability=model_probability,
                            edge=edge,
                            strategy_name=trade_signal.get("strategy_name", ""),
                            seconds_remaining=seconds_remaining,
                            contracts=contracts,
                            trade_file=paper_trade_file,
                        )

                    if trade_recorded:

                        print()
                        print(
                            "LIVE TRADE SUBMITTED"
                            if live_enabled
                            else "PAPER TRADE EXECUTED"
                        )

                        print(
                            f"Side: {side}"
                        )

                        print(
                            f"Bought {contracts} {side} @ "
                            f"${entry_price:.4f}"
                        )

                        print(
                            f"Cost: "
                            f"${entry_price * contracts:.4f}"
                        )

            else:

                print("Order book unavailable")

            print("=" * 60)

            previous_btc_price = btc_price

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:

            print("\nBot stopped.")
            break

        except Exception as e:

            print(f"Error: {e}")

            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    lock_name = "btc15_live_bot" if LIVE_TRADING_ENABLED else "btc15_paper_bot"
    try:
        with RunLock(lock_name):
            main()
    except RuntimeError as exc:
        print(f"Bot already running: {exc}")
