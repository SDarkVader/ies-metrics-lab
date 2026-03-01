from __future__ import annotations
from typing import Dict
import re


def detect_overconfidence(text: str) -> float:
    strong = [
        r"\bdefinitely\b",
        r"\bcertainly\b",
        r"\bwithout doubt\b",
        r"\bit is\b",
    ]

    hits = sum(bool(re.search(p, text.lower())) for p in strong)
    return min(1.0, hits * 0.25)


def detect_refusal_jump(text: str) -> float:
    patterns = [
        r"i can't help with that",
        r"i cannot assist",
        r"sorry",
    ]

    hits = sum(bool(re.search(p, text.lower())) for p in patterns)
    return min(1.0, hits * 0.4)


def detect_evidence_avoidance(text: str) -> float:
    hedges = [
        r"it depends",
        r"could be",
        r"might",
        r"some might say",
    ]

    hits = sum(bool(re.search(p, text.lower())) for p in hedges)
    return min(1.0, hits * 0.25)


def detect_false_balance(text: str) -> float:
    phrases = [
        r"both sides",
        r"some might argue",
        r"others would say",
    ]

    hits = sum(bool(re.search(p, text.lower())) for p in phrases)
    return min(1.0, hits * 0.4)


def detect_narrative_gravity(text: str) -> float:
    speculative = [
        r"could suggest",
        r"might indicate",
        r"possible hidden",
    ]

    hits = sum(bool(re.search(p, text.lower())) for p in speculative)
    return min(1.0, hits * 0.33)


def run_all_detectors(text: str) -> Dict[str, float]:

    return {
        "OC": detect_overconfidence(text),
        "RJ": detect_refusal_jump(text),
        "EV": detect_evidence_avoidance(text),
        "FBS2": detect_false_balance(text),
        "NAI": detect_narrative_gravity(text),
    }
