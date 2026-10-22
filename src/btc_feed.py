import json
import ssl
import time
import websocket


def get_btc_price(*, timeout=10):
    deadline = time.monotonic() + timeout
    ws = websocket.create_connection(
        "wss://ws-feed.exchange.coinbase.com",
        timeout=timeout,
        sslopt={"cert_reqs": ssl.CERT_REQUIRED}
    )

    subscribe = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    try:
        ws.send(json.dumps(subscribe))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise websocket.WebSocketTimeoutException("Timed out waiting for BTC ticker")
            ws.settimeout(remaining)
            raw_message = ws.recv()
            if not raw_message:
                raise websocket.WebSocketConnectionClosedException("BTC feed closed before ticker arrived")
            message = json.loads(raw_message)

            if message.get("type") == "ticker":
                return float(message["price"])
    finally:
        ws.close()


def main():
    while True:
        try:
            price = get_btc_price()
            print(f"BTC: ${price:,.2f}")
        except KeyboardInterrupt:
            print("\nConnection closed")
            break


if __name__ == "__main__":
    main()
