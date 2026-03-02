"""TurnAggregator — per-turn running means and cross-turn divergence statistics.

Given the ordered list of per-turn metric score dicts from MetricScorer.score_all_turns,
this module computes:

  running_means   — cumulative mean of each metric after every turn, so that point-in-time
                    averages can be displayed alongside each turn's raw scores.

  per_metric      — session-level divergence stats for each metric:
                      mean       — arithmetic mean across all turns
                      std        — population standard deviation (0 if only 1 turn)
                      drift      — last_score - first_score  (sign = direction of change)
                      max_delta  — largest absolute change between adjacent turns

  drift_scores()  — flattens per_metric into a flat dict keyed by "{METRIC}_{stat}" so
                    the existing EvaluationEngine can evaluate drift-based rules using the
                    same threshold syntax as regular metric rules.
"""
from __future__ import annotations

import math

METRICS = ["FBS2", "EUS", "TCC", "NAI", "ABC", "CS", "SCS"]


class TurnAggregator:

    @staticmethod
    def compute(turn_scores: list[dict[str, float]]) -> dict:
        """Compute running means and divergence statistics from ordered per-turn scores.

        Args:
            turn_scores: list of metric-score dicts, one per assistant turn in
                         chronological order (as returned by score_all_turns).

        Returns:
            {
                "running_means": [
                    {"FBS2": 0.50, "EUS": 0.70, ...},   # after turn 0
                    {"FBS2": 0.45, "EUS": 0.65, ...},   # mean of turns 0+1
                    ...
                ],
                "per_metric": {
                    "FBS2": {
                        "mean":      0.47,
                        "std":       0.08,
                        "drift":    -0.10,   # positive = score rose, negative = fell
                        "max_delta": 0.20,   # largest single-step change
                    },
                    ...
                },
            }
        """
        if not turn_scores:
            return {"running_means": [], "per_metric": {}}

        present_metrics = [m for m in METRICS if any(m in s for s in turn_scores)]

        # --- Running means -------------------------------------------------
        cumulative: dict[str, list[float]] = {m: [] for m in present_metrics}
        running_means: list[dict[str, float]] = []

        for scores in turn_scores:
            for m in present_metrics:
                if m in scores:
                    cumulative[m].append(scores[m])
            snapshot = {
                m: round(sum(vals) / len(vals), 4)
                for m, vals in cumulative.items()
                if vals
            }
            running_means.append(snapshot)

        # --- Per-metric divergence stats -----------------------------------
        per_metric: dict[str, dict[str, float]] = {}

        for m in present_metrics:
            vals = [s[m] for s in turn_scores if m in s]
            if not vals:
                continue

            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            std = math.sqrt(variance)
            drift = vals[-1] - vals[0]
            deltas = [abs(vals[i] - vals[i - 1]) for i in range(1, len(vals))]
            max_delta = max(deltas) if deltas else 0.0

            per_metric[m] = {
                "mean":      round(mean, 4),
                "std":       round(std, 4),
                "drift":     round(drift, 4),
                "max_delta": round(max_delta, 4),
            }

        return {"running_means": running_means, "per_metric": per_metric}

    @staticmethod
    def drift_scores(per_metric: dict[str, dict[str, float]]) -> dict[str, float]:
        """Flatten per_metric into a flat scores dict for EvaluationEngine.

        Produces keys like ``FBS2_mean``, ``FBS2_std``, ``FBS2_drift``,
        ``FBS2_max_delta``, … for every metric present in per_metric.
        These can be referenced directly in mapping_rules.yaml threshold conditions.
        """
        result: dict[str, float] = {}
        for metric, stats in per_metric.items():
            for stat_name, value in stats.items():
                result[f"{metric}_{stat_name}"] = value
        return result
