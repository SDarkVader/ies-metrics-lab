import json
from pathlib import Path


def load_fixture(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def load_all_fixtures(fixtures_dir: Path) -> list[dict]:
    fixtures = []
    for path in sorted(fixtures_dir.glob("*.json")):
        fixtures.append(load_fixture(path))
    return fixtures
