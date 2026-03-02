from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .aggregator import TurnAggregator
from .engine import EvaluationEngine
from .scorer import MetricScorer
from .transcript import load_all_transcripts, to_fixture_shape, get_assistant_turns


def run_batch(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
) -> list[dict[str, Any]]:
    """Score every assistant turn of every transcript and apply rules.

    Each turn is scored in order so that cross-turn metrics (CS, SCS) use the
    proper preceding context.  After all turns are scored the engine evaluates
    rules against:

      - the **last turn's** raw metric scores (backward-compatible behaviour)
      - **drift metrics** derived from the full turn sequence:
          {METRIC}_mean, {METRIC}_std, {METRIC}_drift, {METRIC}_max_delta

    The returned sentinel dicts are enriched with:
      transcript_id     — transcript id
      condition         — meta.condition
      per_turn_scores   — list of score dicts, one per assistant turn
      running_means     — cumulative mean after each turn
      drift_stats       — per_metric divergence stats (mean/std/drift/max_delta)
    """
    transcripts_dir = Path(transcripts_dir)
    rules_path = Path(rules_path)

    engine = EvaluationEngine(rules_path)
    results: list[dict[str, Any]] = []

    for transcript in load_all_transcripts(transcripts_dir):
        all_turn_results = scorer.score_all_turns(transcript)
        turn_score_list   = [t["scores"] for t in all_turn_results]

        aggregates   = TurnAggregator.compute(turn_score_list)
        last_scores  = turn_score_list[-1] if turn_score_list else {}
        drift_scores = TurnAggregator.drift_scores(aggregates["per_metric"])

        fixture  = to_fixture_shape(transcript)
        sentinel = engine.evaluate(fixture, {**last_scores, **drift_scores})

        # Restore metric_scores to only the 7 base metrics (last turn) so
        # downstream consumers and tests see the familiar structure.
        sentinel["metric_scores"] = last_scores

        # Enrichment
        sentinel["transcript_id"]   = transcript["id"]
        sentinel["condition"]        = transcript["meta"].get("condition", "")
        sentinel["per_turn_scores"]  = turn_score_list
        sentinel["running_means"]    = aggregates["running_means"]
        sentinel["drift_stats"]      = aggregates["per_metric"]

        results.append(sentinel)

    return results


def run_batch_multiturn(
    transcripts_dir: Path,
    rules_path: Path,
    scorer: MetricScorer,
) -> list[dict[str, Any]]:
    """Score every assistant turn in every transcript and apply rules.

    Returns a flat list of per-turn sentinel dicts.  Each entry is enriched with:
      transcript_id  — transcript id
      turn_index     — which turn this is
      condition      — meta.condition
      running_mean   — cumulative mean of each metric up to and including this turn
    """
    transcripts_dir = Path(transcripts_dir)
    rules_path = Path(rules_path)

    engine = EvaluationEngine(rules_path)
    results: list[dict[str, Any]] = []

    for transcript in load_all_transcripts(transcripts_dir):
        fixture           = to_fixture_shape(transcript)
        all_turn_results  = scorer.score_all_turns(transcript)
        all_scores        = [t["scores"] for t in all_turn_results]
        agg               = TurnAggregator.compute(all_scores)

        for i, turn_result in enumerate(all_turn_results):
            sentinel = engine.evaluate(fixture, turn_result["scores"])
            sentinel["transcript_id"] = transcript["id"]
            sentinel["turn_index"]    = turn_result["turn_index"]
            sentinel["condition"]     = transcript["meta"].get("condition", "")
            sentinel["running_mean"]  = (
                agg["running_means"][i] if i < len(agg["running_means"]) else {}
            )
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
