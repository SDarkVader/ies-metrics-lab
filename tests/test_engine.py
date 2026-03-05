from pathlib import Path

import pytest

from ies_lab import EvaluationEngine, load_fixture, load_all_fixtures, build_sentinel

RULES = Path(__file__).parent.parent / "mapping_rules.yaml"
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def engine():
    return EvaluationEngine(RULES)


# --- Rule engine unit tests ---

def test_rule_fb_fires(engine):
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.3},
    )
    assert "FB" in result["failures"]
    assert result["action"] == "revise"


def test_rule_fb_requires_asymmetry_flag(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.3},
    )
    assert "FB" not in result["failures"]


def test_rule_fb_requires_low_score(engine):
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.8},
    )
    assert "FB" not in result["failures"]


def test_rule_oc_fires(engine):
    meta = {"tier": "unknown", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"TCC": 0.4},
    )
    assert "OC" in result["failures"]


def test_rule_oc_requires_unknown_tier(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"TCC": 0.4},
    )
    assert "OC" not in result["failures"]


def test_rule_id_fires(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"ABC": 0.5},
    )
    assert "ID" in result["failures"]


def test_rule_am_fires(engine):
    meta = {"tier": "synthetic_continuity", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"CS": 0.4},
    )
    assert "AM" in result["failures"]


def test_rule_ev_fires(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"EUS": 0.2},
    )
    assert "EV" in result["failures"]


def test_rule_hc_fires_via_scs(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"SCS": 0.5},
    )
    assert "HC" in result["failures"]


def test_rule_hc_fires_via_nai(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"NAI": 0.8},
    )
    assert "HC" in result["failures"]


def test_no_failures_when_all_pass(engine):
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.9, "TCC": 0.9, "ABC": 0.9, "CS": 0.9, "EUS": 0.9, "SCS": 0.9, "NAI": 0.1},
    )
    assert result["failures"] == []
    assert result["action"] is None


def test_multiple_failures_collected(engine):
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.3, "ABC": 0.4},
    )
    assert "FB" in result["failures"]
    assert "ID" in result["failures"]


# --- Fixture loader tests ---

def test_load_fixture_fields():
    fixture = load_fixture(FIXTURES_DIR / "fb_001.json")
    for field in ("id", "family", "prompt", "candidate_output", "context", "meta", "expected"):
        assert field in fixture, f"Missing field: {field}"
    assert fixture["id"] == "fb_001"
    assert "metric_ranges" in fixture["expected"]
    assert "expected_failures" in fixture["expected"]


def test_load_all_fixtures():
    fixtures = load_all_fixtures(FIXTURES_DIR)
    assert len(fixtures) == 15
    ids = {f["id"] for f in fixtures}
    assert "fb_001" in ids
    assert "ev_001" in ids


# --- Sentinel JSON tests ---

def test_sentinel_required_fields():
    fixture = {"id": "x", "family": "y", "meta": {}}
    result = build_sentinel(fixture, {"FBS2": 0.3}, ["FB"], "revise")
    for field in ("sentinel_version", "id", "family", "evaluated_at", "metric_scores", "failures", "action"):
        assert field in result, f"Missing sentinel field: {field}"
    assert result["sentinel_version"] == "1.0"
    assert result["failures"] == ["FB"]
    assert result["action"] == "revise"


# --- End-to-end test with real fixture ---

def test_end_to_end_fb001(engine):
    fixture = load_fixture(FIXTURES_DIR / "fb_001.json")
    sentinel = engine.evaluate(fixture, {"FBS2": 0.3})
    assert sentinel["id"] == "fb_001"
    assert "FB" in sentinel["failures"]
    assert sentinel["action"] == "revise"
    assert sentinel["metric_scores"] == {"FBS2": 0.3}


def test_end_to_end_ev001(engine):
    fixture = load_fixture(FIXTURES_DIR / "ev_001.json")
    sentinel = engine.evaluate(fixture, {"EUS": 0.2})
    assert "EV" in sentinel["failures"]


def test_end_to_end_no_failures(engine):
    fixture = load_fixture(FIXTURES_DIR / "fb_001.json")
    sentinel = engine.evaluate(fixture, {"FBS2": 0.95})
    assert sentinel["failures"] == []
    assert sentinel["action"] is None


# ---------------------------------------------------------------------------
# if_all compound condition tests (P3)
# ---------------------------------------------------------------------------
# These tests use a temporary rules file written to a tmp_path fixture so they
# are fully isolated from the production mapping_rules.yaml.

import tempfile
import textwrap


def _write_rules(tmp_path, rules_yaml: str) -> "Path":
    """Write a minimal rules file to tmp_path and return its path."""
    p = tmp_path / "test_rules.yaml"
    p.write_text(textwrap.dedent(rules_yaml))
    return p


def test_if_all_fires_when_all_conditions_met(tmp_path):
    """if_all rule fires only when every sub-condition is satisfied."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: compound_test
            if_all:
              - asymmetry_flag: true
              - FBS2: "<0.70"
              - EUS: "<0.50"
            then:
              failures_add: [FB]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.60, "EUS": 0.40},
    )
    assert "FB" in result["failures"]
    assert result["action"] == "revise"


def test_if_all_does_not_fire_when_one_condition_fails(tmp_path):
    """if_all rule does NOT fire when any single sub-condition is not met."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: compound_test
            if_all:
              - asymmetry_flag: true
              - FBS2: "<0.70"
              - EUS: "<0.50"
            then:
              failures_add: [FB]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": True}
    # EUS is 0.60 — above the threshold of 0.50 — so the rule must not fire
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.60, "EUS": 0.60},
    )
    assert "FB" not in result["failures"]
    assert result["action"] is None


def test_if_all_does_not_fire_when_meta_condition_fails(tmp_path):
    """if_all rule does NOT fire when the meta sub-condition is not met."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: compound_test
            if_all:
              - asymmetry_flag: true
              - FBS2: "<0.70"
            then:
              failures_add: [FB]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    # asymmetry_flag is False — meta condition fails
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.50},
    )
    assert "FB" not in result["failures"]


def test_if_all_single_condition_behaves_like_flat_if(tmp_path):
    """An if_all with a single sub-condition is equivalent to a flat if:."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: single_if_all
            if_all:
              - FBS2: "<0.70"
            then:
              failures_add: [FB]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.50},
    )
    assert "FB" in result["failures"]


def test_if_all_tier_condition(tmp_path):
    """if_all sub-condition on 'tier' meta field works correctly."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: tier_compound
            if_all:
              - tier: "unknown"
              - TCC: "<0.60"
            then:
              failures_add: [OC]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "unknown", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"TCC": 0.50},
    )
    assert "OC" in result["failures"]


def test_if_all_tier_condition_wrong_tier(tmp_path):
    """if_all tier sub-condition does NOT fire on a different tier."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: tier_compound
            if_all:
              - tier: "unknown"
              - TCC: "<0.60"
            then:
              failures_add: [OC]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"TCC": 0.50},
    )
    assert "OC" not in result["failures"]


def test_if_all_greater_than_threshold(tmp_path):
    """if_all supports '>' threshold syntax in sub-conditions."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: nai_compound
            if_all:
              - NAI: ">0.55"
              - FBS2: "<0.80"
            then:
              failures_add: [HC]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": False}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"NAI": 0.70, "FBS2": 0.70},
    )
    assert "HC" in result["failures"]


def test_flat_if_and_if_all_coexist_in_same_file(tmp_path):
    """A rules file may mix flat if: and compound if_all: rules."""
    rules_path = _write_rules(tmp_path, """
        rules:
          - id: flat_rule
            if:
              FBS2: "<0.50"
            then:
              failures_add: [FB]
              action: revise
          - id: compound_rule
            if_all:
              - asymmetry_flag: true
              - EUS: "<0.40"
            then:
              failures_add: [EV]
              action: revise
    """)
    engine = EvaluationEngine(rules_path)
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.40, "EUS": 0.30},
    )
    assert "FB" in result["failures"]
    assert "EV" in result["failures"]


def test_existing_rules_still_pass_with_new_engine(engine):
    """All original flat-if rules continue to work after the if_all extension."""
    # Re-run a representative sample of the original tests to confirm
    # backward compatibility
    meta = {"tier": "settled", "asymmetry_flag": True}
    result = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta},
        {"FBS2": 0.3},
    )
    assert "FB" in result["failures"]

    meta2 = {"tier": "unknown", "asymmetry_flag": False}
    result2 = engine.evaluate(
        {"id": "t", "family": "f", "meta": meta2},
        {"TCC": 0.4},
    )
    assert "OC" in result2["failures"]
