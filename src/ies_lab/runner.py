from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .engine import EvaluationEngine
from .scorer import MetricScorer
from .transcript import load_all_transcripts, to_fixture_shape, get_assistant_turns


def run_batch(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
) -> list[dict[str, Any]]:
    """Score the final assistant turn of every transcript and apply rules.

    Returns a list of sentinel dicts, each augmented with:
      - transcript_id  (same as sentinel id)
      - condition      (from transcript meta)
    """
    transcripts_dir = Path(transcripts_dir)
    rules_path = Path(rules_path)

    engine = EvaluationEngine(rules_path)
    results: list[dict[str, Any]] = []

    for transcript in load_all_transcripts(transcripts_dir):
        scores = scorer.score(transcript)
        fixture = to_fixture_shape(transcript)
        sentinel = engine.evaluate(fixture, scores)
        sentinel["transcript_id"] = transcript["id"]
        sentinel["condition"] = transcript["meta"].get("condition", "")
        results.append(sentinel)

    return results


def run_batch_multiturn(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
) -> list[dict[str, Any]]:
    """Score every assistant turn in every transcript and apply rules.

    Returns a flat list of per-turn sentinel dicts, each augmented with:
      - transcript_id
      - turn_index
      - condition
    """
    transcripts_dir = Path(transcripts_dir)
    rules_path = Path(rules_path)

    engine = EvaluationEngine(rules_path)
    results: list[dict[str, Any]] = []

    for transcript in load_all_transcripts(transcripts_dir):
        fixture = to_fixture_shape(transcript)
        for turn_result in scorer.score_all_turns(transcript):
            sentinel = engine.evaluate(fixture, turn_result["scores"])
            sentinel["transcript_id"] = transcript["id"]
            sentinel["turn_index"] = turn_result["turn_index"]
            sentinel["condition"] = transcript["meta"].get("condition", "")
            results.append(sentinel)

    return results


def save_run(results: list[dict[str, Any]], output_dir: Path) -> Path:
    """Write results to a timestamped JSON file in output_dir. Returns the file path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    path = output_dir / f"run_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return path
