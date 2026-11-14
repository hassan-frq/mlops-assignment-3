"""
model_store.py — thread-safe singleton that holds the current model artifact.

The "model" for this service is the JSON forecast file produced by
src/train_forecast.py (or the sample fixture while training is in progress).

Gunicorn runs several worker processes and each one has its own copy of this
store. To keep every worker on the same version, the store remembers the
artifact's modification stamp and `refresh()` reloads the file whenever the
stamp changes. The API calls `refresh()` before every request, so a new
artifact published to the shared volume reaches all workers (and all pods)
without having to hit each one with /reload.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_DEFAULT_FIXTURE = (
    Path(__file__).parent.parent / "tests" / "fixtures" / "forecast-example.json"
)

_REQUIRED_KEYS = {"model_version", "trained_through", "metrics", "forecast"}


def _stamp(path: Path) -> tuple[int, int]:
    st = path.stat()
    return (st.st_mtime_ns, st.st_size)


class _ModelStore:
    """Thread-safe container for the latest forecast artifact."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._path: Path | None = None
        self._stamp: tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, path: Path | str | None = None) -> str:
        """Load (or reload) the forecast artifact from *path*.

        Falls back to the sample fixture when *path* is None.
        Returns the model_version string. On any error the previously loaded
        artifact is left untouched.
        """
        resolved = Path(path) if path else _DEFAULT_FIXTURE
        stamp = _stamp(resolved)
        with open(resolved, encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, dict):
            raise ValueError("Artifact must be a JSON object.")
        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            raise ValueError(f"Artifact is missing keys: {sorted(missing)}")
        if not isinstance(data["forecast"], list) or len(data["forecast"]) != 7:
            raise ValueError("Artifact must contain exactly 7 forecast entries.")

        with self._lock:
            self._data = data
            self._path = resolved
            self._stamp = stamp

        return data["model_version"]

    def refresh(self) -> bool:
        """Reload the artifact if the file changed since it was last loaded.

        Returns True when a new copy was loaded. A half-written or invalid
        file is ignored, so the worker keeps serving the last good model.
        """
        with self._lock:
            path, known = self._path, self._stamp
        if path is None:
            return False
        try:
            if _stamp(path) == known:
                return False
            self.load(path)
        except (OSError, ValueError):
            return False
        return True

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
