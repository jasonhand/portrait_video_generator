"""FFmpeg filter-graph renderer for long-form edit plans."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .models import EditPlan, Scene, SourceInfo


DEFAULT_LOGO_PATH = Path(__file__).resolve().parent.parent / "logos" / "ai_tl_logo.png"
DEFAULT_LOWER_THIRD_PATH = (
    Path(__file__).resolve().parent / "hyperframes" / "lower-third" / "lower-third-alpha.mov"
)
DEFAULT_EPISODE85_LOWER_THIRD_PATH = (
    Path(__file__).resolve().parent / "hyperframes" / "episode85-lower-third" / "lower-third-alpha.mov"
)
DEFAULT_LOWER_THIRD_FRAMES = (
    Path(__file__).resolve().parent / "hyperframes" / "lower-third" / ".hf-frames" / "frame_%06d.png"
)
DEFAULT_SPEAKER_FRAME_ROOT = (
    Path(__file__).resolve().parent / "hyperframes" / "lower-third"
)
DEFAULT_EPISODE85_SPEAKER_FRAME_ROOT = (
    Path(__file__).resolve().parent / "hyperframes" / "episode85-speaker-lower-thirds"
)
DEFAULT_CTA_FRAMES = (
    Path(__file__).resolve().parent / "hyperframes" / "cta" / ".hf-frames" / "frame_%06d.png"
)
DEFAULT_CTA_ALPHA_PATH = Path(__file__).resolve().parent / "hyperframes" / "cta" / "cta-alpha.mov"
DEFAULT_PIP_FRAME_ALPHA_PATH = Path(__file__).resolve().parent / "hyperframes" / "pip-frame" / "pip-frame-alpha.mov"
DEFAULT_THREE_PANEL_FRAME_ALPHA_PATH = Path(__file__).resolve().parent / "hyperframes" / "three-panel-frame" / "three-panel-frame-alpha.mov"
DEFAULT_PIP_FRAME_FRAMES = (
    Path(__file__).resolve().parent / "hyperframes" / "pip-frame" / ".hf-frames" / "frame_%06d.png"
)
DEFAULT_THREE_PANEL_FRAME_FRAMES = (
    Path(__file__).resolve().parent / "hyperframes" / "three-panel-frame" / ".hf-frames" / "frame_%06d.png"
)
CTA_STARTS_SECONDS = (420.0, 840.0, 1260.0)
# Keep the overlay active through the HyperFrames card's 8.4–9.0s exit slide.
LOWER_THIRD_SECONDS = 9.1
# Match the HyperFrames lower-third typography: Inter 700 for headings and
# Inter 400 for supporting text. These cached WOFF2 files are also used by the
# lower-third composition in the browser renderer.
INTER_BOLD_FONT = "/Users/jason.hand/.cache/hyperframes/fonts/inter/700-normal-d3b40ef29e5d.woff2"
INTER_REGULAR_FONT = "/Users/jason.hand/.cache/hyperframes/fonts/inter/400-normal-6f1116f03e95.woff2"


def _create_lower_third_asset(path: Path) -> None:
    """Create the opening lower-third card as a transparent PNG."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (1100, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 912, 212), radius=24, fill="#1A1F36", outline="#A960FF", width=4)
    draw.rectangle((8, 8, 20, 212), fill="#A960FF")
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    regular_candidates = [
        *sorted(Path("/Users/jason.hand/.cache/hyperframes/fonts/inter").glob("400-normal-*.woff2")),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_path = next((item for item in candidates if Path(item).is_file()), None)
    regular_path = next((item for item in regular_candidates if Path(item).is_file()), bold_path)
    bold = ImageFont.truetype(bold_path, 48) if bold_path else ImageFont.load_default()
    regular = ImageFont.truetype(regular_path, 34) if regular_path else ImageFont.load_default()
    draw.text((52, 42), "Datadog AI Tools Lab", font=bold, fill="#FFFFFF")
    draw.text((54, 112), "Jason Hand & Tara Schofield", font=regular, fill="#ECDDFF")
    image.save(path)


def _create_speaker_lower_third_asset(path: Path, name: str, title: str) -> None:
    """Create a speaker card matching the opening lower-third treatment."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGBA", (920, 196), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 918, 194), radius=28, fill="#1A1F36", outline="#A960FF", width=3)
    draw.rectangle((2, 2, 18, 194), fill="#A960FF")
    draw.line((48, 169, 858, 169), fill="#A960FF", width=3)
    regular_candidates = [
        *sorted(Path("/Users/jason.hand/.cache/hyperframes/fonts/inter").glob("400-normal-*.woff2")),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    font_path = next((item for item in regular_candidates if Path(item).is_file()), None)
    font = ImageFont.truetype(font_path, 60) if font_path else ImageFont.load_default()
    draw.text((180, 36), name, font=font, fill="#FFFFFF")
    title_font = ImageFont.truetype(font_path, 30) if font_path else ImageFont.load_default()
    draw.text((182, 108), title, font=title_font, fill="#ECDDFF")
    logo_path = Path(__file__).resolve().parent.parent / "logos" / "logo.png"
    if logo_path.is_file():
        logo = Image.open(logo_path).convert("RGBA")
        alpha = logo.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            logo = logo.crop(bbox)
        logo.thumbnail((128, 128), Image.Resampling.LANCZOS)
        image.alpha_composite(logo, (28, 34))
    image.save(path)


def _limited_scenes(
    plan: EditPlan, limit: Optional[float], start_offset: float = 0.0,
    apply_tail: bool = True,
    coalesce_identical: bool = True,
    trim_end: float = 0.0,
) -> Tuple[List[Scene], float]:
    if start_offset < 0 or start_offset >= plan.duration:
        raise ValueError("Trim start must be between 0 and the plan duration")
    if trim_end < 0 or trim_end >= plan.duration - start_offset:
        raise ValueError("Trim end must leave a positive render duration")
    available = plan.duration - start_offset - trim_end
    duration = min(available, limit) if limit else available
    if duration <= 0:
        raise ValueError("Render duration must be greater than zero")
    scenes = []
    source_end = start_offset + duration
    for scene in plan.scenes:
        if scene.end <= start_offset:
            continue
        if scene.start >= source_end:
            break
        scenes.append(
            Scene(
                start=max(scene.start, start_offset) - start_offset,
                end=min(scene.end, source_end) - start_offset,
                source=scene.source,
                scene_type=scene.scene_type,
                zoom=scene.zoom,
                pip_source=scene.pip_source,
                pip_position=scene.pip_position,
                secondary_source=scene.secondary_source,
            )
        )
    if not scenes:
        raise ValueError("The edit plan contains no scenes in the requested render interval")
    if coalesce_identical:
        merged: List[Scene] = []
        for scene in scenes:
            if merged and merged[-1].end == scene.start and merged[-1].source == scene.source and merged[-1].scene_type == scene.scene_type and merged[-1].zoom == scene.zoom and merged[-1].pip_source == scene.pip_source and merged[-1].pip_position == scene.pip_position and merged[-1].secondary_source == scene.secondary_source:
                previous = merged[-1]
                merged[-1] = Scene(previous.start, scene.end, previous.source, previous.scene_type, previous.zoom, previous.pip_source, previous.pip_position, previous.secondary_source)
            else:
                merged.append(scene)
        scenes = merged
    webcams = [source.name for source in plan.sources if source.kind == "webcam"]
    if apply_tail and len(webcams) >= 2:
        tail_start = max(0.0, duration - 20.0)
        for index, scene in enumerate(scenes):
            if scene.start >= tail_start:
                scenes[index] = Scene(
                    start=scene.start,
                    end=scene.end,
                    source=webcams[0],
                    scene_type="webcam_pair",
                    secondary_source=webcams[1],
                )
    return scenes, duration


class _VideoLabels:
    def __init__(self, plan: EditPlan, scenes: Iterable[Scene]):
        counts: Counter[str] = Counter()
        for scene in scenes:
            counts[scene.source] += 1
            if scene.pip_source:
                counts[scene.pip_source] += 1
            if scene.secondary_source:
                counts[scene.secondary_source] += 1
        self.counts = counts
        self.next_index: Dict[str, int] = defaultdict(int)
        self.source_indices = {source.name: index for index, source in enumerate(plan.sources)}

    def split_filters(self) -> List[str]:
        filters = []
        for source_name, count in self.counts.items():
            source_index = self.source_indices[source_name]
            labels = "".join(f"[src_{source_index}_{item}]" for item in range(count))
            filters.append(f"[{source_index}:v]split={count}{labels}")
        return filters

    def take(self, source_name: str) -> str:
        source_index = self.source_indices[source_name]
        item = self.next_index[source_name]
        self.next_index[source_name] += 1
        return f"src_{source_index}_{item}"


def _webcam_filter(label: str, scene: Scene, output_label: str) -> str:
    zoom = max(1.0, scene.zoom)
    scaled_width = int(round(1920 * zoom / 2.0) * 2)
    scaled_height = int(round(1080 * zoom / 2.0) * 2)
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},"
        "setpts=PTS-STARTPTS,"
        f"scale={scaled_width}:{scaled_height}:force_original_aspect_ratio=increase,"
        "crop=1920:1080,setsar=1,format=yuv420p"
        f"[{output_label}]"
    )


def _screen_filter(label: str, scene: Scene, output_label: str) -> str:
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},"
        "setpts=PTS-STARTPTS,"
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x111111,"
        f"setsar=1,format=yuv420p[{output_label}]"
    )


def _screen_pip_filters(
    main_label: str,
    pip_label: str,
    scene: Scene,
    scene_index: int,
    output_label: str,
    frame_input_index: Optional[int] = None,
) -> List[str]:
    base = f"screen_base_{scene_index}"
    pip_video = f"pip_video_{scene_index}"
    # Compact square PiP with rounded corners; this blocks less of the shared
    # screen while keeping the active speaker recognizable.
    video_mask = (
        "if(lte(pow(max(abs(X-W/2)-(W/2-24),0),2)+"
        "pow(max(abs(Y-H/2)-(H/2-24),0),2),pow(24,2)),255,0)"
    )
    filters = [
        _screen_filter(main_label, scene, base),
        (
            f"[{pip_label}]trim=start={scene.start:.3f}:end={scene.end:.3f},"
            "setpts=PTS-STARTPTS,"
            "scale=300:300:force_original_aspect_ratio=increase,crop=300:300,"
            "setsar=1,format=rgba,"
            f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{video_mask}'[{pip_video}]"
        ),
    ]
    if frame_input_index is not None:
        frame_label = f"pip_frame_{scene_index}"
        framed_base = f"pip_framed_base_{scene_index}"
        filters.extend([
            f"[{frame_input_index}:v]format=rgba[{frame_label}]",
            f"[{base}][{frame_label}]overlay=x=0:y=0:shortest=1[{framed_base}]",
            f"[{framed_base}][{pip_video}]overlay=x=W-w-32:y=32:shortest=1,format=yuv420p[{output_label}]",
        ])
    else:
        filters.append(
            f"[{base}][{pip_video}]overlay=x=W-w-32:y=32:shortest=1,"
            f"format=yuv420p[{output_label}]"
        )
    return filters


def _panel_filter(label: str, scene: Scene, width: int, output_label: str) -> str:
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},"
        "setpts=PTS-STARTPTS,"
        f"scale={width}:1080:force_original_aspect_ratio=increase,"
        f"crop={width}:1080,setsar=1,format=yuv420p[{output_label}]"
    )


def _rounded_panel_filter(label: str, scene: Scene, width: int, output_label: str) -> str:
    """Fill a tall camera panel while clipping its corners softly."""
    radius = 28
    mask = (
        f"if(lte(pow(max(abs(X-W/2)-(W/2-{radius}),0),2)+"
        f"pow(max(abs(Y-H/2)-(H/2-{radius}),0),2),pow({radius},2)),255,0)"
    )
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},setpts=PTS-STARTPTS,"
        f"scale={width}:1080:force_original_aspect_ratio=increase,crop={width}:1080,"
        f"setsar=1,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{mask}'[{output_label}]"
    )


def _stacked_camera_filter(
    first_label: str, second_label: str, scene: Scene, width: int, output_label: str
) -> str:
    """Stack two rounded camera tiles on the left of a 3-panel composition."""
    # Reserve an 8px canvas allowance around the 440px camera tiles. The
    # animated HyperFrames frame is 448px wide; overlaying it onto a 440px
    # main input causes FFmpeg to keep the main width and crop the frame's
    # right outline. The 4px inset aligns the tile with the frame's inner edge.
    canvas_width = width + 8
    tile_height = 520
    radius = 28
    mask = (
        f"if(lte(pow(max(abs(X-W/2)-(W/2-{radius}),0),2)+"
        f"pow(max(abs(Y-H/2)-(H/2-{radius}),0),2),pow({radius},2)),255,0)"
    )
    first = f"{output_label}_first"
    second = f"{output_label}_second"
    bg = f"{output_label}_bg"
    return (
        f"[{first_label}]trim=start={scene.start:.3f}:end={scene.end:.3f},setpts=PTS-STARTPTS,"
        f"scale={width}:{tile_height}:force_original_aspect_ratio=increase,crop={width}:{tile_height},"
        f"setsar=1,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{mask}'[{first}];"
        f"[{second_label}]trim=start={scene.start:.3f}:end={scene.end:.3f},setpts=PTS-STARTPTS,"
        f"scale={width}:{tile_height}:force_original_aspect_ratio=increase,crop={width}:{tile_height},"
        f"setsar=1,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{mask}'[{second}];"
        f"color=c=0xA960FF:s={canvas_width}x1080:r=30[{bg}];"
        f"[{bg}][{first}]overlay=x=4:y=8:shortest=1[${output_label}_top];"
        f"[${output_label}_top][{second}]overlay=x=4:y=552:shortest=1,"
        f"format=yuv420p[{output_label}]"
    ).replace("[$", "[")


def _rounded_square_panel_filter(label: str, scene: Scene, width: int, output_label: str) -> str:
    """Render a small rounded webcam square centered in a colored side panel."""
    tile = 320
    tile_label = f"{output_label}_tile"
    mask = (
        "if(lte(pow(max(abs(X-W/2)-(W/2-24),0),2)+"
        "pow(max(abs(Y-H/2)-(H/2-24),0),2),pow(24,2)),255,0)"
    )
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},setpts=PTS-STARTPTS,"
        f"scale={tile}:{tile}:force_original_aspect_ratio=increase,crop={tile}:{tile},"
        f"setsar=1,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='{mask}'[{tile_label}];"
        f"color=c=0x34008D:s={width}x1080:r=30[${output_label}_bg];"
        f"[${output_label}_bg][{tile_label}]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1,"
        f"format=yuv420p[{output_label}]"
    ).replace("[$", "[")


def _screen_panel_filter(label: str, scene: Scene, width: int, output_label: str) -> str:
    """Contain the complete screenshare; letterbox instead of cropping sides."""
    return (
        f"[{label}]trim=start={scene.start:.3f}:end={scene.end:.3f},"
        "setpts=PTS-STARTPTS,"
        f"scale={width}:1080:force_original_aspect_ratio=decrease,"
        f"pad={width}:1080:(ow-iw)/2:(oh-ih)/2:color=0xA960FF,"
        f"setsar=1,format=yuv420p[{output_label}]"
    )


def build_filter_graph(
    plan: EditPlan,
    scenes: List[Scene],
    render_duration: float,
    include_screen_audio: bool,
    logo_input_index: Optional[int] = None,
    lower_third_input_index: Optional[int] = None,
    cta_input_index: Optional[int] = None,
    pip_frame_input_index: Optional[int] = None,
    three_panel_frame_input_index: Optional[int] = None,
    speaker_lower_third_inputs: Optional[Dict[str, int]] = None,
    speaker_animated: Optional[Dict[str, bool]] = None,
    apply_fade_in: bool = True,
    apply_fade_out: bool = True,
    cta_time_offset: float = 0.0,
) -> str:
    labels = _VideoLabels(plan, scenes)
    filters = labels.split_filters()
    scene_outputs = []

    for index, scene in enumerate(scenes):
        output_label = f"scene_{index}"
        main_label = labels.take(scene.source)
        if scene.scene_type in {"webcam_full", "webcam_zoom"}:
            filters.append(_webcam_filter(main_label, scene, output_label))
        elif scene.scene_type == "webcam_pair":
            if not scene.secondary_source:
                raise ValueError(f"Scene {index} is missing secondary_source")
            right_label = labels.take(scene.secondary_source)
            left = f"pair_left_{index}"
            right = f"pair_right_{index}"
            filters.extend(
                [
                    _rounded_panel_filter(main_label, scene, 960, left),
                    _rounded_panel_filter(right_label, scene, 960, right),
                    f"[{left}][{right}]hstack=inputs=2,format=yuv420p[{output_label}]",
                ]
            )
        elif scene.scene_type == "three_panel":
            if not scene.secondary_source or not scene.pip_source:
                raise ValueError(f"Scene {index} is missing three-panel sources")
            right_label = labels.take(scene.secondary_source)
            center_label = labels.take(scene.pip_source)
            left = f"three_left_{index}"
            center = f"three_center_{index}"
            filters.extend(
                [
                    _stacked_camera_filter(main_label, right_label, scene, 440, left),
                    _screen_panel_filter(center_label, scene, 1472, center),
                    f"[{center}]drawtext=text='View more episodes at dtdg.co/aitl':"
                    f"fontfile={INTER_REGULAR_FONT}:"
                    "fontcolor=white:fontsize=56:x=(w-text_w)/2:y=h-78:borderw=1:bordercolor=0x34008D[three_center_text]"
                ]
            )
            if three_panel_frame_input_index is not None:
                framed_left = f"three_left_framed_{index}"
                filters.append(f"[{three_panel_frame_input_index}:v]format=rgba[three_frame_{index}]")
                filters.append(
                    f"[{left}][three_frame_{index}]overlay=x=0:y=0:shortest=1[{framed_left}]"
                )
                left = framed_left
            filters.append(f"[{left}][three_center_text]hstack=inputs=2,format=yuv420p[{output_label}]")
        elif scene.scene_type == "screen_full":
            filters.append(_screen_filter(main_label, scene, output_label))
        elif scene.scene_type == "screen_pip":
            if not scene.pip_source:
                raise ValueError(f"Scene {index} is missing pip_source")
            filters.extend(
                _screen_pip_filters(
                    main_label,
                    labels.take(scene.pip_source),
                    scene,
                    index,
                    output_label,
                    pip_frame_input_index,
                )
            )
        else:
            raise ValueError(f"Unknown scene type: {scene.scene_type}")
        scene_outputs.append(f"[{output_label}]")

    logo_corner_label = None
    if logo_input_index is not None:
        filters.append(f"[{logo_input_index}:v]split=2[logo_upper_src][logo_lower_src]")
        # ai_tl_logo.png is a large transparent canvas; crop to the artwork
        # before scaling so edge padding applies to the visible logo itself.
        filters.append("[logo_upper_src]crop=1073:422:430:307,scale=-1:135,format=rgba[logo_upper]")
        filters.append("[logo_lower_src]crop=1073:422:430:307,scale=-1:135,format=rgba[logo_lower]")
        logo_corner_label = "logo_upper"

    concatenated_label = "video_concat" if logo_corner_label is not None else "vout"
    filters.append(
        "".join(scene_outputs)
        + f"concat=n={len(scene_outputs)}:v=1:a=0[{concatenated_label}]"
    )
    if logo_corner_label is not None:
        pip_intervals = []
        elapsed = 0.0
        for scene in scenes:
            if scene.scene_type == "screen_pip":
                pip_intervals.append(
                    f"between(t,{elapsed:.3f},{elapsed + (scene.end - scene.start):.3f})"
                )
            elapsed += scene.end - scene.start
        pip_enabled = "+".join(pip_intervals) or "0"
        filters.append(
            f"[{concatenated_label}][{logo_corner_label}]overlay=x=W-w-5:y=5:"
            f"enable='not({pip_enabled})':shortest=1,format=yuv420p[video_logo_upper]"
        )
        filters.append(
            "[video_logo_upper][logo_lower]overlay=x=W-w-5:y=H-h-5:"
            f"enable='{pip_enabled}':shortest=1,format=yuv420p[video_logo]"
        )
        logo_output_label = "video_logo"
    else:
        logo_output_label = concatenated_label
    if cta_input_index is not None:
        # Reset the holographic toast movie for every scheduled occurrence.
        # A single looped input carries a global timestamp; after the first
        # toast, later windows could land on transparent frames and appear to
        # have disappeared entirely. Each branch starts at frame zero and is
        # shifted onto the absolute output timeline.
        cta_label = logo_output_label
        for cta_index, absolute_start in enumerate(CTA_STARTS_SECONDS):
            start = absolute_start - cta_time_offset
            if start + 6.0 <= 0 or start >= render_duration:
                continue
            cta_end = min(render_duration, start + 6.0)
            asset_label = f"cta_asset_{cta_index}"
            output_label = f"video_cta_{cta_index}"
            filters.append(
                f"[{cta_input_index}:v]trim=duration=6.000,setpts=PTS-STARTPTS+{start:.3f}/TB,"
                f"format=rgba[{asset_label}]"
            )
            filters.append(
                f"[{cta_label}][{asset_label}]overlay=x=48:y=H-h-24:"
                f"enable='between(t,{start:.3f},{cta_end:.3f})':"
                f"eof_action=pass:format=auto,format=yuv420p[{output_label}]"
            )
            cta_label = output_label
        if cta_label != logo_output_label:
            base_label = cta_label
    base_label = cta_label if cta_input_index is not None and cta_label != logo_output_label else logo_output_label
    if lower_third_input_index is not None:
        input_label = base_label
        intro_chain = (
            f"eof_action=pass:format=auto"
            + (",fade=t=in:st=0:d=1" if apply_fade_in else "")
            + (f",fade=t=out:st={max(0.0, render_duration - 1.0):.3f}:d=1" if apply_fade_out else "")
            + ",format=yuv420p[video_intro]"
        )
        filters.extend(
            [
                f"[{lower_third_input_index}:v]format=rgba[lower_third]",
                (
                    f"[{input_label}][lower_third]overlay=x=48:y=H-h-24:"
                    f"enable='between(t,0,{LOWER_THIRD_SECONDS:.3f})':"
                    + intro_chain
                ),
            ]
        )
        base_label = "video_intro"

    # Add occasional speaker IDs only during longer full-camera scenes.
    if speaker_lower_third_inputs:
        elapsed = 0.0
        events: Dict[str, List[Tuple[float, float]]] = defaultdict(list)
        last_event_by_source: Dict[str, float] = {}
        for scene in scenes:
            if elapsed >= 12.0 and scene.scene_type in {"webcam_full", "webcam_zoom"} and scene.duration >= 5.0:
                source_lower = scene.source.lower()
                # Keep Ryan's IDs less frequent than Stephen's, but guarantee
                # an early appearance and then allow additional cards roughly
                # every 2.5 minutes when a qualifying full-camera scene exists.
                # This is evaluated on the trimmed render timeline.
                if "ryan" in source_lower:
                    last = last_event_by_source.get(scene.source)
                    should_show = elapsed >= 30.0 and (last is None or elapsed - last >= 150.0)
                else:
                    should_show = int(elapsed / 5.0) % 12 == 0
                # Keep Ryan's console walkthrough around 5:09 unobstructed.
                if ("episode-85" in plan.episode.lower() or "episode_85" in plan.episode.lower()) and 295.0 <= elapsed < 320.0:
                    should_show = False
                if should_show:
                    events[scene.source].append((elapsed, elapsed + scene.duration))
                    last_event_by_source[scene.source] = elapsed
            elapsed += scene.duration
        for source_name, intervals in events.items():
            input_index = speaker_lower_third_inputs.get(source_name)
            if input_index is None:
                continue
            for interval_index, (start, end) in enumerate(intervals):
                # HyperFrames lower-third assets are 10 seconds long. Cap the
                # visible window so a longer camera scene cannot loop the
                # alpha movie and restart the card animation.
                display_end = min(end, start + LOWER_THIRD_SECONDS)
                output_label = f"speaker_overlay_{input_index}_{interval_index}"
                # Reset the HyperFrames movie to frame zero for every event.
                # A looped input otherwise keeps a global timestamp, so later
                # lower thirds can begin halfway through their animation and
                # appear/disappear abruptly. Shift the trimmed asset to the
                # event's absolute timeline before overlaying it.
                asset_label = f"speaker_asset_{input_index}_{interval_index}"
                filters.append(
                    f"[{input_index}:v]trim=duration={LOWER_THIRD_SECONDS:.3f},"
                    f"setpts=PTS-STARTPTS+{start:.3f}/TB,format=rgba[{asset_label}]"
                )
                # Enter from the left and reverse the same motion to leave the
                # frame. Each occurrence gets its own timing expression so a
                # later card cannot reuse the first card's exit animation.
                if (speaker_animated or {}).get(source_name):
                    x_expr = (
                        "-80*max(0,min(1,(%.3f-t)/0.4))"
                        "-1920*max(0,min(1,(t-%.3f)/0.4))" % (start, display_end - 0.4)
                    )
                    y_expr = "0"
                else:
                    x_expr = (
                        "48-80*max(0,min(1,(%.3f-t)/0.4))"
                        "-992*max(0,min(1,(t-%.3f)/0.4))" % (start, display_end - 0.4)
                    )
                    y_expr = "H-h-24"
                filters.append(
                    f"[{base_label}][{asset_label}]overlay=x='{x_expr}':y={y_expr}:"
                    f"enable='between(t,{start:.3f},{display_end:.3f})':eof_action=pass:format=auto,"
                    f"format=yuv420p[{output_label}]"
                )
                base_label = output_label
    if base_label != "vout":
        filters.append(f"[{base_label}]format=yuv420p[vout]")

    audio_sources = [source for source in plan.sources if source.kind == "webcam" and source.has_audio]
    if include_screen_audio:
        audio_sources.extend(
            source for source in plan.sources if source.kind == "screen" and source.has_audio
        )
    audio_labels = []
    source_indices = {source.name: index for index, source in enumerate(plan.sources)}
    for item, source in enumerate(audio_sources):
        label = f"audio_{item}"
        filters.append(
            f"[{source_indices[source.name]}:a]atrim=start=0:end={render_duration:.3f},"
            f"asetpts=PTS-STARTPTS,aresample=48000[{label}]"
        )
        audio_labels.append(f"[{label}]")
    if audio_labels:
        filters.append(
            "".join(audio_labels)
            + f"amix=inputs={len(audio_labels)}:duration=longest:normalize=0,"
            f"alimiter=limit=0.95,atrim=duration={render_duration:.3f}[aout]"
        )
    else:
        filters.append(
            f"anullsrc=r=48000:cl=stereo,atrim=duration={render_duration:.3f}[aout]"
        )
    return ";\n".join(filters) + "\n"


def _input_arguments(plan: EditPlan, render_duration: float, start_offset: float = 0.0) -> List[str]:
    arguments = []
    # Keep a small decode cushion so a scene ending exactly at the chunk
    # boundary still has a final frame after trim/PTS normalization.
    input_duration = render_duration + 0.5
    for source in plan.sources:
        local_start = max(0.0, plan.common_start + start_offset - source.offset)
        arguments.extend(
            [
                "-ss",
                f"{local_start:.6f}",
                "-t",
                f"{input_duration:.6f}",
                "-i",
                source.path,
            ]
        )
    return arguments


def probe_output(path: Path) -> Dict[str, object]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def verify_output(probe: Dict[str, object], expected_duration: float) -> None:
    streams = probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video or (video.get("width"), video.get("height")) != (1920, 1080):
        raise RuntimeError("Rendered output is not 1920x1080 video")
    if video.get("codec_name") != "h264":
        raise RuntimeError(f"Rendered video codec is {video.get('codec_name')}, expected h264")
    if not audio or audio.get("codec_name") != "aac":
        raise RuntimeError("Rendered output does not contain AAC audio")
    actual_duration = float(probe.get("format", {}).get("duration", 0.0))
    if abs(actual_duration - expected_duration) > 0.25:
        raise RuntimeError(
            f"Rendered duration is {actual_duration:.3f}s, expected {expected_duration:.3f}s"
        )


def render_plan(
    plan: EditPlan,
    output: Path,
    preview_seconds: Optional[float] = None,
    include_screen_audio: bool = False,
    overwrite: bool = False,
    keep_workdir: bool = False,
    logo_path: Optional[Path] = None,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    video_encoder: str = "libx264",
    preset: str = "veryfast",
    apply_tail: bool = True,
    coalesce_identical: bool = True,
    apply_fade_in: bool = True,
    apply_fade_out: bool = True,
    cta_time_offset: float = 0.0,
) -> Dict[str, object]:
    output = Path(output).resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists; pass --overwrite to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    for source in plan.sources:
        if not Path(source.path).is_file():
            raise FileNotFoundError(f"Source from edit plan no longer exists: {source.path}")

    resolved_logo = Path(logo_path).resolve() if logo_path else DEFAULT_LOGO_PATH
    if not resolved_logo.is_file():
        raise FileNotFoundError(f"Logo image not found: {resolved_logo}")

    scenes, render_duration = _limited_scenes(
        plan, preview_seconds, trim_start, apply_tail, coalesce_identical, trim_end
    )
    cta_first_frame = DEFAULT_CTA_FRAMES.parent / "frame_000001.png"
    cta_available = DEFAULT_CTA_ALPHA_PATH.is_file() or cta_first_frame.is_file()
    pip_frame_available = DEFAULT_PIP_FRAME_ALPHA_PATH.is_file() or DEFAULT_PIP_FRAME_FRAMES.parent.joinpath("frame_000001.png").is_file()
    three_panel_frame_available = DEFAULT_THREE_PANEL_FRAME_ALPHA_PATH.is_file() or DEFAULT_THREE_PANEL_FRAME_FRAMES.parent.joinpath("frame_000001.png").is_file()
    workdir = Path(tempfile.mkdtemp(prefix="long-form-", dir=str(output.parent)))
    speaker_assets: Dict[str, Path] = {}
    speaker_animated: Dict[str, bool] = {}
    for source in plan.sources:
        if source.kind != "webcam":
            continue
        name_lower = source.name.lower()
        if "jason" in name_lower:
            display_name, title = "Jason Hand", "Senior Advocate - AI & Cloud"
        elif "tara" in name_lower:
            display_name, title = "Tara Schofield", "Technical Advocate - Cloud"
        elif "ryan" in name_lower:
            display_name, title = "Ryan MacLean", "Senior Technical Advocate - Cloud & AI"
        elif "stephen" in name_lower:
            display_name, title = "Stephen Rosenthal", "Senior Software Engineer - Auth & Identity"
        else:
            display_name, title = Path(source.name).stem, ""
        frame_key = display_name.lower().split()[0]
        speaker_root = DEFAULT_EPISODE85_SPEAKER_FRAME_ROOT if "episode-85" in plan.episode.lower() or "episode_85" in plan.episode.lower() else DEFAULT_SPEAKER_FRAME_ROOT
        # Episode-specific speaker compositions are kept in per-speaker
        # directories; resolve those before falling back to a static PNG.
        asset_root = speaker_root / frame_key if speaker_root.name == "episode85-speaker-lower-thirds" else speaker_root
        alpha_path = asset_root / f"{frame_key}-lower-third-alpha.mov"
        frame_dir = asset_root / f".hf-frames-{frame_key}"
        frame_pattern = frame_dir / "frame_%06d.png"
        if alpha_path.is_file():
            speaker_assets[source.name] = alpha_path
            speaker_animated[source.name] = True
        elif (frame_dir / "frame_000001.png").is_file():
            speaker_assets[source.name] = frame_pattern
            speaker_animated[source.name] = True
        else:
            asset_path = workdir / f"speaker-{len(speaker_assets)}.png"
            _create_speaker_lower_third_asset(asset_path, display_name, title)
            speaker_assets[source.name] = asset_path
            speaker_animated[source.name] = False
    pip_frame_input_index = len(plan.sources) + (3 if cta_available else 2) if pip_frame_available else None
    three_panel_frame_input_index = (
        len(plan.sources) + 2 + int(cta_available) + int(pip_frame_available)
        if three_panel_frame_available else None
    )
    speaker_input_base = len(plan.sources) + 2 + int(cta_available) + int(pip_frame_available) + int(three_panel_frame_available)
    speaker_input_indices = {
        source_name: speaker_input_base + index
        for index, source_name in enumerate(speaker_assets)
    }
    filter_path = workdir / "filter-complex.txt"
    filter_path.write_text(
        build_filter_graph(
            plan,
            scenes,
            render_duration,
            include_screen_audio,
            logo_input_index=len(plan.sources),
            lower_third_input_index=len(plan.sources) + 1,
            cta_input_index=len(plan.sources) + 2 if cta_available else None,
            pip_frame_input_index=pip_frame_input_index,
            three_panel_frame_input_index=three_panel_frame_input_index,
            speaker_lower_third_inputs=speaker_input_indices,
            speaker_animated=speaker_animated,
            apply_fade_in=apply_fade_in,
            apply_fade_out=apply_fade_out,
            cta_time_offset=cta_time_offset,
        ),
        encoding="utf-8",
    )

    command = ["ffmpeg", "-hide_banner", "-v", "error"]
    command.extend(_input_arguments(plan, render_duration, trim_start))
    command.extend(["-loop", "1", "-framerate", "30", "-i", str(resolved_logo)])
    first_frame = DEFAULT_LOWER_THIRD_FRAMES.parent / "frame_000001.png"
    lower_third_path = DEFAULT_EPISODE85_LOWER_THIRD_PATH if ("episode-85" in plan.episode.lower() or "episode_85" in plan.episode.lower()) else DEFAULT_LOWER_THIRD_PATH
    if lower_third_path.is_file():
        command.extend(["-stream_loop", "-1", "-i", str(lower_third_path)])
    elif first_frame.is_file():
        command.extend(
            ["-framerate", "30", "-start_number", "1", "-i", str(DEFAULT_LOWER_THIRD_FRAMES)]
        )
    else:
        lower_third_path = workdir / "lower-third.png"
        _create_lower_third_asset(lower_third_path)
        command.extend(["-loop", "1", "-framerate", "30", "-i", str(lower_third_path)])
    if cta_available:
        if DEFAULT_CTA_ALPHA_PATH.is_file():
            command.extend(["-stream_loop", "-1", "-i", str(DEFAULT_CTA_ALPHA_PATH)])
        else:
            command.extend(["-stream_loop", "-1", "-framerate", "30", "-start_number", "1", "-i", str(DEFAULT_CTA_FRAMES)])
    if pip_frame_available:
        if DEFAULT_PIP_FRAME_ALPHA_PATH.is_file():
            command.extend(["-stream_loop", "-1", "-i", str(DEFAULT_PIP_FRAME_ALPHA_PATH)])
        else:
            command.extend(["-stream_loop", "-1", "-framerate", "30", "-start_number", "1", "-i", str(DEFAULT_PIP_FRAME_FRAMES)])
    if three_panel_frame_available:
        if DEFAULT_THREE_PANEL_FRAME_ALPHA_PATH.is_file():
            command.extend(["-stream_loop", "-1", "-i", str(DEFAULT_THREE_PANEL_FRAME_ALPHA_PATH)])
        else:
            command.extend(["-stream_loop", "-1", "-framerate", "30", "-start_number", "1", "-i", str(DEFAULT_THREE_PANEL_FRAME_FRAMES)])
    for asset_path in speaker_assets.values():
        if asset_path.suffix.lower() == ".mov":
            command.extend(["-stream_loop", "-1", "-i", str(asset_path)])
        elif "%06d" in str(asset_path):
            command.extend(
                ["-loop", "1", "-framerate", "30", "-start_number", "1", "-i", str(asset_path)]
            )
        else:
            command.extend(["-loop", "1", "-framerate", "30", "-i", str(asset_path)])
    encode_options = ["-c:v", video_encoder]
    if video_encoder == "libx264":
        encode_options += ["-preset", preset, "-crf", "20"]
    else:
        # Apple VideoToolbox uses bitrate controls rather than x264's CRF.
        encode_options += ["-allow_sw", "1", "-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M"]
    command.extend(
        [
            "-filter_complex_script",
            str(filter_path),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            *encode_options,
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            "-y" if overwrite else "-n",
            str(output),
        ]
    )

    print(f"Rendering {render_duration:.1f}s across {len(scenes)} scenes to {output}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    last_percent = -5
    stderr = ""
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if line.startswith("out_time_ms="):
                raw_value = line.partition("=")[2].strip()
                if not raw_value.isdigit():
                    continue
                microseconds = int(raw_value)
                percent = min(100, int((microseconds / 1_000_000) / render_duration * 100))
                if percent >= last_percent + 5:
                    print(f"  FFmpeg progress: {percent}%")
                    last_percent = percent
        stderr = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
    except Exception:
        process.terminate()
        process.communicate()
        raise
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
    if return_code != 0:
        raise RuntimeError(f"FFmpeg render failed ({return_code}):\n{stderr[:2000]}\n...\n{stderr[-2000:]}")

    verification = probe_output(output)
    verify_output(verification, render_duration)
    if keep_workdir:
        print(f"Kept FFmpeg work directory: {workdir}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return verification


def render_plan_chunked(
    plan: EditPlan,
    output: Path,
    chunk_seconds: float = 300.0,
    preview_seconds: Optional[float] = None,
    include_screen_audio: bool = False,
    overwrite: bool = False,
    keep_workdir: bool = False,
    logo_path: Optional[Path] = None,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
    video_encoder: str = "libx264",
    preset: str = "ultrafast",
    coalesce_identical: bool = True,
) -> Dict[str, object]:
    """Render independent chunks, then join them without another video encode.

    Chunking keeps FFmpeg's filter graph bounded and makes long renders resumable.
    Every chunk uses the same dimensions, frame rate, codecs, and audio layout,
    allowing the final concat step to use stream copy.
    """
    if chunk_seconds <= 0:
        raise ValueError("Chunk duration must be greater than zero")
    if trim_start < 0 or trim_start >= plan.duration:
        raise ValueError("Trim start must be between 0 and the plan duration")
    if trim_end < 0 or trim_end >= plan.duration - trim_start:
        raise ValueError("Trim end must leave a positive render duration")
    total_available = plan.duration - trim_start - trim_end
    total = min(total_available, preview_seconds) if preview_seconds else total_available
    if total <= 0:
        raise ValueError("Render duration must be greater than zero")
    output = Path(output).resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists; pass --overwrite to replace it: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    chunk_dir = Path(tempfile.mkdtemp(prefix="long-form-chunks-", dir=str(output.parent))).resolve()
    chunk_paths: List[Path] = []
    try:
        offset = 0.0
        index = 0
        while offset < total - 0.001:
            length = min(chunk_seconds, total - offset)
            chunk_path = chunk_dir / f"chunk-{index:04d}.mp4"
            render_plan(
                plan,
                chunk_path,
                preview_seconds=length,
                include_screen_audio=include_screen_audio,
                overwrite=True,
                keep_workdir=keep_workdir,
                logo_path=logo_path,
                trim_start=trim_start + offset,
                # The chunk length already ends at the shortened final
                # timeline; applying trim_end again inside a chunk would
                # remove the tail twice.
                trim_end=0.0,
                video_encoder=video_encoder,
                preset=preset,
                apply_tail=(offset + length >= total - 0.001),
                coalesce_identical=coalesce_identical,
                apply_fade_in=(offset <= 0.001),
                apply_fade_out=(offset + length >= total - 0.001),
                cta_time_offset=offset,
            )
            chunk_paths.append(chunk_path)
            offset += length
            index += 1
        concat_list = chunk_dir / "concat.txt"
        concat_list.write_text("".join(f"file '{path.as_posix().replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n" for path in chunk_paths), encoding="utf-8")
        concat_command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c", "copy", "-movflags", "+faststart", "-y", str(output),
        ]
        subprocess.run(concat_command, check=True)
        verification = probe_output(output)
        verify_output(verification, total)
        print(f"Chunked render verified: {len(chunk_paths)} chunks -> {output}")
        return verification
    finally:
        if not keep_workdir:
            shutil.rmtree(chunk_dir, ignore_errors=True)
