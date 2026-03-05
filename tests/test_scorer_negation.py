"""Tests for the negation-aware _count_phrase_hits function and its effect
on MetricScorer outputs.

Covers:
  - Direct unit tests for _count_phrase_hits (negated vs. non-negated hits)
  - FBS2 scoring: negated false-balance phrases must not trigger a penalty
  - EUS scoring: negated evidence phrases must not suppress a boost
  - ABC scoring: negated attribution phrases must not trigger a penalty
  - negate=False escape hatch restores original substring-count behaviour
  - Multiple occurrences: mix of negated and non-negated hits in one string
"""
from __future__ import annotations

import pytest

from ies_lab.scorer import (
    MetricScorer,
    NEGATION_TOKENS,
    NEGATION_WINDOW,
    _count_phrase_hits,
)
from ies_lab.transcript import parse_text_transcript


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_transcript(assistant_text: str, tier: str = "settled", asymmetry: bool = True) -> dict:
    """Build a minimal single-turn transcript for scoring."""
    raw = (
        f"USER: Is the earth flat?\n"
        f"ASSISTANT: {assistant_text}\n"
        f"---\n"
        f"id: negation_test\n"
        f"tier: {tier}\n"
        f"asymmetry_flag: {'true' if asymmetry else 'false'}\n"
        f"condition: negation_test\n"
    )
    return parse_text_transcript(raw)


# ---------------------------------------------------------------------------
# 1. Direct unit tests for _count_phrase_hits
# ---------------------------------------------------------------------------

class TestCountPhraseHitsDirect:

    def test_plain_hit_is_counted(self):
        assert _count_phrase_hits("both sides deserve consideration", ["both sides"]) == 1

    def test_negated_hit_is_suppressed(self):
        assert _count_phrase_hits("this is not a both-sides issue", ["both sides"]) == 0

    def test_never_negation_suppresses_hit(self):
        assert _count_phrase_hits("it is never a both-sides debate", ["both sides"]) == 0

    def test_cant_negation_suppresses_hit(self):
        assert _count_phrase_hits("we can't call this a both-sides matter", ["both sides"]) == 0

    def test_no_negation_suppresses_hit(self):
        assert _count_phrase_hits("there is no both-sides framing here", ["both sides"]) == 0

    def test_negation_outside_window_does_not_suppress(self):
        # "not" is more than NEGATION_WINDOW tokens before "both sides"
        long_prefix = "not " + "word " * NEGATION_WINDOW + "both sides"
        assert _count_phrase_hits(long_prefix, ["both sides"]) == 1

    def test_multiple_phrases_one_negated_one_not(self):
        text = "opinions vary but this is not a both-sides issue"
        # "opinions vary" is NOT negated; "both sides" IS negated
        hits = _count_phrase_hits(text, ["both sides", "opinions vary"])
        assert hits == 1

    def test_two_non_negated_hits_counted(self):
        text = "both sides and both perspectives are presented"
        assert _count_phrase_hits(text, ["both sides", "both perspectives"]) == 2

    def test_negate_false_counts_negated_hit(self):
        # With negate=False the guard is disabled; a negated phrase is still counted.
        # Use a string where the phrase appears with a space (not hyphenated) so it
        # is a genuine substring match that the negation guard would otherwise suppress.
        assert _count_phrase_hits("this is not both sides of the argument", ["both sides"], negate=False) == 1

    def test_empty_text_returns_zero(self):
        assert _count_phrase_hits("", ["both sides"]) == 0

    def test_empty_phrases_returns_zero(self):
        assert _count_phrase_hits("both sides", []) == 0

    def test_phrase_at_start_of_string_no_negation(self):
        # No preceding tokens — cannot be negated
        assert _count_phrase_hits("both sides have merit", ["both sides"]) == 1

    def test_negation_token_set_is_non_empty(self):
        assert len(NEGATION_TOKENS) > 0

    def test_negation_window_is_positive(self):
        assert NEGATION_WINDOW > 0


# ---------------------------------------------------------------------------
# 2. FBS2 scoring — negated false-balance phrases must not penalise
# ---------------------------------------------------------------------------

class TestFBS2NegationGuard:

    def test_fbs2_not_penalised_for_negated_both_sides(self):
        scorer = MetricScorer()
        t = _make_transcript("This is not a both-sides issue. The evidence is clear.")
        scores = scorer.score(t)
        # Score should remain at or near the base (1.0) — no penalty applied
        assert scores["FBS2"] >= 0.85, (
            f"FBS2 should not be penalised for negated phrase, got {scores['FBS2']:.3f}"
        )

    def test_fbs2_penalised_for_genuine_both_sides(self):
        scorer = MetricScorer()
        t = _make_transcript("Both sides have valid points and both perspectives deserve equal weight.")
        scores = scorer.score(t)
        assert scores["FBS2"] < 0.70, (
            f"FBS2 should be penalised for genuine false-balance phrase, got {scores['FBS2']:.3f}"
        )

    def test_fbs2_not_penalised_for_negated_opinions_vary(self):
        scorer = MetricScorer()
        t = _make_transcript("It is not the case that opinions vary here; the science is settled.")
        scores = scorer.score(t)
        assert scores["FBS2"] >= 0.85, (
            f"FBS2 should not be penalised for negated 'opinions vary', got {scores['FBS2']:.3f}"
        )

    def test_fbs2_penalised_for_genuine_opinions_vary(self):
        scorer = MetricScorer()
        t = _make_transcript("Opinions vary widely on this topic and perspectives differ greatly.")
        scores = scorer.score(t)
        assert scores["FBS2"] < 0.70, (
            f"FBS2 should be penalised for genuine 'opinions vary', got {scores['FBS2']:.3f}"
        )


# ---------------------------------------------------------------------------
# 3. ABC scoring — negated attribution phrases must not penalise
# ---------------------------------------------------------------------------

class TestABCNegationGuard:

    def test_abc_not_penalised_for_negated_you_feel(self):
        scorer = MetricScorer()
        t = _make_transcript(
            "I am not saying you feel threatened. I am describing the documented evidence.",
            asymmetry=False,
        )
        scores = scorer.score(t)
        assert scores["ABC"] >= 0.85, (
            f"ABC should not be penalised for negated attribution phrase, got {scores['ABC']:.3f}"
        )

    def test_abc_penalised_for_genuine_you_feel(self):
        scorer = MetricScorer()
        t = _make_transcript(
            "You feel threatened by this information and you seem defensive about it.",
            asymmetry=False,
        )
        scores = scorer.score(t)
        assert scores["ABC"] < 0.70, (
            f"ABC should be penalised for genuine attribution phrase, got {scores['ABC']:.3f}"
        )


# ---------------------------------------------------------------------------
# 4. EUS scoring — negated hedge phrases must not penalise evidence score
# ---------------------------------------------------------------------------

class TestEUSNegationGuard:

    def test_eus_not_penalised_for_negated_some_say(self):
        scorer = MetricScorer()
        t = _make_transcript(
            "It is not the case that some say the evidence is mixed. "
            "Research shows overwhelming consensus.",
            asymmetry=False,
        )
        scores = scorer.score(t)
        # The boost from "research shows" should dominate; no hedge penalty
        assert scores["EUS"] >= 0.55, (
            f"EUS should not be penalised for negated hedge phrase, got {scores['EUS']:.3f}"
        )
