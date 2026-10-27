import os

from bot import main as run_bot
from live_execution import DUAL_LIVE_BOT_ID
from run_lock import RunLock


def main():
    if os.getenv("KALSHI_LIVE_TRADING", "").lower() != "true":
        raise SystemExit("Live trading disabled. Set KALSHI_LIVE_TRADING=true to enable it.")

    try:
        # The original live bot uses the same lock: only one can submit orders.
        with RunLock("btc15_live_bot"):
            run_bot(
                live_enabled=True,
                live_bot_id=DUAL_LIVE_BOT_ID,
                enable_early_up=False,
                bot_name="BTC 15M YES/NO LIVE BOT",
            )
    except RuntimeError as exc:
        raise SystemExit(f"YES/NO live bot could not start: {exc}") from exc


if __name__ == "__main__":
    main()
