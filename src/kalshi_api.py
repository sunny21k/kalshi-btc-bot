import os
import base64
import time
from decimal import Decimal
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import requests

load_dotenv()

API_KEY_ID = os.getenv("KALSHI_API_KEY_ID")
PRIVATE_KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH")

BASE_URL = "https://api.elections.kalshi.com"


def load_private_key():
    if not PRIVATE_KEY_PATH:
        raise RuntimeError("KALSHI_PRIVATE_KEY_PATH is not set in .env")

    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(
            f.read(),
            password=None
        )


def get_headers(method, path):
    if not API_KEY_ID:
        raise RuntimeError("KALSHI_API_KEY_ID is not set in .env")

    private_key = load_private_key()

    method = method.upper()
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}{method}{path}".encode()

    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )

    headers = {
        "KALSHI-ACCESS-KEY": API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": timestamp,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
    }

    return headers


def request(method, path, *, params=None, json=None):
    headers = get_headers(method, path)
    if json is not None:
        headers["Content-Type"] = "application/json"

    response = requests.request(
        method.upper(),
        BASE_URL + path,
        headers=headers,
        params=params,
        json=json,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_markets_for_series(series_ticker, status="open"):
    path = "/trade-api/v2/markets"

    return request(
        "GET",
        path,
        params={
            "series_ticker": series_ticker,
            "status": status,
            "limit": 100,
        },
    )


def get_orderbook(ticker):
    path = f"/trade-api/v2/markets/{ticker}/orderbook"
    return request("GET", path)

def get_market(ticker):
    path = f"/trade-api/v2/markets/{ticker}"
    return request("GET", path)


def create_order(
    ticker,
    *,
    side,
    count,
    price,
    client_order_id,
    time_in_force="immediate_or_cancel",
    post_only=False,
    exchange_index=None,
):
    path = "/trade-api/v2/portfolio/events/orders"
    payload = {
        "ticker": ticker,
        "client_order_id": client_order_id,
        "side": side,
        "count": str(Decimal(str(count))),
        "price": f"{Decimal(str(price)):.4f}",
        "time_in_force": time_in_force,
        "self_trade_prevention_type": "taker_at_cross",
        "post_only": post_only,
    }
    if exchange_index is not None:
        payload["exchange_index"] = exchange_index

    return request("POST", path, json=payload)
