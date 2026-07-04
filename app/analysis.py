"""Video → frames → Claude vision analysis."""

import base64
import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import anthropic

from .prompts import LIFTS, SYSTEM_PROMPT

log = logging.getLogger("lifty")

MODEL = os.environ.get("LIFTY_MODEL", "claude-opus-4-8")
MAX_FRAMES = int(os.environ.get("LIFTY_MAX_FRAMES", "16"))
# Long-edge pixel size for extracted frames. ~900px keeps per-frame token cost
# moderate while leaving enough detail to judge positions.
FRAME_EDGE = int(os.environ.get("LIFTY_FRAME_EDGE", "896"))
# Deliberate cost cap per analysis (includes thinking tokens).
MAX_TOKENS = int(os.environ.get("LIFTY_MAX_TOKENS", "16000"))

_client = anthropic.Anthropic()


class VideoError(Exception):
    """Raised when the uploaded file can't be processed as a video."""


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise VideoError(
            f"Server misconfiguration: `{cmd[0]}` is not installed. "
            "Install ffmpeg on the server (see README)."
        ) from exc


def _probe_duration(video_path: Path) -> float:
    proc = _run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(video_path),
        ],
        timeout=60,
    )
    if proc.returncode != 0:
        raise VideoError("Could not read the video file. Is it a valid video?")
    try:
        return float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise VideoError("Could not determine video duration.") from exc


def extract_frames(video_path: Path) -> list[tuple[float, bytes]]:
    """Extract up to MAX_FRAMES evenly spaced JPEG frames.

    Returns a list of (timestamp_seconds, jpeg_bytes) in chronological order.
    """
    duration = _probe_duration(video_path)
    if duration <= 0:
        raise VideoError("Video appears to be empty.")
    if duration > 120:
        raise VideoError(
            "Video is longer than 2 minutes. Trim it to just the set "
            "(ideally 5-30 seconds) and try again."
        )

    n = min(MAX_FRAMES, max(4, int(duration * 4)))  # ≥4 fps worth for short clips
    with tempfile.TemporaryDirectory() as tmp:
        out_pattern = str(Path(tmp) / "frame_%03d.jpg")
        proc = _run(
            [
                "ffmpeg", "-v", "error", "-i", str(video_path),
                "-vf",
                f"fps={n}/{duration:.4f},"
                f"scale={FRAME_EDGE}:{FRAME_EDGE}:force_original_aspect_ratio=decrease",
                "-frames:v", str(n),
                "-q:v", "3",
                out_pattern,
            ],
            timeout=300,
        )
        if proc.returncode != 0:
            log.error("ffmpeg failed: %s", proc.stderr[-2000:])
            raise VideoError("Could not extract frames from the video.")

        files = sorted(Path(tmp).glob("frame_*.jpg"))
        if not files:
            raise VideoError("No frames could be extracted from the video.")

        step = duration / len(files)
        return [
            (round((i + 0.5) * step, 2), f.read_bytes())
            for i, f in enumerate(files)
        ]


def _build_user_content(
    lift_key: str,
    frames: list[tuple[float, bytes]],
    notes: str,
    previous_feedback: str | None,
) -> list[dict]:
    lift = LIFTS[lift_key]
    content: list[dict] = [
        {
            "type": "text",
            "text": (
                f"I just filmed a set. Declared exercise: {lift['label']}.\n\n"
                f"{lift['standard']}\n\n"
                f"Below are {len(frames)} frames extracted from the video in "
                "chronological order, each labelled with its approximate "
                "timestamp."
            ),
        }
    ]
    for ts, jpeg in frames:
        content.append({"type": "text", "text": f"Frame at ~{ts}s:"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(jpeg).decode("ascii"),
                },
            }
        )

    trailer = "That is the whole set. Give me your feedback before my next set."
    if notes.strip():
        trailer += f"\n\nMy notes on this set: {notes.strip()}"
    if previous_feedback:
        trailer += (
            "\n\nFor context, this is the feedback you gave me on my PREVIOUS "
            "set of this same exercise - tell me whether I acted on the cue:\n"
            f"---\n{previous_feedback}\n---"
        )
    content.append({"type": "text", "text": trailer})
    return content


def stream_feedback(
    lift_key: str,
    frames: list[tuple[float, bytes]],
    notes: str = "",
    previous_feedback: str | None = None,
) -> Iterator[str]:
    """Yield feedback text chunks from Claude as they arrive."""
    content = _build_user_content(lift_key, frames, notes, previous_feedback)
    with _client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
        if final.stop_reason == "max_tokens":
            yield "\n\n*(Feedback was cut short by the response length limit.)*"
        elif final.stop_reason == "refusal":
            yield "\n\n*(The model declined to analyse this video.)*"
