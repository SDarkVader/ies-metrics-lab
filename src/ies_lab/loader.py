"""**DEPRECATED** — use :func:`ies_lab.fixture.load_all_fixtures` instead.

This module is retained only for backward compatibility.  It will be removed
in a future release.  The ``include_path=True`` parameter on
``load_all_fixtures`` provides the same ``_fixture_path`` metadata that this
module used to add.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

warnings.warn(
    "ies_lab.loader is deprecated. Use ies_lab.fixture.load_all_fixtures(include_path=True) instead.",
    DeprecationWarning,
    stacklevel=2,
)

from .fixture import load_all_fixtures as _load_all  # noqa: E402


def load_fixtures(fixtures_dir: str | Path = "fixtures") -> list[dict[str, Any]]:
    """Deprecated wrapper — delegates to ``fixture.load_all_fixtures(include_path=True)``."""
    return _load_all(fixtures_dir, include_path=True)
