"""
tests/test_api.py — pytest suite for the Flask BTC-USD forecast API.

Run with:
    pytest -v tests/test_api.py

The fixture at tests/fixtures/forecast-example.json is used as the
model artifact so the tests are fully self-contained (no network, no
trained model required).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.app import create_app

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "forecast-example.json"


@pytest.fixture(scope="module")
def client():
    """Return a Flask test client backed by the sample fixture."""
    app = create_app(artifact_path=str(FIXTURE_PATH))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="module")
def fixture_data():
    """Return the raw fixture dict for assertion comparisons."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_status_ok(self, client):
        body = resp = client.get("/health").get_json()
        assert body["status"] == "ok"

    def test_includes_model_version(self, client, fixture_data):
        body = client.get("/health").get_json()
        assert body["model_version"] == fixture_data["model_version"]


# ---------------------------------------------------------------------------
# /predict
# ---------------------------------------------------------------------------


class TestPredict:
    def test_post_empty_json_returns_200(self, client):
        resp = client.post("/predict", json={})
        assert resp.status_code == 200

    def test_forecast_has_seven_entries(self, client):
        body = client.post("/predict", json={}).get_json()
        assert len(body["forecast"]) == 7

    def test_forecast_entries_have_date_and_close(self, client):
        body = client.post("/predict", json={}).get_json()
        for entry in body["forecast"]:
            assert "date" in entry
            assert "close_usd" in entry

    def test_forecast_dates_are_ascending(self, client):
        body = client.post("/predict", json={}).get_json()
        dates = [e["date"] for e in body["forecast"]]
        assert dates == sorted(dates)

    def test_close_usd_values_are_positive(self, client):
        body = client.post("/predict", json={}).get_json()
        for entry in body["forecast"]:
            assert entry["close_usd"] > 0

    def test_model_version_in_response(self, client, fixture_data):
        body = client.post("/predict", json={}).get_json()
        assert body["model_version"] == fixture_data["model_version"]

    def test_trained_through_in_response(self, client, fixture_data):
        body = client.post("/predict", json={}).get_json()
        assert body["trained_through"] == fixture_data["trained_through"]

    def test_missing_content_type_returns_400(self, client):
        resp = client.post(
            "/predict",
            data="{}",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_get_method_not_allowed(self, client):
        resp = client.get("/predict")
        assert resp.status_code == 405

    def test_forecast_matches_fixture(self, client, fixture_data):
        body = client.post("/predict", json={}).get_json()
        assert body["forecast"] == fixture_data["forecast"]


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_contains_metrics_dict(self, client):
        body = client.get("/metrics").get_json()
        assert isinstance(body["metrics"], dict)

    def test_mae_and_rmse_present(self, client, fixture_data):
        body = client.get("/metrics").get_json()
        assert "mae" in body["metrics"]
        assert "rmse" in body["metrics"]

    def test_metrics_values_match_fixture(self, client, fixture_data):
        body = client.get("/metrics").get_json()
        assert body["metrics"] == fixture_data["metrics"]

    def test_model_version_in_metrics(self, client, fixture_data):
        body = client.get("/metrics").get_json()
        assert body["model_version"] == fixture_data["model_version"]


# ---------------------------------------------------------------------------
# /reload
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_with_explicit_path_returns_200(self, client):
        resp = client.post("/reload", json={"path": str(FIXTURE_PATH)})
        assert resp.status_code == 200

    def test_reload_reports_version(self, client, fixture_data):
        body = client.post("/reload", json={"path": str(FIXTURE_PATH)}).get_json()
        assert body["model_version"] == fixture_data["model_version"]
        assert body["status"] == "reloaded"

    def test_reload_without_body_uses_default(self, client):
        # Empty body — falls back to env var or fixture
        resp = client.post("/reload", json={})
        assert resp.status_code == 200

    def test_reload_bad_path_returns_422(self, client):
        resp = client.post("/reload", json={"path": "/nonexistent/path/model.json"})
        assert resp.status_code == 422

    def test_predict_after_reload_still_works(self, client, fixture_data):
        client.post("/reload", json={"path": str(FIXTURE_PATH)})
        body = client.post("/predict", json={}).get_json()
        assert len(body["forecast"]) == 7

    def test_get_method_not_allowed(self, client):
        resp = client.get("/reload")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unknown_route_returns_404(self, client):
        resp = client.get("/doesnotexist")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "error" in body
