"""Daily BTC forecast pipeline. The scheduler and API share the model volume."""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import get_current_context


@dag(
    schedule="15 0 * * *",
    start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
)
def btc_etl_pipeline():
    @task
    def fetch_daily_data():
        from src.etl_fetch import fetch

        end = get_current_context()["data_interval_end"].in_timezone("UTC").date()
        path = Path("/opt/airflow/data") / end.isoformat() / "raw.csv"
        fetch(end - timedelta(days=365), end, path)
        return str(path)

    @task
    def prepare_features(raw):
        import pandas as pd

        frame = pd.read_csv(raw, parse_dates=["Date"]).sort_values("Date")
        close = frame["Close"]
        frame["ma_7"] = close.rolling(7).mean()
        frame["ma_30"] = close.rolling(30).mean()
        frame["volatility_7"] = close.pct_change().rolling(7).std()
        # Keep the full close series for AR(1), including indicator warm-up rows.
        path = Path(raw).with_name("features.csv")
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")
        return str(path)

    @task
    def train_and_evaluate(features):
        from src.train_forecast import train

        path = Path(features).with_name("candidate.json")
        candidate = train(Path(features), path)
        logging.info("Validation: %s %s", candidate["metrics"], candidate["validation"])
        return str(path)

    @task
    def publish_accepted(candidate_path):
        from src.train_forecast import publish

        candidate = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
        if not candidate["validation"]["accepted"]:
            raise AirflowSkipException("Candidate did not beat last-close baseline.")
        live = Path("/app/models/forecast.json")
        if live.exists():
            current = json.loads(live.read_text(encoding="utf-8"))
            if current["trained_through"] > candidate["trained_through"]:
                raise AirflowSkipException("A more recent forecast is already live.")
        publish(candidate, live)
        return candidate["model_version"]

    @task
    def reload_api(version):
        request = Request(
            os.environ["API_RELOAD_URL"], data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
        if result.get("model_version") != version:
            raise ValueError(f"API did not confirm expected version {version}")
        logging.info("API confirmed model %s", version)

    reload_api(publish_accepted(train_and_evaluate(prepare_features(fetch_daily_data()))))


pipeline = btc_etl_pipeline()
