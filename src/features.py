"""Build trailing indicators without discarding the AR model's close history."""

from pathlib import Path

import pandas as pd


def prepare_features(source, destination):
    frame = pd.read_csv(source, parse_dates=["Date"]).sort_values("Date")
    close = frame["Close"]
    frame["ma_7"] = close.rolling(7).mean()
    frame["ma_30"] = close.rolling(30).mean()
    frame["volatility_7"] = close.pct_change().rolling(7).std()
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(destination, index=False, date_format="%Y-%m-%d")
