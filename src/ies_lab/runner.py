from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .search import GroundTruthSearch

from .engine import EvaluationEngine
from .scorer import MetricScorer
from .transcript import (
    load_all_transcripts,
    get_assistant_turns,
    get_context_before_turn,
    to_fixture_shape,
)


def run_batch(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
    search: "GroundTruthSearch | None" = None,
    output_dir: Path | None = None,
) -> list[dict]:
    """
    Score and evaluate the last assistant turn of every transcript in a directory.
    Returns one Sentinel JSON dict per transcript.
    """
    engine = EvaluationEngine(rules_path)
    transcripts = load_all_transcripts(Path(transcripts_dir))
    results = []

    for transcript in transcripts:
        scores = scorer.score(transcript)
        fixture = to_fixture_shape(transcript)
        sentinel = engine.evaluate(fixture, scores)
        sentinel["transcript_id"] = transcript["id"]
        sentinel["condition"] = transcript["meta"].get("condition", "unspecified")
        if search:
            sentinel["search_context"] = _collect_search_sources(search, transcript)
        results.append(sentinel)

    if output_dir:
        save_run(results, output_dir)
    return results


def run_batch_multiturn(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
    search: "GroundTruthSearch | None" = None,
    output_dir: Path | None = None,
) -> list[dict]:
    """
    Score and evaluate every assistant turn of every transcript.
    Returns one Sentinel JSON dict per (transcript × assistant turn).
    Each dict includes 'transcript_id' and 'turn_index'.
    """
    engine = EvaluationEngine(rules_path)
    transcripts = load_all_transcripts(Path(transcripts_dir))
    results = []

    for transcript in transcripts:
        assistant_turns = get_assistant_turns(transcript)
        for turn in assistant_turns:
            turn_index = turn["turn_index"]
            scores = scorer.score_turn(transcript, turn_index)
            context = get_context_before_turn(transcript, turn_index)

            fixture = {
                "id": f"{transcript['id']}_t{turn_index}",
                "family": transcript["meta"].get("condition", "transcript"),
                "meta": transcript["meta"],
                "prompt": next(
                    (t["content"] for t in transcript.get("turns", []) if t["role"] == "user"),
                    "",
                ),
                "candidate_output": turn["content"],
                "context": [{"role": t["role"], "content": t["content"]} for t in context],
            }

            sentinel = engine.evaluate(fixture, scores)
            sentinel["transcript_id"] = transcript["id"]
            sentinel["turn_index"] = turn_index
            sentinel["condition"] = transcript["meta"].get("condition", "unspecified")
            if search:
                sentinel["search_context"] = _collect_search_sources(search, transcript)
            results.append(sentinel)

    if output_dir:
        save_run(results, output_dir, suffix="multiturn")
    return results


def save_run(results: list[dict], output_dir: Path, suffix: str = "batch") -> Path:
    """Save run results to a timestamped JSON file in output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"run_{suffix}_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    return path


def _collect_search_sources(search: "GroundTruthSearch", transcript: dict) -> list[str]:
    prompt = next(
        (t["content"] for t in transcript.get("turns", []) if t["role"] == "user"),
        "",
    )
    if not prompt:
        return []
    try:
        result = search.lookup(prompt)
        return [s["url"] for s in result.sources if s.get("url")]
    except Exception:
        return []
