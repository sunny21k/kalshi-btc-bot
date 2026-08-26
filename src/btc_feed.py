import json
import websocket


def on_message(ws, message):
    data = json.loads(message)

    if data.get("type") == "ticker":
        price = float(data["price"])
        print(f"BTC: ${price:,.2f}")


def on_error(ws, error):
    print("Error:", error)


def on_close(ws, close_status_code, close_msg):
    print("Connection closed")


def on_open(ws):
    print("Connected to Coinbase BTC feed")

    subscribe = {
        "type": "subscribe",
        "product_ids": ["BTC-USD"],
        "channels": ["ticker"]
    }

    ws.send(json.dumps(subscribe))


ws = websocket.WebSocketApp(
    "wss://ws-feed.exchange.coinbase.com",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()