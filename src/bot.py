import time
from datetime import datetime, timezone
from decimal import Decimal

from btc_feed import get_btc_price
from kalshi_api import get_markets_for_series, get_orderbook
from strategy import (
    calculate_btc_change,
    get_signal,
    estimate_probability,
    calculate_edge,
    make_decision,
)
from data_logger import log_market_data
from paper_execution import record_paper_trade


SERIES = "KXBTC15M"
POLL_SECONDS = 5


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


def price_to_cents(price):
    price = Decimal(str(price))

    if price <= Decimal("1"):
        return price * Decimal("100")

    return price


def get_yes_quote(orderbook):
    orderbook_fp = orderbook.get("orderbook_fp", {})

    yes_levels = orderbook_fp.get("yes_dollars", [])
    no_levels = orderbook_fp.get("no_dollars", [])

    if not yes_levels or not no_levels:
        return None, None, None, None

    yes_bid = max(
        price_to_cents(level[0])
        for level in yes_levels
    )

    no_bid = max(
        price_to_cents(level[0])
        for level in no_levels
    )

    yes_ask = Decimal("100") - no_bid
    no_ask = Decimal("100") - yes_bid

    spread = yes_ask - yes_bid

    return yes_bid, yes_ask, no_bid, no_ask, spread


def main():

    print("Starting BTC + Kalshi bot...")

    previous_btc_price = None

    while True:

        try:

            btc_price = Decimal(
                str(get_btc_price())
            )

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
            ) = get_yes_quote(orderbook)

            if previous_btc_price is None:

                price_change = Decimal("0")

            else:

                price_change = calculate_btc_change(
                    btc_price,
                    previous_btc_price
                )

            signal = get_signal(price_change)

            model_probability = estimate_probability(
                signal,
                price_change
            )

            edge = None
            decision = "WAIT"

            if yes_ask is not None:

                if signal == "UP":

                    edge = calculate_edge(
                        model_probability,
                        yes_ask
                    )

                elif signal == "DOWN":

                    no_probability = (
                        Decimal("1")
                        - model_probability
                    )

                    edge = calculate_edge(
                        no_probability,
                        no_ask
                    )

                decision = make_decision(
                    signal,
                    model_probability,
                    yes_ask,
                    no_ask,
                )

            seconds_remaining = get_seconds_remaining(
                market
            )

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
            print("BTC 15M BOT")
            print("=" * 60)

            print(
                f"BTC Price: ${btc_price:,.2f}"
            )

            print(
                f"BTC Change: {price_change:.4f}%"
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
                    f"YES Bid: {yes_bid:.1f}c"
                )

                print(
                    f"YES Ask: {yes_ask:.1f}c"
                )

                print(
                    f"NO Bid: {no_bid:.1f}c"
                )

                print(
                    f"NO Ask: {no_ask:.1f}c"
                )

                print(
                    f"Spread: {spread:.1f}c"
                )

                if edge is not None:

                    print(
                        f"Edge: {edge * 100:.1f}%"
                    )

                print(
                    f"Decision: {decision}"
                )

                # PAPER TRADING ONLY
                if decision in ("BUY YES", "BUY NO"):

                    if decision == "BUY YES":

                        side = "YES"
                        entry_price = (
                            yes_ask / Decimal("100")
                        )

                    else:

                        side = "NO"
                        entry_price = (
                            no_ask / Decimal("100")
                        )

                    trade_recorded = record_paper_trade(
                        ticker=ticker,
                        side=side,
                        prediction=signal,
                        entry_price=entry_price,
                        model_probability=(
                            model_probability
                            if side == "YES"
                            else Decimal("1")
                            - model_probability
                        ),
                        edge=edge,
                        contracts=1,
                    )

                    if trade_recorded:

                        print()
                        print("PAPER TRADE EXECUTED")

                        print(
                            f"Side: {side}"
                        )

                        print(
                            f"Bought 1 {side} @ "
                            f"${entry_price:.4f}"
                        )

                        print(
                            f"Cost: "
                            f"${entry_price:.4f}"
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
    main()
