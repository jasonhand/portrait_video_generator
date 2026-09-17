"""Deterministic scene scheduling for long-form edits."""

from __future__ import annotations

import random
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .analysis import AnalysisResult
from .models import EditPlan, Scene, SourceInfo


MIN_SCENE_SECONDS = 5.0
TARGET_SCENE_MIN = 5.0
TARGET_SCENE_MAX = 5.0
PAUSE_SNAP_SECONDS = 0.5
AUDIO_ACTIVITY_THRESHOLD = 0.02
# Long-form edits should feel calm; punch zooms are intentionally rare.
ZOOM_PROBABILITY = 0.10
SCREEN_RUN_MIN_SECONDS = 20.0
# A run ends on the next analysis boundary, which can be shifted by 0.5s
# toward a pause. Keeping the target at most 26s guarantees the completed
# block never exceeds 30s.
SCREEN_RUN_TARGET_MAX_SECONDS = 26.0
SCREEN_RUN_START_PROBABILITY = 0.42
SCREEN_RUN_COOLDOWN_SECONDS = 8.0
SCREEN_EDGE_GUARD_SECONDS = 60.0
SCREEN_INACTIVE_START_PROBABILITY = 0.45
DUAL_WEBCAM_PROBABILITY = 0.10
THREE_PANEL_PROBABILITY = 0.15


def _sample_range(start: float, end: float, interval: float, length: int) -> range:
    first = max(0, int(start / interval))
    last = min(length, max(first + 1, int(end / interval + 0.999)))
    return range(first, last)


def _mean(values: Sequence[float], indices: Iterable[int]) -> float:
    selected = [values[index] for index in indices if 0 <= index < len(values)]
    return sum(selected) / len(selected) if selected else 0.0


def _mixed_audio_at(analysis: AnalysisResult, time_seconds: float) -> float:
    index = int(time_seconds / analysis.audio_interval)
    return max(
        (levels[index] for levels in analysis.audio_levels.values() if index < len(levels)),
        default=0.0,
    )


def _snap_to_pause(
    proposed: float,
    previous: float,
    duration: float,
    analysis: AnalysisResult,
) -> float:
    lower = max(previous + MIN_SCENE_SECONDS, proposed - PAUSE_SNAP_SECONDS)
    upper = min(duration, proposed + PAUSE_SNAP_SECONDS)
    if upper <= lower:
        return min(duration, max(previous + MIN_SCENE_SECONDS, proposed))
    step = analysis.audio_interval
    candidates = []
    cursor = lower
    while cursor <= upper + 1e-6:
        candidates.append(cursor)
        cursor += step
    return min(candidates, key=lambda value: (_mixed_audio_at(analysis, value), abs(value - proposed)))


def _build_intervals(
    duration: float, analysis: AnalysisResult, rng: random.Random
) -> List[Tuple[float, float]]:
    if duration <= MIN_SCENE_SECONDS:
        return [(0.0, duration)]
    boundaries = [0.0]
    while boundaries[-1] < duration:
        proposed = boundaries[-1] + rng.uniform(TARGET_SCENE_MIN, TARGET_SCENE_MAX)
        if duration - proposed < MIN_SCENE_SECONDS:
            break
        boundary = _snap_to_pause(proposed, boundaries[-1], duration, analysis)
        if duration - boundary < MIN_SCENE_SECONDS:
            break
        boundaries.append(boundary)
    boundaries.append(duration)
    return [(boundaries[index], boundaries[index + 1]) for index in range(len(boundaries) - 1)]


def _screen_is_active(analysis: AnalysisResult, start: float, end: float) -> bool:
    indices = _sample_range(start, end, analysis.screen_interval, len(analysis.screen_active))
    return any(analysis.screen_active[index] for index in indices)


def _screen_has_content(analysis: AnalysisResult, start: float, end: float) -> bool:
    """Return whether a screen frame is visibly present in this interval.

    Activity alone is insufficient because a static screen has no difference
    score.  The synchronized screen track also contains black filler between
    source clips, which must never become a rendered screen scene.
    """
    present = analysis.screen_present
    if not present:
        # Backwards-compatible behavior for hand-built/test AnalysisResult
        # instances created before screen_present was added.
        return True
    first_present = next((index for index, value in enumerate(present) if value), None)
    # Leave one complete scene interval of safety after the first detected
    # content frame. This compensates for FFmpeg's seek/frame timestamp
    # quantization and prevents a scene from opening on a residual black frame.
    content_start = (first_present * analysis.screen_interval) if first_present is not None else float("inf")
    if first_present is None or start < content_start + (2 * MIN_SCENE_SECONDS):
        return False
    indices = _sample_range(start, end, analysis.screen_interval, len(present))
    # Require every sampled frame in the interval to be real content.  Using
    # ``any`` would allow a five-second scene to begin in black filler and
    # switch into the screen clip partway through the scene.
    selected = [present[index] for index in indices]
    return bool(selected) and all(selected)


def _speaker_for_scene(
    webcams: Sequence[SourceInfo],
    analysis: AnalysisResult,
    start: float,
    end: float,
    previous: Optional[str],
) -> str:
    scores: Dict[str, float] = {}
    for source in webcams:
        levels = analysis.audio_levels.get(source.name, [])
        indices = _sample_range(start, end, analysis.audio_interval, len(levels))
        scores[source.name] = _mean(levels, indices)
    loudest = max(scores, key=scores.get)
    # This deliberately mirrors the Shorts editor: a webcam is active above
    # 0.02 raw RMS and the loudest active source owns the shot. Retain the
    # previous camera only during genuine silence.
    if scores[loudest] <= AUDIO_ACTIVITY_THRESHOLD and previous:
        return previous
    return loudest


def _ensure_source_coverage(
    scenes: List[Scene], webcams: Sequence[SourceInfo]
) -> List[Scene]:
    present = {scene.source for scene in scenes if scene.scene_type.startswith("webcam")}
    missing = [source for source in webcams if source.name not in present]
    candidates = [
        index
        for index, scene in enumerate(scenes)
        if scene.scene_type.startswith("webcam") and scene.start < 120.0
    ]
    for source, index in zip(missing, candidates):
        old = scenes[index]
        scenes[index] = replace(old, source=source.name, scene_type="webcam_full", zoom=1.0)
    return scenes


def build_edit_plan(
    episode: str,
    sources: List[SourceInfo],
    common_start: float,
    duration: float,
    analysis: AnalysisResult,
    seed: int,
) -> EditPlan:
    rng = random.Random(seed)
    webcams = [source for source in sources if source.kind == "webcam"]
    screen = next(source for source in sources if source.kind == "screen")
    intervals = _build_intervals(duration, analysis, rng)

    scenes: List[Scene] = []
    previous_speaker: Optional[str] = None
    previous_webcam_source: Optional[str] = None
    previous_webcam_zoom = False
    screen_run_until: Optional[float] = None
    screen_run_position: Optional[str] = None
    screen_has_been_shown = False
    screen_cooldown_until = 0.0
    episode85 = "episode-85" in episode.lower() or "episode_85" in episode.lower()

    for start, end in intervals:
        speaker = _speaker_for_scene(webcams, analysis, start, end, previous_speaker)
        screen_active = _screen_is_active(analysis, start, end)
        screen_has_content = _screen_has_content(analysis, start, end)
        # Episode 85's synchronized composite begins with a known four-second
        # black lead-in before the first timestamped screen clip. Keep that
        # lead-in out of all screen layouts; webcam scenes cover the opening.
        if "screen-composite" in screen.name.lower() and start < 210.0:
            screen_has_content = False
        # Episode 85 has several timestamped Stephen shares. Once the first
        # real screen frame is available, prefer it for every usable interval
        # instead of waiting for the generic long-form probability/edge guard.
        if episode85 and screen_has_content and duration - start >= SCREEN_RUN_MIN_SECONDS:
            screen_run_until = start + SCREEN_RUN_TARGET_MAX_SECONDS
            screen_run_position = "upper_right"
        if screen_run_until is not None and screen_has_content:
            choose_screen = True
        elif screen_run_until is not None and not screen_has_content:
            # A run cannot span a synchronized source gap. End it immediately
            # and fall back to the speaking webcam for this interval.
            screen_run_until = None
            screen_run_position = None
            screen_cooldown_until = end + SCREEN_RUN_COOLDOWN_SECONDS
            choose_screen = False
        elif start < screen_cooldown_until:
            choose_screen = False
        else:
            enough_time_for_run = duration - start >= SCREEN_RUN_MIN_SECONDS
            guard_fits_episode = duration >= (
                2 * SCREEN_EDGE_GUARD_SECONDS + SCREEN_RUN_MIN_SECONDS
            )
            away_from_edges = (
                not guard_fits_episode
                or (
                    start >= SCREEN_EDGE_GUARD_SECONDS
                    and duration - start >= SCREEN_EDGE_GUARD_SECONDS
                )
            )
            choose_screen = (
                screen_active
                and enough_time_for_run
                and away_from_edges
                and (
                    not screen_has_been_shown
                    or rng.random() < SCREEN_RUN_START_PROBABILITY
                )
            )
            if episode85 and screen_has_content and enough_time_for_run:
                choose_screen = True
            # In the middle of a recording, bias toward showing the screen
            # even when the low-cost activity detector is inconclusive.
            if (
                not choose_screen
                and screen_has_content
                and enough_time_for_run
                and away_from_edges
            ):
                choose_screen = rng.random() < SCREEN_INACTIVE_START_PROBABILITY
            if choose_screen:
                screen_run_until = start + rng.uniform(
                    SCREEN_RUN_MIN_SECONDS, SCREEN_RUN_TARGET_MAX_SECONDS
                )
                screen_run_position = "upper_right"
                screen_has_been_shown = True

        if choose_screen:
            # Hold the screen+PiP treatment for a complete 20-30 second block.
            # The PiP source may change with the active speaker, but the layout
            # and corner remain stable for the entire block.
            scene_type = "screen_pip"
            scene = Scene(
                start=round(start, 3),
                end=round(end, 3),
                source=screen.name,
                scene_type=scene_type,
                pip_source=speaker,
                pip_position=screen_run_position,
            )
            if screen_run_until is not None and end >= screen_run_until:
                screen_run_until = None
                screen_run_position = None
                screen_cooldown_until = end + SCREEN_RUN_COOLDOWN_SECONDS
        else:
            # Apply the Shorts zoom range less often for long-form viewing.
            # Never zoom twice consecutively, and start a new speaker unzoomed.
            use_zoom = (
                speaker == previous_webcam_source
                and not previous_webcam_zoom
                and rng.random() < ZOOM_PROBABILITY
            )
            guard_fits_episode = duration >= (
                2 * SCREEN_EDGE_GUARD_SECONDS + SCREEN_RUN_MIN_SECONDS
            )
            three_panel_allowed = not guard_fits_episode or (
                start >= SCREEN_EDGE_GUARD_SECONDS
                and duration - start >= SCREEN_EDGE_GUARD_SECONDS
            )
            use_three_panel = (
                len(webcams) >= 2
                and screen_has_content
                and three_panel_allowed
                and rng.random() < THREE_PANEL_PROBABILITY
            )
            use_dual_webcam = (
                not use_three_panel
                and len(webcams) >= 2
                and rng.random() < DUAL_WEBCAM_PROBABILITY
            )
            if use_three_panel:
                scene_type = "three_panel"
            elif use_dual_webcam:
                scene_type = "webcam_pair"
            else:
                scene_type = "webcam_zoom" if use_zoom else "webcam_full"
            zoom = round(rng.uniform(1.05, 1.15), 4) if use_zoom else 1.0
            secondary = None
            if (use_three_panel or use_dual_webcam) and len(webcams) >= 2:
                alternatives = [item.name for item in webcams if item.name != speaker]
                secondary = alternatives[0] if alternatives else None
            scene = Scene(
                start=round(start, 3),
                end=round(end, 3),
                source=speaker,
                scene_type=scene_type,
                zoom=zoom,
                secondary_source=secondary,
                pip_source=screen.name if use_three_panel else None,
            )
            previous_webcam_source = speaker
            previous_webcam_zoom = use_zoom
        scenes.append(scene)
        previous_speaker = speaker

    # Never let the Episode 85 composite's initial black lead-in leak into the
    # output. Replace any accidental early screen scene with its speaking
    # webcam (the scene interval and audio timing remain unchanged).
    sanitized: List[Scene] = []
    for scene in scenes:
        if "screen-composite" in screen.name.lower() and scene.start < 210.0 and scene.scene_type in {"screen_pip", "screen_full", "three_panel"}:
            webcam_name = scene.pip_source if scene.scene_type == "screen_pip" else scene.source
            if webcam_name not in {item.name for item in webcams}:
                webcam_name = webcams[0].name
            scene = replace(scene, source=webcam_name, scene_type="webcam_full", zoom=1.0, pip_source=None, pip_position=None, secondary_source=None)
        sanitized.append(scene)
    scenes = _ensure_source_coverage(sanitized, webcams)

    # Episode 85 ending direction: the rendered file trims four seconds from
    # the plan, so output 19:10–19:14 maps to plan 19:14–19:18. Force Ryan's
    # full camera for that four-second handoff, then hold both cameras through
    # the final fade instead of allowing a random late scene to replace it.
    if "episode-85" in episode.lower() or "episode_85" in episode.lower():
        ryan = next((item.name for item in webcams if "ryan" in item.name.lower()), None)
        stephen = next((item.name for item in webcams if "stephen" in item.name.lower()), None)
        if ryan and stephen and duration >= 1158.0:
            forced: List[Scene] = []
            for scene in scenes:
                cuts = [point for point in (1158.0,) if scene.start < point < scene.end]
                points = [scene.start, *cuts, scene.end]
                for left, right in zip(points, points[1:]):
                    forced.append(replace(scene, start=round(left, 3), end=round(right, 3)))
            scenes = forced
            for index, scene in enumerate(scenes):
                if scene.start >= 1153.0 and scene.start < 1158.0:
                    scenes[index] = replace(scene, source=ryan, scene_type="webcam_full", zoom=1.0, pip_source=None, pip_position=None, secondary_source=None)
                elif scene.start >= 1158.0:
                    scenes[index] = replace(scene, source=ryan, scene_type="webcam_pair", zoom=1.0, pip_source=None, pip_position=None, secondary_source=stephen)

    return EditPlan(
        version=1,
        episode=episode,
        seed=seed,
        common_start=round(common_start, 6),
        duration=round(duration, 3),
        sources=sources,
        scenes=scenes,
        settings={
            "canvas": {"width": 1920, "height": 1080, "fps": 30},
            "target_scene_seconds": [TARGET_SCENE_MIN, TARGET_SCENE_MAX],
            "minimum_scene_seconds": MIN_SCENE_SECONDS,
            "pause_snap_seconds": PAUSE_SNAP_SECONDS,
            "audio_interval_seconds": analysis.audio_interval,
            "screen_interval_seconds": analysis.screen_interval,
            "screen_hold_seconds": 20,
            "screen_run_start_probability": SCREEN_RUN_START_PROBABILITY,
            "screen_inactive_start_probability": SCREEN_INACTIVE_START_PROBABILITY,
            "screen_edge_guard_seconds": SCREEN_EDGE_GUARD_SECONDS,
            "speaker_pip_during_screen_activity": True,
            "zoom_range": [1.05, 1.15],
            "zoom_probability": ZOOM_PROBABILITY,
            "screen_run_seconds": [SCREEN_RUN_MIN_SECONDS, 30.0],
            "screen_run_cooldown_seconds": SCREEN_RUN_COOLDOWN_SECONDS,
            "audio_activity_threshold": AUDIO_ACTIVITY_THRESHOLD,
            "audio_sources": "webcams",
            "dual_webcam_probability": DUAL_WEBCAM_PROBABILITY,
            "three_panel_probability": THREE_PANEL_PROBABILITY,
        },
    )
