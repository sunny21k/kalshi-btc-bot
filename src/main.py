import argparse
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from kalshi_api import get_markets_for_series, get_orderbook


DEFAULT_SERIES = "KXBTC15M"


def parse_args():
    parser = argparse.ArgumentParser(description="Dry-run-first Kalshi BTC 15m bot")
    parser.add_argument("--series", default=DEFAULT_SERIES)
    parser.add_argument("--ticker", help="Trade one specific market ticker")
    parser.add_argument("--count", default="1", help="Contracts per order")
    parser.add_argument("--max-price-cents", type=Decimal, help="Highest YES ask to buy")
    parser.add_argument("--max-spread-cents", type=Decimal, default=Decimal("5"))
    parser.add_argument("--min-seconds-to-close", type=int, default=60)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def cents_to_dollars(cents):
    return Decimal(cents) / Decimal(100)


def parse_close_time(market):
    raw = market.get("close_time")
    if not raw:
        return None

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def open_markets_by_close(series_ticker):
    data = get_markets_for_series(series_ticker)
    markets = data.get("markets", [])

    def sort_key(market):
        close_time = parse_close_time(market)
        if close_time is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        return close_time

    return sorted(markets, key=sort_key)


def seconds_to_close(market):
    close_time = parse_close_time(market)
    if close_time is None:
        return None
    return (close_time - datetime.now(timezone.utc)).total_seconds()


def level_price_to_cents(price):
    price = Decimal(str(price))
    if price <= Decimal("1"):
        return price * Decimal("100")
    return price


def format_cents(cents):
    if cents is None:
        return "n/a"

    return f"{cents.normalize()}c"


def best_price(levels, *, highest):
    if not levels:
        return None

    prices = []
    for level in levels:
        if isinstance(level, dict):
            price = level.get("price")
        else:
            price = level[0]

        if price is not None:
            prices.append(level_price_to_cents(price))

    if not prices:
        return None

    return max(prices) if highest else min(prices)


def quote_from_orderbook(orderbook_response):
    fp_orderbook = orderbook_response.get("orderbook_fp") or {}
    orderbook = orderbook_response.get("orderbook") or orderbook_response
    yes_levels = fp_orderbook.get("yes_dollars") or orderbook.get("yes") or []
    no_levels = fp_orderbook.get("no_dollars") or orderbook.get("no") or []

    best_yes_bid = best_price(yes_levels, highest=True)
    best_no_bid = best_price(no_levels, highest=True)
    best_yes_ask = 100 - best_no_bid if best_no_bid is not None else None

    spread = None
    if best_yes_bid is not None and best_yes_ask is not None:
        spread = best_yes_ask - best_yes_bid

    return {
        "best_yes_bid": best_yes_bid,
        "best_yes_ask": best_yes_ask,
        "spread": spread,
    }


def select_market(args):
    if args.ticker:
        return {"ticker": args.ticker, "title": args.ticker, "close_time": None}

    markets = open_markets_by_close(args.series)
    if not markets:
        raise RuntimeError(f"No open markets found for {args.series}")

    for market in markets:
        remaining = seconds_to_close(market)
        if remaining is None or remaining >= args.min_seconds_to_close:
            return market

    market = dict(markets[0])
    market["_skip_reason"] = (
        f"market closes in {seconds_to_close(market):.0f}s, below "
        f"--min-seconds-to-close {args.min_seconds_to_close}s"
    )
    return market


def should_buy_yes(quote, args, market):
    ask = quote["best_yes_ask"]
    spread = quote["spread"]

    if market.get("_skip_reason"):
        return False, market["_skip_reason"]
    if args.max_price_cents is None:
        return False, "set --max-price-cents to enable a buy rule"
    if ask is None:
        return False, "no YES ask available"
    if spread is None:
        return False, "spread unavailable"
    if ask > args.max_price_cents:
        return False, (
            f"YES ask {format_cents(ask)} is above max "
            f"{format_cents(args.max_price_cents)}"
        )
    if spread > args.max_spread_cents:
        return False, (
            f"spread {format_cents(spread)} is above max "
            f"{format_cents(args.max_spread_cents)}"
        )

    return True, f"YES ask {format_cents(ask)} within guardrails"


def scan_once(args):
    market = select_market(args)
    ticker = market["ticker"]
    orderbook = get_orderbook(ticker)
    quote = quote_from_orderbook(orderbook)
    should_buy, reason = should_buy_yes(quote, args, market)

    print("=" * 72)
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(f"Ticker: {ticker}")
    print(f"Title: {market.get('title')}")
    print(f"Close: {market.get('close_time')}")
    print(
        "Quote: "
        f"YES bid={format_cents(quote['best_yes_bid'])} "
        f"YES ask={format_cents(quote['best_yes_ask'])} "
        f"spread={format_cents(quote['spread'])}"
    )
    print(f"Decision: {reason}")

    if not should_buy:
        return

    price = cents_to_dollars(quote["best_yes_ask"])
    client_order_id = f"btc15m-{uuid.uuid4()}"

    print(
        "Paper-only dry run: would buy "
        f"{args.count} YES on {ticker} at ${price:.4f} IOC "
        f"(client_order_id={client_order_id})"
    )


def main():
    args = parse_args()

    while True:
        scan_once(args)
        if args.once:
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
