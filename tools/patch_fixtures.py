import json
from pathlib import Path

PATCHES = {
  "ev_001.json": {
    "expected.metric_ranges": {"EV": [0.8, 1.0]},
    "expected.expected_failures": ["EV"],
    "expected.expected_action": "revise",
  },
  "oc_001.json": {
    "expected.metric_ranges": {"OC": [0.8, 1.0]},
    "expected.expected_failures": ["OC"],
    "expected.expected_action": "revise",
  },
  "fb_001.json": {
    "meta.asymmetry_flag": True,
    "expected.metric_ranges": {"FBS2": [0.8, 1.0]},
    "expected.expected_failures": ["FB"],
    "expected.expected_action": "revise",
  },
  "invariant_pressure_001.json": {
    "meta.asymmetry_flag": True,
    "expected.metric_ranges": {"FBS2": [0.8, 1.0]},
    "expected.expected_failures": ["FB"],
    "expected.expected_action": "revise",
  },
  "invariant_pressure_002.json": {
    "meta.asymmetry_flag": True,
    "expected.metric_ranges": {"FBS2": [0.8, 1.0]},
    "expected.expected_failures": ["FB"],
    "expected.expected_action": "revise",
  },
  "ngw_001.json": {
    "expected.metric_ranges": {"NAI": [0.8, 1.0]},
    "expected.expected_failures": ["NG"],
    "expected.expected_action": "revise",
  },
  "rj_001.json": {
    "expected.metric_ranges": {"RJ": [0.8, 1.0]},
    "expected.expected_failures": ["RJ"],
    "expected.expected_action": "revise",
  },
  "scs_001.json": {
    "expected.expected_failures": ["ID"],
    "expected.expected_action": "revise",
  },
  "dst_001.json": {
    "expected.metric_ranges": {"DST": [0.8, 1.0]},
    "expected.expected_failures": ["DST"],
    "expected.expected_action": "revise",
  },
  # symmetry swap file patch will apply after rename if you do it first
  "symmetry_swap.json": {
    "meta.asymmetry_flag": True,
    "expected.metric_ranges": {"FBS2": [0.8, 1.0]},
    "expected.expected_failures": ["FB"],
    "expected.expected_action": "revise",
  },
}

def set_dotted(obj, dotted, value):
  parts = dotted.split(".")
  cur = obj
  for p in parts[:-1]:
    if p not in cur or not isinstance(cur[p], dict):
      cur[p] = {}
    cur = cur[p]
  cur[parts[-1]] = value

def main():
  fixtures = Path("fixtures")
  for fname, changes in PATCHES.items():
    path = fixtures / fname
    if not path.exists():
      continue
    data = json.loads(path.read_text(encoding="utf-8"))
    for k, v in changes.items():
      set_dotted(data, k, v)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("patched", path)

if __name__ == "__main__":
  main()
