# conftest.py — pytest configuration; ensures the repo root is on sys.path
# so that `from app.xxx import ...` works without installing the package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
