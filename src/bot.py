import time
from datetime import datetime, timezone

from btc_feed import get_btc_price
from kalshi_api import get_markets_for_series, get_orderbook


SERIES = "KXBTC15M"


def get_next_market():
    data = get_markets_for_series(SERIES)
    markets = data.get("markets", [])

    if not markets:
        return None

    markets.sort(key=lambda m: m.get("close_time", ""))
    return markets[0]


def get_quote(orderbook):
    book = orderbook.get("orderbook_fp", {})

    yes = book.get("yes_dollars", [])
    no = book.get("no_dollars", [])

    if not yes or not no:
        return None, None, None

    yes_bid = max(float(level[0]) for level in yes)
    no_bid = max(float(level[0]) for level in no)

    yes_ask = 1 - no_bid
    spread = yes_ask - yes_bid

    return yes_bid, yes_ask, spread


def seconds_remaining(close_time):
    close = datetime.fromisoformat(
        close_time.replace("Z", "+00:00")
    )

    return max(
        0,
        int((close - datetime.now(timezone.utc)).total_seconds())
    )


def format_time(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}m {seconds}s"


def main():
    print("Starting BTC + Kalshi bot...")

    while True:
        try:
            btc_price = get_btc_price()
            market = get_next_market()

            if not market:
                print("No open market found.")
                time.sleep(5)
                continue

            ticker = market["ticker"]
            close_time = market["close_time"]

            orderbook = get_orderbook(ticker)

            yes_bid, yes_ask, spread = get_quote(orderbook)

            remaining = seconds_remaining(close_time)

            print("\n" + "=" * 60)
            print("BTC 15M BOT")
            print("=" * 60)

            print(f"BTC Price: ${btc_price:,.2f}")
            print()
            print(f"Market: {ticker}")
            print(f"Close: {close_time}")
            print(f"Time Remaining: {format_time(remaining)}")
            print()

            if yes_bid is not None:
                print(f"YES Bid: {yes_bid * 100:.0f}c")
                print(f"YES Ask: {yes_ask * 100:.0f}c")
                print(f"Spread: {(yes_ask - yes_bid) * 100:.1f}c")
            else:
                print("Order book unavailable")

            print("=" * 60)

            time.sleep(5)

        except KeyboardInterrupt:
            print("\nBot stopped.")
            break

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()