import json
import re
from pathlib import Path

import yaml


def parse_text_transcript(text: str) -> dict:
    """Parse a raw .txt transcript into the IES transcript JSON schema."""
    parts = text.split("---", 1)
    dialogue = parts[0].strip()
    meta_block = parts[1].strip() if len(parts) > 1 else ""

    turns = []
    turn_index = 0
    for line in dialogue.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(USER|ASSISTANT|SYSTEM):\s*(.+)$", line, re.IGNORECASE)
        if match:
            role = match.group(1).lower()
            if role == "user":
                role = "user"
            elif role == "assistant":
                role = "assistant"
            else:
                role = "system"
            turns.append({"turn_index": turn_index, "role": role, "content": match.group(2)})
            turn_index += 1

    meta: dict = yaml.safe_load(meta_block) if meta_block else {}
    transcript_id = str(meta.pop("id", f"transcript_{turn_index:03d}"))
    tier = str(meta.pop("tier", "unknown"))
    asymmetry_flag = bool(meta.pop("asymmetry_flag", False))
    condition = str(meta.pop("condition", "unspecified"))

    return {
        "id": transcript_id,
        "source": "text_import",
        "meta": {
            "tier": tier,
            "asymmetry_flag": asymmetry_flag,
            "condition": condition,
        },
        "turns": turns,
        "evidence_pack": None,
    }


def load_transcript(path: Path) -> dict:
    """Load a transcript from a .txt or .json file."""
    path = Path(path)
    if path.suffix == ".json":
        with open(path) as f:
            return json.load(f)
    with open(path) as f:
        return parse_text_transcript(f.read())


def load_all_transcripts(transcripts_dir: Path) -> list[dict]:
    """Load all .txt and .json transcripts from a directory."""
    transcripts_dir = Path(transcripts_dir)
    transcripts = []
    for path in sorted(transcripts_dir.glob("*.txt")) + sorted(transcripts_dir.glob("*.json")):
        transcripts.append(load_transcript(path))
    return transcripts


def get_assistant_turns(transcript: dict) -> list[dict]:
    """Return all assistant turns from a transcript, in order."""
    return [t for t in transcript.get("turns", []) if t["role"] == "assistant"]


def get_candidate_output(transcript: dict) -> str:
    """Return the content of the last assistant turn."""
    assistant_turns = get_assistant_turns(transcript)
    if not assistant_turns:
        return ""
    return assistant_turns[-1]["content"]


def get_context_before_turn(transcript: dict, turn_index: int) -> list[dict]:
    """Return all turns that precede the given turn_index."""
    return [t for t in transcript.get("turns", []) if t["turn_index"] < turn_index]


def to_fixture_shape(transcript: dict) -> dict:
    """Convert a transcript to the fixture-compatible shape expected by EvaluationEngine."""
    return {
        "id": transcript["id"],
        "family": transcript["meta"].get("condition", "transcript"),
        "meta": transcript["meta"],
        "prompt": next(
            (t["content"] for t in transcript.get("turns", []) if t["role"] == "user"),
            "",
        ),
        "candidate_output": get_candidate_output(transcript),
        "context": [
            {"role": t["role"], "content": t["content"]}
            for t in get_context_before_turn(
                transcript,
                get_assistant_turns(transcript)[-1]["turn_index"]
                if get_assistant_turns(transcript)
                else 0,
            )
        ],
    }
