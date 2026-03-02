"""Unit tests for TurnAggregator — running means and drift statistics."""
import math
from ies_lab.aggregator import TurnAggregator


def test_empty_input():
    result = TurnAggregator.compute([])
    assert result["running_means"] == []
    assert result["per_metric"] == {}


def test_single_turn_running_mean_equals_scores():
    scores = {"FBS2": 0.80, "EUS": 0.60, "TCC": 0.70}
    result = TurnAggregator.compute([scores])
    assert len(result["running_means"]) == 1
    assert result["running_means"][0]["FBS2"] == 0.80
    assert result["running_means"][0]["EUS"] == 0.60


def test_single_turn_drift_is_zero():
    scores = {"FBS2": 0.80, "EUS": 0.60}
    result = TurnAggregator.compute([scores])
    assert result["per_metric"]["FBS2"]["drift"] == 0.0
    assert result["per_metric"]["FBS2"]["std"] == 0.0
    assert result["per_metric"]["FBS2"]["max_delta"] == 0.0


def test_running_means_accumulate():
    s0 = {"FBS2": 1.00, "EUS": 0.40}
    s1 = {"FBS2": 0.60, "EUS": 0.60}
    result = TurnAggregator.compute([s0, s1])

    rm = result["running_means"]
    assert len(rm) == 2
    # After first turn: running mean = first turn's scores
    assert rm[0]["FBS2"] == 1.00
    assert rm[0]["EUS"]  == 0.40
    # After second turn: running mean = mean of both
    assert abs(rm[1]["FBS2"] - 0.80) < 1e-6
    assert abs(rm[1]["EUS"]  - 0.50) < 1e-6


def test_drift_last_minus_first():
    s0 = {"FBS2": 1.00}
    s1 = {"FBS2": 0.70}
    s2 = {"FBS2": 0.40}
    result = TurnAggregator.compute([s0, s1, s2])
    # drift = last - first = 0.40 - 1.00 = -0.60
    assert abs(result["per_metric"]["FBS2"]["drift"] - (-0.60)) < 1e-6


def test_max_delta_is_largest_step():
    s0 = {"FBS2": 1.00}
    s1 = {"FBS2": 0.80}   # delta = 0.20
    s2 = {"FBS2": 0.40}   # delta = 0.40  ← largest
    result = TurnAggregator.compute([s0, s1, s2])
    assert abs(result["per_metric"]["FBS2"]["max_delta"] - 0.40) < 1e-6


def test_std_two_turns():
    s0 = {"FBS2": 1.00}
    s1 = {"FBS2": 0.60}
    result = TurnAggregator.compute([s0, s1])
    # mean = 0.80; std = sqrt(((1.00-0.80)^2 + (0.60-0.80)^2) / 2) = sqrt(0.04) = 0.20
    assert abs(result["per_metric"]["FBS2"]["std"] - 0.20) < 1e-6


def test_drift_scores_flattening():
    s0 = {"FBS2": 1.00, "EUS": 0.50}
    s1 = {"FBS2": 0.70, "EUS": 0.30}
    result = TurnAggregator.compute([s0, s1])
    flat = TurnAggregator.drift_scores(result["per_metric"])

    assert "FBS2_mean"      in flat
    assert "FBS2_std"       in flat
    assert "FBS2_drift"     in flat
    assert "FBS2_max_delta" in flat
    assert "EUS_mean"       in flat
    # Values should match per_metric
    assert flat["FBS2_drift"] == result["per_metric"]["FBS2"]["drift"]


def test_drift_scores_empty_per_metric():
    flat = TurnAggregator.drift_scores({})
    assert flat == {}


def test_only_metrics_present_in_input_are_reported():
    # If NAI is absent from the input, it should not appear in per_metric
    s0 = {"FBS2": 0.80}
    result = TurnAggregator.compute([s0])
    assert "FBS2" in result["per_metric"]
    assert "NAI" not in result["per_metric"]


def test_three_turn_running_means_order():
    turns = [
        {"FBS2": 0.90},
        {"FBS2": 0.80},
        {"FBS2": 0.70},
    ]
    result = TurnAggregator.compute(turns)
    rm = result["running_means"]
    assert len(rm) == 3
    assert rm[0]["FBS2"] == pytest_approx(0.90)
    assert rm[1]["FBS2"] == pytest_approx(0.85)
    assert rm[2]["FBS2"] == pytest_approx(0.80)


def pytest_approx(v, rel=1e-4):
    """Tiny inline approximate-equal helper (avoids pytest import at module level)."""
    class _Approx:
        def __eq__(self, other):
            return abs(other - v) <= rel
        def __repr__(self):
            return f"~{v}"
    return _Approx()
