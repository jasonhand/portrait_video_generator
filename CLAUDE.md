# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Project overview

**CAIVE** (Claude AI Video Editor) turns raw multi-camera recordings into finished video. The primary interface is conversation: a user describes the edit they want, and Claude analyzes footage, proposes a plan, renders a preview for approval, and produces the final file.

Two independent pipelines:

| Pipeline | Module | Output |
|---|---|---|
| **Shorts** | `stacked_script/stack.py` | 1080x1920 portrait (9:16) with burned-in captions |
| **Long-form** | `long_form/` | 1920x1080 landscape (16:9) with HyperFrames overlays, no captions |

**These two must stay separate.** `long_form/` never imports from `stacked_script.stack`, and long-form work must not modify the Shorts rendering paths. Both `.claude/skills/` files state this guardrail explicitly. If a change appears to require coupling them, stop and ask.

## Working conversationally

Users drive CAIVE by talking, not by memorizing flags. When someone describes an edit:

1. **Don't ask for the flags** — ask for the episode name, then infer the rest. Source discovery, sync, and layout selection are automatic.
2. **Report the plan before rendering.** After `analyze`, state the matched screen/webcam files, the common duration, the seed, and the scene-type counts. Let the user react to that before spending render time.
3. **Preview before full renders.** A full episode takes 15+ minutes. Render 120 seconds first and get explicit approval. `/generate-long-form` enforces this gate; honor it in conversational flows too.
4. **Never `--overwrite` without explicit permission.** Renders are expensive and outputs are hard to reproduce.
5. **Never claim success without probing the output.** Run `ffprobe` and check resolution, codecs, and duration. `long_form/STATUS.md` records multiple cases where a render looked complete and was not.
6. **Verify caption and overlay changes visually.** Generate a layout preview or a short render and actually look at it before reporting that positioning is fixed.

Two packaged skills live in `.claude/skills/`, both marked `disable-model-invocation: true` — they are slash-command only and must not be auto-triggered:

- `/generate-long-form <episode>` — analyze → preview → approval gate → full render
- `/generate-thumbnail <episode> <title>` — 1920x1080 thumbnail PNG

The `vtt-clip-finder` agent in `.claude/agents/` handles transcript analysis for Shorts.

## Technology stack

- **Python 3.8+**
- `moviepy>=2.0.0` — Shorts video processing, frame capture
- `pillow>=9.2.0,<12.0` — preview and thumbnail composition
- `numpy` — audio RMS and screen-diff analysis (arrives transitively via moviepy; not declared)
- `streamlit>=1.28.0` — legacy UI only
- **FFmpeg / ffprobe** — required on `PATH`; both pipelines shell out constantly
- **Node.js / `npx`** — thumbnail titles and HyperFrames authoring, pinned to `hyperframes@0.8.27`
- Dev: `pytest>=8.0.0`, `playwright>=1.40.0`

## Development setup

```bash
pip install -r requirements.txt        # runtime
pip install -r requirements-dev.txt    # + pytest, playwright
playwright install chromium            # visual regression tests only
```

Assets are gitignored and must exist locally: `logos/logo.png` (Shorts), `logos/ai_tl_logo.png` (long-form), plus `source_video/` and `transcripts/` contents.

## File structure

```
portrait_video_generator/
├── README.md                      # User-facing docs, Claude-first
├── CLAUDE.md                      # This file
├── AGENTS.md                      # Agent-neutral copy of this file
├── requirements.txt
├── requirements-dev.txt
│
├── .claude/
│   ├── agents/vtt-clip-finder.md
│   ├── skills/generate-long-form/SKILL.md
│   ├── skills/generate-thumbnail/SKILL.md
│   └── settings.local.json        # Permission allow-list
│
├── stacked_script/stack.py        # Shorts engine
├── create_clips_from_analysis.py  # Batch clip renderer
├── utils/burn_subs.py             # Standalone subtitle burner
├── pvg.py                         # Legacy Streamlit UI (Shorts only)
├── .streamlit/config.toml
│
├── long_form/
│   ├── __init__.py                # Re-exports EditPlan, Scene, SourceInfo
│   ├── __main__.py                # python -m long_form
│   ├── cli.py                     # Subcommands + plan validation
│   ├── sources.py                 # Discovery, StreamYard offsets, sync
│   ├── analysis.py                # Audio RMS + screen activity
│   ├── scheduler.py               # Scene boundaries + layout choice
│   ├── models.py                  # Dataclasses + plan serialization
│   ├── renderer.py                # Filtergraph, overlays, chunked render
│   ├── thumbnail.py               # Four thumbnail layouts
│   ├── hyperframes/               # Overlay compositions + built assets
│   └── STATUS.md                  # Render log / continuation notes
│
├── tests/
│   ├── long_form_test.py          # unittest, 5 tests
│   ├── hyperframes_visual_test.py # pytest + playwright, 3 tests
│   └── hyperframes_baselines/     # 3 reference PNGs
│
├── logos/            # gitignored
├── transcripts/      # gitignored
├── source_video/     # gitignored
└── output/           # gitignored
```

---

# Long-form editor architecture

Two stages with a reviewable JSON edit plan between them. **The plan is the source of truth** — previews and final renders come from the same file, so what the user approves is what they get. Never render from anything but a plan on disk.

Invoked as `python -m long_form.cli <subcommand>` (or `python -m long_form`).

## `sources.py` — discovery and synchronization

- `OFFSET_PATTERN` matches `(\d+)h_(\d+)m_(\d+)s_(\d+)ms` in the filename stem; `parse_streamyard_offset()` returns 0.0 when absent.
- `probe_source()` runs `ffprobe` and builds a `SourceInfo`. **Role assignment is filename-based**: `kind = "screen" if "screen" in path.name.lower() else "webcam"`. There are only two kinds.
- `discover_paths()` globs `*.mp4` then `*.MP4`, keeps stems containing the episode string case-insensitively, and falls back to matching the first digit run in the episode name.
- `discover_sources(input_dir, episode, screen_override=None)` requires **exactly one** screen source and at least one webcam. With `--screen`, the override must be one of the matched files and becomes the screen; everything else becomes a webcam.
- `common_interval()` returns `common_start = max(offset)` and duration to `min(offset + duration)`; raises if the recordings don't overlap.

## `analysis.py` — signal-level analysis

No transcripts, no speech-to-text. Pure signal processing via `ffmpeg` + `numpy`.

`analyze_sources()` returns an `AnalysisResult` with `audio_interval=0.5`, `audio_levels` keyed by source name, `screen_interval=1.0`, `screen_scores`, `screen_active`, `screen_present`.

**`analyze_audio(source, common_start, duration, interval=0.5, sample_rate=8000)`** decodes mono `f32le` PCM at 8 kHz from `_local_start = max(0.0, common_start - source.offset)` and returns **raw RMS** per window. Levels are deliberately **not** normalized per track — normalizing would make a quiet camera look as loud as the active speaker and break speaker detection. Returns zeros when `has_audio` is false.

**`analyze_screen(source, common_start, duration, interval=1.0, hold_seconds=20)`** decodes 320x180 gray frames at 1 fps with `setpts=PTS-STARTPTS,fps=1,scale=320:180,format=gray`.

- `present[i] = mean(frame) > 5.0` — rejects black filler while accepting dark application UIs
- `scores[i] = mean(abs(frame - previous))`, first sample 0.0
- Adaptive activity threshold: `max(median + 2.0*mad, percentile65, 0.75)`
- Each above-threshold sample holds `active` True for the next `hold_seconds/interval` = 20 samples, so a slide that goes static after a transition still counts as live

## `models.py` — data model

Three dataclasses, JSON-serializable via `dataclasses.asdict`.

```python
@dataclass(frozen=True)
class SourceInfo:
    path: str; name: str; kind: str; offset: float; duration: float
    width: int; height: int; fps: float; has_audio: bool

@dataclass(frozen=True)
class Scene:
    start: float; end: float; source: str; scene_type: str
    zoom: float = 1.0
    pip_source: Optional[str] = None
    pip_position: Optional[str] = None
    secondary_source: Optional[str] = None
    # property: duration == end - start

@dataclass
class EditPlan:
    version: int; episode: str; seed: int
    common_start: float; duration: float
    sources: List[SourceInfo]; scenes: List[Scene]
    settings: Dict[str, Any] = field(default_factory=dict)
    # to_dict(), save(path), load(path), source_by_name(name)
```

Plan JSON (abridged):

```json
{
  "version": 1,
  "episode": "Episode-85",
  "seed": 2446315577,
  "common_start": 1.374,
  "duration": 1169.133,
  "sources": [
    { "path": "...", "name": "Episode-85-Ryan-webcam-...mp4", "kind": "webcam",
      "offset": 1.313, "duration": 1169.233, "width": 3840, "height": 2160,
      "fps": 30.0, "has_audio": true }
  ],
  "scenes": [
    { "start": 0.0, "end": 5.5, "source": "...webcam...mp4",
      "scene_type": "webcam_full", "zoom": 1.0,
      "pip_source": null, "pip_position": null, "secondary_source": null }
  ],
  "settings": { "canvas": { "width": 1920, "height": 1080, "fps": 30 }, "...": "..." }
}
```

All eight `Scene` fields are always written, nulls explicit. `settings` is a free-form record of the scheduler constants used, written for provenance — the renderer does not read it.

For `three_panel` scenes: `source` = speaking webcam, `secondary_source` = the other webcam, `pip_source` = the screen source name.

## `scheduler.py` — scene boundaries and layout

Entry point: `build_edit_plan(episode, sources, common_start, duration, analysis, seed) -> EditPlan`. All randomness comes from `random.Random(seed)`, so **plans are fully deterministic** — the same inputs and seed produce byte-identical JSON. A test asserts this; don't introduce unseeded randomness.

**Note:** this module schedules scenes only. Lower thirds and CTA toasts are scheduled in `renderer.py`, which is surprising and worth remembering.

### Constants

```
MIN_SCENE_SECONDS = 5.0          TARGET_SCENE_MIN/MAX = 5.0 / 5.0
PAUSE_SNAP_SECONDS = 0.5         AUDIO_ACTIVITY_THRESHOLD = 0.02
ZOOM_PROBABILITY = 0.10          DUAL_WEBCAM_PROBABILITY = 0.10
THREE_PANEL_PROBABILITY = 0.15
SCREEN_RUN_MIN_SECONDS = 20.0    SCREEN_RUN_TARGET_MAX_SECONDS = 26.0
SCREEN_RUN_START_PROBABILITY = 0.42
SCREEN_RUN_COOLDOWN_SECONDS = 8.0
SCREEN_EDGE_GUARD_SECONDS = 60.0
SCREEN_INACTIVE_START_PROBABILITY = 0.45
```

`SCREEN_RUN_TARGET_MAX_SECONDS` is 26.0, not 30.0, specifically so a completed run never exceeds 30 s after 0.5 s pause snapping. A test asserts runs fall in [20, 30]; changing one number without the other breaks it.

### Timing

`_build_intervals()` steps forward by `rng.uniform(TARGET_SCENE_MIN, TARGET_SCENE_MAX)` (currently always exactly 5.0 s), then `_snap_to_pause()` moves each boundary up to ±0.5 s onto the 0.5 s audio grid, choosing the candidate with the lowest mixed audio level (tie-break: closest to proposed). Cuts land in pauses rather than mid-word. The loop stops early rather than leaving a final scene under 5 s; the last interval ends exactly at `duration`.

### Speaker selection

`_speaker_for_scene()` averages each webcam's RMS over the interval and takes the loudest — **unless** its mean is `<= 0.02`, in which case the previous speaker is held. This prevents thrashing during silence.

### Layout selection

Screen runs require `_screen_is_active` (any active sample in the interval), at least 20 s of episode remaining, and 60 s of clearance from both edges (only enforced when `duration >= 2*60 + 20`). The first screen appearance is unconditional given those; later ones need `rng.random() < 0.42`. If activity detection is inconclusive but content is present, a second chance uses `< 0.45`. An 8 s cooldown follows each run, and a run ends immediately if the interval loses screen content.

`_screen_has_content()` requires **every** sampled `screen_present` frame in the interval to be true, and suppresses screen layouts until 10 s (`2 * MIN_SCENE_SECONDS`) after the first content frame.

Webcam variants, in priority order: `three_panel` (≥2 webcams, screen content, away from edges, `< 0.15`) → `webcam_pair` (≥2 webcams, `< 0.10`) → `webcam_zoom` (same speaker continues, previous scene not zoomed, `< 0.10`, `zoom = round(rng.uniform(1.05, 1.15), 4)`) → `webcam_full`.

`_ensure_source_coverage()` forces any webcam that never appears to replace one webcam scene starting before 120.0 s.

### Hard-coded episode rules

These are not configurable and will confuse anyone debugging a different episode:

- Sources named `*screen-composite*`: screen content suppressed for `start < 210.0`, plus a post-pass rewriting any `screen_pip` / `screen_full` / `three_panel` scene before 210.0 s into `webcam_full`.
- Episode name containing `episode-85` / `episode_85`: screen preferred aggressively whenever content exists; and with both a `ryan` and `stephen` webcam and `duration >= 1158.0`, scenes split at 1158.0 s, the 1153.0–1158.0 s scene is forced to Ryan `webcam_full`, and everything from 1158.0 s on is forced to `webcam_pair`.

If asked to generalize these, treat it as a real refactor: lift them into `EditPlan.settings` or CLI flags rather than adding more name matches.

## `cli.py` — subcommands and validation

Parser: "Analyze and render an experimental 16:9 long-form edit". Subparsers use `dest="command", required=True`, each setting `handler` via `set_defaults`.

### `analyze`

`--input-dir` (required), `--episode` (required), `--plan` (required), `--seed` (defaults to `zlib.crc32(episode.encode()) & 0xFFFFFFFF`), `--screen` (optional override).

### `render`

| Flag | Default |
|---|---|
| `--plan`, `--output` | required |
| `--preview-seconds` | `None` (full length) |
| `--trim-start`, `--trim-end` | `0.0` |
| `--chunk-seconds` | `300.0` (`0` = one pass) |
| `--video-encoder` | `libx264` \| `h264_videotoolbox` |
| `--preset` | `ultrafast` (`ultrafast`…`medium`) |
| `--no-coalesce` | off → `coalesce_identical=not args.no_coalesce` |
| `--include-screen-audio` | off |
| `--logo` | `DEFAULT_LOGO_PATH` = `logos/ai_tl_logo.png` |
| `--overwrite`, `--keep-workdir` | off |

**Known inconsistency:** the CLI defaults `--preset` to `ultrafast`, `render_plan()`'s signature to `veryfast`, and `render_plan_chunked()`'s to `ultrafast`. For deliverables, pass `--preset veryfast` explicitly — at CRF 20 it yields a much smaller file for modest extra time. Worth unifying, but don't change a default silently.

### Thumbnail subcommands

`thumbnail` (`--at` optional, defaults to the midpoint of the overlap window), `guest-thumbnail`, `guest-headshot-thumbnail` (`--x-shift`, `--zoom`), `guest-diagonal-thumbnail` (`--x-bias`, `--zoom`). The three guest variants **require** `--at`.

### `validate_plan(plan)`

Enforces `version == 1`, non-empty scenes, contiguity (each scene starts within 0.01 s of the previous end), positive durations, every `source`/`pip_source`/`secondary_source` present in `plan.sources`, `duration >= MIN_SCENE_SECONDS` except the final scene, and `cursor == plan.duration` within 0.01 s. Carries a hard-coded Episode-85 exception permitting one short scene in the 1154.0–1158.0 s window.

`main()` catches `FileNotFoundError, FileExistsError, ValueError, RuntimeError, subprocess.CalledProcessError` and returns 1.

## `renderer.py` — the render pipeline

### Public API

```python
render_plan(plan, output, preview_seconds=None, include_screen_audio=False,
            overwrite=False, keep_workdir=False, logo_path=None,
            trim_start=0.0, trim_end=0.0, video_encoder="libx264",
            preset="veryfast", apply_tail=True, coalesce_identical=True,
            apply_fade_in=True, apply_fade_out=True,
            cta_time_offset=0.0) -> Dict[str, object]

render_plan_chunked(plan, output, chunk_seconds=300.0, preview_seconds=None,
                    include_screen_audio=False, overwrite=False,
                    keep_workdir=False, logo_path=None, trim_start=0.0,
                    trim_end=0.0, video_encoder="libx264",
                    preset="ultrafast", coalesce_identical=True) -> Dict[str, object]
```

### Asset constants

```
DEFAULT_LOGO_PATH                    = <repo>/logos/ai_tl_logo.png
DEFAULT_LOWER_THIRD_PATH             = long_form/hyperframes/lower-third/lower-third-alpha.mov
DEFAULT_EPISODE85_LOWER_THIRD_PATH   = long_form/hyperframes/episode85-lower-third/lower-third-alpha.mov
DEFAULT_SPEAKER_FRAME_ROOT           = long_form/hyperframes/lower-third
DEFAULT_EPISODE85_SPEAKER_FRAME_ROOT = long_form/hyperframes/episode85-speaker-lower-thirds
DEFAULT_CTA_ALPHA_PATH               = long_form/hyperframes/cta/cta-alpha.mov
DEFAULT_PIP_FRAME_ALPHA_PATH         = long_form/hyperframes/pip-frame/pip-frame-alpha.mov
DEFAULT_THREE_PANEL_FRAME_ALPHA_PATH = long_form/hyperframes/three-panel-frame/three-panel-frame-alpha.mov
CTA_STARTS_SECONDS                   = (420.0, 840.0, 1260.0)
LOWER_THIRD_SECONDS                  = 9.1
```

Each `.mov` has a `.hf-frames/frame_%06d.png` counterpart used as fallback.

### Filtergraph construction

`build_filter_graph(...)` returns a `;\n`-joined filter script, written to `filter-complex.txt` and passed via `-filter_complex_script` — it's far too long for a command line.

`_VideoLabels` counts how many times each source is used as `source` / `pip_source` / `secondary_source`, emits one `split=N` per input, and hands out `src_<inputIndex>_<n>` labels via `take()`. Each source is decoded exactly once.

Per-scene filters all normalize with `trim=start:end`, `setpts=PTS-STARTPTS`, `setsar=1`, and end in `[scene_<i>]`:

- `_webcam_filter` — scale by `zoom` to even dimensions (`1920*zoom`, `1080*zoom`) with `force_original_aspect_ratio=increase`, then `crop=1920:1080`
- `_screen_filter` — `scale=1920:1080:force_original_aspect_ratio=decrease` then centered `pad` with `color=0x111111`
- `webcam_pair` — two `_rounded_panel_filter` 960x1080 panels (28px rounded corners via a `geq` alpha mask), `hstack`ed
- `three_panel` — `_stacked_camera_filter` builds a 448px-wide `color=0xA960FF` canvas with two 440x520 rounded tiles at y=8 and y=552; `_screen_panel_filter` letterboxes the screen into 1472x1080; a `drawtext` adds `View more episodes at dtdg.co/aitl` (Inter regular, 56pt, `y=h-78`, `borderw=1:bordercolor=0x34008D`). **The animated three-panel frame must be overlaid onto the left column before the `hstack`** — referencing `three_left_*` before `_stacked_camera_filter()` defines it produced a misleading "matches no streams" error that appeared to implicate the speaker lower thirds. Don't reorder this.
- `screen_pip` — screen base, a 300x300 webcam PiP with 24px rounded corners, optional animated `pip-frame` overlay at `x=0:y=0`, then PiP overlay at `x=W-w-32:y=32`

All scene outputs join with `concat=n=<N>:v=1:a=0`.

**Logo**: input is `split=2`, both branches `crop=1073:422:430:307,scale=-1:135,format=rgba`. Upper-right at `x=W-w-5:y=5` when *not* in a `screen_pip` interval; lower-right at `x=W-w-5:y=H-h-5` exactly during `screen_pip` intervals, via `between(t,...)` terms summed with `+`.

**Fades** are attached to the opening lower-third filter chain: `fade=t=in:st=0:d=1` when `apply_fade_in`, `fade=t=out:st=max(0, render_duration-1):d=1` when `apply_fade_out`.

**Audio**: every webcam source with audio (plus screen audio when `include_screen_audio`) is `atrim`ed to `render_duration`, `asetpts=PTS-STARTPTS`, `aresample=48000`, then `amix=inputs=N:duration=longest:normalize=0,alimiter=limit=0.95,atrim=duration=<render_duration>[aout]`. With no audio sources, falls back to `anullsrc=r=48000:cl=stereo`.

### Overlay scheduling (in this module, not the scheduler)

**Opening lower third**: `enable='between(t,0,9.100)'`, overlaid at `x=48:y=H-h-24`.

**Speaker lower thirds**: candidates need `elapsed >= 12.0`, `scene_type in {"webcam_full","webcam_zoom"}`, and `scene.duration >= 5.0`. A source whose name contains `ryan` shows when `elapsed >= 30.0` and ≥150 s since that source's last card; all others use `int(elapsed / 5.0) % 12 == 0`. Episode 85 suppresses cards for `295.0 <= elapsed < 320.0`. Each occurrence is capped at 9.1 s with a 0.4 s slide each way. Animated assets slide `x` from `-80` to `-1920` at `y=0`; static PNG fallbacks sit at `x≈48, y=H-h-24`.

**CTA toasts**: for each of `CTA_STARTS_SECONDS` shifted by `-cta_time_offset` and clipped to the render window, a separate branch does `trim=duration=6.000,setpts=PTS-STARTPTS+<start>/TB,format=rgba`, overlaid at `x=48:y=H-h-24` with `enable='between(t,start,start+6)'` and `eof_action=pass`.

**Every overlay occurrence gets its own filter branch with its own `trim` + PTS reset.** This is load-bearing. Combining occurrences made cards inherit the looped movie's global animation phase — a card would slide away and reappear mid-episode, or land on a transparent frame. If you find yourself deduplicating overlay branches to shrink the graph, don't.

### Scene trimming and coalescing

`_limited_scenes(plan, limit, start_offset=0.0, apply_tail=True, coalesce_identical=True, trim_end=0.0)` rebases scenes onto a zero-based timeline, drops or clips scenes outside the window, merges adjacent scenes identical in every field when `coalesce_identical`, and — when `apply_tail` and ≥2 webcams — rewrites every scene starting in the final 20 s into `webcam_pair` using `webcams[0]` + `webcams[1]`.

### Input ordering

`_input_arguments()` emits `-ss <local_start> -t <render_duration + 0.5> -i <path>` per source. **The 0.5 s decode cushion matters**: without it, a scene ending exactly on a chunk boundary loses its final frame.

Overlay inputs are appended in a fixed order and **the indices passed to `build_filter_graph` must match**: sources, logo (`-loop 1 -framerate 30`), lower third, CTA, pip-frame, three-panel frame, then one input per speaker asset. `.mov` assets use `-stream_loop -1`; `%06d` sequences use `-loop 1 -framerate 30 -start_number 1`. This coupling is fragile — if you add an overlay input, update both the argument list and the index plumbing in `render_plan`.

### Encoder options

```
-c:v libx264 -preset <preset> -crf 20
# or
-c:v h264_videotoolbox -allow_sw 1 -b:v 8M -maxrate 12M -bufsize 16M
```

Plus `-pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -ar 48000 -movflags +faststart -progress pipe:1 -nostats`, and `-y`/`-n` per `overwrite`. FFmpeg runs with `-hide_banner -v error`; progress is parsed from `out_time_ms=` and printed every 5%.

### Chunked rendering

`render_plan_chunked()` loops `render_plan` over `chunk_seconds` slices into `chunk-%04d.mp4` in a temp dir, passing `overwrite=True`, `trim_start=trim_start+offset`, `trim_end=0.0`, `cta_time_offset=offset`, `apply_fade_in` only on the first chunk, and `apply_tail`/`apply_fade_out` only on the last. Chunks join with the concat demuxer (`-f concat -safe 0 -c copy -movflags +faststart`) — **stream copy, no second encode, no generation loss**.

Fade handling is chunk-aware by design. Middle chunks get neither fade; a one-pass render gets both. Any output rendered before this fix has fades at chunk boundaries.

### Verification

`probe_output(path)` returns ffprobe JSON; `verify_output(probe, expected_duration)` asserts 1920x1080, `h264`, `aac`, and duration within 0.25 s. Always run this before reporting a render complete.

### Speaker name mapping

`render_plan` builds the speaker card map by filename substring: `jason` → Jason Hand / Senior Advocate - AI & Cloud; `tara` → Tara Schofield / Technical Advocate - Cloud; `ryan` → Ryan MacLean / Senior Technical Advocate - Cloud & AI; `stephen` → Stephen Rosenthal / Senior Software Engineer - Auth & Identity. Anything else falls back to the file stem with no title.

Per speaker, asset resolution prefers `<first-name>-lower-third-alpha.mov`, then `.hf-frames-<first-name>/frame_%06d.png`, then a PIL-generated static PNG via `_create_speaker_lower_third_asset()`.

### Known dead code and machine-specific paths

- `screen_full` is renderable but unreachable from the current scheduler
- `_rounded_square_panel_filter` and `INTER_BOLD_FONT` are defined but unreferenced
- `INTER_REGULAR_FONT` is an absolute path under `/Users/jason.hand/.cache/hyperframes/fonts/` — the three-panel `drawtext` is machine-specific and will fail elsewhere

## `thumbnail.py` — thumbnail composition

Builds 1920x1080 PNGs: grab a frame with MoviePy/PIL, render a HyperFrames holographic title to a transparent `.mov` via the pinned CLI, extract one settled frame with FFmpeg, composite title + `ai_tl_logo.png`.

```
HYPERFRAMES_VERSION = "0.8.27"     TITLE_SETTLE_SECONDS = 2.5
CANVAS = 1920x1080                 PANEL_WIDTH = 960
LOGO_CROP_BOX = (430, 307, 1503, 729)   LOGO_HEIGHT = 135   LOGO_MARGIN = 5
```

`render_holographic_title()` runs:

```bash
npx --yes hyperframes@0.8.27 render <project> --format mov --quality high \
    --variables '{"title": "<title>"}' --output <workdir>/thumbnail-title.mov
ffmpeg -y -ss 2.5 -i <mov> -update 1 -frames:v 1 -pix_fmt rgba <workdir>/thumbnail-title.png
```

The 2.5 s seek lands after the intro animation settles. Four layouts (`compose_*` / `generate_*` pairs): split-screen, guest side, guest headshot, guest diagonal. `_discover_webcam_sources` needs ≥2 files with `webcam` in the stem and uses the first two; `_discover_guest_source` needs exactly one matching the guest fragment.

## HyperFrames compositions

`long_form/hyperframes/` holds nine project/asset directories:

| Directory | Purpose |
|---|---|
| `lower-third/` | Opening card + Jason/Tara speaker cards |
| `episode85-lower-third/` | Episode-85 opening variant |
| `episode85-speaker-lower-thirds/{ryan,stephen}/` | Per-speaker cards |
| `cta/` | Six-second like-and-subscribe toast (`data-duration="6"`) |
| `pip-frame/` | Animated border for the screen_pip inset |
| `three-panel-frame/` | Animated borders for the three-panel column |
| `thumbnail-title/`, `thumbnail-title-{side,stacked,diagonal}/` | Title treatments (`data-duration="4"`, var `title`) |

### Authoring conventions

**`index.html` is the source of truth.** Each is a standalone 1920x1080 page with a transparent background, `data-resolution="landscape"`, a JSON `data-composition-variables` attribute on `<html>` declaring typed variables, a root `div#root` with `data-composition-id="main"` / `data-start` / `data-duration` / `data-width` / `data-height`, clip children with `class="clip"` + `data-start` / `data-duration` / `data-track-index`, `data-var-text="<varId>"` text bindings, GSAP 3.14.2 from jsDelivr, and a paused `gsap.timeline()` registered as `window.__timelines["main"]`.

`hyperframes.json` pins the schema and registry and sets `paths` to `{blocks: "compositions", components: "compositions/components", assets: "assets"}`. `meta.json` is `{id, name, createdAt}`. `package.json` scripts (pinning `hyperframes@0.8.27`): `dev` = preview, `check`, `render`, `publish`. Projects without a `package.json` (`pip-frame`, `three-panel-frame`) have only `index.html`.

Vendored HyperFrames `CLAUDE.md` / `AGENTS.md` files exist inside several composition directories. Those are framework boilerplate, not project guidance — don't treat them as authoritative for CAIVE.

### Asset regeneration — open gap

The transparent `*-alpha.mov` overlays are **committed build artifacts, and no script in this repo regenerates them.** The exact `hyperframes render` invocation used to produce ProRes with alpha, and how each per-speaker variant was produced with different heading/subheading variables, is recorded nowhere. Only thumbnail titles are rendered programmatically (in `thumbnail.py`).

If you work this out, write the command down here rather than leaving it implicit again.

The `.hf-frames*` directories are PNG sequences (~300 frames = 10 s at 30 fps) kept as fallback and debug output. Only `.hf-frames` and `.hf-frames-<first-name>` are referenced by code; the many suffixed variants (`-previous`, `-straight`, `-updated`, `-before-logo`, `-before-speaker`, `-fixed`, `-before-magenta`) are historical snapshots.

---

# Shorts pipeline architecture

## Core functions (`stacked_script/stack.py`)

- `get_video_files()`, `get_vtt_files()` — discovery
- `parse_vtt_file()` — parses `HH:MM:SS.mmm --> HH:MM:SS.mmm` into subtitle entries
- `extract_vtt_segment()` — pulls a clip's range from a full-episode VTT and rebases timestamps to 0:00
- `wrap_subtitle_text()` — manual word-level wrapping
- `convert_srt_to_ass_with_positioning()` — SRT → ASS with CAIVE styling and per-mode positioning
- `cleanup_subtitle_files()` — removes temporary `.srt` files
- `create_portrait_video()` — stacked-layout pipeline with subtitle support
- `create_multi_cut_video()` — quick-cut pipeline with speaker detection and zoom
- `get_audio_level()` — RMS of a 0.5 s audio window at a given offset
- `create_layout_preview()` — static PIL preview including caption styling
- `trim_video()`, `display_menu()`, `get_user_selection()`, `ask_for_*()` — CLI helpers

## Processing pipeline

1. Validate inputs (≥2 MP4s)
2. Select mode: 2 / 3 / 4-video stack, or multi-cut
3. Assign videos to positions
4. Detect VTT files in the directory
5. Optional static layout preview (~2 s to generate)
6. Choose output: 1–3 clips (30/45/60 s), a 5-second preview at a timestamp, or the full video
7. Trim all sources to the shortest duration
8. Resize and center-crop to 1080x1920
9. Extract, convert, and burn subtitles
10. Overlay the logo
11. Composite and export at 30 fps H.264/AAC
12. Clean up temporary subtitle files
13. Print a summary of all clips

## Center cropping (2-video mode)

1. Resize to 1080px wide, preserving aspect ratio
2. If the result is taller than the allocated 960px, crop vertically from center
3. If shorter, resize to fill the height, then crop horizontally from center

Result: both videos fill exactly 50% of the screen with centered content.

Section heights: 960px (2-video), 640px (3-video), 480px (4-video).

## Dynamic speaker detection (multi-cut)

`get_audio_level(clip, time)` extracts a 0.5 s audio segment and returns its RMS, or 0.0 if there's no audio or the time exceeds the clip duration.

For each 2.5–3.5 s segment, audio is sampled **every 0.5 s across the whole segment** for every webcam, averaged per camera, and speakers above an RMS of **0.02** are ranked loudest-first. The loudest camera wins; the screen video is always an option; with no active speaker it falls back to the screen. No camera holds more than two consecutive segments.

The earlier implementation pre-analyzed the video once and checked audio only at each segment's start, which mishandled back-and-forth conversation where the speaker changes mid-segment. **Don't revert to start-of-segment sampling.** The threshold moved from 0.01 to 0.02 to cut false positives.

Debug output:

```
Segment 1: 0.0s-2.8s (2.8s) - Video 2 (WEBCAM) [speakers: Video 2: 0.0245, Video 3: 0.0098] ← DOMINANT
```

Zoom: 50% of segments get 1.05x–1.15x, applied by resize + center-crop to preserve 1080x1920. Audio survives the transform. Video selection is weighted 95% Primary / 5% Secondary when labeled.

## Caption system

### Why manual text wrapping

ASS format's automatic wrapping and margin settings proved unreliable. After repeated attempts with `MarginL`, `MarginR`, and `WrapStyle`, captions still overflowed the screen edges. Text is now pre-wrapped at the word level before being written to the ASS file. **This is deliberate — do not replace it with ASS automatic wrapping.**

`wrap_subtitle_text(text, max_chars_per_line=22)`: collapses newlines to spaces, accumulates words while the line fits, and joins lines with `\\N` (ASS line break, not `\n`). 22 characters is conservative for 120pt at 1080px wide. If captions still overflow, lower that number.

### Styling

Defined in `stack.py` and mirrored in `utils/burn_subs.py` — **keep both in sync.**

- **Font**: National 2, 120pt (`find_font_path()` resolves it, falling back to Arial-Bold)
- **Primary**: `#ECDDFF` → RGB (236, 221, 255) → ASS BGR `&HFFDDEC`
- **Outline**: `#34008D` → RGB (52, 0, 141) → ASS BGR `&H8D0034`, width 3px, shadow 3px
- **MarginV from bottom**: 400px multi-cut/letterbox, 850px 2-video, 750px 3-video
- **Padding**: 80px left and right
- **Alignment**: 2 (center); **WrapStyle**: 0 (disabled)
- **PlayResX/Y**: 1080 / 1920

Burned via FFmpeg's `ass` filter: `f"ass={str(ass_path.absolute())}"`, passed through `ffmpeg_params`.

`create_layout_preview()` renders the same styling with PIL using sample text, so caption position can be iterated in ~2 seconds instead of a full render.

## Logo and title

Logo: sized to 1/3 of the top section height, positioned at (2px, 2px), from `logos/logo.png`.

Optional title: up to 50 characters, National 2 Bold 80pt white with a black outline, top center, 100px down.

## `create_clips_from_analysis.py`

Reads a `vtt-clip-finder` suggestions markdown file and renders clips. Mode argument: `varied` (default — 70% multi-cut, 20% single, 10% stacked), `multi`, or a fixed `2`/`3`/`4`. Output to `output/<episode>/`.

```bash
python create_clips_from_analysis.py transcripts/Episode-85_clip_suggestions.md varied
```

## `vtt-clip-finder` agent

`.claude/agents/vtt-clip-finder.md`, model `sonnet`. Input: a VTT path. Outputs, both mandatory: a suggestions markdown file written next to the VTT (`Ep52.vtt` → `Ep52_clip_suggestions.md`), and the rendered clips — the agent runs `create_clips_from_analysis.py` itself without asking. It then edits a `## Generated Clips` table into the top of the markdown.

Constraints: exactly 5 clips, ranked; **30 s minimum, 179.0 s (2:59) maximum** with an arithmetic validation checklist; target 120–179 s, with sub-90 s clips the exception. Captions are mandatory.

Style: titles are descriptive and factual. Clickbait constructions are explicitly banned — "Secret Weapon", "Nobody's Talking About", "Just Got Exposed", "This Will Blow Your Mind". Descriptions are technical and educational, avoiding rhetorical hooks.

---

# Testing

Neither suite is referenced from the legacy docs; `long_form/STATUS.md` is the only other place they're recorded.

## Long-form (`tests/long_form_test.py`) — unittest, 5 tests

```bash
python -m unittest tests.long_form_test -v
```

- `SourceTests.test_streamyard_offset` — filename offset parsing (`01h_02m_03s_456ms` → 3723.456); non-StreamYard names → 0.0
- `SourceTests.test_common_interval_uses_overlap` — the intersection window across three offset sources
- `SchedulerTests.test_plan_is_reproducible_and_valid` — two `build_edit_plan(seed=42)` calls produce identical dicts; `validate_plan` passes; scenes cover 0.0 → full duration
- `SchedulerTests.test_plan_uses_sources_and_hybrid_palette` — both webcams used; `screen_pip` present; first screen scene within 30 s of activity; every `screen_pip` has a `pip_source` and `pip_position == "upper_right"`; `webcam_zoom` share ≤ 0.35; screen runs last 20–30 s; consecutive runs ≥ 8 s apart; speaker selection tracks synthetic audio levels
- `RendererTests.test_all_scene_types_render_to_landscape_mp4` — synthesizes clips with `ffmpeg lavfi`, builds a four-scene plan covering `webcam_full` / `webcam_zoom` / `screen_full` / `screen_pip`, asserts plan JSON round-trips, renders, and probes for 1920x1080 H.264/AAC at ~8.0 s

Requires `ffmpeg` and `ffprobe` on the `PATH`, but generates its own media — no sample footage needed.

## Visual regressions (`tests/hyperframes_visual_test.py`) — pytest, 3 tests

```bash
python -m pytest tests/hyperframes_visual_test.py
```

Skips entirely via `pytest.importorskip` if Playwright is missing. Each of `thumbnail-title-{side,stacked,diagonal}` is loaded in headless Chromium at 1920x1080 from a `file://` URL (no server), its timeline jumped to `window.__timelines['main'].progress(1).pause()` — the settled end state matching what the real pipeline's frame extraction captures — then screenshotted with `omit_background=True`. The RGBA diff must have ≤ **1%** (`MAX_DIFF_RATIO = 0.01`) of pixels differing from the baseline.

To accept intentional changes:

```bash
UPDATE_HYPERFRAMES_BASELINES=1 python -m pytest tests/hyperframes_visual_test.py
```

That writes the new baseline and skips the test. Baselines are 1920x1080 RGBA PNGs in `tests/hyperframes_baselines/`. `thumbnail-title/` itself is **not** covered — only the three variants.

## Conventions and gaps

- `.gitignore` excludes `test_*.py`, which is why files are named `*_test.py`. Keep that convention or the tests get ignored.
- There is no `conftest.py`, `pytest.ini`, `pyproject.toml`, `setup.cfg`, or `tox.ini` anywhere.
- `hyperframes_visual_test.py` imports `numpy`, which isn't declared in either requirements file (it arrives via moviepy).
- The Shorts pipeline has **no automated tests**. Verify it manually with a layout preview or a short clip.

## Pre-commit checks

```bash
python -m py_compile long_form/renderer.py long_form/cli.py
git diff --check
python -m unittest tests.long_form_test -v
```

---

# Legacy: Streamlit interface

`pvg.py` is a Streamlit GUI (`streamlit run pvg.py`) that wraps `stacked_script.stack` without modifying it. **It is not actively maintained.** It covers only the Shorts pipeline and has no awareness of `long_form/`, HyperFrames overlays, or thumbnails.

It imports `create_portrait_video()`, `create_multi_cut_video()`, `create_layout_preview()`, `get_vtt_files()`, and `trim_video()`; uses `tempfile.mkdtemp()` for uploads and `st.session_state` to persist across reruns; generates thumbnails via MoviePy's `get_frame()` at the 5-second mark; and styles itself with the `#34008D` / `#ECDDFF` palette. Upload limits are in `.streamlit/config.toml` (`maxUploadSize = 2000`, in MB — restart after changing).

Don't invest in this file unless the user explicitly asks. Direct feature work toward the conversational workflow.

---

# Code quality guidelines

1. **Keep the pipelines separate.** `long_form/` must not import from `stacked_script.stack`, and long-form work must not touch Shorts rendering paths.
2. **Verify visual changes visually.** Generate a layout preview, a short render, or a screenshot and look at it before claiming caption or overlay positioning is fixed.
3. **Probe every render.** `ffprobe` for resolution, codecs, and duration. Never report success on the basis of a process exiting.
4. **Keep scheduling deterministic.** All randomness goes through `random.Random(seed)`.
5. **Maintain manual caption wrapping.** ASS automatic wrapping is unreliable and was already tried.
6. **Keep one filter branch per overlay occurrence.** Deduplicating them reintroduces animation-phase bugs.
7. **Preserve the color scheme**: `#ECDDFF` and `#34008D` throughout, and document both RGB and ASS BGR forms for any new ASS color.
8. **Keep `stack.py` and `utils/burn_subs.py` caption styling in sync.**
9. **Keep cleanup automatic.** Temporary `.srt` / `.ass` files and work directories should disappear without user action.
10. **Show summaries at the end**, not incrementally — filename, duration, file size, processing time for every clip or chunk.
11. **Don't add more episode-name special cases.** Lift the existing ones into settings or flags instead.
12. **Preview before full renders**, and never `--overwrite` without explicit approval.
13. **Keep AGENTS.md in sync with this file.** It's the agent-neutral copy; update both together.

---

# Troubleshooting

| Problem | Cause / fix |
|---|---|
| FFmpeg "matches no streams" in a long-form render | A filtergraph label referenced before definition. Re-run with `--keep-workdir` and read `filter-complex.txt`. The error frequently misattributes the cause — the three-panel ordering bug appeared to implicate speaker lower thirds. |
| Render "finished" but output is wrong | Probe it: `ffprobe -v error -show_entries format=duration:stream=codec_name,codec_type,width,height -of json <file>` |
| `cannot create compression session: -12908` | VideoToolbox unavailable even with `-allow_sw 1`. Use `--video-encoder libx264`. On a compatible Mac, test with a 30 s chunk before a full render. |
| Render too slow | `--preset ultrafast` (much larger files) or `--chunk-seconds 180` for cheaper failure recovery. `veryfast` at CRF 20 is far smaller than `ultrafast`. |
| Overlay card slides away and reappears | Overlay occurrences were combined into one branch. Each needs its own `trim` + PTS reset. |
| Fades appear mid-episode | Output predates the chunk-aware fade fix, or `apply_fade_in`/`apply_fade_out` were passed to middle chunks. |
| Wrong file treated as the screen share | Detection is filename-based (`screen` in the name). Pass `--screen PATH`. |
| "Sources share no common interval" | Recordings don't overlap after StreamYard offsets. Check the filename offsets. |
| Three-panel `drawtext` fails | `INTER_REGULAR_FONT` is an absolute path under `~/.cache/hyperframes/fonts/`. Update for the local machine. |
| Overlay missing from a render | The `.mov` is absent and so are the `.hf-frames` PNGs, so it fell back to a static PIL card. Check the asset paths. |
| Captions cut off at the edges | Lower `max_chars_per_line` in `wrap_subtitle_text()`. Don't switch to ASS auto-wrapping. |
| VTT extraction fails | Confirm the file covers the clip range and uses `HH:MM:SS.mmm` / `MM:SS.mmm`. Replace spaces in filenames with underscores. |
| Logo missing | Shorts wants `logos/logo.png`; long-form wants `logos/ai_tl_logo.png`. `logos/` is gitignored. |
| MoviePy / Pillow errors | `pip install -r requirements.txt` |
| Visual tests all skip | Playwright isn't installed: `pip install -r requirements-dev.txt && playwright install chromium` |

---

# Recent changes history

- **Rebrand to CAIVE** (Claude AI Video Editor): docs and code headers renamed from "Portrait Video Generator" / "Video Stacker". The conversational Claude workflow is now documented as the primary interface; Streamlit is marked legacy and unmaintained. Module paths, filenames, and CLI commands are unchanged.
- **Documentation catch-up**: the long-form editor, HyperFrames overlay system, and both test suites are now documented in README.md, CLAUDE.md, and AGENTS.md. Previously they appeared only in `long_form/STATUS.md`. AGENTS.md was regenerated — the old copy was a mechanical Claude→Codex find-replace carrying a bogus `Codex.ai/code` URL and a broken `.Codex/agents/` path.
- **Long-form landscape editor** (`long_form/`): analyze → JSON edit plan → render, producing 1920x1080 multi-camera edits with deterministic seeded scheduling, speaker-aware cutting from RMS audio, adaptive screen-activity detection, and five scene layouts.
- **HyperFrames overlays**: animated holographic lower thirds (opening + per-speaker), a recurring CTA toast at 7/14/21 minutes, and animated frames for the screen PiP and three-panel column. Perspective transforms were removed from lower thirds so borders stay parallel to the canvas.
- **Per-occurrence overlay branches**: each scheduled overlay gets its own `trim` + PTS reset, fixing cards that inherited the looped asset's global animation phase and slid away mid-episode.
- **Three-panel filter ordering fix**: the animated frame overlay referenced `three_left_*` before `_stacked_camera_filter()` defined it, producing a misleading "matches no streams" error. The frame is now overlaid before the `hstack`.
- **Hybrid chunked rendering**: `render_plan_chunked()` renders bounded chunks and concatenates with stream copy. Fades are chunk-aware (first chunk in, last chunk out only), and sources get a 0.5 s decode cushion so boundary scenes keep their final frame.
- **Visual regression tests**: Playwright screenshots of the thumbnail-title compositions at settled timeline end, diffed against baselines at a 1% tolerance, with `UPDATE_HYPERFRAMES_BASELINES=1` to accept changes.
- **Four thumbnail layouts**: split-screen plus three guest variants (side, headshot, diagonal), with holographic titles rendered through the pinned HyperFrames CLI.
- **Dynamic speaker-aware cutting** (multi-cut Shorts): replaced static pre-analysis with sampling every 0.5 s across each segment's full duration, averaging per camera and cutting to the loudest. Threshold raised from 0.01 to 0.02 RMS.
- **Random zoom in multi-cut mode**: 50% of segments get 1.05x–1.15x via resize + center-crop.
- **Caption position tuning**: 400px from bottom for multi-cut/letterbox, 850px for 2-video, 750px for 3-video.
- **vtt-clip-finder tone change**: default style is now descriptive and factual rather than clickbait; sensational title patterns are explicitly banned.
- **Optional burned title text**: up to 50 characters, National 2 Bold 80pt white with black outline, top center.
- **Caption overflow fix**: manual word-level wrapping at 22 chars/line, replacing unreliable ASS auto-wrapping.
- **Font and color scheme**: National 2 at 120pt, `#ECDDFF` fill with `#34008D` outline.
- **Automatic cleanup**: `cleanup_subtitle_files()` removes temporary `.srt` files after processing.
