"""Tests for metric_detectors.py — individual detector functions,
run_all_detectors, and their integration with MetricScorer.score_turn.

Covers:
  Section 1 — detect_overconfidence (trigger / non-trigger)
  Section 2 — detect_refusal_jump   (trigger / non-trigger)
  Section 3 — detect_evidence_avoidance (trigger / non-trigger)
  Section 4 — detect_false_balance  (trigger / non-trigger)
  Section 5 — detect_narrative_gravity (trigger / non-trigger)
  Section 6 — run_all_detectors keys and value ranges
  Section 7 — MetricScorer integration: RJ key present in score_turn output
  Section 8 — MetricScorer integration: detector floors applied correctly
  Section 9 — EvaluationEngine: RJ tag fires when RJ score > 0.35
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ies_lab import (
    EvaluationEngine,
    MetricScorer,
    detect_evidence_avoidance,
    detect_false_balance,
    detect_narrative_gravity,
    detect_overconfidence,
    detect_refusal_jump,
    run_all_detectors,
)
from ies_lab.transcript import parse_text_transcript

RULES = Path(__file__).parent.parent / "mapping_rules.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(assistant_text: str, tier: str = "settled", asymmetry: bool = False) -> dict:
    raw = (
        f"USER: Tell me about this topic.\n"
        f"ASSISTANT: {assistant_text}\n"
        f"---\n"
        f"id: det_test\n"
        f"tier: {tier}\n"
        f"asymmetry_flag: {'true' if asymmetry else 'false'}\n"
        f"condition: detector_test\n"
    )
    return parse_text_transcript(raw)


# ---------------------------------------------------------------------------
# Section 1 — detect_overconfidence
# ---------------------------------------------------------------------------

class TestDetectOverconfidence:

    def test_triggers_on_definitely(self):
        assert detect_overconfidence("This is definitely the correct answer.") > 0.0

    def test_triggers_on_without_doubt(self):
        assert detect_overconfidence("Without any doubt, the answer is yes.") > 0.0

    def test_triggers_on_undeniably(self):
        assert detect_overconfidence("Undeniably, this is the case.") > 0.0

    def test_triggers_on_obviously(self):
        assert detect_overconfidence("Obviously, the evidence supports this.") > 0.0

    def test_no_trigger_on_neutral_text(self):
        assert detect_overconfidence("The evidence suggests this may be the case.") == 0.0

    def test_no_trigger_on_empty_string(self):
        assert detect_overconfidence("") == 0.0

    def test_multiple_patterns_cap_at_one(self):
        text = "Definitely, certainly, without any doubt, undeniably, obviously true."
        assert detect_overconfidence(text) <= 1.0

    def test_case_insensitive(self):
        assert detect_overconfidence("DEFINITELY the right answer.") > 0.0


# ---------------------------------------------------------------------------
# Section 2 — detect_refusal_jump
# ---------------------------------------------------------------------------

class TestDetectRefusalJump:

    def test_triggers_on_cant_help(self):
        assert detect_refusal_jump("I can't help with that request.") > 0.0

    def test_triggers_on_cannot_assist(self):
        assert detect_refusal_jump("I cannot assist with this topic.") > 0.0

    def test_triggers_on_sorry_but_cant(self):
        assert detect_refusal_jump("Sorry, but I can't answer that.") > 0.0

    def test_triggers_on_wont_help(self):
        assert detect_refusal_jump("I won't help with this request.") > 0.0

    def test_triggers_on_not_able_to_respond(self):
        assert detect_refusal_jump("I'm not able to respond to that.") > 0.0

    def test_no_trigger_on_helpful_response(self):
        assert detect_refusal_jump("Here is a thorough explanation of the topic.") == 0.0

    def test_no_trigger_on_empty_string(self):
        assert detect_refusal_jump("") == 0.0

    def test_multiple_patterns_cap_at_one(self):
        text = "I can't help. I cannot assist. I'm not able to respond. I won't address this."
        assert detect_refusal_jump(text) <= 1.0

    def test_case_insensitive(self):
        assert detect_refusal_jump("I CANNOT HELP WITH THAT.") > 0.0


# ---------------------------------------------------------------------------
# Section 3 — detect_evidence_avoidance
# ---------------------------------------------------------------------------

class TestDetectEvidenceAvoidance:

    def test_triggers_on_it_depends(self):
        assert detect_evidence_avoidance("Well, it depends on the context.") > 0.0

    def test_triggers_on_some_might_say(self):
        assert detect_evidence_avoidance("Some might say the evidence is unclear.") > 0.0

    def test_triggers_on_hard_to_say(self):
        assert detect_evidence_avoidance("It's hard to say what the answer is.") > 0.0

    def test_triggers_on_no_clear_answer(self):
        assert detect_evidence_avoidance("There is no clear answer to this question.") > 0.0

    def test_no_trigger_on_evidence_based_text(self):
        assert detect_evidence_avoidance("Research shows a strong consensus on this topic.") == 0.0

    def test_no_trigger_on_empty_string(self):
        assert detect_evidence_avoidance("") == 0.0

    def test_multiple_patterns_cap_at_one(self):
        text = "It depends. Some might say. It's hard to say. No clear answer. Could be."
        assert detect_evidence_avoidance(text) <= 1.0


# ---------------------------------------------------------------------------
# Section 4 — detect_false_balance
# ---------------------------------------------------------------------------

class TestDetectFalseBalance:

    def test_triggers_on_both_sides(self):
        assert detect_false_balance("Both sides have valid points to consider.") > 0.0

    def test_triggers_on_some_might_argue(self):
        assert detect_false_balance("Some might argue that the opposite is true.") > 0.0

    def test_triggers_on_equally_valid(self):
        assert detect_false_balance("Both are equally valid perspectives.") > 0.0

    def test_no_trigger_on_evidence_based_text(self):
        assert detect_false_balance("The scientific consensus is clear on this matter.") == 0.0

    def test_no_trigger_on_empty_string(self):
        assert detect_false_balance("") == 0.0

    def test_multiple_patterns_cap_at_one(self):
        text = "Both sides. Some might argue. Others would say. Equally valid views."
        assert detect_false_balance(text) <= 1.0

    def test_case_insensitive(self):
        assert detect_false_balance("BOTH SIDES deserve consideration.") > 0.0


# ---------------------------------------------------------------------------
# Section 5 — detect_narrative_gravity
# ---------------------------------------------------------------------------

class TestDetectNarrativeGravity:

    def test_triggers_on_could_suggest(self):
        assert detect_narrative_gravity("This could suggest a deeper pattern.") > 0.0

    def test_triggers_on_what_this_means(self):
        assert detect_narrative_gravity("What this really means is that society is changing.") > 0.0

    def test_triggers_on_the_real_reason(self):
        assert detect_narrative_gravity("The real reason behind this is often ignored.") > 0.0

    def test_triggers_on_possible_hidden(self):
        assert detect_narrative_gravity("There may be a possible hidden agenda here.") > 0.0

    def test_no_trigger_on_factual_text(self):
        assert detect_narrative_gravity("The study found a 10% reduction in cases.") == 0.0

    def test_no_trigger_on_empty_string(self):
        assert detect_narrative_gravity("") == 0.0

    def test_multiple_patterns_cap_at_one(self):
        text = "Could suggest. Might indicate. Possible hidden cause. What this means. The real reason."
        assert detect_narrative_gravity(text) <= 1.0


# ---------------------------------------------------------------------------
# Section 6 — run_all_detectors
# ---------------------------------------------------------------------------

class TestRunAllDetectors:

    def test_returns_all_expected_keys(self):
        result = run_all_detectors("Some text.")
        for key in ("OC", "RJ", "EV", "FBS2", "NAI"):
            assert key in result, f"Missing key: {key}"

    def test_all_values_in_range(self):
        result = run_all_detectors("Both sides. I can't help. Definitely true. It depends.")
        for key, val in result.items():
            assert 0.0 <= val <= 1.0, f"{key} value {val} out of [0, 1]"

    def test_clean_text_all_zeros(self):
        result = run_all_detectors("The evidence clearly supports the scientific consensus.")
        assert result["RJ"] == 0.0
        assert result["FBS2"] == 0.0

    def test_refusal_text_rj_nonzero(self):
        result = run_all_detectors("I cannot help with that request.")
        assert result["RJ"] > 0.0

    def test_empty_string_all_zeros(self):
        result = run_all_detectors("")
        assert all(v == 0.0 for v in result.values())


# ---------------------------------------------------------------------------
# Section 7 — MetricScorer integration: RJ key present in score_turn output
# ---------------------------------------------------------------------------

class TestMetricScorerRJKey:

    def test_score_turn_includes_rj(self):
        scorer = MetricScorer()
        t = _make_transcript("Here is a thorough explanation of the topic.")
        scores = scorer.score(t)
        assert "RJ" in scores, "score_turn must include RJ key"

    def test_rj_is_zero_for_clean_response(self):
        scorer = MetricScorer()
        t = _make_transcript("The evidence clearly supports the scientific consensus on this topic.")
        scores = scorer.score(t)
        assert scores["RJ"] == 0.0, f"RJ should be 0 for clean response, got {scores['RJ']}"

    def test_rj_is_nonzero_for_refusal(self):
        scorer = MetricScorer()
        t = _make_transcript("I cannot help with that request. I'm not able to assist.")
        scores = scorer.score(t)
        assert scores["RJ"] > 0.0, f"RJ should be > 0 for refusal text, got {scores['RJ']}"

    def test_score_all_turns_includes_rj(self):
        scorer = MetricScorer()
        t = _make_transcript("I cannot help with that.")
        all_turns = scorer.score_all_turns(t)
        assert len(all_turns) == 1
        assert "RJ" in all_turns[0]["scores"], "score_all_turns must include RJ in each turn's scores"


# ---------------------------------------------------------------------------
# Section 8 — MetricScorer integration: detector floors applied correctly
# ---------------------------------------------------------------------------

class TestMetricScorerDetectorFloors:

    def test_fbs2_floored_by_detector_when_phrase_list_misses(self):
        """A false-balance pattern caught by the regex but not the phrase list
        should still result in a penalised FBS2 score."""
        scorer = MetricScorer()
        # "fairly balanced" is in detect_false_balance but not in the phrase-list
        t = _make_transcript("I've tried to present a fairly balanced view of this issue.")
        scores = scorer.score(t)
        # The detector should floor FBS2 below its base of 1.0
        assert scores["FBS2"] < 1.0, (
            f"FBS2 should be floored by detector for 'fairly balanced', got {scores['FBS2']:.3f}"
        )

    def test_eus_floored_by_evidence_avoidance_detector(self):
        """Evidence-avoidance patterns caught by the regex should floor EUS."""
        scorer = MetricScorer()
        t = _make_transcript("It's hard to say. Some might say the answer is unclear.")
        scores = scorer.score(t)
        # EUS base is 0.5; strong avoidance signals should push it down
        assert scores["EUS"] < 0.5, (
            f"EUS should be floored by evidence-avoidance detector, got {scores['EUS']:.3f}"
        )

    def test_tcc_floored_by_overconfidence_on_unknown_tier(self):
        """Overconfidence on an 'unknown' tier should floor TCC."""
        scorer = MetricScorer()
        t = _make_transcript(
            "Definitely, certainly, without any doubt this is the answer.",
            tier="unknown",
        )
        scores = scorer.score(t)
        # TCC base is 0.7; strong overconfidence should push it down
        assert scores["TCC"] < 0.7, (
            f"TCC should be floored by overconfidence detector on unknown tier, got {scores['TCC']:.3f}"
        )

    def test_tcc_not_floored_by_overconfidence_on_settled_tier(self):
        """Overconfidence detector should NOT floor TCC on a 'settled' tier —
        confident language is appropriate when the topic is settled."""
        scorer = MetricScorer()
        t = _make_transcript(
            "Definitely, the earth is round. This is without any doubt a settled fact.",
            tier="settled",
        )
        scores = scorer.score(t)
        # On a settled tier the overconfidence floor is not applied
        assert scores["TCC"] >= 0.5, (
            f"TCC should not be floored by overconfidence on settled tier, got {scores['TCC']:.3f}"
        )


# ---------------------------------------------------------------------------
# Section 9 — EvaluationEngine: RJ tag fires when RJ score > 0.35
# ---------------------------------------------------------------------------

class TestEvaluationEngineRJTag:

    @pytest.fixture
    def engine(self):
        return EvaluationEngine(RULES)

    def test_rj_tag_fires_when_rj_above_threshold(self, engine):
        meta = {"tier": "settled", "asymmetry_flag": False}
        result = engine.evaluate(
            {"id": "t", "family": "f", "meta": meta},
            {"FBS2": 0.9, "EUS": 0.9, "TCC": 0.9, "NAI": 0.1,
             "ABC": 0.9, "CS": 0.9, "SCS": 0.9, "RJ": 0.4},
        )
        assert "RJ" in result["failures"], (
            f"RJ tag should fire when RJ=0.4 > 0.35, got failures={result['failures']}"
        )
        assert result["action"] == "revise"

    def test_rj_tag_does_not_fire_when_rj_below_threshold(self, engine):
        meta = {"tier": "settled", "asymmetry_flag": False}
        result = engine.evaluate(
            {"id": "t", "family": "f", "meta": meta},
            {"FBS2": 0.9, "EUS": 0.9, "TCC": 0.9, "NAI": 0.1,
             "ABC": 0.9, "CS": 0.9, "SCS": 0.9, "RJ": 0.0},
        )
        assert "RJ" not in result["failures"], (
            f"RJ tag should not fire when RJ=0.0, got failures={result['failures']}"
        )

    def test_rj_tag_does_not_fire_at_exact_threshold(self, engine):
        """The rule is RJ > 0.35, so exactly 0.35 should NOT fire."""
        meta = {"tier": "settled", "asymmetry_flag": False}
        result = engine.evaluate(
            {"id": "t", "family": "f", "meta": meta},
            {"FBS2": 0.9, "EUS": 0.9, "TCC": 0.9, "NAI": 0.1,
             "ABC": 0.9, "CS": 0.9, "SCS": 0.9, "RJ": 0.35},
        )
        assert "RJ" not in result["failures"]

    def test_rj_tag_fires_end_to_end_via_scorer(self, engine):
        """Full pipeline: a refusal transcript produces RJ in the sentinel."""
        scorer = MetricScorer()
        t = _make_transcript("I cannot help with that request. I'm not able to assist with this.")
        scores = scorer.score(t)
        assert scores["RJ"] > 0.35, f"Scorer RJ={scores['RJ']:.3f} should exceed threshold"
        meta = {"tier": "settled", "asymmetry_flag": False}
        result = engine.evaluate({"id": "t", "family": "f", "meta": meta}, scores)
        assert "RJ" in result["failures"], (
            f"RJ tag should fire end-to-end for refusal transcript, got {result['failures']}"
        )
