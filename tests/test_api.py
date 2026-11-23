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
        body = client.get("/health").get_json()
        assert body["status"] == "ok"

    def test_includes_model_version(self, client, fixture_data):
        body = client.get("/health").get_json()
        assert body["model_version"] == fixture_data["model_version"]

    def test_includes_uptime(self, client):
        body = client.get("/health").get_json()
        assert isinstance(body["uptime_seconds"], (int, float))
        assert body["uptime_seconds"] >= 0


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

    def test_malformed_json_returns_400(self, client):
        resp = client.post(
            "/predict",
            data="{not valid json",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_empty_body_with_json_type_returns_400(self, client):
        resp = client.post("/predict", data="", content_type="application/json")
        assert resp.status_code == 400

    def test_non_object_json_returns_400(self, client):
        resp = client.post("/predict", json=[1, 2, 3])
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


class TestVersionSwitch:
    """Reload must move the service from one model version to another."""

    @staticmethod
    def _artifact(path, version, base):
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        data["model_version"] = version
        for i, entry in enumerate(data["forecast"]):
            entry["close_usd"] = base + i
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_reload_switches_version(self, tmp_path):
        model = tmp_path / "forecast.json"
        self._artifact(model, "v1", 100)
        app = create_app(artifact_path=str(model))
        c = app.test_client()
        assert c.post("/predict", json={}).get_json()["model_version"] == "v1"

        self._artifact(model, "v2", 200)
        resp = c.post("/reload", json={})
        assert resp.status_code == 200
        assert resp.get_json()["model_version"] == "v2"

        body = c.post("/predict", json={}).get_json()
        assert body["model_version"] == "v2"
        assert body["forecast"][0]["close_usd"] == 200
        assert c.get("/health").get_json()["model_version"] == "v2"
        assert c.get("/metrics").get_json()["model_version"] == "v2"

    def test_new_artifact_is_picked_up_without_reload(self, tmp_path):
        """Simulates a worker that never received the /reload request."""
        model = tmp_path / "forecast.json"
        self._artifact(model, "v1", 100)
        app = create_app(artifact_path=str(model))
        c = app.test_client()
        assert c.get("/health").get_json()["model_version"] == "v1"

        self._artifact(model, "v2", 200)
        assert c.get("/health").get_json()["model_version"] == "v2"

    def test_invalid_artifact_keeps_last_good_model(self, tmp_path):
        model = tmp_path / "forecast.json"
        self._artifact(model, "v1", 100)
        app = create_app(artifact_path=str(model))
        c = app.test_client()

        model.write_text("{broken", encoding="utf-8")
        assert c.post("/reload", json={}).status_code == 422
        assert c.post("/predict", json={}).get_json()["model_version"] == "v1"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unknown_route_returns_404(self, client):
        resp = client.get("/doesnotexist")
        assert resp.status_code == 404
        body = resp.get_json()
        assert "error" in body
