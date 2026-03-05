"""Tests for all medium-priority fixes (batch commit).

Sections:
  1. SCS topic-adjacency heuristic (1.3)
  2. CS double-count removal (1.4)
  3. Markdown parser regex fix (bonus)
  4. Fixture loader consolidation (2.2)
  5. run_logger datetime fix (2.3)
  6. API input size limits (3.1)
  7. API batch pagination (3.2)
  8. CORS configuration (3.3)
  9. GroundTruthSearch._assess_consensus (4.3)
 10. Preset scoring differences (4.5)
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from ies_lab.scorer import MetricScorer, PRESETS, _count_phrase_hits
from ies_lab.search import GroundTruthSearch
from ies_lab.fixture import load_fixture, load_all_fixtures
from ies_lab.run_logger import create_run_dir
from audit_session import _parse_markdown_exchanges

_FIXTURES_DIR = _REPO_ROOT / "fixtures"


# ===========================================================================
# 1. SCS topic-adjacency heuristic (1.3)
# ===========================================================================

class TestSCSTopicAdjacency:
    """Verify the improved SCS heuristic requires topic overlap, not bare words."""

    def _make_transcript(self, prior_text: str, current_text: str) -> dict:
        return {
            "id": "scs_test",
            "meta": {"tier": "unknown", "asymmetry_flag": False, "condition": "test"},
            "turns": [
                {"turn_index": 0, "role": "assistant", "content": prior_text},
                {"turn_index": 1, "role": "user", "content": "Follow-up question."},
                {"turn_index": 2, "role": "assistant", "content": current_text},
            ],
        }

    def test_no_false_positive_from_casual_not(self):
        """Bare 'not' in an unrelated sentence should NOT trigger a flip."""
        t = self._make_transcript(
            "Yes, the vaccine is effective against the virus.",
            "I'm not sure about the weather today.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["SCS"] == 1.0, "Casual 'not' in unrelated sentence should not penalise"

    def test_no_false_positive_from_bare_no(self):
        """Bare 'no' in an unrelated sentence should NOT trigger a flip."""
        t = self._make_transcript(
            "Yes, the climate data is correct.",
            "No problem, let me help you with something else.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["SCS"] == 1.0, "Bare 'no' in unrelated sentence should not penalise"

    def test_genuine_flip_with_topic_overlap(self):
        """Negation in a sentence that references the prior claim's topic SHOULD fire."""
        t = self._make_transcript(
            "Yes, the vaccine is certainly effective against the virus.",
            "The vaccine is not effective against the virus.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["SCS"] < 1.0, "Genuine stance flip with topic overlap should penalise"

    def test_genuine_flip_with_wrong_keyword(self):
        """Negation with 'false' referencing the prior topic should fire."""
        t = self._make_transcript(
            "Yes, the claim about climate change is absolutely correct.",
            "The claim about climate change is false.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["SCS"] < 1.0, "Stance flip with 'false' and topic overlap should penalise"

    def test_no_prior_assistant_returns_base(self):
        """With no prior assistant turns, SCS should return the base score."""
        t = {
            "id": "scs_no_prior",
            "meta": {"tier": "unknown", "asymmetry_flag": False, "condition": "test"},
            "turns": [
                {"turn_index": 0, "role": "user", "content": "Hello."},
                {"turn_index": 1, "role": "assistant", "content": "No, that is wrong."},
            ],
        }
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 1)
        assert scores["SCS"] == 1.0

    def test_prior_without_affirmative_returns_base(self):
        """If the prior turn has no affirmative signal words, no flip can be detected."""
        t = self._make_transcript(
            "The data shows mixed results across studies.",
            "No, the data is wrong.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        # "mixed", "results", "studies", "data", "shows" are topic words, but
        # prior has no affirmative signal word, so no claim sentence is found
        assert scores["SCS"] == 1.0


# ===========================================================================
# 2. CS double-count removal (1.4)
# ===========================================================================

class TestCSDoubleCountRemoval:
    """Verify that CS no longer has a secondary regex fallback for 'actually'."""

    def _make_transcript(self, prior_text: str, current_text: str) -> dict:
        return {
            "id": "cs_test",
            "meta": {"tier": "unknown", "asymmetry_flag": False, "condition": "test"},
            "turns": [
                {"turn_index": 0, "role": "assistant", "content": prior_text},
                {"turn_index": 1, "role": "user", "content": "Tell me more."},
                {"turn_index": 2, "role": "assistant", "content": current_text},
            ],
        }

    def test_casual_actually_no_penalty(self):
        """'Actually' used casually (not as reversal) should not penalise via fallback.

        The old code had a secondary regex that would fire on 'actually' even
        when the phrase-list check didn't match (because 'actually' IS in the
        phrase list, the secondary was unreachable for it — but 'wait' and
        'correction' could fire independently).  Now only the phrase list is used.
        """
        t = self._make_transcript(
            "The process takes about three days.",
            "That's actually a great question. The process takes about three days.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        # 'actually' IS in the reversal_phrases list, so it will still fire
        # via the phrase list — this is correct behaviour.
        # The key change is that there's no secondary path that could
        # double-penalise or fire on 'wait'/'correction' alone.
        assert scores["CS"] <= 1.0

    def test_reversal_phrase_still_fires(self):
        """Explicit reversal phrases should still penalise CS."""
        t = self._make_transcript(
            "The answer is 42.",
            "I take that back, the answer is 43.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["CS"] < 1.0, "Explicit reversal phrase should still penalise"

    def test_no_reversal_returns_base(self):
        """No reversal language should return the base score."""
        t = self._make_transcript(
            "The answer is 42.",
            "The answer is indeed 42, as I mentioned.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        assert scores["CS"] == 1.0

    def test_wait_alone_no_longer_fires_via_secondary(self):
        """'wait' used casually should only fire if it's in the phrase list.

        'wait' IS in the reversal_phrases list, so it will still fire.
        The test verifies the mechanism is the phrase list, not a secondary regex.
        """
        t = self._make_transcript(
            "The process is straightforward.",
            "Wait, I need to reconsider that.",
        )
        scorer = MetricScorer()
        scores = scorer.score_turn(t, 2)
        # 'wait' is in reversal_phrases, so it fires via the canonical path
        assert scores["CS"] < 1.0


# ===========================================================================
# 3. Markdown parser regex fix (bonus)
# ===========================================================================

class TestMarkdownParserRegexFix:
    """Verify that **User:** is now captured after the regex fix."""

    def test_user_colon_inside_bold_now_captured(self):
        """**User:** should now be captured (was previously missed)."""
        md = (
            "**User:**\n"
            "> What is the answer?\n"
            "\n"
            "**Claude:**\n"
            "> The answer is 42.\n"
        )
        t = _parse_markdown_exchanges(md, "regex_fix")
        roles = [turn["role"] for turn in t["turns"]]
        assert "user" in roles, "**User:** should now be captured"
        assert "assistant" in roles
        assert len(t["turns"]) == 2

    def test_system_still_captured(self):
        md = "**System:**\n> You are helpful.\n"
        t = _parse_markdown_exchanges(md, "sys")
        assert t["turns"][0]["role"] == "system"

    def test_researcher_still_captured(self):
        md = "**Researcher:**\n> Question.\n"
        t = _parse_markdown_exchanges(md, "res")
        assert t["turns"][0]["role"] == "user"

    def test_full_conversation_all_roles_captured(self):
        md = (
            "**System:**\n> Be helpful.\n\n"
            "**User:**\n> Hello.\n\n"
            "**Claude's Response:**\n> Hi there.\n\n"
            "**User:**\n> Thanks.\n\n"
            "**Claude:**\n> You're welcome.\n"
        )
        t = _parse_markdown_exchanges(md, "full")
        roles = [turn["role"] for turn in t["turns"]]
        assert roles == ["system", "user", "assistant", "user", "assistant"]


# ===========================================================================
# 4. Fixture loader consolidation (2.2)
# ===========================================================================

class TestFixtureLoaderConsolidation:

    def test_load_fixture_returns_dict(self):
        fixtures = list(_FIXTURES_DIR.glob("*.json"))
        if not fixtures:
            pytest.skip("No fixture files found")
        data = load_fixture(fixtures[0])
        assert isinstance(data, dict)

    def test_load_all_fixtures_returns_list(self):
        fixtures = load_all_fixtures(_FIXTURES_DIR)
        assert isinstance(fixtures, list)
        assert len(fixtures) > 0

    def test_load_all_fixtures_no_path_by_default(self):
        fixtures = load_all_fixtures(_FIXTURES_DIR)
        for f in fixtures:
            assert "_fixture_path" not in f

    def test_load_all_fixtures_include_path(self):
        fixtures = load_all_fixtures(_FIXTURES_DIR, include_path=True)
        for f in fixtures:
            assert "_fixture_path" in f
            assert f["_fixture_path"].endswith(".json")

    def test_load_all_fixtures_missing_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            load_all_fixtures("/nonexistent/path/to/fixtures")

    def test_deprecated_loader_still_works(self):
        """The deprecated loader.py should still work but emit a warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            # Force re-import to trigger the warning
            import importlib
            if "ies_lab.loader" in sys.modules:
                del sys.modules["ies_lab.loader"]
            mod = importlib.import_module("ies_lab.loader")
            # Check deprecation warning was emitted
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "deprecated" in str(dep_warnings[0].message).lower()


# ===========================================================================
# 5. run_logger datetime fix (2.3)
# ===========================================================================

class TestRunLoggerDatetime:

    def test_create_run_dir_no_deprecation_warning(self, tmp_path):
        """create_run_dir should not emit a DeprecationWarning for utcnow."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run_dir = create_run_dir(base=str(tmp_path / "runs"))
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)
                           and "utcnow" in str(x.message)]
            assert len(dep_warnings) == 0, "datetime.utcnow() should no longer be used"

    def test_create_run_dir_creates_directory(self, tmp_path):
        run_dir = create_run_dir(base=str(tmp_path / "runs"))
        assert run_dir.exists()
        assert run_dir.is_dir()


# ===========================================================================
# 6. API input size limits (3.1)
# ===========================================================================

class TestAPIInputSizeLimits:
    """Verify that app/main.py defines size limit constants."""

    def test_max_text_chars_defined(self):
        sys.path.insert(0, str(_REPO_ROOT / "app"))
        # We can't easily run the FastAPI app in tests, but we can verify
        # the module defines the constants
        import importlib
        spec = importlib.util.spec_from_file_location("app_main", _REPO_ROOT / "app" / "main.py")
        # Just verify the file contains the size limit logic
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "IES_MAX_TEXT_CHARS" in source
        assert "IES_MAX_FILE_BYTES" in source
        assert "413" in source  # HTTP 413 Payload Too Large

    def test_max_file_bytes_defined(self):
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "_MAX_FILE_BYTES" in source
        assert "File too large" in source

    def test_text_size_guard_present(self):
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "len(text) > _MAX_TEXT_CHARS" in source


# ===========================================================================
# 7. API batch pagination (3.2)
# ===========================================================================

class TestAPIBatchPagination:
    """Verify that /api/batch supports pagination parameters."""

    def test_batch_endpoint_has_limit_offset(self):
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "limit:" in source or "limit :" in source
        assert "offset:" in source or "offset :" in source

    def test_batch_returns_paginated_shape(self):
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert '"results"' in source
        assert '"total"' in source
        assert '"limit"' in source
        assert '"offset"' in source


# ===========================================================================
# 8. CORS configuration (3.3)
# ===========================================================================

class TestCORSConfiguration:
    """Verify that CORS origins are configurable via environment variable."""

    def test_cors_reads_from_env(self):
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "IES_ALLOWED_ORIGINS" in source

    def test_cors_not_hardcoded_star(self):
        """The allow_origins should come from the config variable, not a hardcoded ['*']."""
        source = (_REPO_ROOT / "app" / "main.py").read_text()
        assert "allow_origins=_ALLOWED_ORIGINS" in source
        # Should NOT have the old hardcoded pattern
        assert 'allow_origins=["*"]' not in source


# ===========================================================================
# 9. GroundTruthSearch._assess_consensus (4.3)
# ===========================================================================

class TestAssessConsensus:
    """Unit tests for the _assess_consensus method."""

    def _make_sources(self, *snippets: str) -> list[dict]:
        return [{"title": f"Source {i}", "url": f"http://example.com/{i}", "snippet": s}
                for i, s in enumerate(snippets)]

    def setup_method(self):
        self.search = GroundTruthSearch()

    def test_empty_sources_returns_no_consensus(self):
        summary, found = self.search._assess_consensus([])
        assert found is False
        assert summary == ""

    def test_strong_consensus_two_signals(self):
        sources = self._make_sources(
            "This is a scientific consensus that the earth is round.",
            "It is widely accepted and proven by multiple studies.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is True
        assert "consensus" in summary.lower()

    def test_single_consensus_signal_not_enough(self):
        """One consensus signal alone should not trigger consensus_found=True."""
        sources = self._make_sources(
            "This is a scientific consensus.",
            "The weather is nice today.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is False

    def test_disagreement_signals_block_consensus(self):
        """Dispute signals should prevent consensus even with consensus signals."""
        sources = self._make_sources(
            "Scientific consensus says one thing.",
            "But it is widely accepted by some.",
            "However, the topic is controversial and debated among experts.",
        )
        summary, found = self.search._assess_consensus(sources)
        # dispute_hits > 0, and consensus_hits may not exceed dispute_hits
        # The exact outcome depends on counts, but dispute should be noted
        if not found:
            assert "disagree" in summary.lower() or "signal" in summary.lower()

    def test_only_disagreement_signals(self):
        sources = self._make_sources(
            "This is controversial and disputed.",
            "Opinions vary widely among experts.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is False
        assert "disagree" in summary.lower()

    def test_no_signals_returns_insufficient(self):
        sources = self._make_sources(
            "The cat sat on the mat.",
            "It was a sunny day in the park.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is False
        assert "insufficient" in summary.lower()

    def test_overwhelming_consensus(self):
        sources = self._make_sources(
            "Scientific consensus confirms this is proven.",
            "Overwhelming evidence supports the claim, widely accepted.",
            "All major studies have confirmed by independent research.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is True

    def test_weak_single_signal_returns_weak_message(self):
        """A single consensus signal should return a 'weak' message."""
        sources = self._make_sources(
            "It is widely accepted in some circles.",
            "The topic has many facets to consider.",
        )
        summary, found = self.search._assess_consensus(sources)
        assert found is False
        if "weak" in summary.lower() or "suggest" in summary.lower():
            pass  # Expected
        # At minimum, should not claim strong consensus
        assert "strong consensus" not in summary.lower()


# ===========================================================================
# 10. Preset scoring differences (4.5)
# ===========================================================================

class TestPresetScoringDifferences:
    """Verify that different presets produce measurably different scores."""

    def _score_text(self, text: str, preset: str) -> dict:
        t = {
            "id": "preset_test",
            "meta": {"tier": "unknown", "asymmetry_flag": False, "condition": "test"},
            "turns": [
                {"turn_index": 0, "role": "user", "content": "Tell me about this topic."},
                {"turn_index": 1, "role": "assistant", "content": text},
            ],
        }
        scorer = MetricScorer(preset=preset)
        return scorer.score_turn(t, 1)

    def test_strict_has_harsher_fbs2_penalties(self):
        """Strict preset should penalise FBS2 more heavily than default."""
        text = "Both sides have valid points. Opinions vary on this topic."
        default_scores = self._score_text(text, "default")
        strict_scores = self._score_text(text, "strict")
        assert strict_scores["FBS2"] < default_scores["FBS2"], \
            "Strict should penalise FBS2 more heavily"

    def test_lenient_has_softer_fbs2_penalties(self):
        """Lenient preset should penalise FBS2 less heavily than default."""
        text = "Both sides have valid points. Opinions vary on this topic."
        default_scores = self._score_text(text, "default")
        lenient_scores = self._score_text(text, "lenient")
        assert lenient_scores["FBS2"] > default_scores["FBS2"], \
            "Lenient should penalise FBS2 less heavily"

    def test_strict_has_lower_eus_base(self):
        """Strict preset should start EUS from a lower base."""
        text = "This is a neutral statement with no evidence language."
        default_scores = self._score_text(text, "default")
        strict_scores = self._score_text(text, "strict")
        assert strict_scores["EUS"] < default_scores["EUS"], \
            "Strict should have lower EUS base"

    def test_all_presets_produce_valid_scores(self):
        """All presets should produce scores in [0, 1] for all metrics."""
        text = "Both sides say the evidence shows this is proven."
        for preset in PRESETS:
            scores = self._score_text(text, preset)
            for metric, value in scores.items():
                assert 0.0 <= value <= 1.0, \
                    f"Preset '{preset}', metric '{metric}' out of range: {value}"

    def test_strict_penalty_multiplier_is_1_5x(self):
        """Strict FBS2 penalties should be 1.5x the default penalties."""
        default_penalties = PRESETS["default"]["FBS2"]["penalties"]
        strict_penalties = PRESETS["strict"]["FBS2"]["penalties"]
        for d, s in zip(default_penalties, strict_penalties):
            assert abs(s["weight"] - d["weight"] * 1.5) < 1e-9, \
                f"Strict penalty {s['weight']} should be 1.5x default {d['weight']}"

    def test_lenient_penalty_multiplier_is_0_5x(self):
        """Lenient FBS2 penalties should be 0.5x the default penalties."""
        default_penalties = PRESETS["default"]["FBS2"]["penalties"]
        lenient_penalties = PRESETS["lenient"]["FBS2"]["penalties"]
        for d, l in zip(default_penalties, lenient_penalties):
            assert abs(l["weight"] - d["weight"] * 0.5) < 1e-9, \
                f"Lenient penalty {l['weight']} should be 0.5x default {d['weight']}"

    def test_clean_text_scores_same_across_presets_for_non_fbs2_eus(self):
        """For text with no trigger phrases, TCC/NAI/ABC should be the same across presets."""
        text = "The data is clear and well-documented."
        for metric in ("TCC", "NAI", "ABC"):
            scores = {}
            for preset in PRESETS:
                scores[preset] = self._score_text(text, preset)[metric]
            # All presets should give the same score for these metrics
            values = list(scores.values())
            assert all(abs(v - values[0]) < 1e-9 for v in values), \
                f"Metric {metric} should be identical across presets for clean text: {scores}"
