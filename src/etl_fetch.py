# /// script
# requires-python = ">=3.11"
# dependencies = ["yfinance>=0.2.54,<2"]
# ///
"""Fetch completed BTC-USD daily candles and atomically publish a raw CSV."""

import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
import yfinance as yf


def fetch(start: date, end: date, output: Path) -> int:
    """Fetch the inclusive start through the exclusive end in UTC."""
    if not start < end <= datetime.now(timezone.utc).date():
        raise ValueError("Choose a start before end, with end no later than today.")
    frame = yf.Ticker("BTC-USD").history(
        start=start.isoformat(), end=end.isoformat(), interval="1d",
        auto_adjust=False, raise_errors=True,
    )
    columns = ["Open", "High", "Low", "Close", "Volume"]
    if frame.empty:
        raise ValueError("Yahoo returned no BTC-USD data for this range.")
    frame = frame[columns].sort_index()
    frame.index = frame.index.tz_convert("UTC").tz_localize(None)
    expected = pd.date_range(start, end - timedelta(days=1), freq="D")
    if not frame.index.equals(expected):
        raise ValueError("Yahoo returned missing, duplicate, or unexpected dates.")
    prices = frame[["Open", "Close"]]
    if (
        not np.isfinite(frame.to_numpy()).all()
        or (frame["Low"] <= 0).any()
        or (frame["Volume"] < 0).any()
        or (prices.min(axis=1) < frame["Low"]).any()
        or (prices.max(axis=1) > frame["High"]).any()
    ):
        raise ValueError("Yahoo returned invalid prices or volume.")

    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        frame.to_csv(staging, index_label="Date", date_format="%Y-%m-%d")
        staging.replace(output)
    finally:
        staging.unlink(missing_ok=True)
    return len(frame)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, help="First UTC date")
    parser.add_argument("--end", type=date.fromisoformat, help="Exclusive UTC date")
    parser.add_argument("--output", type=Path, default=Path("data/raw/btc_usd.csv"))
    args = parser.parse_args()
    end = args.end or datetime.now(timezone.utc).date()
    start = args.start or end - timedelta(days=365)
    try:
        count = fetch(start, end, args.output)
    except Exception as error:
        parser.exit(1, f"BTC-USD fetch failed: {error}\n")
    print(f"Saved {count} daily rows ({start} through {end - timedelta(days=1)})")
    print(args.output.resolve())
