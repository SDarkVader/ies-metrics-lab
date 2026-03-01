from pathlib import Path

import yaml


class EvaluationEngine:
    def __init__(self, rules_path: Path):
        with open(rules_path) as f:
            self._rules = yaml.safe_load(f)["rules"]

    def evaluate(self, fixture: dict, metric_scores: dict) -> dict:
        from .sentinel import build_sentinel

        failures: set[str] = set()
        action: str | None = None
        meta = fixture.get("meta", {})

        for rule in self._rules:
            if self._rule_matches(rule["if"], meta, metric_scores):
                for tag in rule["then"]["failures_add"]:
                    failures.add(tag)
                if action is None:
                    action = rule["then"].get("action")

        return build_sentinel(
            fixture=fixture,
            metric_scores=metric_scores,
            failures=sorted(failures),
            action=action,
        )

    def _rule_matches(self, conditions: dict, meta: dict, scores: dict) -> bool:
        for key, value in conditions.items():
            if key == "asymmetry_flag":
                if meta.get("asymmetry_flag") != value:
                    return False
            elif key == "tier":
                if meta.get("tier") != value:
                    return False
            elif isinstance(value, str) and value.startswith("<"):
                threshold = float(value[1:])
                if scores.get(key, 1.0) >= threshold:
                    return False
            elif isinstance(value, str) and value.startswith(">"):
                threshold = float(value[1:])
                if scores.get(key, 0.0) <= threshold:
                    return False
        return True
