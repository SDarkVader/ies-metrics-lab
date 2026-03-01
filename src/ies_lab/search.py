from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GroundTruthResult:
    query: str
    sources: list[dict] = field(default_factory=list)
    consensus_found: bool = False
    consensus_summary: str = ""
    tier_suggestion: str = "unknown"
    asymmetry_suggestion: bool = False


class GroundTruthSearch:
    """
    Web search grounding for factual claims.

    Uses the duckduckgo-search library (no API key required).
    Falls back gracefully to consensus_found=False if offline or library missing.
    Results are cached to avoid redundant network calls.
    """

    def __init__(self, cache_path: Path | None = None, max_results: int = 5):
        self._cache_path = Path(cache_path) if cache_path else None
        self._max_results = max_results
        self._cache: dict[str, dict] = {}
        if self._cache_path and self._cache_path.exists():
            try:
                with open(self._cache_path) as f:
                    self._cache = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def lookup(self, query: str) -> GroundTruthResult:
        if query in self._cache:
            return self._deserialise(self._cache[query])

        result = self._fetch(query)
        self._cache[query] = self._serialise(result)
        self._save_cache()
        return result

    # ------------------------------------------------------------------

    def _fetch(self, query: str) -> GroundTruthResult:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return GroundTruthResult(query=query)

        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=self._max_results))
        except Exception:
            return GroundTruthResult(query=query)

        if not raw:
            return GroundTruthResult(query=query)

        sources = [
            {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
            for r in raw
        ]
        consensus_summary, consensus_found = self._assess_consensus(sources)
        tier_suggestion = "settled" if consensus_found else "unknown"
        asymmetry_suggestion = consensus_found

        return GroundTruthResult(
            query=query,
            sources=sources,
            consensus_found=consensus_found,
            consensus_summary=consensus_summary,
            tier_suggestion=tier_suggestion,
            asymmetry_suggestion=asymmetry_suggestion,
        )

    def _assess_consensus(self, sources: list[dict]) -> tuple[str, bool]:
        """
        Naive consensus detection: if the top snippets share dominant keywords,
        treat that as consensus. Returns (summary, consensus_found).
        """
        if not sources:
            return "", False

        snippets = " ".join(s["snippet"] for s in sources).lower()
        consensus_signals = [
            "scientific consensus", "overwhelming evidence", "widely accepted",
            "established fact", "proven", "confirmed by", "all major",
            "unanimously", "no credible evidence to the contrary",
        ]
        disagreement_signals = [
            "controversial", "debated", "disputed", "opinions vary",
            "some scientists", "not all experts agree", "contested",
        ]

        consensus_hits = sum(1 for s in consensus_signals if s in snippets)
        dispute_hits = sum(1 for s in disagreement_signals if s in snippets)

        if consensus_hits > dispute_hits and consensus_hits >= 2:
            summary = f"Sources indicate strong consensus. ({consensus_hits} consensus signals)"
            return summary, True
        if dispute_hits > 0:
            summary = f"Sources show disagreement. ({dispute_hits} dispute signals)"
            return summary, False

        # Fallback: moderately confident if any consensus signal present
        if consensus_hits >= 1:
            return "Sources suggest consensus, but signal is weak.", False

        return "Insufficient signal to determine consensus.", False

    def _serialise(self, result: GroundTruthResult) -> dict:
        return {
            "query": result.query,
            "sources": result.sources,
            "consensus_found": result.consensus_found,
            "consensus_summary": result.consensus_summary,
            "tier_suggestion": result.tier_suggestion,
            "asymmetry_suggestion": result.asymmetry_suggestion,
        }

    def _deserialise(self, data: dict) -> GroundTruthResult:
        return GroundTruthResult(**data)

    def _save_cache(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._cache_path, "w") as f:
            json.dump(self._cache, f, indent=2)
