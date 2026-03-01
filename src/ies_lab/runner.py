from ies_lab.run_logger import create_run_dir, save_json
from __future__ import annotations
from typing import Any, Dict, List
from ies_lab.loader import load_fixtures
from ies_lab.mapping import load_mapping_rules, apply_rules

def _midpoint(rng: List[float]) -> float:
    return (float(rng[0]) + float(rng[1])) / 2.0

def from ies_lab.metric_detectors import run_all_detectors

text = f["candidate_output"]
metrics = run_all_detectors(text)

def run_local_consistency_check() -> List[Dict[str, Any]]:
    fixtures = load_fixtures()
    mapping = load_mapping_rules()

    results: List[Dict[str, Any]] = []
    for f in fixtures:
        metrics = metrics_from_expected(f)
        _, tags, action = apply_rules(mapping, f, metrics)

        exp = f.get("expected", {})
        expected_failures = exp.get("expected_failures", []) or []
        expected_action = exp.get("expected_action", "publish")

        results.append({
            "id": f.get("id"),
            "file": f.get("_fixture_path"),
            "expected_failures": expected_failures,
            "mapped_failures": tags,
            "expected_action": expected_action,
            "mapped_action": action,
            "pass_failures": set(expected_failures).issubset(set(tags)),
            "pass_action": expected_action == action,
        })
    return results

if __name__ == "__main__":
    out = run_local_consistency_check()
    # print a compact report
    bad = [r for r in out if not (r["pass_failures"] and r["pass_action"])]
    print(f"Total fixtures: {len(out)}")
    print(f"Failures: {len(bad)}")
    for r in bad:
        print(f"- {r['id']} ({r['file']}): expected {r['expected_failures']}/{r['expected_action']} "
              f"got {r['mapped_failures']}/{r['mapped_action']}")
        
        run_dir = create_run_dir()

save_json(run_dir, "results.json", results)

print(f"Run saved to: {run_dir}")
