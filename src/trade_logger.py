from paper_execution import record_paper_trade


TRADE_FILE = "data/paper_trades.csv"


def initialize_trade_file():
    from paper_execution import initialize_trade_file as _initialize_trade_file

    _initialize_trade_file()


def log_paper_trade(
    ticker,
    signal,
    model_probability,
    yes_ask,
    edge,
    contracts,
):
    side = "YES" if signal == "UP" else "NO"
    return record_paper_trade(
        ticker=ticker,
        side=side,
        prediction=signal,
        entry_price=yes_ask,
        model_probability=model_probability,
        edge=edge,
        contracts=contracts,
    )
