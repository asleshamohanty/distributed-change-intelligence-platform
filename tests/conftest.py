"""Ensures the app/ and ml/ packages are importable regardless of how
pytest is invoked (this repo's Dockerfile runs it from /app, with tests/
copied alongside app/ and ml/ as siblings)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
