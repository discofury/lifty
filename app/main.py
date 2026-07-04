"""Lifty — between-sets technique feedback for Olympic weightlifting."""

import logging
import shutil
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import analysis
from .analysis import VideoError, extract_frames, stream_feedback
from .prompts import LIFTS

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lifty")

app = FastAPI(title="Lifty")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # iPhone 4K clips are big; keep clips short anyway

# Per-session memory of the last feedback given for each lift, so the model can
# check whether the previous cue was acted on. In-memory only: survives a gym
# session, not a server restart. Keyed by a client-generated session id.
_history_lock = threading.Lock()
_history: OrderedDict[str, dict[str, str]] = OrderedDict()
_MAX_SESSIONS = 200
_MAX_FEEDBACK_CHARS = 4000


def _get_previous(session_id: str, lift: str) -> str | None:
    with _history_lock:
        return _history.get(session_id, {}).get(lift)


def _store_feedback(session_id: str, lift: str, feedback: str) -> None:
    with _history_lock:
        session = _history.setdefault(session_id, {})
        session[lift] = feedback[:_MAX_FEEDBACK_CHARS]
        _history.move_to_end(session_id)
        while len(_history) > _MAX_SESSIONS:
            _history.popitem(last=False)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/lifts")
def lifts() -> JSONResponse:
    return JSONResponse(
        [{"key": key, "label": lift["label"]} for key, lift in LIFTS.items()]
    )


@app.post("/api/analyze")
async def analyze(
    video: UploadFile = File(...),
    lift: str = Form(...),
    notes: str = Form(""),
    session_id: str = Form(""),
):
    if lift not in LIFTS:
        raise HTTPException(status_code=400, detail=f"Unknown lift: {lift}")

    # Persist the upload to a temp file so ffmpeg can seek in it.
    suffix = Path(video.filename or "clip.mov").suffix or ".mov"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    size = 0
    try:
        while chunk := await video.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail="Video too large. Trim the clip to just the set.",
                )
            tmp.write(chunk)
        tmp.close()

        try:
            frames = extract_frames(tmp_path)
        except VideoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BaseException:
        tmp.close()
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.unlink(missing_ok=True)

    previous = _get_previous(session_id, lift) if session_id else None
    log.info(
        "Analyzing %s: %d frames, %.1f MB upload, previous=%s",
        lift, len(frames), size / 1e6, bool(previous),
    )

    def generate():
        collected: list[str] = []
        try:
            for text in stream_feedback(lift, frames, notes, previous):
                collected.append(text)
                yield text
        except anthropic.AuthenticationError:
            yield "\n\n**Server error:** invalid or missing ANTHROPIC_API_KEY."
        except anthropic.RateLimitError:
            yield "\n\n**Rate limited** — wait a moment and re-upload."
        except anthropic.APIStatusError as exc:
            log.exception("Claude API error")
            yield f"\n\n**API error ({exc.status_code})** — try again."
        except anthropic.APIConnectionError:
            yield "\n\n**Network error** reaching the Claude API — try again."
        else:
            if session_id and collected:
                _store_feedback(session_id, lift, "".join(collected))

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )


@app.get("/api/health")
def health() -> JSONResponse:
    problems = []
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        problems.append("ffmpeg/ffprobe not found on PATH")
    try:
        analysis._client.api_key  # noqa: B018 — presence check only
    except Exception:
        problems.append("Anthropic client not configured")
    return JSONResponse({"ok": not problems, "problems": problems, "model": analysis.MODEL})
