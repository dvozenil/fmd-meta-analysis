"""Pytest configuration for the fmd-meta-analysis repo.

``fnd_meta_search.py`` calls ``_parse_args()`` at import time (line 120), so
a bare ``pytest`` collects with pytest's own argv (no ``--mode`` / ``--no-dedup``
flags) and argparse raises ``SystemExit:2`` before any test body runs.

The patch must happen at **module import time**, not in a session fixture:
pytest imports this ``conftest.py`` at session startup, *before* it collects
any ``tests/`` module, so replacing ``sys.argv`` here guarantees test modules
that do ``from fnd_meta_search import ...`` at module scope import cleanly.
A ``@pytest.fixture(scope="session")`` is too late — its setup body runs after
collection has already imported the test modules (verified empirically: the
fixture-only version still crashes with ``SystemExit:2`` at collection).
"""
import sys

_ORIGINAL_ARGV = sys.argv
# Give fnd_meta_search a harmless, valid argv so its import-time _parse_args()
# succeeds. The mode/options picked here are irrelevant to the unit tests,
# which only exercise query building and record-parsing helpers.
sys.argv = ["fnd_meta_search", "--full", "--no-dedup", "--auto"]
