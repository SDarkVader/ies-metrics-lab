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
