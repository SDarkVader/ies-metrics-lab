"""DEPRECATED — do not use in new code.

This module defined an alternative rule-evaluation system (``apply_rules`` /
``when`` / ``when_all``) that was never wired into the production pipeline.
It is retained here for reference only and will be removed in a future release.

Use :class:`ies_lab.engine.EvaluationEngine` instead, which now supports both
the original flat ``if:`` format and the compound ``if_all:`` list format.
"""
import warnings
warnings.warn(
    "ies_lab.mapping is deprecated and will be removed in a future release. "
    "Use ies_lab.engine.EvaluationEngine instead.",
    DeprecationWarning,
    stacklevel=2,
)

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import yaml

@dataclass
class RuleMatch:
    rule_id: str
    add_tags: List[str]
    action: Optional[str]

def _get_field(obj: Dict[str, Any], dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

def _cmp(op: str, left: Any, right: Any) -> bool:
    if left is None:
        return False
    if op == "==": return left == right
    if op == "!=": return left != right
    if op == ">":  return float(left) > float(right)
    if op == ">=": return float(left) >= float(right)
    if op == "<":  return float(left) < float(right)
    if op == "<=": return float(left) <= float(right)
    raise ValueError(f"Unsupported op: {op}")

def load_mapping_rules(path: str = "mapping_rules.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def apply_rules(
    mapping: Dict[str, Any],
    fixture: Dict[str, Any],
    metrics: Dict[str, float],
) -> Tuple[List[RuleMatch], List[str], str]:
    matches: List[RuleMatch] = []
    tags: List[str] = []
    action: str = mapping.get("default", {}).get("action", "publish")

    for rule in mapping.get("rules", []):
        rid = rule.get("id", "unnamed_rule")

        def eval_cond(cond: Dict[str, Any]) -> bool:
            # field-based condition
            if "field" in cond:
                v = _get_field(fixture, cond["field"])
                return _cmp(cond["op"], v, cond["value"])
            # metric-based condition
            if "metric" in cond:
                v = metrics.get(cond["metric"])
                return _cmp(cond["op"], v, cond["value"])
            raise ValueError(f"Bad condition in rule {rid}: {cond}")

        ok = True
        if "when" in rule:
            ok = eval_cond(rule["when"])
        elif "when_all" in rule:
            ok = all(eval_cond(c) for c in rule["when_all"])
        else:
            raise ValueError(f"Rule {rid} missing when/when_all")

        if ok:
            then = rule.get("then", {})
            add = then.get("add_tags", []) or []
            act = then.get("action")
            matches.append(RuleMatch(rule_id=rid, add_tags=add, action=act))
            for t in add:
                if t not in tags:
                    tags.append(t)
            if act:
                action = act

    return matches, tags, action
