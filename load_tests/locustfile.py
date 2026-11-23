"""Exercise the public prediction route and count invalid forecasts as failures."""

import math
from datetime import date, timedelta

from locust import HttpUser, between, task


class ForecastUser(HttpUser):
    wait_time = between(0.05, 0.15)

    @task
    def predict(self):
        with self.client.post(
            "/predict", json={}, timeout=10, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}")
                return
            try:
                body = response.json()
                if not isinstance(body["model_version"], str) or not body["model_version"]:
                    raise ValueError("Missing model version")
                cutoff = date.fromisoformat(body["trained_through"])
                forecast = body["forecast"]
                if not isinstance(forecast, list) or len(forecast) != 7:
                    raise ValueError("Expected seven predictions")
                for day, row in enumerate(forecast, start=1):
                    if date.fromisoformat(row["date"]) != cutoff + timedelta(days=day):
                        raise ValueError("Unexpected forecast date")
                    price = row["close_usd"]
                    if (
                        isinstance(price, bool)
                        or not isinstance(price, (int, float))
                        or not math.isfinite(price)
                        or price <= 0
                    ):
                        raise ValueError("Invalid closing price")
            except (ValueError, KeyError, TypeError) as error:
                response.failure(f"Invalid forecast: {error}")
