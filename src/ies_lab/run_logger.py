from pathlib import Path
from datetime import datetime
import json


def create_run_dir(base="runs"):

    timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

    run_dir = Path(base) / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    return run_dir


def save_json(run_dir, filename, data):

    path = Path(run_dir) / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return path
