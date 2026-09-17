"""Input discovery and synchronization for long-form recordings."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import SourceInfo


OFFSET_PATTERN = re.compile(r"(\d+)h_(\d+)m_(\d+)s_(\d+)ms", re.IGNORECASE)


def parse_streamyard_offset(path: Path) -> float:
    """Return the recording offset encoded in a StreamYard filename."""
    match = OFFSET_PATTERN.search(Path(path).stem)
    if not match:
        return 0.0
    hours, minutes, seconds, milliseconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0


def _fps(value: str) -> float:
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return float(value)
    return float(numerator) / float(denominator) if float(denominator) else 0.0


def probe_source(path: Path) -> SourceInfo:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    video_stream = next(
        (stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise ValueError(f"No video stream found in {path}")
    has_audio = any(stream.get("codec_type") == "audio" for stream in payload.get("streams", []))
    return SourceInfo(
        path=str(path.resolve()),
        name=path.name,
        kind="screen" if "screen" in path.name.lower() else "webcam",
        offset=parse_streamyard_offset(path),
        duration=float(payload["format"]["duration"]),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=_fps(video_stream.get("r_frame_rate", "0/1")),
        has_audio=has_audio,
    )


def discover_paths(input_dir: Path, episode: str) -> List[Path]:
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    all_paths = sorted(input_dir.glob("*.mp4")) + sorted(input_dir.glob("*.MP4"))
    if not all_paths:
        raise ValueError(f"No MP4 files found in {input_dir}")

    exact = [path for path in all_paths if episode.lower() in path.stem.lower()]
    if exact:
        return exact

    episode_number = re.search(r"\d+", episode)
    if episode_number:
        numbered = [path for path in all_paths if episode_number.group(0) in path.stem]
        if numbered:
            return numbered
    raise ValueError(f"No MP4 files in {input_dir} match episode '{episode}'")


def discover_sources(
    input_dir: Path,
    episode: str,
    screen_override: Optional[Path] = None,
) -> List[SourceInfo]:
    paths = discover_paths(input_dir, episode)
    override = Path(screen_override).resolve() if screen_override else None
    if override and override not in [path.resolve() for path in paths]:
        raise ValueError(f"Screen override is not one of the matched episode files: {override}")

    sources = []
    for path in paths:
        source = probe_source(path)
        if override:
            source = SourceInfo(
                **{
                    **source.__dict__,
                    "kind": "screen" if path.resolve() == override else "webcam",
                }
            )
        sources.append(source)

    screens = [source for source in sources if source.kind == "screen"]
    webcams = [source for source in sources if source.kind == "webcam"]
    if len(screens) != 1:
        raise ValueError(
            f"Expected exactly one screen source, found {len(screens)}. "
            "Use --screen PATH to select it explicitly."
        )
    if not webcams:
        raise ValueError("At least one webcam source is required")
    return sources


def common_interval(sources: Iterable[SourceInfo]) -> Tuple[float, float]:
    source_list = list(sources)
    if not source_list:
        raise ValueError("At least one source is required")
    common_start = max(source.offset for source in source_list)
    common_end = min(source.offset + source.duration for source in source_list)
    if common_end <= common_start:
        raise ValueError("The source recordings do not share a synchronized interval")
    return common_start, common_end - common_start

