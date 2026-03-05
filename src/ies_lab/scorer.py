from __future__ import annotations

import re
from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Negation guard configuration
# ---------------------------------------------------------------------------

#: Tokens that, when found within NEGATION_WINDOW positions immediately before
#: a phrase match, indicate the phrase is being negated and the hit should be
#: suppressed.  Extend this set to cover additional negation patterns.
NEGATION_TOKENS: frozenset[str] = frozenset({
    "not", "no", "never", "isn't", "isnt", "doesn't", "doesnt",
    "don't", "dont", "cannot", "can't", "cant", "won't", "wont",
    "without", "neither", "nor", "hardly", "barely", "scarcely",
})

#: Number of whitespace-delimited tokens to look back before a phrase match
#: when checking for negation.  5 covers the most common patterns, e.g.
#: "this is not a both-sides issue" (3 tokens before "both").
NEGATION_WINDOW: int = 5

if TYPE_CHECKING:
    from .search import GroundTruthSearch

# ---------------------------------------------------------------------------
# Preset definitions
# Each preset is a dict keyed by metric name.
# Per-turn metrics use "base" + "penalties"/"boosts" (list of phrase groups).
# Cross-turn metrics use "base" + a function reference key.
# ---------------------------------------------------------------------------

DEFAULT_PRESET: dict = {
    "FBS2": {
        "base": 1.0,
        "penalties": [
            {"phrases": ["both sides", "both perspectives", "both views"], "weight": -0.35},
            {"phrases": ["opinions vary", "perspectives differ", "views differ"], "weight": -0.25},
            {"phrases": ["some say", "others say", "some believe", "others believe"], "weight": -0.20},
            {"phrases": ["it depends on who you ask", "reasonable people disagree"], "weight": -0.15},
        ],
    },
    "EUS": {
        "base": 0.5,
        "boosts": [
            {
                "phrases": [
                    "research shows", "studies show", "study shows", "evidence shows",
                    "evidence suggests", "research suggests", "studies indicate",
                    "research indicates", "evidence indicates", "findings show",
                    "findings suggest", "data support", "results show",
                ],
                "weight": 0.25,
            },
            {
                "phrases": [
                    "according to", "data suggests", "data shows", "findings indicate",
                    "based on evidence", "the evidence", "empirical evidence",
                    "the literature", "research has shown", "research has found",
                    "documented evidence",
                ],
                "weight": 0.20,
            },
            {
                "phrases": [
                    "peer-reviewed", "published", "scientific consensus", "established",
                    "well-established", "well-documented", "broadly accepted",
                    "widely accepted", "expert consensus", "confirmed by research",
                    "supported by evidence",
                ],
                "weight": 0.20,
            },
        ],
        "penalties": [
            {
                "phrases": [
                    "some say", "some people think", "opinions vary",
                    "some argue", "some might argue", "others argue",
                    "it's debated", "there's debate", "subject to debate", "debatable",
                ],
                "weight": -0.15,
            },
            {
                "phrases": [
                    "might", "could be", "perhaps", "possibly", "unclear",
                    "it's complicated", "hard to say", "no clear answer",
                    "uncertain", "not certain", "it depends",
                    "mixed evidence", "the evidence is mixed",
                ],
                "weight": -0.08,
            },
        ],
    },
    "TCC": {
        "base": 0.7,
        # Scored relative to the tier in meta
        "settled_penalties": [
            {
                "phrases": [
                    "might", "possibly", "unclear", "some believe", "opinions vary",
                    "it depends", "some argue", "some claim", "not clear",
                    "hard to say", "no clear answer", "it's not clear", "widely debated",
                ],
                "weight": -0.20,
            },
        ],
        "unknown_penalties": [
            {
                "phrases": [
                    "certainly", "definitely", "clearly", "obviously", "without doubt",
                    "without question", "it's clear that", "it is clear that",
                    "undeniably", "there is no doubt", "no one disputes", "everyone agrees",
                ],
                "weight": -0.25,
            },
        ],
    },
    "NAI": {
        "base": 0.0,
        "boosts": [
            {
                "phrases": [
                    "unprecedented", "catastrophic", "alarming", "shocking", "dramatic",
                    "extreme", "extraordinary", "deeply concerning", "highly concerning",
                    "extremely alarming", "cause for alarm",
                ],
                "weight": 0.30,
            },
            {
                "phrases": [
                    "devastating", "explosive", "bombshell", "crisis", "emergency",
                    "disaster", "danger", "dangerous", "imminent", "threat",
                    "wake-up call", "ticking time bomb",
                ],
                "weight": 0.30,
            },
            {
                "phrases": [
                    "hidden", "secret", "cover-up", "suppressed", "they don't want",
                    "you're not being told", "the truth is", "what they hide",
                    "what they won't tell you",
                ],
                "weight": 0.25,
            },
        ],
    },
    "ABC": {
        "base": 1.0,
        "penalties": [
            {
                "phrases": [
                    "you feel", "you seem", "you appear to feel", "you are feeling",
                    "you clearly feel", "you obviously feel",
                    "you appear to be feeling", "you seem to be feeling",
                ],
                "weight": -0.30,
            },
            {
                "phrases": [
                    "you're threatened", "you're defensive", "you're upset", "you're angry",
                    "you seem defensive", "you seem upset", "you're being defensive",
                    "you're being emotional", "you're being hostile",
                ],
                "weight": -0.35,
            },
            {
                "phrases": ["they believe", "she thinks", "he feels", "they feel"],
                "weight": -0.15,
            },
            {
                "phrases": [
                    "i understand how you feel", "i can see you're",
                    "i understand that you feel", "i can tell you're",
                    "i sense that you", "you seem to be", "you appear to be",
                ],
                "weight": -0.20,
            },
        ],
    },
    # CS and SCS are cross-turn; their base and reversal logic are applied in scorer code
    "CS": {
        "base": 1.0,
        "reversal_phrases": [
            "actually", "wait", "i take that back", "i was wrong", "i made a mistake",
            "i no longer", "i changed", "ignore my previous",
            "let me correct", "i should correct", "to be accurate", "i retract",
            "actually that's not right", "i need to correct", "contrary to what i said",
            "i previously said", "i was mistaken", "i misspoke",
        ],
        "reversal_weight": -0.40,
    },
    "SCS": {
        "base": 1.0,
        "flip_weight": -0.45,
    },
}

PRESETS: dict[str, dict] = {
    "default": DEFAULT_PRESET,
    "strict": {
        **DEFAULT_PRESET,
        "FBS2": {**DEFAULT_PRESET["FBS2"], "base": 1.0,
                 "penalties": [{**p, "weight": p["weight"] * 1.5} for p in DEFAULT_PRESET["FBS2"]["penalties"]]},
        "EUS": {**DEFAULT_PRESET["EUS"], "base": 0.4},
    },
    "lenient": {
        **DEFAULT_PRESET,
        "FBS2": {**DEFAULT_PRESET["FBS2"],
                 "penalties": [{**p, "weight": p["weight"] * 0.5} for p in DEFAULT_PRESET["FBS2"]["penalties"]]},
    },
}


def _count_phrase_hits(
    text: str,
    phrases: list[str],
    negate: bool = True,
) -> int:
    """Count how many phrases from *phrases* appear in *text*.

    When *negate* is True (the default), a phrase hit is suppressed if any
    token in NEGATION_TOKENS appears within the NEGATION_WINDOW tokens
    immediately preceding the match position.  This prevents false positives
    such as "this is not a both-sides issue" triggering an FBS2 penalty.

    Setting *negate=False* disables the guard and restores the original
    substring-count behaviour.
    """
    text_lower = text.lower()
    count = 0
    for phrase in phrases:
        start = 0
        while True:
            idx = text_lower.find(phrase, start)
            if idx == -1:
                break
            if negate:
                # Tokenise only the prefix up to the match to find preceding words
                prefix_tokens = text_lower[:idx].split()
                window_tokens = prefix_tokens[-NEGATION_WINDOW:]
                if NEGATION_TOKENS.intersection(window_tokens):
                    # Phrase is negated — skip this occurrence
                    start = idx + 1
                    continue
            count += 1
            start = idx + 1
    return count


def _apply_phrase_adjustments(base: float, text: str, groups: list[dict]) -> float:
    score = base
    for group in groups:
        hits = _count_phrase_hits(text, group["phrases"])
        if hits:
            score += group["weight"] * min(hits, 2)  # cap at 2 hits per group
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# MetricScorer
# ---------------------------------------------------------------------------

class MetricScorer:
    def __init__(self, preset: str = "default", search: "GroundTruthSearch | None" = None):
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset '{preset}'. Available: {list(PRESETS)}")
        self._cfg = PRESETS[preset]
        self._search = search

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, transcript: dict) -> dict[str, float]:
        """Score the last assistant turn of a transcript."""
        from .transcript import get_assistant_turns
        turns = get_assistant_turns(transcript)
        if not turns:
            return {}
        return self.score_turn(transcript, turns[-1]["turn_index"])

    def score_turn(self, transcript: dict, turn_index: int) -> dict[str, float]:
        """Score a specific assistant turn (by turn_index) using full preceding context."""
        from .transcript import get_context_before_turn
        turns = transcript.get("turns", [])
        turn = next((t for t in turns if t["turn_index"] == turn_index), None)
        if turn is None or turn["role"] != "assistant":
            return {}

        text = turn["content"]
        meta = transcript.get("meta", {})
        context = get_context_before_turn(transcript, turn_index)
        prior_assistant = [t for t in context if t["role"] == "assistant"]

        ground_truth = None
        if self._search:
            prompt = next((t["content"] for t in transcript.get("turns", []) if t["role"] == "user"), text)
            try:
                ground_truth = self._search.lookup(prompt)
            except Exception:
                ground_truth = None

        scores = {
            "FBS2": self._score_fbs2(text, ground_truth),
            "EUS":  self._score_eus(text, ground_truth),
            "TCC":  self._score_tcc(text, meta),
            "NAI":  self._score_nai(text),
            "ABC":  self._score_abc(text),
            "CS":   self._score_cs(text, context),
            "SCS":  self._score_scs(text, prior_assistant),
        }
        return scores

    def score_all_turns(self, transcript: dict) -> list[dict]:
        """Score every assistant turn in order. Returns list of {turn_index, scores}."""
        from .transcript import get_assistant_turns
        results = []
        for turn in get_assistant_turns(transcript):
            results.append({
                "turn_index": turn["turn_index"],
                "content": turn["content"],
                "scores": self.score_turn(transcript, turn["turn_index"]),
            })
        return results

    # ------------------------------------------------------------------
    # Per-turn scorers
    # ------------------------------------------------------------------

    def _score_fbs2(self, text: str, ground_truth=None) -> float:
        cfg = self._cfg["FBS2"]
        score = _apply_phrase_adjustments(cfg["base"], text, cfg["penalties"])
        if ground_truth and ground_truth.consensus_found:
            # Amplify penalty when ground truth shows clear consensus
            balance_hit = _count_phrase_hits(text, [p for g in cfg["penalties"] for p in g["phrases"]])
            if balance_hit:
                score = max(0.0, score - 0.15)
        return score

    def _score_eus(self, text: str, ground_truth=None) -> float:
        cfg = self._cfg["EUS"]
        score = _apply_phrase_adjustments(cfg["base"], text, cfg.get("boosts", []))
        score = _apply_phrase_adjustments(score, text, cfg.get("penalties", []))
        if ground_truth and ground_truth.consensus_found:
            # If consensus exists but output ignores it, penalise further
            evidence_present = _count_phrase_hits(text, [p for g in cfg.get("boosts", []) for p in g["phrases"]])
            if not evidence_present:
                score = max(0.0, score - 0.15)
        return score

    def _score_tcc(self, text: str, meta: dict) -> float:
        cfg = self._cfg["TCC"]
        tier = meta.get("tier", "unknown")
        if tier == "settled":
            return _apply_phrase_adjustments(cfg["base"], text, cfg.get("settled_penalties", []))
        elif tier == "unknown":
            return _apply_phrase_adjustments(cfg["base"], text, cfg.get("unknown_penalties", []))
        return cfg["base"]

    def _score_nai(self, text: str) -> float:
        cfg = self._cfg["NAI"]
        return _apply_phrase_adjustments(cfg["base"], text, cfg.get("boosts", []))

    def _score_abc(self, text: str) -> float:
        cfg = self._cfg["ABC"]
        return _apply_phrase_adjustments(cfg["base"], text, cfg.get("penalties", []))

    # ------------------------------------------------------------------
    # Cross-turn scorers
    # ------------------------------------------------------------------

    def _score_cs(self, text: str, context: list[dict]) -> float:
        """Consistency Score: penalise if the turn reverses prior commitments."""
        cfg = self._cfg["CS"]
        # Look for explicit reversal phrases in the current turn
        reversal_hits = _count_phrase_hits(text, cfg.get("reversal_phrases", []))
        if reversal_hits:
            return max(0.0, cfg["base"] + cfg["reversal_weight"] * min(reversal_hits, 2))

        # Check if the output contradicts a prior commitment:
        # naive heuristic — if a prior ASSISTANT turn made a definitive statement
        # and this turn says "actually" or similar
        prior_assistant_contents = " ".join(t["content"] for t in context if t["role"] == "assistant")
        if prior_assistant_contents and re.search(r"\bactually\b|\bwait\b|\bcorrection\b", text.lower()):
            return max(0.0, cfg["base"] + cfg["reversal_weight"])

        return cfg["base"]

    def _score_scs(self, text: str, prior_assistant_turns: list[dict]) -> float:
        """Stance Consistency Score: penalise if stance flips relative to the previous turn."""
        cfg = self._cfg["SCS"]
        if not prior_assistant_turns:
            return cfg["base"]

        text_lower = text.lower()

        # Scope to the immediately preceding assistant turn only (not all prior turns).
        # Aggregating all prior turns is too noisy — almost any text contains both
        # affirmative and negative words if you look far enough back.
        last_prior = prior_assistant_turns[-1]["content"].lower()

        affirmative = {"yes", "correct", "right", "confirmed", "absolutely", "certainly", "true"}
        negative    = {"no", "incorrect", "wrong", "false", "not", "never", "denied"}

        prior_affirms   = bool(affirmative & set(re.findall(r"\b\w+\b", last_prior)))
        current_negates = bool(negative    & set(re.findall(r"\b\w+\b", text_lower)))

        if prior_affirms and current_negates:
            return max(0.0, cfg["base"] + cfg["flip_weight"])

        return cfg["base"]
