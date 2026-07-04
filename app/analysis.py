"""Video → frames → Claude vision analysis."""

import base64
import json
import logging
import os
import re
import statistics
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

import anthropic

from .prompts import LIFTS, SYSTEM_PROMPT

log = logging.getLogger("lifty")

MODEL = os.environ.get("LIFTY_MODEL", "claude-sonnet-5")
MAX_FRAMES = int(os.environ.get("LIFTY_MAX_FRAMES", "12"))
# Long-edge pixel size for extracted frames. Image tokens scale with pixel
# area (~area/750), so 768px costs ~25% less per frame than 896px while still
# resolving body/bar positions.
FRAME_EDGE = int(os.environ.get("LIFTY_FRAME_EDGE", "768"))
# Deliberate cost cap per analysis (includes thinking tokens).
MAX_TOKENS = int(os.environ.get("LIFTY_MAX_TOKENS", "16000"))
# Thinking/output spend: low | medium | high. Medium is plenty for a set
# review; raise to high if you want deeper analysis per set.
EFFORT = os.environ.get("LIFTY_EFFORT", "medium")
# Motion-trim the clip so frames are spent on the lift, not on walking up to
# the bar. Set LIFTY_TRIM=0 to always sample the whole clip.
TRIM = os.environ.get("LIFTY_TRIM", "1") != "0"
# Seconds kept either side of the detected movement.
TRIM_MARGIN = 0.75

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


_METADATA_RE = re.compile(
    r"pts_time:(?P<ts>[\d.]+).*?lavfi\.signalstats\.YDIF=(?P<ydif>[\d.eE+-]+)",
    re.DOTALL,
)


def _detect_active_window(video_path: Path, duration: float) -> tuple[float, float] | None:
    """Find the time window that contains the movement.

    Samples the clip at 10 Hz at thumbnail size and reads ffmpeg's per-frame
    temporal-difference statistic (YDIF). A stationary camera watching a
    stationary lifter produces a low, flat baseline; the set itself stands
    out clearly above it. Returns (start, end) in seconds, or None when no
    clear active region exists (handheld footage, constant motion, or a clip
    that is all lift) - in which case the caller samples the whole clip.
    """
    proc = _run(
        [
            "ffmpeg", "-v", "error", "-i", str(video_path),
            "-vf", "fps=10,scale=160:-2,signalstats,"
                   "metadata=print:key=lavfi.signalstats.YDIF:file=-",
            "-f", "null", "-",
        ],
        timeout=120,
    )
    if proc.returncode != 0:
        return None

    samples: list[tuple[float, float]] = []
    for match in _METADATA_RE.finditer(proc.stdout):
        try:
            samples.append((float(match.group("ts")), float(match.group("ydif"))))
        except ValueError:
            continue
    if len(samples) < 10:
        return None

    # Smooth over ~0.5s to ignore single-frame flicker.
    values = [v for _, v in samples]
    smoothed = [
        sum(values[max(0, i - 2): i + 3]) / len(values[max(0, i - 2): i + 3])
        for i in range(len(values))
    ]
    baseline = statistics.median(smoothed)
    peak = max(smoothed)
    # No clear separation between "idle" and "moving" - don't trim.
    if peak < 1.0 or peak < 3 * baseline:
        return None

    threshold = baseline + 0.2 * (peak - baseline)
    active = [samples[i][0] for i, v in enumerate(smoothed) if v >= threshold]
    start = max(0.0, active[0] - TRIM_MARGIN)
    end = min(duration, active[-1] + TRIM_MARGIN)
    if end - start < 1.5 or (end - start) > 0.9 * duration:
        return None
    return (start, end)


def extract_frames(video_path: Path) -> list[tuple[float, bytes]]:
    """Extract up to MAX_FRAMES evenly spaced JPEG frames.

    When motion trimming is enabled, frames are spread over just the part of
    the clip where movement happens, so none are wasted on setup/rest time.
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

    start, end = 0.0, duration
    if TRIM:
        window = _detect_active_window(video_path, duration)
        if window:
            start, end = window
            log.info(
                "Motion trim: using %.1fs-%.1fs of %.1fs clip", start, end, duration
            )
    span = end - start

    n = min(MAX_FRAMES, max(4, int(span * 4)))  # ≥4 fps worth for short spans
    with tempfile.TemporaryDirectory() as tmp:
        out_pattern = str(Path(tmp) / "frame_%03d.jpg")
        seek = ["-ss", f"{start:.3f}"] if start > 0 else []
        proc = _run(
            [
                "ffmpeg", "-v", "error", *seek, "-i", str(video_path),
                "-t", f"{span:.3f}",
                "-vf",
                f"fps={n}/{span:.4f},"
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

        step = span / len(files)
        return [
            (round(start + (i + 0.5) * step, 2), f.read_bytes())
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
        output_config={"effort": EFFORT},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
        if final.stop_reason == "max_tokens":
            yield "\n\n*(Feedback was cut short by the response length limit.)*"
        elif final.stop_reason == "refusal":
            yield "\n\n*(The model declined to analyse this video.)*"
