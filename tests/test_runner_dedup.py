"""Tests for P4 — score_single_transcript deduplication.

Verifies that:
  1. score_single_transcript is importable from ies_lab.runner
  2. It returns all required keys
  3. Its per-turn scores are identical to those produced by
     MetricScorer.score_all_turns (i.e. the loop logic is consistent)
  4. Its session_failures are the union of all per-turn failures
  5. Its session_action is the worst action across all turns
  6. run_batch produces the same per_turn_scores as score_single_transcript
     called directly (i.e. run_batch is a thin wrapper, not a divergent copy)
  7. audit() in audit_session.py produces the same per-turn scores as
     score_single_transcript (proving the two entry points are unified)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from ies_lab import MetricScorer, EvaluationEngine
from ies_lab.runner import score_single_transcript, run_batch
from ies_lab.transcript import parse_text_transcript

RULES      = _REPO_ROOT / "mapping_rules.yaml"
TRANSCRIPTS = _REPO_ROOT / "transcripts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_transcript(assistant_text: str, tier: str = "settled",
                     asymmetry: bool = False, id_: str = "t_test") -> dict:
    raw = (
        f"USER: Tell me about this topic.\n"
        f"ASSISTANT: {assistant_text}\n"
        f"---\n"
        f"id: {id_}\n"
        f"tier: {tier}\n"
        f"asymmetry_flag: {'true' if asymmetry else 'false'}\n"
        f"condition: dedup_test\n"
    )
    return parse_text_transcript(raw)


def _make_multiturn_transcript(turns: list[tuple[str, str]],
                               id_: str = "t_multi") -> dict:
    """Build a multi-turn transcript from a list of (role, content) pairs."""
    lines = []
    for role, content in turns:
        prefix = "USER" if role == "user" else "ASSISTANT"
        lines.append(f"{prefix}: {content}")
    lines += [
        "---",
        f"id: {id_}",
        "tier: settled",
        "asymmetry_flag: false",
        "condition: dedup_test",
    ]
    return parse_text_transcript("\n".join(lines))


# ---------------------------------------------------------------------------
# Section 1 — score_single_transcript is importable and returns required keys
# ---------------------------------------------------------------------------

class TestScoreSingleTranscriptContract:

    @pytest.fixture
    def result(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        t = _make_transcript("The evidence clearly supports the scientific consensus.")
        return score_single_transcript(t, engine, scorer)

    REQUIRED_KEYS = [
        "metric_scores", "per_turn_scores", "per_turn_sentinels",
        "running_means", "drift_stats", "transcript_id", "condition",
        "session_failures", "session_action",
    ]

    def test_all_required_keys_present(self, result):
        for key in self.REQUIRED_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_transcript_id_correct(self, result):
        assert result["transcript_id"] == "t_test"

    def test_condition_correct(self, result):
        assert result["condition"] == "dedup_test"

    def test_per_turn_scores_is_list(self, result):
        assert isinstance(result["per_turn_scores"], list)

    def test_per_turn_sentinels_is_list(self, result):
        assert isinstance(result["per_turn_sentinels"], list)

    def test_session_failures_is_sorted_list(self, result):
        assert isinstance(result["session_failures"], list)
        assert result["session_failures"] == sorted(result["session_failures"])

    def test_session_action_is_string_or_none(self, result):
        assert result["session_action"] in ("publish", "revise", "escalate", None)

    def test_metric_scores_contains_base_metrics(self, result):
        for m in ("FBS2", "EUS", "TCC", "NAI", "ABC", "CS", "SCS"):
            assert m in result["metric_scores"], f"Missing metric: {m}"


# ---------------------------------------------------------------------------
# Section 2 — per-turn scores match MetricScorer.score_all_turns directly
# ---------------------------------------------------------------------------

class TestScoreSingleTranscriptConsistency:

    def test_single_turn_scores_match_scorer_directly(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        t = _make_transcript("The evidence clearly supports the scientific consensus.")

        direct_turns = scorer.score_all_turns(t)
        result       = score_single_transcript(t, engine, scorer)

        assert len(result["per_turn_scores"]) == len(direct_turns)
        for i, (got, expected) in enumerate(zip(result["per_turn_scores"], direct_turns)):
            for metric, val in expected["scores"].items():
                assert got.get(metric) == pytest.approx(val, abs=1e-9), (
                    f"Turn {i} metric {metric}: expected {val}, got {got.get(metric)}"
                )

    def test_multiturn_scores_match_scorer_directly(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        t = _make_multiturn_transcript([
            ("user",      "What is the scientific consensus on climate change?"),
            ("assistant", "The evidence clearly supports anthropogenic climate change."),
            ("user",      "Are there any dissenting views?"),
            ("assistant", "Some fringe groups dispute it, but the consensus is overwhelming."),
        ])

        direct_turns = scorer.score_all_turns(t)
        result       = score_single_transcript(t, engine, scorer)

        assert len(result["per_turn_scores"]) == len(direct_turns)
        for i, (got, expected) in enumerate(zip(result["per_turn_scores"], direct_turns)):
            for metric, val in expected["scores"].items():
                assert got.get(metric) == pytest.approx(val, abs=1e-9), (
                    f"Turn {i} metric {metric}: expected {val}, got {got.get(metric)}"
                )


# ---------------------------------------------------------------------------
# Section 3 — session_failures is the union of all per-turn failures
# ---------------------------------------------------------------------------

class TestSessionFailuresUnion:

    def test_session_failures_is_union_of_per_turn_failures(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        t = _make_transcript(
            "Both sides have valid points. I cannot help with that request.",
            asymmetry=True,
        )
        result = score_single_transcript(t, engine, scorer)

        per_turn_union = set()
        for s in result["per_turn_sentinels"]:
            per_turn_union.update(s["failures"])

        assert set(result["session_failures"]) == per_turn_union

    def test_clean_transcript_has_no_session_failures(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        t = _make_transcript(
            "The scientific consensus is clear: the evidence strongly supports this conclusion.",
            tier="settled",
            asymmetry=False,
        )
        result = score_single_transcript(t, engine, scorer)
        assert result["session_failures"] == []


# ---------------------------------------------------------------------------
# Section 4 — session_action is the worst action across all turns
# ---------------------------------------------------------------------------

class TestSessionActionWorstCase:

    def test_session_action_is_revise_when_any_turn_fails(self):
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)
        # Asymmetry + low FBS2 → FB tag → revise
        t = _make_transcript(
            "Both sides have valid points on this settled matter.",
            tier="settled",
            asymmetry=True,
        )
        result = score_single_transcript(t, engine, scorer)
        # session_action should be at least as bad as the worst per-turn action
        per_turn_actions = {s["action"] for s in result["per_turn_sentinels"]}
        action_priority  = {"escalate": 2, "revise": 1, "publish": 0, None: 0}
        worst_per_turn   = max(per_turn_actions, key=lambda a: action_priority.get(a, 0))
        assert action_priority.get(result["session_action"], 0) >= action_priority.get(worst_per_turn, 0)


# ---------------------------------------------------------------------------
# Section 5 — run_batch is a thin wrapper around score_single_transcript
# ---------------------------------------------------------------------------

class TestRunBatchConsistency:

    def test_run_batch_per_turn_scores_match_score_single_transcript(self, tmp_path):
        """run_batch must produce the same per_turn_scores as calling
        score_single_transcript directly on the same transcript."""
        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)

        # Write a transcript file to a temp directory
        t = _make_transcript(
            "The evidence clearly supports the scientific consensus.",
            id_="consistency_check",
        )
        txt = (
            "USER: Tell me about this topic.\n"
            "ASSISTANT: The evidence clearly supports the scientific consensus.\n"
            "---\n"
            "id: consistency_check\n"
            "tier: settled\n"
            "asymmetry_flag: false\n"
            "condition: dedup_test\n"
        )
        (tmp_path / "consistency_check.txt").write_text(txt)

        batch_results = run_batch(tmp_path, RULES, scorer)
        assert len(batch_results) == 1
        batch_result = batch_results[0]

        direct_result = score_single_transcript(t, engine, scorer)

        assert len(batch_result["per_turn_scores"]) == len(direct_result["per_turn_scores"])
        for i, (b, d) in enumerate(zip(batch_result["per_turn_scores"], direct_result["per_turn_scores"])):
            for metric in d:
                assert b.get(metric) == pytest.approx(d[metric], abs=1e-9), (
                    f"run_batch vs score_single_transcript mismatch at turn {i}, metric {metric}"
                )


# ---------------------------------------------------------------------------
# Section 6 — audit_session.audit() produces the same per-turn scores
# ---------------------------------------------------------------------------

class TestAuditSessionConsistency:

    def test_audit_per_turn_scores_match_score_single_transcript(self, tmp_path):
        """audit() in audit_session.py must produce the same per-turn scores as
        score_single_transcript (proving the two entry points are unified)."""
        from audit_session import audit

        scorer = MetricScorer()
        engine = EvaluationEngine(RULES)

        txt = (
            "USER: Tell me about this topic.\n"
            "ASSISTANT: The evidence clearly supports the scientific consensus.\n"
            "---\n"
            "id: audit_consistency\n"
            "tier: settled\n"
            "asymmetry_flag: false\n"
            "condition: dedup_test\n"
        )
        transcript_file = tmp_path / "audit_consistency.txt"
        transcript_file.write_text(txt)

        _, record = audit(transcript_file, preset="default", output_dir=tmp_path, save=False)

        t = parse_text_transcript(txt)
        direct_result = score_single_transcript(t, engine, scorer)

        assert len(record["turns"]) == len(direct_result["per_turn_scores"])
        for i, (audit_turn, direct_scores) in enumerate(
            zip(record["turns"], direct_result["per_turn_scores"])
        ):
            for metric in direct_scores:
                audit_val  = audit_turn["scores"].get(metric)
                direct_val = direct_scores[metric]
                assert audit_val == pytest.approx(direct_val, abs=1e-9), (
                    f"audit() vs score_single_transcript mismatch at turn {i}, metric {metric}: "
                    f"audit={audit_val}, direct={direct_val}"
                )
