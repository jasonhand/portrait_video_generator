"""Low-cost audio and screen activity analysis for automatic editing."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .models import SourceInfo


@dataclass
class AnalysisResult:
    audio_interval: float
    audio_levels: Dict[str, List[float]]
    screen_interval: float
    screen_scores: List[float]
    screen_active: List[bool]
    # True when the sampled screen frame contains non-black content.  This is
    # separate from activity: a static screen can have zero frame-to-frame
    # change, while synchronized source bundles may contain black filler.
    screen_present: List[bool] = field(default_factory=list)


def _local_start(source: SourceInfo, common_start: float) -> float:
    return max(0.0, common_start - source.offset)


def analyze_audio(
    source: SourceInfo,
    common_start: float,
    duration: float,
    interval: float = 0.5,
    sample_rate: int = 8000,
) -> List[float]:
    sample_count = max(1, int(np.ceil(duration / interval)))
    if not source.has_audio:
        return [0.0] * sample_count

    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{_local_start(source, common_start):.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        source.path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    result = subprocess.run(command, check=True, capture_output=True)
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    window = max(1, int(sample_rate * interval))
    raw = []
    for index in range(sample_count):
        chunk = samples[index * window : (index + 1) * window]
        raw.append(float(np.sqrt(np.mean(np.square(chunk)))) if chunk.size else 0.0)

    # Keep raw RMS values so webcam tracks can be compared using the same
    # active-speaker rule as the Shorts generator. Normalizing each microphone
    # independently can make background noise on a quiet track look dominant.
    return raw


def analyze_screen(
    source: SourceInfo,
    common_start: float,
    duration: float,
    interval: float = 1.0,
    hold_seconds: int = 20,
) -> tuple[List[float], List[bool], List[bool]]:
    width, height = 320, 180
    frame_size = width * height
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{_local_start(source, common_start):.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        source.path,
        "-vf",
        # Reset timestamps after the seek so the sampled presence/activity
        # arrays line up with the common timeline (without this, FFmpeg can
        # retain the source PTS and shift samples several seconds forward).
        f"setpts=PTS-STARTPTS,fps={1 / interval:g},scale={width}:{height},format=gray",
        "-an",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    scores: List[float] = []
    present: List[bool] = []
    previous = None
    assert process.stdout is not None
    while True:
        data = process.stdout.read(frame_size)
        if len(data) < frame_size:
            break
        frame = np.frombuffer(data, dtype=np.uint8).astype(np.int16)
        # Composite screen tracks use exact black frames for timestamp gaps.
        # A low brightness threshold avoids selecting those gaps while still
        # accepting dark application UIs as real screenshare content.
        present.append(float(np.mean(frame)) > 5.0)
        if previous is None:
            scores.append(0.0)
        else:
            scores.append(float(np.mean(np.abs(frame - previous))))
        previous = frame
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    if process.wait() != 0:
        raise RuntimeError(f"Screen analysis failed for {source.name}: {stderr[-500:]}")
    if not scores:
        return [], [], []

    values = np.asarray(scores, dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    percentile = float(np.percentile(values, 65))
    threshold = max(median + 2.0 * mad, percentile, 0.75)
    changes = values > threshold

    hold_frames = max(1, int(round(hold_seconds / interval)))
    active = np.zeros(len(values), dtype=bool)
    for index in np.flatnonzero(changes):
        active[index : min(len(active), index + hold_frames + 1)] = True
    return [float(value) for value in values], [bool(value) for value in active], present


def analyze_sources(
    sources: List[SourceInfo], common_start: float, duration: float
) -> AnalysisResult:
    webcams = [source for source in sources if source.kind == "webcam"]
    screen = next(source for source in sources if source.kind == "screen")
    audio_levels = {
        source.name: analyze_audio(source, common_start, duration) for source in webcams
    }
    screen_scores, screen_active, screen_present = analyze_screen(screen, common_start, duration)
    return AnalysisResult(
        audio_interval=0.5,
        audio_levels=audio_levels,
        screen_interval=1.0,
        screen_scores=screen_scores,
        screen_active=screen_active,
        screen_present=screen_present,
    )
