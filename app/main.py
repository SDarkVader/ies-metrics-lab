"""IES Metrics Lab — FastAPI web server.

Serves the single-page frontend and exposes three API endpoints:

    GET  /                        → HTML frontend
    POST /api/audit               → score + evaluate a single transcript
    GET  /api/batch               → run pipeline on transcripts/ directory
    GET  /api/examples            → list bundled example transcripts

Run (from repo root):
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

Then open http://<your-machine-ip>:8080 from any device on the same network.

Environment variables
---------------------
IES_ALLOWED_ORIGINS  Comma-separated list of allowed CORS origins.
                     Defaults to ``*`` (all origins) for local development.
                     Example: ``https://example.com,https://app.example.com``

IES_MAX_TEXT_CHARS   Maximum character count accepted by ``/api/audit`` for
                     the ``text`` field.  Defaults to 500 000 (~500 KB).

IES_MAX_FILE_BYTES   Maximum file size in bytes accepted by ``/api/audit``
                     for file uploads.  Defaults to 2 000 000 (2 MB).
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
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
# Configuration from environment
# ---------------------------------------------------------------------------

_MAX_TEXT_CHARS: int = int(os.environ.get("IES_MAX_TEXT_CHARS", "500000"))
_MAX_FILE_BYTES: int = int(os.environ.get("IES_MAX_FILE_BYTES", "2000000"))

_ALLOWED_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get("IES_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="IES Metrics Lab", version="0.1.0", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
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

    Input size limits are enforced to prevent denial-of-service:
    - ``text``: max ``IES_MAX_TEXT_CHARS`` characters (default 500 000)
    - ``file``: max ``IES_MAX_FILE_BYTES`` bytes (default 2 MB)
    """
    if preset not in ("default", "strict", "lenient"):
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset}'")

    tmp_path: Path | None = None
    try:
        if file is not None:
            # Read file with size guard
            content = await file.read()
            if len(content) > _MAX_FILE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large ({len(content):,} bytes). "
                           f"Maximum allowed: {_MAX_FILE_BYTES:,} bytes.",
                )
            suffix = Path(file.filename or "x.txt").suffix or ".txt"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
        elif text:
            # Text size guard
            if len(text) > _MAX_TEXT_CHARS:
                raise HTTPException(
                    status_code=413,
                    detail=f"Text too large ({len(text):,} chars). "
                           f"Maximum allowed: {_MAX_TEXT_CHARS:,} characters.",
                )
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
async def api_batch(
    preset: str = Query(default="default"),
    limit:  int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Run the full evaluation pipeline on the bundled transcripts/ directory.

    Supports pagination via ``limit`` and ``offset`` query parameters.
    Returns a dict with ``results`` (the page), ``total`` (total count),
    ``limit``, and ``offset`` for the client to paginate through.
    """
    if preset not in ("default", "strict", "lenient"):
        raise HTTPException(status_code=400, detail=f"Unknown preset '{preset}'")
    scorer  = MetricScorer(preset=preset)
    all_results = run_batch(_TRANSCRIPTS_DIR, _RULES_PATH, scorer)
    total = len(all_results)
    page = all_results[offset : offset + limit]
    return {
        "results": page,
        "total":   total,
        "limit":   limit,
        "offset":  offset,
    }
