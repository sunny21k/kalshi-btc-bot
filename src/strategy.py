from collections import deque
import time


prices = deque(maxlen=240)


def add_price(price):
    prices.append((time.time(), price))


def get_price_ago(seconds):
    now = time.time()

    for timestamp, price in reversed(prices):
        if now - timestamp >= seconds:
            return price

    return None


def get_signal():
    if len(prices) < 10:
        return "WAIT"

    current = prices[-1][1]

    price_30s = get_price_ago(30)
    price_60s = get_price_ago(60)
    price_120s = get_price_ago(120)

    if not price_30s or not price_60s or not price_120s:
        return "WAIT"

    momentum_30 = (current - price_30s) / price_30s
    momentum_60 = (current - price_60s) / price_60s
    momentum_120 = (current - price_120s) / price_120s

    score = (
        momentum_30 * 0.5
        + momentum_60 * 0.3
        + momentum_120 * 0.2
    )

    if score > 0.0003:
        return "UP"

    if score < -0.0003:
        return "DOWN"

    return "NEUTRAL"