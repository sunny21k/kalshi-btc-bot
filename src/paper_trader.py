from paper_execution import initialize_trade_file, record_paper_trade as _record_paper_trade


TRADES_FILE = "data/paper_trades.csv"


def initialize_trades_file():
    initialize_trade_file()


def record_paper_trade(
    ticker,
    prediction,
    entry_price,
    model_probability,
    edge,
    contracts=1,
):
    """
    Record a simulated trade at the exact moment
    the bot decides to BUY.

    No real money is used.
    """
    side = "YES" if prediction == "UP" else "NO"
    recorded = _record_paper_trade(
        ticker=ticker,
        side=side,
        prediction=prediction,
        entry_price=entry_price,
        model_probability=model_probability,
        edge=edge,
        contracts=contracts,
    )

    if recorded:
        print(f"PAPER TRADE: BUY {contracts} {side} @ ${entry_price:.4f}")

    return recorded
