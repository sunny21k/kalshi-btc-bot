from bot import main as run_bot
from paper_execution import DUAL_TRADE_FILE
from run_lock import RunLock


def main():
    try:
        with RunLock("btc15_dual_paper_bot"):
            run_bot(
                live_enabled=False,
                paper_sides=("YES", "NO"),
                paper_trade_file=DUAL_TRADE_FILE,
                enable_early_up=False,
                bot_name="BTC 15M YES/NO PAPER BOT",
            )
    except RuntimeError as exc:
        print(f"YES/NO paper bot could not start: {exc}", flush=True)


if __name__ == "__main__":
    main()
