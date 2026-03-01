from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

def load_fixtures(fixtures_dir: str | Path = "fixtures") -> List[Dict[str, Any]]:
    fixtures_path = Path(fixtures_dir)
    if not fixtures_path.exists():
        raise FileNotFoundError(f"fixtures directory not found: {fixtures_path.resolve()}")

    fixtures: List[Dict[str, Any]] = []
    for p in sorted(fixtures_path.glob("*.json")):
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
            data["_fixture_path"] = str(p)
            fixtures.append(data)
    return fixtures
