"""
app.py — Flask API for the BTC-USD 7-day forecast service.

Endpoints
---------
GET  /health    Liveness probe.
POST /predict   Return the next 7-day BTC-USD forecast.
GET  /metrics   Return the latest model's validation metrics.
POST /reload    Hot-reload the model artifact from disk.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request

from app.model_store import store

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(artifact_path: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load the artifact on startup (use env var, CLI arg, or fixture fallback)
    _artifact = artifact_path or os.environ.get("MODEL_ARTIFACT_PATH")
    store.load(_artifact)

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
            }
        )

    @app.post("/predict")
    def predict():
        """Return the 7-day BTC-USD forecast.

        Body: ``{}`` (empty JSON object) or any JSON object (body is ignored).
        Returns 400 when the Content-Type is not application/json.
        """
        # Require JSON content-type; allow empty body `{}`
        if not request.is_json:
            return (
                jsonify({"error": "Content-Type must be application/json"}),
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

        Body (optional JSON):
            ``{"path": "/path/to/forecast.json"}``

        When *path* is omitted the value of the ``MODEL_ARTIFACT_PATH``
        environment variable is used; if that is also unset the sample
        fixture is loaded.
        """
        if request.is_json and request.get_json(silent=True):
            body = request.get_json()
            artifact_path_override = body.get("path")
        else:
            artifact_path_override = None

        resolved = (
            artifact_path_override
            or os.environ.get("MODEL_ARTIFACT_PATH")
            or None
        )

        try:
            version = store.load(resolved)
        except (FileNotFoundError, ValueError) as exc:
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
