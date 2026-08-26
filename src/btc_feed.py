import json
import ssl
import websocket


def get_btc_price():
    ws = websocket.create_connection(
        "wss://ws-feed.exchange.coinbase.com",
        sslopt={"cert_reqs": ssl.CERT_REQUIRED}
    )

    subscribe = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    ws.send(json.dumps(subscribe))

    while True:
        message = json.loads(ws.recv())

        if message.get("type") == "ticker":
            price = float(message["price"])
            ws.close()
            return price


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