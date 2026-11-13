"""
model_store.py — thread-safe singleton that holds the current model artifact.

The "model" for this service is the JSON forecast file produced by
src/train_forecast.py (or the sample fixture while training is in progress).
Callers reload it at any time by calling ModelStore.load(path).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_DEFAULT_FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "forecast-example.json"


class _ModelStore:
    """Thread-safe container for the latest forecast artifact."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._path: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: Path | str | None = None) -> str:
        """Load (or reload) the forecast artifact from *path*.

        Falls back to the sample fixture when *path* is None.
        Returns the model_version string.
        """
        resolved = Path(path) if path else _DEFAULT_FIXTURE
        with open(resolved, encoding="utf-8") as fh:
            data = json.load(fh)

        # Basic schema validation
        required = {"model_version", "trained_through", "metrics", "forecast"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Artifact is missing keys: {missing}")
        if len(data["forecast"]) != 7:
            raise ValueError("Artifact must contain exactly 7 forecast entries.")

        with self._lock:
            self._data = data
            self._path = resolved

        return data["model_version"]

    @property
    def version(self) -> str:
        with self._lock:
            return self._data.get("model_version", "unknown")

    @property
    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get("metrics", {}))

    @property
    def forecast(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._data.get("forecast", []))

    @property
    def trained_through(self) -> str:
        with self._lock:
            return self._data.get("trained_through", "unknown")

    def is_loaded(self) -> bool:
        with self._lock:
            return bool(self._data)


# Module-level singleton
store = _ModelStore()
