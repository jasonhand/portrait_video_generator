"""Thumbnail generator for long-form episodes.

Builds a side-by-side screenshot from the episode's two webcam sources,
then layers the ai_tl_logo.png watermark and a HyperFrames-rendered
holographic title card on top, matching the styling already used for the
long-form lower-thirds/CTA overlays.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .renderer import DEFAULT_LOGO_PATH
from .sources import common_interval, discover_paths, probe_source

HYPERFRAMES_VERSION = "0.8.27"
THUMBNAIL_TITLE_PROJECT = Path(__file__).resolve().parent / "hyperframes" / "thumbnail-title"
THUMBNAIL_TITLE_SIDE_PROJECT = Path(__file__).resolve().parent / "hyperframes" / "thumbnail-title-side"
THUMBNAIL_TITLE_STACKED_PROJECT = Path(__file__).resolve().parent / "hyperframes" / "thumbnail-title-stacked"
THUMBNAIL_TITLE_DIAGONAL_PROJECT = Path(__file__).resolve().parent / "hyperframes" / "thumbnail-title-diagonal"

# Frame offset into the title-card render where the entrance animation has
# settled and the holographic edge is mid-cycle (matches the moment used to
# preview the lower-third's steady state).
TITLE_SETTLE_SECONDS = 2.5

CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
PANEL_WIDTH = CANVAS_WIDTH // 2

# ai_tl_logo.png is a large transparent canvas; crop to the artwork bounding
# box before scaling, matching the corner-logo overlay in renderer.py
# (`crop=1073:422:430:307`, scaled to 135px tall, 5px padding).
LOGO_CROP_BOX = (430, 307, 1503, 729)
LOGO_HEIGHT = 135
LOGO_MARGIN = 5

# Guest-solo layout: the guest's webcam fills the whole canvas, the title
# card sits low in the left column, and the logo is enlarged, raised toward
# the top of the open right column, and tilted beside their face.
GUEST_LOGO_HEIGHT = 220
GUEST_LOGO_MARGIN_RIGHT = 90
GUEST_LOGO_TOP = 50
GUEST_LOGO_ROTATION_DEGREES = -10  # negative = tilted clockwise (to the right)

# Guest-headshot layout (A/B alternative): a tighter crop on the guest's
# head/neck fills a panel on the right, set against a brand-gradient
# background, with the logo and title stacked in the open left column.
# Crop box is expressed as fractions of the source frame so it's resolution
# independent; top stays above the hairline so nothing above the neck is
# ever cut off, bottom extends past the chin into the neck/shoulders.
HEADSHOT_CROP_BOX_FRACTIONS = (0.259, 0.065, 0.694, 0.852)  # left, top, right, bottom
HEADSHOT_PANEL_LEFT = 860
HEADSHOT_FEATHER_WIDTH = 140

HEADSHOT_BG_COLOR_TOP_LEFT = (26, 31, 54)  # matches title-card background (#1a1f36)
HEADSHOT_BG_COLOR_BOTTOM_RIGHT = (52, 0, 141)  # matches title-card accent (#34008D)

HEADSHOT_LOGO_HEIGHT = 240
HEADSHOT_LOGO_LEFT = 100
HEADSHOT_LOGO_TOP = 70
HEADSHOT_LOGO_ROTATION_DEGREES = 10  # positive = tilted counter-clockwise (to the left)

# Guest-diagonal layout (A/B alternative): the guest's full-frame webcam
# fills the whole canvas, and a diagonal ribbon banner cuts across the right
# side holding the title, with the logo badged near the top of the ribbon.
# The ribbon's slanted edge stays clear of the x-range the guest's face
# occupies in a centered webcam frame; only background/shoulders sit under it.
DIAGONAL_LOGO_HEIGHT = 160
DIAGONAL_LOGO_LEFT = 1400
DIAGONAL_LOGO_TOP = 420
DIAGONAL_LOGO_ROTATION_DEGREES = 0  # straight, no tilt


def _fill_crop(
    image,
    target_width: int,
    target_height: int,
    x_bias: float = 0.5,
    zoom: float = 1.0,
):
    """Scale `image` to fill target_width x target_height, cropping the overflow.

    `zoom` scales beyond the minimum cover-fit to zoom in further, and
    `x_bias` (0=favor left edge, 0.5=center, 1=favor right edge) picks where
    within the horizontal overflow the crop window sits. Defaults reproduce
    the original center-crop behavior.
    """
    from PIL import Image

    scale = max(target_width / image.width, target_height / image.height) * zoom
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    max_left = resized.width - target_width
    max_top = resized.height - target_height
    left = max(0, min(round(max_left * x_bias), max_left))
    top = max(0, min(round(max_top * 0.5), max_top))
    return resized.crop((left, top, left + target_width, top + target_height))


def _diagonal_gradient(width: int, height: int, color_top_left, color_bottom_right):
    """Render a top-left-to-bottom-right linear gradient as an RGB PIL image."""
    import numpy as np
    from PIL import Image

    x_ramp = np.linspace(0.0, 1.0, width)
    y_ramp = np.linspace(0.0, 1.0, height)
    mix = np.clip((x_ramp[None, :] + y_ramp[:, None]) / 2.0, 0.0, 1.0)[..., None]
    start = np.array(color_top_left, dtype=np.float64)
    end = np.array(color_bottom_right, dtype=np.float64)
    pixels = (start * (1.0 - mix) + end * mix).astype("uint8")
    return Image.fromarray(pixels, "RGB")


def capture_frame(video_path: Path, at_seconds: Optional[float] = None):
    """Grab a single frame from a video as an RGBA PIL image."""
    from PIL import Image
    from moviepy import VideoFileClip

    with VideoFileClip(str(video_path)) as clip:
        timestamp = clip.duration / 2 if at_seconds is None else at_seconds
        timestamp = min(max(timestamp, 0.0), max(clip.duration - 0.1, 0.0))
        frame = clip.get_frame(timestamp)

    return Image.fromarray(frame).convert("RGBA")


def _discover_webcam_sources(input_dir: Path, episode: str):
    """Find the episode's webcam MP4s, ignoring screen-share files entirely."""
    paths = discover_paths(Path(input_dir), episode)
    webcam_paths = [path for path in paths if "webcam" in path.stem.lower()]
    if len(webcam_paths) < 2:
        raise ValueError(
            f"Need at least 2 webcam sources for a split-screen thumbnail, found "
            f"{len(webcam_paths)} in {input_dir} for episode '{episode}'"
        )
    return [probe_source(path) for path in webcam_paths[:2]]


def capture_split_screen(
    input_dir: Path,
    episode: str,
    at_seconds: Optional[float] = None,
):
    """Build a side-by-side screenshot from the episode's two webcam sources."""
    from PIL import Image

    webcams = _discover_webcam_sources(input_dir, episode)

    common_start, duration = common_interval(webcams)
    offset_seconds = duration / 2 if at_seconds is None else at_seconds
    offset_seconds = min(max(offset_seconds, 0.0), max(duration - 0.1, 0.0))
    absolute_time = common_start + offset_seconds

    canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT))
    for index, source in enumerate(webcams):
        local_time = absolute_time - source.offset
        frame = capture_frame(Path(source.path), local_time)
        panel = _fill_crop(frame, PANEL_WIDTH, CANVAS_HEIGHT)
        canvas.alpha_composite(panel, (index * PANEL_WIDTH, 0))
    return canvas


def _discover_guest_source(input_dir: Path, episode: str, guest_name: str):
    """Find the episode's webcam MP4 belonging to the named guest."""
    paths = discover_paths(Path(input_dir), episode)
    webcam_paths = [
        path
        for path in paths
        if "webcam" in path.stem.lower() and guest_name.lower() in path.stem.lower()
    ]
    if len(webcam_paths) != 1:
        raise ValueError(
            f"Expected exactly one webcam source matching guest '{guest_name}', found "
            f"{len(webcam_paths)} in {input_dir} for episode '{episode}'"
        )
    return probe_source(webcam_paths[0])


def capture_guest_frame(
    input_dir: Path,
    episode: str,
    guest_name: str,
    at_seconds: float,
    x_bias: float = 0.5,
    zoom: float = 1.0,
):
    """Grab a single full-frame screenshot from the named guest's webcam source.

    `x_bias`/`zoom` let a layout pull the subject away from center (e.g. so a
    diagonal ribbon on the right doesn't crowd the guest's face) without
    affecting layouts that use the default centered framing.
    """
    source = _discover_guest_source(input_dir, episode, guest_name)
    frame = capture_frame(Path(source.path), at_seconds)
    return _fill_crop(frame, CANVAS_WIDTH, CANVAS_HEIGHT, x_bias=x_bias, zoom=zoom)


def capture_guest_headshot(
    input_dir: Path,
    episode: str,
    guest_name: str,
    at_seconds: float,
    x_shift: float = 0.0,
    zoom: float = 1.0,
):
    """Grab a tight head/neck crop from the named guest's webcam source.

    The crop box never moves its top edge below the hairline, so the head is
    never cut off; it's free to extend past the chin into the neck/shoulders.

    `x_shift` nudges the crop box's horizontal center (as a fraction of frame
    width, positive = right) to recenter on a guest who doesn't sit dead
    center in their own webcam frame; `zoom` narrows the box to zoom in
    further. Defaults reproduce the original fixed crop box.
    """
    source = _discover_guest_source(input_dir, episode, guest_name)
    frame = capture_frame(Path(source.path), at_seconds)

    left_frac, top_frac, right_frac, bottom_frac = HEADSHOT_CROP_BOX_FRACTIONS
    width_frac = (right_frac - left_frac) / zoom
    center_frac = (left_frac + right_frac) / 2 + x_shift
    left_frac = center_frac - width_frac / 2
    right_frac = center_frac + width_frac / 2

    box = (
        round(frame.width * left_frac),
        round(frame.height * top_frac),
        round(frame.width * right_frac),
        round(frame.height * bottom_frac),
    )
    return frame.crop(box)


def render_holographic_title(
    title_text: str,
    workdir: Path,
    project: Path = THUMBNAIL_TITLE_PROJECT,
) -> Path:
    """Render the holographic title composition and extract one settled frame."""
    mov_path = workdir / "thumbnail-title.mov"
    subprocess.run(
        [
            "npx",
            "--yes",
            f"hyperframes@{HYPERFRAMES_VERSION}",
            "render",
            str(project),
            "--format",
            "mov",
            "--quality",
            "high",
            "--variables",
            json.dumps({"title": title_text}),
            "--output",
            str(mov_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    frame_path = workdir / "thumbnail-title.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(TITLE_SETTLE_SECONDS),
            "-i",
            str(mov_path),
            "-update",
            "1",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            str(frame_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return frame_path


def compose_thumbnail(
    screenshot,
    title_frame_path: Path,
    output_path: Path,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    """Composite the split-screen screenshot, holographic title, and logo into one PNG."""
    from PIL import Image

    canvas = screenshot.convert("RGBA")

    title_frame = Image.open(title_frame_path).convert("RGBA")
    canvas.alpha_composite(title_frame, (0, 0))

    if logo_path.is_file():
        logo = Image.open(logo_path).convert("RGBA").crop(LOGO_CROP_BOX)
        scale = LOGO_HEIGHT / logo.height
        logo = logo.resize((round(logo.width * scale), LOGO_HEIGHT), Image.Resampling.LANCZOS)
        x = canvas.width - logo.width - LOGO_MARGIN
        canvas.alpha_composite(logo, (x, LOGO_MARGIN))

    canvas.convert("RGB").save(output_path, "PNG")


def generate_thumbnail(
    input_dir: Path,
    episode: str,
    title_text: str,
    output_path: Path,
    at_seconds: Optional[float] = None,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    screenshot = capture_split_screen(input_dir, episode, at_seconds)
    with tempfile.TemporaryDirectory(prefix="thumbnail-title-") as workdir:
        title_frame_path = render_holographic_title(title_text, Path(workdir))
        compose_thumbnail(screenshot, title_frame_path, output_path, logo_path)


def compose_guest_thumbnail(
    screenshot,
    title_frame_path: Path,
    output_path: Path,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    """Composite the guest's full-frame screenshot, side title card, and logo into one PNG."""
    from PIL import Image

    canvas = screenshot.convert("RGBA")

    title_frame = Image.open(title_frame_path).convert("RGBA")
    canvas.alpha_composite(title_frame, (0, 0))

    if logo_path.is_file():
        logo = Image.open(logo_path).convert("RGBA").crop(LOGO_CROP_BOX)
        scale = GUEST_LOGO_HEIGHT / logo.height
        logo = logo.resize((round(logo.width * scale), GUEST_LOGO_HEIGHT), Image.Resampling.LANCZOS)
        logo = logo.rotate(GUEST_LOGO_ROTATION_DEGREES, resample=Image.BICUBIC, expand=True)
        x = canvas.width - logo.width - GUEST_LOGO_MARGIN_RIGHT
        y = GUEST_LOGO_TOP
        canvas.alpha_composite(logo, (x, y))

    canvas.convert("RGB").save(output_path, "PNG")


def generate_guest_thumbnail(
    input_dir: Path,
    episode: str,
    guest_name: str,
    title_text: str,
    output_path: Path,
    at_seconds: float,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    """Build a single-guest thumbnail: full-frame webcam, side title card, side logo."""
    screenshot = capture_guest_frame(input_dir, episode, guest_name, at_seconds)
    with tempfile.TemporaryDirectory(prefix="thumbnail-title-side-") as workdir:
        title_frame_path = render_holographic_title(
            title_text, Path(workdir), project=THUMBNAIL_TITLE_SIDE_PROJECT
        )
        compose_guest_thumbnail(screenshot, title_frame_path, output_path, logo_path)


def compose_guest_headshot_thumbnail(
    headshot,
    title_frame_path: Path,
    output_path: Path,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    """Composite the zoomed headshot (right), title card, and logo (stacked left) into one PNG."""
    from PIL import Image

    canvas = _diagonal_gradient(
        CANVAS_WIDTH, CANVAS_HEIGHT, HEADSHOT_BG_COLOR_TOP_LEFT, HEADSHOT_BG_COLOR_BOTTOM_RIGHT
    ).convert("RGBA")

    panel_width = CANVAS_WIDTH - HEADSHOT_PANEL_LEFT
    panel = _fill_crop(headshot.convert("RGBA"), panel_width, CANVAS_HEIGHT)

    # Feather the panel's left edge into the background gradient so the crop
    # doesn't read as a pasted rectangle.
    alpha = panel.getchannel("A")
    import numpy as np

    alpha_array = np.array(alpha, dtype=np.float64)
    feather = np.clip(np.arange(panel_width) / HEADSHOT_FEATHER_WIDTH, 0.0, 1.0)
    alpha_array *= feather[None, :]
    panel.putalpha(Image.fromarray(alpha_array.astype("uint8"), "L"))
    canvas.alpha_composite(panel, (HEADSHOT_PANEL_LEFT, 0))

    if logo_path.is_file():
        logo = Image.open(logo_path).convert("RGBA").crop(LOGO_CROP_BOX)
        scale = HEADSHOT_LOGO_HEIGHT / logo.height
        logo = logo.resize((round(logo.width * scale), HEADSHOT_LOGO_HEIGHT), Image.Resampling.LANCZOS)
        logo = logo.rotate(HEADSHOT_LOGO_ROTATION_DEGREES, resample=Image.BICUBIC, expand=True)
        canvas.alpha_composite(logo, (HEADSHOT_LOGO_LEFT, HEADSHOT_LOGO_TOP))

    title_frame = Image.open(title_frame_path).convert("RGBA")
    canvas.alpha_composite(title_frame, (0, 0))

    canvas.convert("RGB").save(output_path, "PNG")


def generate_guest_headshot_thumbnail(
    input_dir: Path,
    episode: str,
    guest_name: str,
    title_text: str,
    output_path: Path,
    at_seconds: float,
    logo_path: Path = DEFAULT_LOGO_PATH,
    x_shift: float = 0.0,
    zoom: float = 1.0,
) -> None:
    """Build the A/B alternative: zoomed headshot on the right, title/logo stacked on the left."""
    headshot = capture_guest_headshot(
        input_dir, episode, guest_name, at_seconds, x_shift=x_shift, zoom=zoom
    )
    with tempfile.TemporaryDirectory(prefix="thumbnail-title-stacked-") as workdir:
        title_frame_path = render_holographic_title(
            title_text, Path(workdir), project=THUMBNAIL_TITLE_STACKED_PROJECT
        )
        compose_guest_headshot_thumbnail(headshot, title_frame_path, output_path, logo_path)


def compose_guest_diagonal_thumbnail(
    screenshot,
    title_frame_path: Path,
    output_path: Path,
    logo_path: Path = DEFAULT_LOGO_PATH,
) -> None:
    """Composite the guest's full-frame screenshot, diagonal ribbon title, and badged logo."""
    from PIL import Image

    canvas = screenshot.convert("RGBA")

    title_frame = Image.open(title_frame_path).convert("RGBA")
    canvas.alpha_composite(title_frame, (0, 0))

    if logo_path.is_file():
        logo = Image.open(logo_path).convert("RGBA").crop(LOGO_CROP_BOX)
        scale = DIAGONAL_LOGO_HEIGHT / logo.height
        logo = logo.resize((round(logo.width * scale), DIAGONAL_LOGO_HEIGHT), Image.Resampling.LANCZOS)
        logo = logo.rotate(DIAGONAL_LOGO_ROTATION_DEGREES, resample=Image.BICUBIC, expand=True)
        canvas.alpha_composite(logo, (DIAGONAL_LOGO_LEFT, DIAGONAL_LOGO_TOP))

    canvas.convert("RGB").save(output_path, "PNG")


def generate_guest_diagonal_thumbnail(
    input_dir: Path,
    episode: str,
    guest_name: str,
    title_text: str,
    output_path: Path,
    at_seconds: float,
    logo_path: Path = DEFAULT_LOGO_PATH,
    x_bias: float = 0.5,
    zoom: float = 1.0,
) -> None:
    """Build the second A/B alternative: full-frame webcam with a diagonal ribbon title banner."""
    screenshot = capture_guest_frame(
        input_dir, episode, guest_name, at_seconds, x_bias=x_bias, zoom=zoom
    )
    with tempfile.TemporaryDirectory(prefix="thumbnail-title-diagonal-") as workdir:
        title_frame_path = render_holographic_title(
            title_text, Path(workdir), project=THUMBNAIL_TITLE_DIAGONAL_PROJECT
        )
        compose_guest_diagonal_thumbnail(screenshot, title_frame_path, output_path, logo_path)


def thumbnail_command(args: argparse.Namespace) -> int:
    generate_thumbnail(
        input_dir=args.input_dir,
        episode=args.episode,
        title_text=args.title,
        output_path=args.output,
        at_seconds=args.at,
    )
    print("\nThumbnail generated")
    print(f"  Output: {args.output}")
    print(f"  Size: {args.output.stat().st_size / 1024:.1f} KiB")
    return 0


def guest_thumbnail_command(args: argparse.Namespace) -> int:
    generate_guest_thumbnail(
        input_dir=args.input_dir,
        episode=args.episode,
        guest_name=args.guest,
        title_text=args.title,
        output_path=args.output,
        at_seconds=args.at,
    )
    print("\nGuest thumbnail generated")
    print(f"  Output: {args.output}")
    print(f"  Size: {args.output.stat().st_size / 1024:.1f} KiB")
    return 0


def guest_headshot_thumbnail_command(args: argparse.Namespace) -> int:
    generate_guest_headshot_thumbnail(
        input_dir=args.input_dir,
        episode=args.episode,
        guest_name=args.guest,
        title_text=args.title,
        output_path=args.output,
        at_seconds=args.at,
        x_shift=args.x_shift,
        zoom=args.zoom,
    )
    print("\nGuest headshot thumbnail generated")
    print(f"  Output: {args.output}")
    print(f"  Size: {args.output.stat().st_size / 1024:.1f} KiB")
    return 0


def guest_diagonal_thumbnail_command(args: argparse.Namespace) -> int:
    generate_guest_diagonal_thumbnail(
        input_dir=args.input_dir,
        episode=args.episode,
        guest_name=args.guest,
        title_text=args.title,
        output_path=args.output,
        at_seconds=args.at,
        x_bias=args.x_bias,
        zoom=args.zoom,
    )
    print("\nGuest diagonal thumbnail generated")
    print(f"  Output: {args.output}")
    print(f"  Size: {args.output.stat().st_size / 1024:.1f} KiB")
    return 0
