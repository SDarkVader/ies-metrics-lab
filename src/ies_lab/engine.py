"""Rule evaluation engine for IES Metrics Lab.

This is the single authoritative rule evaluator used throughout the pipeline.
Rules are loaded from ``mapping_rules.yaml`` and evaluated against a fixture's
metadata and a dict of metric scores.

Rule condition formats
----------------------
Two formats are supported and may be mixed freely within a single rule file:

**Flat ``if:`` format** (original, backward-compatible)::

    - id: false_balance_asymmetry
      if:
        asymmetry_flag: true
        FBS2: "<0.70"
      then:
        failures_add: [FB]
        action: revise

  Each key in ``if:`` is evaluated as an AND condition.  Meta fields
  (``asymmetry_flag``, ``tier``) are matched by equality.  Metric keys use
  string threshold syntax: ``"<0.60"`` means ``score < 0.60``,
  ``">0.55"`` means ``score > 0.55``.

**Compound ``if_all:`` format** (extended, for multi-condition rules)::

    - id: false_balance_compound
      if_all:
        - asymmetry_flag: true
        - FBS2: "<0.70"
        - EUS: "<0.50"
      then:
        failures_add: [FB]
        action: revise

  ``if_all:`` is a list of condition dicts.  Every condition in the list must
  pass for the rule to fire (logical AND).  Each condition dict uses the same
  key/value syntax as the flat ``if:`` format.  This enables rules that require
  multiple metric thresholds to all be met simultaneously.

.. note::
   ``mapping.py`` is deprecated.  It defined an alternative rule-evaluation
   system (``apply_rules`` / ``when`` / ``when_all``) that was never wired into
   the production pipeline.  Use this module (``engine.py``) exclusively.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml


class EvaluationEngine:
    """Load rules from *rules_path* and evaluate them against fixture metadata
    and metric scores.

    Parameters
    ----------
    rules_path:
        Path to a ``mapping_rules.yaml`` file.  The file must contain a
        top-level ``rules:`` list.
    """

    def __init__(self, rules_path: Path) -> None:
        with open(rules_path) as f:
            self._rules = yaml.safe_load(f)["rules"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, fixture: dict, metric_scores: dict) -> dict:
        """Evaluate all rules against *fixture* and *metric_scores*.

        Returns a sentinel dict produced by :func:`ies_lab.sentinel.build_sentinel`.
        """
        from .sentinel import build_sentinel

        failures: set[str] = set()
        action: str | None = None
        meta = fixture.get("meta", {})

        for rule in self._rules:
            # Support both flat `if:` and compound `if_all:` formats
            conditions = rule.get("if_all") or rule.get("if")
            if conditions is None:
                continue
            if self._rule_matches(conditions, meta, metric_scores):
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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rule_matches(
        self,
        conditions: Union[dict, list],
        meta: dict,
        scores: dict,
    ) -> bool:
        """Recursively evaluate *conditions* against *meta* and *scores*.

        Accepts two forms:

        * **dict** — flat condition map (``if:`` format).  Every key/value pair
          must pass (logical AND).
        * **list** — compound condition list (``if_all:`` format).  Every item
          in the list is itself a condition dict; all must pass (logical AND).
        """
        if isinstance(conditions, list):
            # if_all: every sub-condition dict must match
            return all(
                self._rule_matches(sub, meta, scores)
                for sub in conditions
            )

        # Flat dict: every key/value pair is an AND condition
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
