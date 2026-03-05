"""Comprehensive tests for tools/audit_session.py (P5).

Covers:
  Section 1  — _parse_markdown_exchanges (markdown parser)
  Section 2  — load_any (format detection and loading)
  Section 3  — _score_direction_ok (scoring helper)
  Section 4  — _format_scores (score formatting)
  Section 5  — _avg_scores (score averaging)
  Section 6  — _drift_signal (drift trend indicator)
  Section 7  — build_report (markdown report builder)
  Section 8  — build_evidence_record (evidence record builder)
  Section 9  — _update_findings_index (persistence logic)
  Section 10 — audit() end-to-end with save=False
  Section 11 — audit() end-to-end with save=True (file persistence)
  Section 12 — audit() with existing fixture transcripts
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from audit_session import (
    _parse_markdown_exchanges,
    load_any,
    _score_direction_ok,
    _format_scores,
    _avg_scores,
    _drift_signal,
    build_report,
    build_evidence_record,
    _update_findings_index,
    audit,
    METRICS,
    METRIC_META,
)

RULES       = _REPO_ROOT / "mapping_rules.yaml"
FIXTURES    = _REPO_ROOT / "fixtures"
TRANSCRIPTS = _REPO_ROOT / "transcripts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_txt_transcript(tmp_path: Path, id_: str = "test_t",
                          assistant_text: str = "The evidence is clear.",
                          tier: str = "settled",
                          asymmetry: bool = False) -> Path:
    txt = (
        f"USER: Tell me about this topic.\n"
        f"ASSISTANT: {assistant_text}\n"
        f"---\n"
        f"id: {id_}\n"
        f"tier: {tier}\n"
        f"asymmetry_flag: {'true' if asymmetry else 'false'}\n"
        f"condition: test_condition\n"
    )
    p = tmp_path / f"{id_}.txt"
    p.write_text(txt)
    return p


def _write_json_transcript(tmp_path: Path, id_: str = "json_t") -> Path:
    data = {
        "id": id_,
        "source": "test",
        "meta": {"tier": "settled", "asymmetry_flag": False, "condition": "json_test"},
        "turns": [
            {"turn_index": 0, "role": "user", "content": "Hello."},
            {"turn_index": 1, "role": "assistant", "content": "The evidence is clear."},
        ],
    }
    p = tmp_path / f"{id_}.json"
    p.write_text(json.dumps(data))
    return p


def _write_md_transcript(tmp_path: Path, id_: str = "md_t") -> Path:
    md = (
        "**User:**\n"
        "> What is the answer?\n"
        "\n"
        "**Claude's Response:**\n"
        "> The evidence clearly supports the consensus.\n"
    )
    p = tmp_path / f"{id_}.md"
    p.write_text(md)
    return p


def _make_aggregates(score_dicts: list[dict]) -> dict:
    """Build an aggregates dict matching what TurnAggregator.compute returns."""
    from ies_lab.aggregator import TurnAggregator
    return TurnAggregator.compute(score_dicts)


def _make_turn_results(scores: dict, failures: list = None, action: str = None) -> list[dict]:
    return [{
        "turn_index": 0,
        "content": "Test content.",
        "scores": scores,
        "failures": failures or [],
        "action": action,
    }]


# ---------------------------------------------------------------------------
# Section 1 — _parse_markdown_exchanges
# ---------------------------------------------------------------------------

class TestParseMarkdownExchanges:

    def test_parses_assistant_turns_from_claude_pattern(self):
        """The regex captures **Claude...**  but NOT **User:** because
        the colon sits inside the bold markers and the 'User' branch
        in the alternation is an exact literal without [^*]*.  This is
        a known limitation (documented in the analysis report) — the
        test verifies current behaviour."""
        md = (
            "**User:**\n"
            "> What is the answer?\n"
            "\n"
            "**Claude's Response:**\n"
            "> The answer is 42.\n"
        )
        t = _parse_markdown_exchanges(md, "test_id")
        assert t["id"] == "test_id"
        assert t["source"] == "markdown_import"
        # Both User and Claude turns are captured (regex fixed)
        assert len(t["turns"]) == 2
        assert t["turns"][0]["role"] == "user"
        assert t["turns"][1]["role"] == "assistant"
        assert "42" in t["turns"][1]["content"]

    def test_strips_blockquote_markers(self):
        md = (
            "**User:**\n"
            "> Hello there.\n"
            "> How are you?\n"
            "\n"
            "**Claude:**\n"
            "> I am fine.\n"
        )
        t = _parse_markdown_exchanges(md, "strip_test")
        # Both User and Claude turns are captured (regex fixed)
        assert len(t["turns"]) == 2
        assert t["turns"][0]["role"] == "user"
        assert ">" not in t["turns"][0]["content"]
        assert "Hello there." in t["turns"][0]["content"]
        assert t["turns"][1]["role"] == "assistant"
        assert ">" not in t["turns"][1]["content"]
        assert "I am fine." in t["turns"][1]["content"]

    def test_researcher_role_mapped_to_user(self):
        """Researcher[^*]* in the regex consumes the colon, so
        **Researcher:** IS captured and mapped to 'user'."""
        md = (
            "**Researcher:**\n"
            "> Question.\n"
            "\n"
            "**Claude:**\n"
            "> Answer.\n"
        )
        t = _parse_markdown_exchanges(md, "researcher")
        assert len(t["turns"]) == 2
        assert t["turns"][0]["role"] == "user"
        assert t["turns"][1]["role"] == "assistant"

    def test_system_role_mapped_correctly(self):
        """System[^*]* in the regex consumes the colon, so
        **System:** IS captured and mapped to 'system'.
        **User:** is NOT captured (exact literal, no [^*]*)."""
        md = (
            "**System:**\n"
            "> You are a helpful assistant.\n"
            "\n"
            "**User:**\n"
            "> Hi.\n"
            "\n"
            "**Claude:**\n"
            "> Hello.\n"
        )
        t = _parse_markdown_exchanges(md, "system_test")
        roles = [turn["role"] for turn in t["turns"]]
        assert "system" in roles
        assert "assistant" in roles
        # User: IS now captured after regex fix (User[^*]*)
        assert roles.count("user") == 1

    def test_fallback_for_no_matches(self):
        md = "Just some plain text without any exchange blocks."
        t = _parse_markdown_exchanges(md, "fallback")
        assert len(t["turns"]) == 1
        assert t["turns"][0]["role"] == "assistant"
        assert t["turns"][0]["content"] == md[:4000]

    def test_meta_defaults(self):
        md = "**User:**\n> Hi.\n\n**Claude:**\n> Hello.\n"
        t = _parse_markdown_exchanges(md, "meta_test")
        assert t["meta"]["tier"] == "unknown"
        assert t["meta"]["asymmetry_flag"] is False
        assert t["meta"]["condition"] == "session_log"

    def test_turn_indices_sequential(self):
        """All turns are captured; indices are sequential."""
        md = (
            "**User:**\n> Q1.\n\n"
            "**Claude:**\n> A1.\n\n"
            "**User:**\n> Q2.\n\n"
            "**Claude:**\n> A2.\n"
        )
        t = _parse_markdown_exchanges(md, "seq_test")
        indices = [turn["turn_index"] for turn in t["turns"]]
        assert indices == [0, 1, 2, 3]
        roles = [turn["role"] for turn in t["turns"]]
        assert roles == ["user", "assistant", "user", "assistant"]

    def test_user_without_colon_inside_bold_is_captured(self):
        """When the colon is OUTSIDE the bold markers, User IS captured."""
        md = (
            "**User**:\n"
            "> Question.\n"
            "\n"
            "**Claude**:\n"
            "> Answer.\n"
        )
        t = _parse_markdown_exchanges(md, "user_outside_colon")
        roles = [turn["role"] for turn in t["turns"]]
        assert "user" in roles
        assert "assistant" in roles
        assert len(t["turns"]) == 2


# ---------------------------------------------------------------------------
# Section 2 — load_any
# ---------------------------------------------------------------------------

class TestLoadAny:

    def test_loads_txt_format(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        result = load_any(p)
        assert len(result) == 1
        assert result[0]["id"] == "test_t"

    def test_loads_json_single_transcript(self, tmp_path):
        p = _write_json_transcript(tmp_path)
        result = load_any(p)
        assert len(result) == 1
        assert result[0]["id"] == "json_t"

    def test_loads_md_format(self, tmp_path):
        p = _write_md_transcript(tmp_path)
        result = load_any(p)
        assert len(result) == 1
        assert result[0]["id"] == "md_t"

    def test_raises_on_unsupported_format(self, tmp_path):
        p = tmp_path / "test.csv"
        p.write_text("a,b,c")
        with pytest.raises(ValueError, match="Unsupported file format"):
            load_any(p)


# ---------------------------------------------------------------------------
# Section 3 — _score_direction_ok
# ---------------------------------------------------------------------------

class TestScoreDirectionOk:

    def test_fbs2_healthy(self):
        assert _score_direction_ok("FBS2", 0.85) is True

    def test_fbs2_unhealthy(self):
        assert _score_direction_ok("FBS2", 0.50) is False

    def test_nai_healthy(self):
        assert _score_direction_ok("NAI", 0.30) is True

    def test_nai_unhealthy(self):
        assert _score_direction_ok("NAI", 0.70) is False

    def test_unknown_metric_always_ok(self):
        assert _score_direction_ok("UNKNOWN", 0.0) is True


# ---------------------------------------------------------------------------
# Section 4 — _format_scores
# ---------------------------------------------------------------------------

class TestFormatScores:

    def test_includes_all_metrics(self):
        scores = {m: 0.80 for m in METRICS}
        result = _format_scores(scores)
        for m in METRICS:
            assert m in result

    def test_warns_on_low_fbs2(self):
        scores = {"FBS2": 0.50, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        result = _format_scores(scores)
        # FBS2 should have a warning flag
        assert "FBS2: 0.50 ⚠" in result

    def test_no_warn_on_healthy_scores(self):
        scores = {"FBS2": 0.90, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        result = _format_scores(scores)
        assert "⚠" not in result

    def test_skips_missing_metrics(self):
        scores = {"FBS2": 0.80}
        result = _format_scores(scores)
        assert "EUS" not in result


# ---------------------------------------------------------------------------
# Section 5 — _avg_scores
# ---------------------------------------------------------------------------

class TestAvgScores:

    def test_averages_correctly(self):
        score_list = [
            {"FBS2": 0.80, "EUS": 0.60},
            {"FBS2": 0.60, "EUS": 0.40},
        ]
        result = _avg_scores(score_list)
        assert result["FBS2"] == pytest.approx(0.70, abs=0.01)
        assert result["EUS"] == pytest.approx(0.50, abs=0.01)

    def test_empty_list_returns_empty(self):
        assert _avg_scores([]) == {}

    def test_single_item_returns_same(self):
        score_list = [{"FBS2": 0.80}]
        result = _avg_scores(score_list)
        assert result["FBS2"] == pytest.approx(0.80, abs=0.01)


# ---------------------------------------------------------------------------
# Section 6 — _drift_signal
# ---------------------------------------------------------------------------

class TestDriftSignal:

    def test_stable_when_drift_near_zero(self):
        result = _drift_signal("FBS2", drift=0.01, std=0.05)
        assert "stable" in result

    def test_improving_when_lower_is_bad_and_drift_positive(self):
        result = _drift_signal("FBS2", drift=0.10, std=0.05)
        assert "improving" in result

    def test_degrading_when_lower_is_bad_and_drift_negative(self):
        result = _drift_signal("FBS2", drift=-0.10, std=0.05)
        assert "degrading" in result

    def test_high_variance_warning(self):
        result = _drift_signal("FBS2", drift=0.01, std=0.20)
        assert "⚠" in result

    def test_nai_improving_when_drift_negative(self):
        # NAI: higher=speculative, lower_is_bad=False, so negative drift = improving
        result = _drift_signal("NAI", drift=-0.10, std=0.05)
        assert "improving" in result


# ---------------------------------------------------------------------------
# Section 7 — build_report
# ---------------------------------------------------------------------------

class TestBuildReport:

    def test_report_contains_session_id(self):
        transcript = {"id": "report_test", "meta": {"tier": "settled", "condition": "test"},
                      "turns": [{"turn_index": 0, "role": "user", "content": "Hi"},
                                {"turn_index": 1, "role": "assistant", "content": "Hello."}]}
        scores = {"FBS2": 0.90, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, [], None, aggregates)
        assert "report_test" in report

    def test_report_contains_turn_analysis(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"},
                      "turns": [{"turn_index": 0, "role": "user", "content": "Q"},
                                {"turn_index": 1, "role": "assistant", "content": "A"}]}
        scores = {"FBS2": 0.90, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        turn_results = [{
            "turn_index": 1, "content": "A", "scores": scores,
            "failures": [], "action": None,
        }]
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, [], None, aggregates)
        assert "Turn-by-Turn Analysis" in report

    def test_report_contains_failures_when_present(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"},
                      "turns": [{"turn_index": 0, "role": "user", "content": "Q"},
                                {"turn_index": 1, "role": "assistant", "content": "A"}]}
        scores = {"FBS2": 0.50, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        turn_results = [{
            "turn_index": 1, "content": "A", "scores": scores,
            "failures": ["FB"], "action": "revise",
        }]
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, ["FB"], "revise", aggregates)
        assert "Failures Detected" in report
        assert "FB" in report
        assert "revise" in report

    def test_report_contains_no_failures_section_when_clean(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"},
                      "turns": [{"turn_index": 0, "role": "user", "content": "Q"},
                                {"turn_index": 1, "role": "assistant", "content": "A"}]}
        scores = {"FBS2": 0.90, "EUS": 0.80, "TCC": 0.80, "NAI": 0.10,
                  "ABC": 0.80, "CS": 0.80, "SCS": 0.80}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, [], None, aggregates)
        assert "No failures detected" in report

    def test_report_contains_finding_template(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"},
                      "turns": [{"turn_index": 0, "role": "assistant", "content": "A"}]}
        scores = {"FBS2": 0.90}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, [], None, aggregates)
        assert "Finding Template" in report
        assert "finding_id:" in report

    def test_report_contains_drift_analysis(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"},
                      "turns": [{"turn_index": 0, "role": "assistant", "content": "A"}]}
        scores = {"FBS2": 0.90, "EUS": 0.80}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        report = build_report(transcript, turn_results, [], None, aggregates)
        assert "Behavioral Drift Analysis" in report


# ---------------------------------------------------------------------------
# Section 8 — build_evidence_record
# ---------------------------------------------------------------------------

class TestBuildEvidenceRecord:

    def test_record_has_required_keys(self):
        transcript = {"id": "rec_t", "meta": {"tier": "settled", "condition": "c"}}
        scores = {"FBS2": 0.90}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        record = build_evidence_record(transcript, turn_results, [], None, aggregates)
        for key in ("session_id", "system", "date", "condition", "tier",
                     "asymmetry_flag", "audited_at", "turns", "session_failures",
                     "session_action", "avg_scores", "drift_analysis",
                     "running_means", "analyst_notes"):
            assert key in record, f"Missing key: {key}"

    def test_record_session_id_matches(self):
        transcript = {"id": "rec_t", "meta": {"tier": "settled", "condition": "c"}}
        scores = {"FBS2": 0.90}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        record = build_evidence_record(transcript, turn_results, [], None, aggregates)
        assert record["session_id"] == "rec_t"

    def test_record_turns_match_input(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"}}
        scores = {"FBS2": 0.90}
        turn_results = _make_turn_results(scores, failures=["FB"], action="revise")
        aggregates = _make_aggregates([scores])
        record = build_evidence_record(transcript, turn_results, ["FB"], "revise", aggregates)
        assert len(record["turns"]) == 1
        assert record["turns"][0]["failures"] == ["FB"]
        assert record["session_action"] == "revise"

    def test_record_avg_scores_backward_compat(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"}}
        scores = {"FBS2": 0.90, "EUS": 0.60}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        record = build_evidence_record(transcript, turn_results, [], None, aggregates)
        assert "avg_scores" in record
        assert "FBS2" in record["avg_scores"]

    def test_record_default_action_is_publish(self):
        transcript = {"id": "t", "meta": {"tier": "settled", "condition": "c"}}
        scores = {"FBS2": 0.90}
        turn_results = _make_turn_results(scores)
        aggregates = _make_aggregates([scores])
        record = build_evidence_record(transcript, turn_results, [], None, aggregates)
        assert record["session_action"] == "publish"


# ---------------------------------------------------------------------------
# Section 9 — _update_findings_index
# ---------------------------------------------------------------------------

class TestUpdateFindingsIndex:

    def _make_record(self, session_id: str = "idx_t", failures: list = None,
                     action: str = "publish") -> dict:
        return {
            "session_id": session_id,
            "system": "test_system",
            "date": "2025-01-01",
            "condition": "test_condition",
            "session_failures": failures or [],
            "session_action": action,
            "audited_at": "2025-01-01T00:00:00+00:00",
        }

    def test_creates_index_file_if_not_exists(self, tmp_path):
        record = self._make_record()
        _update_findings_index(tmp_path, record)
        index_path = tmp_path / "findings_index.json"
        assert index_path.exists()
        with open(index_path) as f:
            index = json.load(f)
        assert len(index) == 1
        assert index[0]["session_id"] == "idx_t"

    def test_appends_to_existing_index(self, tmp_path):
        r1 = self._make_record(session_id="s1")
        r2 = self._make_record(session_id="s2")
        _update_findings_index(tmp_path, r1)
        _update_findings_index(tmp_path, r2)
        with open(tmp_path / "findings_index.json") as f:
            index = json.load(f)
        assert len(index) == 2
        ids = {e["session_id"] for e in index}
        assert ids == {"s1", "s2"}

    def test_updates_existing_entry_by_session_id(self, tmp_path):
        r1 = self._make_record(session_id="s1", action="publish")
        r2 = self._make_record(session_id="s1", action="revise")
        _update_findings_index(tmp_path, r1)
        _update_findings_index(tmp_path, r2)
        with open(tmp_path / "findings_index.json") as f:
            index = json.load(f)
        assert len(index) == 1
        assert index[0]["action"] == "revise"

    def test_preserves_other_entries_on_update(self, tmp_path):
        r1 = self._make_record(session_id="s1")
        r2 = self._make_record(session_id="s2")
        r1_updated = self._make_record(session_id="s1", action="escalate")
        _update_findings_index(tmp_path, r1)
        _update_findings_index(tmp_path, r2)
        _update_findings_index(tmp_path, r1_updated)
        with open(tmp_path / "findings_index.json") as f:
            index = json.load(f)
        assert len(index) == 2
        s1_entry = next(e for e in index if e["session_id"] == "s1")
        assert s1_entry["action"] == "escalate"

    def test_index_entry_has_correct_keys(self, tmp_path):
        record = self._make_record(failures=["FB", "EV"])
        _update_findings_index(tmp_path, record)
        with open(tmp_path / "findings_index.json") as f:
            index = json.load(f)
        entry = index[0]
        for key in ("session_id", "system", "date", "condition",
                     "failures", "action", "audited_at"):
            assert key in entry, f"Missing key: {key}"
        assert entry["failures"] == ["FB", "EV"]


# ---------------------------------------------------------------------------
# Section 10 — audit() end-to-end with save=False
# ---------------------------------------------------------------------------

class TestAuditEndToEndNoSave:

    def test_returns_report_and_record(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        report, record = audit(p, preset="default", output_dir=tmp_path, save=False)
        assert isinstance(report, str)
        assert isinstance(record, dict)

    def test_report_is_markdown(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        report, _ = audit(p, preset="default", output_dir=tmp_path, save=False)
        assert "# IES Audit Report" in report

    def test_record_has_session_id(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="e2e_test")
        _, record = audit(p, preset="default", output_dir=tmp_path, save=False)
        assert record["session_id"] == "e2e_test"

    def test_record_has_turns(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        _, record = audit(p, preset="default", output_dir=tmp_path, save=False)
        assert len(record["turns"]) >= 1

    def test_record_turns_have_scores(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        _, record = audit(p, preset="default", output_dir=tmp_path, save=False)
        for turn in record["turns"]:
            assert "scores" in turn
            assert isinstance(turn["scores"], dict)

    def test_no_files_written_when_save_false(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        audit(p, preset="default", output_dir=tmp_path, save=False)
        sessions_dir = tmp_path / "sessions"
        assert not sessions_dir.exists()

    def test_strict_preset_works(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        report, record = audit(p, preset="strict", output_dir=tmp_path, save=False)
        assert isinstance(report, str)
        assert isinstance(record, dict)

    def test_lenient_preset_works(self, tmp_path):
        p = _write_txt_transcript(tmp_path)
        report, record = audit(p, preset="lenient", output_dir=tmp_path, save=False)
        assert isinstance(report, str)
        assert isinstance(record, dict)


# ---------------------------------------------------------------------------
# Section 11 — audit() end-to-end with save=True
# ---------------------------------------------------------------------------

class TestAuditEndToEndWithSave:

    def test_creates_session_directory(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="save_test")
        audit(p, preset="default", output_dir=tmp_path, save=True)
        session_dir = tmp_path / "sessions" / "save_test"
        assert session_dir.exists()

    def test_writes_report_md(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="save_test")
        audit(p, preset="default", output_dir=tmp_path, save=True)
        report_path = tmp_path / "sessions" / "save_test" / "report.md"
        assert report_path.exists()
        content = report_path.read_text()
        assert "# IES Audit Report" in content

    def test_writes_session_json(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="save_test")
        audit(p, preset="default", output_dir=tmp_path, save=True)
        session_path = tmp_path / "sessions" / "save_test" / "session.json"
        assert session_path.exists()
        with open(session_path) as f:
            record = json.load(f)
        assert record["session_id"] == "save_test"

    def test_creates_findings_index(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="save_test")
        audit(p, preset="default", output_dir=tmp_path, save=True)
        index_path = tmp_path / "findings_index.json"
        assert index_path.exists()
        with open(index_path) as f:
            index = json.load(f)
        assert len(index) >= 1
        assert index[0]["session_id"] == "save_test"

    def test_repeated_audit_updates_findings_index(self, tmp_path):
        p = _write_txt_transcript(tmp_path, id_="repeat_test")
        audit(p, preset="default", output_dir=tmp_path, save=True)
        audit(p, preset="default", output_dir=tmp_path, save=True)
        with open(tmp_path / "findings_index.json") as f:
            index = json.load(f)
        # Should update in-place, not duplicate
        matching = [e for e in index if e["session_id"] == "repeat_test"]
        assert len(matching) == 1


# ---------------------------------------------------------------------------
# Section 12 — audit() with existing fixture transcripts
# ---------------------------------------------------------------------------

class TestAuditWithExistingTranscripts:

    @pytest.fixture(params=sorted(TRANSCRIPTS.glob("*.txt")), ids=lambda p: p.stem)
    def transcript_path(self, request):
        return request.param

    def test_existing_transcript_produces_valid_report(self, transcript_path, tmp_path):
        """Every existing transcript in the repo should produce a valid audit
        report without errors."""
        report, record = audit(
            transcript_path, preset="default", output_dir=tmp_path, save=False
        )
        assert isinstance(report, str)
        assert len(report) > 0
        assert "# IES Audit Report" in report

    def test_existing_transcript_record_has_turns(self, transcript_path, tmp_path):
        _, record = audit(
            transcript_path, preset="default", output_dir=tmp_path, save=False
        )
        if isinstance(record, dict) and "sessions" in record:
            # Multi-session record
            for session in record["sessions"]:
                assert len(session["turns"]) >= 1
        else:
            assert len(record["turns"]) >= 1

    def test_existing_transcript_scores_in_range(self, transcript_path, tmp_path):
        _, record = audit(
            transcript_path, preset="default", output_dir=tmp_path, save=False
        )
        records = record.get("sessions", [record]) if isinstance(record, dict) else [record]
        for rec in records:
            for turn in rec["turns"]:
                for metric, val in turn["scores"].items():
                    assert 0.0 <= val <= 1.0, (
                        f"{transcript_path.stem}: turn {turn['turn_index']} "
                        f"metric {metric}={val} out of [0,1]"
                    )
