# AIntegrity Audit Agent

A persistent AI audit agent operating under the AIntegrity framework developed by Steven Dark.

## Overview

The agent has three functions:

1. **Interrogator** — conducts PLI-style audit conversations, tracking commitments and flagging evasion in real time
2. **Evaluator** — analyses transcripts against the AIntegrity framework (PLI methodology, IES metrics, vulnerability taxonomy, regulatory mappings)
3. **IES Feeder** — structures findings into IES-compatible transcript JSON and runs them through the existing IES pipeline

The agent does **not** modify any existing IES files. It adds new output only.

## Installation

```bash
pip install openai
export OPENAI_API_KEY=your_key_here
```

## Usage

### Evaluate a single transcript
```bash
python tools/aintegrity_agent.py evaluate transcripts/my_session.txt
python tools/aintegrity_agent.py evaluate transcripts/my_session.txt --preset strict
```

### Live PLI interrogation mode
```bash
python tools/aintegrity_agent.py interrogate
```
Paste AI responses one at a time. The agent tracks commitments, flags evasion, and suggests next questions.

### Batch evaluate a directory
```bash
python tools/aintegrity_agent.py batch transcripts/
```

## Output

All output goes to `evidence/agent_sessions/<session_id>/`:

| File | Contents |
|------|----------|
| `report.md` | Full audit report (Markdown) |
| `agent_findings.json` | Structured agent analysis |
| `ies/` | IES pipeline output (scores, Sentinel JSON) |
| `ies_transcript.json` | IES-compatible transcript (for re-running) |
| `combined_findings.json` | Agent + IES combined output |
| `calibration_review.txt` | Flags where agent and IES disagree (for Steven Dark review) |

## Calibration Loop

When the agent detects failure tags that the IES did not (or vice versa), it writes a `calibration_review.txt` file. These flags are the primary input for:

- Updating `mapping_rules.yaml` thresholds
- Adding new metrics to the IES scorer
- Refining the agent's system prompt

This is how the agent's audits calibrate the metrics over time.

## Adding Logic Profiles

The agent's reasoning is governed by its system prompt in `aintegrity_agent.py`. To add new logic:

1. Update the `SYSTEM_PROMPT` constant in `aintegrity_agent.py`
2. Or pass a `--profile` file (future feature — Claude to implement)

New IES metrics are added via `mapping_rules.yaml` as always. The agent reads the metric definitions from its system prompt and applies them automatically.

## Architecture

```
transcript file
      │
      ▼
AIntegrity Agent (LLM + system prompt)
      │
      ├── Premise audit
      ├── Commitment tracking
      ├── Contradiction detection
      ├── Vulnerability classification
      └── Regulatory mapping
      │
      ▼
IES-compatible transcript JSON
      │
      ▼
IES Pipeline (existing: scorer → engine → sentinel)
      │
      ▼
Sentinel JSON + Markdown report
      │
      ▼
Calibration flags → mapping_rules.yaml updates
```

## Notes for Claude Code

- This file is standalone. It imports from the existing IES codebase but does not modify it.
- The `SYSTEM_PROMPT` constant is the agent's knowledge base. It can be extended freely.
- The `calibration_flags` in the output JSON are the primary signal for improving the IES scorer.
- The `MVE` (Moral Verdict Without Epistemic Standing) and `PF` (Premise Failure) tags are AIntegrity extensions not yet in `mapping_rules.yaml` — add them when ready.
