"""
app.py — Flask API for the BTC-USD 7-day forecast service.

Endpoints
---------
GET  /health    Liveness probe (status, model version, uptime).
POST /predict   Return the next 7-day BTC-USD forecast.
GET  /metrics   Return the latest model's validation metrics.
POST /reload    Hot-reload the model artifact from disk.
"""

from __future__ import annotations

import os
import time

from flask import Flask, jsonify, request

from app.model_store import store

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(artifact_path: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    started_at = time.monotonic()

    # Load the artifact on startup (use env var, CLI arg, or fixture fallback)
    _artifact = artifact_path or os.environ.get("MODEL_ARTIFACT_PATH") or None
    store.load(_artifact)

    @app.before_request
    def _pick_up_new_model():
        """Make every worker notice an artifact that changed on disk."""
        store.refresh()

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------

    @app.get("/health")
    def health():
        """Liveness / readiness probe."""
        if not store.is_loaded():
            return jsonify({"status": "not ready"}), 503
        return jsonify(
            {
                "status": "ok",
                "model_version": store.version,
                "uptime_seconds": round(time.monotonic() - started_at, 1),
            }
        )

    @app.post("/predict")
    def predict():
        """Return the 7-day BTC-USD forecast.

        Body: a JSON object, normally ``{}``. Its content is ignored.
        Returns 400 when the Content-Type is not application/json or the body
        is not valid JSON.
        """
        if not request.is_json:
            return (
                jsonify({"error": "Content-Type must be application/json"}),
                400,
            )

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return (
                jsonify({"error": "Request body must be a valid JSON object"}),
                400,
            )

        if not store.is_loaded():
            return jsonify({"error": "Model not loaded yet"}), 503

        return jsonify(
            {
                "model_version": store.version,
                "trained_through": store.trained_through,
                "forecast": store.forecast,
            }
        )

    @app.get("/metrics")
    def metrics():
        """Return the validation metrics of the currently loaded model."""
        if not store.is_loaded():
            return jsonify({"error": "Model not loaded yet"}), 503

        return jsonify(
            {
                "model_version": store.version,
                "trained_through": store.trained_through,
                "metrics": store.metrics,
            }
        )

    @app.post("/reload")
    def reload():
        """Hot-reload the model artifact.

        Body (optional JSON): ``{"path": "/path/to/forecast.json"}``

        When *path* is omitted, MODEL_ARTIFACT_PATH is used; if that is also
        unset the sample fixture is loaded. Other Gunicorn workers pick up the
        same file change on their next request (see ModelStore.refresh), so one
        call is enough to move the whole service to a new version. A *path*
        override only changes the worker that receives it.
        """
        body = request.get_json(silent=True) if request.is_json else None
        override = body.get("path") if isinstance(body, dict) else None

        resolved = (
            override or os.environ.get("MODEL_ARTIFACT_PATH") or artifact_path or None
        )

        try:
            version = store.load(resolved)
        except (OSError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 422

        return jsonify({"status": "reloaded", "model_version": version})

    # -----------------------------------------------------------------------
    # Error handlers
    # -----------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(exc):
        return jsonify({"error": "Internal server error", "detail": str(exc)}), 500

    return app


# ---------------------------------------------------------------------------
# Entry-point (development only — production uses Gunicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5000, debug=False)
