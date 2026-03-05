"""Fixture loading utilities.

Provides a single, canonical set of functions for loading JSON fixture files.
The ``include_path`` parameter on ``load_all_fixtures`` subsumes the
``_fixture_path`` metadata key that was previously added by the now-deprecated
``loader.py`` module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_fixture(path: Path) -> dict[str, Any]:
    """Load a single JSON fixture file and return its contents as a dict."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_all_fixtures(
    fixtures_dir: str | Path = "fixtures",
    *,
    include_path: bool = False,
) -> list[dict[str, Any]]:
    """Load every ``*.json`` file in *fixtures_dir*, sorted by filename.

    Parameters
    ----------
    fixtures_dir:
        Directory containing the fixture JSON files.  Accepts a string or
        ``Path``.  Defaults to ``"fixtures"`` (relative to cwd).
    include_path:
        If ``True``, each returned dict will contain a ``_fixture_path``
        key with the string path to the source file.  This replaces the
        functionality that was previously in ``loader.py``.

    Raises
    ------
    FileNotFoundError
        If *fixtures_dir* does not exist.
    """
    fixtures_path = Path(fixtures_dir)
    if not fixtures_path.exists():
        raise FileNotFoundError(
            f"fixtures directory not found: {fixtures_path.resolve()}"
        )

    fixtures: list[dict[str, Any]] = []
    for path in sorted(fixtures_path.glob("*.json")):
        data = load_fixture(path)
        if include_path:
            data["_fixture_path"] = str(path)
        fixtures.append(data)
    return fixtures
