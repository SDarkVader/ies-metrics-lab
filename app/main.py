"""IES Metrics Lab — FastAPI web server.

Serves the single-page frontend and exposes three API endpoints:

    GET  /                        → HTML frontend
    POST /api/audit               → score + evaluate a single transcript
    GET  /api/batch               → run pipeline on transcripts/ directory
    GET  /api/examples            → list bundled example transcripts

Run (from repo root):
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

Then open http://<your-machine-ip>:8080 from any device on the same network.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Path setup — app/ lives one level below the repo root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from ies_lab import MetricScorer, run_batch           # noqa: E402
from audit_session import audit as _audit, load_any  # noqa: E402

_RULES_PATH      = _REPO_ROOT / "mapping_rules.yaml"
_TRANSCRIPTS_DIR = _REPO_ROOT / "transcripts"
_STATIC_DIR      = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="IES Metrics Lab", version="0.1.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/examples")
async def examples():
    """Return the content of every bundled example transcript."""
    results = []
    for path in sorted(_TRANSCRIPTS_DIR.glob("*.txt")):
        results.append({
            "filename": path.name,
            "id":       path.stem,
            "content":  path.read_text(encoding="utf-8"),
        })
    return results


@app.post("/api/audit")
async def api_audit(
    file:   UploadFile | None = File(default=None),
    text:   str | None        = Form(default=None),
    preset: str               = Form(default="default"),
):
    """Score and evaluate a single transcript.

    Supply either a file upload (file=) or raw transcript text (text=).
    Returns the markdown report plus the structured evidence record.
    """
    if preset not in ("default", "strict", "lenient"):
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset}'")

    tmp_path: Path | None = None
    try:
        if file is not None:
            suffix = Path(file.filename or "x.txt").suffix or ".txt"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(await file.read())
                tmp_path = Path(tmp.name)
        elif text:
            with tempfile.NamedTemporaryFile(
                suffix=".txt", delete=False, mode="w", encoding="utf-8"
            ) as tmp:
                tmp.write(text)
                tmp_path = Path(tmp.name)
        else:
            raise HTTPException(status_code=400, detail="Supply 'file' or 'text'")

        report, record = _audit(tmp_path, preset=preset, save=False)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()

    # Normalise: audit() returns a single record or {"sessions": [...]}
    if isinstance(record, dict) and "sessions" in record:
        record = record["sessions"][0]

    return {
        "report":   report,
        "record":   record,
        "failures": record.get("session_failures", []),
        "action":   record.get("session_action", "publish"),
    }


@app.get("/api/batch")
async def api_batch(preset: str = "default") -> list[dict[str, Any]]:
    """Run the full evaluation pipeline on the bundled transcripts/ directory."""
    if preset not in ("default", "strict", "lenient"):
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset}'")
    scorer  = MetricScorer(preset=preset)
    results = run_batch(_TRANSCRIPTS_DIR, _RULES_PATH, scorer)
    return results
