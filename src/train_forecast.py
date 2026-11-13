"""Fit an autoregression to daily closes and evaluate a seven-day forecast."""

import csv
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from tempfile import NamedTemporaryFile


def fit(prices):
    previous, following = prices[:-1], prices[1:]
    x_mean, y_mean = mean(previous), mean(following)
    variance = sum((x - x_mean) ** 2 for x in previous)
    slope = 0.0
    if variance:
        slope = sum(
            (x - x_mean) * (y - y_mean) for x, y in zip(previous, following)
        ) / variance
    return {"intercept": y_mean - slope * x_mean, "slope": slope}


def predict(model, last):
    result = []
    for _ in range(7):
        last = model["intercept"] + model["slope"] * last
        if not math.isfinite(last) or last <= 0:
            raise ValueError("Model produced an invalid closing price.")
        result.append(last)
    return result


def publish(artifact, destination):
    destination.parent.mkdir(exist_ok=True, parents=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        temp.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def train(source, destination):
    with source.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    dates = [date.fromisoformat(row["Date"]) for row in rows]
    prices = [float(row["Close"]) for row in rows]
    if len(prices) < 10 or not all(math.isfinite(p) and p > 0 for p in prices):
        raise ValueError("Expected at least ten positive daily closing prices.")
    if any(b - a != timedelta(days=1) for a, b in zip(dates, dates[1:])):
        raise ValueError("Expected consecutive dates in ascending order.")

    training = prices[:-7]
    validation = predict(fit(training), training[-1])
    errors = [actual - predicted for actual, predicted in zip(prices[-7:], validation)]
    model_mae = mean(map(abs, errors))
    baseline_mae = mean(abs(actual - training[-1]) for actual in prices[-7:])
    metrics = {
        "mae": round(model_mae, 2),
        "rmse": round(math.sqrt(mean(e * e for e in errors)), 2),
    }
    model = fit(prices)
    forecast = [
        {"date": (dates[-1] + timedelta(days=i)).isoformat(), "close_usd": round(p, 2)}
        for i, p in enumerate(predict(model, prices[-1]), start=1)
    ]
    artifact = {
        "trained_through": dates[-1].isoformat(), "metrics": metrics,
        "forecast": forecast, "model": {"type": "AR(1)", **model},
        "validation": {
            "start": dates[-7].isoformat(),
            "end": dates[-1].isoformat(),
            "last_close_baseline_mae": round(baseline_mae, 2),
            "accepted": model_mae < baseline_mae,
        },
    }
    digest = hashlib.sha256(json.dumps(artifact).encode()).hexdigest()[:12]
    artifact["model_version"] = f"ar1-{digest}"
    publish(artifact, destination)
    return artifact


if __name__ == "__main__":
    output = Path("models/candidate.json")
    artifact = train(Path("data/raw/btc_usd.csv"), output)
    print(output, artifact["model_version"], artifact["metrics"])
    print(artifact["validation"])
    if artifact["validation"]["accepted"]:
        publish(artifact, Path("models/forecast.json"))
        print("Published accepted forecast to models/forecast.json")
