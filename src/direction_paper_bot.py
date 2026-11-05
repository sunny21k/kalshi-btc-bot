from bot import main as run_bot
from direction_strategy import make_direction_paper_decision
from paper_execution import DIRECTION_TRADE_FILE
from run_lock import RunLock


def main():
    try:
        with RunLock("btc15_direction_paper_bot"):
            run_bot(
                live_enabled=False,
                paper_sides=("YES", "NO"),
                paper_trade_file=DIRECTION_TRADE_FILE,
                paper_bot_id="btc15_direction_paper",
                market_data_file="data/direction_market_data.csv",
                decision_fn=make_direction_paper_decision,
                enable_early_up=False,
                bot_name="BTC 15M DIRECTION PAPER BOT",
            )
    except RuntimeError as exc:
        print(f"Direction paper bot could not start: {exc}", flush=True)


if __name__ == "__main__":
    main()
