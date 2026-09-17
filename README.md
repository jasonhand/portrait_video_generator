# CAIVE — Claude AI Video Editor

CAIVE turns raw multi-camera recordings into finished video, by conversation. You point Claude at a folder of source recordings and describe what you want; Claude analyzes the footage, proposes an edit, renders a preview for your approval, and produces the final file.

Two pipelines ship in the box:

| Pipeline | Output | Use it for |
|---|---|---|
| **Shorts** (`stacked_script/`) | 1080x1920 portrait, 9:16 | YouTube Shorts, TikTok, Instagram Reels. Stacked or quick-cut layouts with burned-in captions. |
| **Long-form** (`long_form/`) | 1920x1080 landscape, 16:9 | Full episodes. Multi-camera scene rotation with animated HyperFrames lower thirds, CTA toasts, and framed picture-in-picture. |

The two pipelines are deliberately independent. The long-form editor never calls into the Shorts engine, so work on one cannot break the other.

---

## The primary interface is a conversation

CAIVE is designed to be driven by Claude, not by memorizing flags. The commands in this README exist so you can check Claude's work, script a batch job, or debug a render — but the intended day-to-day experience is asking for what you want in plain language.

Open the project in Claude (Claude Code in a terminal, or Cowork with this folder connected) and start describing the edit.

### Getting clips out of an episode

```
Find the five best short clips in transcripts/Episode-85.vtt and render them.
```

Claude reads the transcript, picks moments with strong openings, writes its reasoning to a suggestions file you can review, and then renders the clips with captions burned in. You can push back at any point:

```
Clip 3 starts too late — back it up about eight seconds so we catch the setup.
Re-render clip 3 only.
```

```
Make them all multi-cut instead of stacked, and keep each one under two minutes.
```

### Building a long-form episode

```
Analyze the Episode-85 recordings in source_video/ and show me the edit plan.
```

Claude discovers which files are webcams and which is the screen share, measures where the recordings overlap, analyzes audio to find who is speaking, detects when the screen share has meaningful activity, and writes a JSON edit plan. It will report the scene breakdown before rendering anything:

```
223 scenes: 128 screen_pip, 62 webcam_full, 16 webcam_zoom, 10 three_panel, 7 webcam_pair
```

Then ask for a preview before committing to a 15-minute render:

```
Render the first two minutes so I can check the framing.
```

```
The opening has four seconds of dead air before anyone talks — trim that,
drop the last two seconds, and render the full episode.
```

### Asking about the footage

```
Which webcam has the most talk time in this episode?
```

```
Is the screen share readable at 1080p, or should we avoid screen_pip scenes?
```

```
Why did the renderer put a three-panel scene at 8:40?
```

### What Claude will ask you for

- **The episode name**, used to match source filenames (`Episode-85`, `Episode_84`)
- **Which file is the screen share**, if the filename-based detection is ambiguous
- **Approval after the preview**, before any full render — long renders are expensive and this gate is intentional
- **Explicit confirmation before overwriting** an existing output file

### Two slash commands

Two workflows are packaged as skills in `.claude/skills/`. They are marked `disable-model-invocation: true`, meaning Claude will not trigger them on its own — you invoke them by name:

```
/generate-long-form Episode_85
/generate-thumbnail Episode_85 "Building agents that actually ship"
```

`/generate-long-form` walks the full analyze → preview → approve → render sequence with the approval gate enforced. `/generate-thumbnail` produces a 1920x1080 thumbnail PNG. Everything these skills do can also be requested conversationally; the skills just guarantee the sequence.

---

## Installation

```bash
git clone <repository-url>
cd portrait_video_generator
pip install -r requirements.txt
```

### Prerequisites

- **Python 3.8+**
- **FFmpeg and ffprobe** on your `PATH` — both pipelines shell out to them constantly
- **Node.js / `npx`** — only needed for thumbnail generation and for re-authoring HyperFrames compositions
- **Claude Code or Cowork**, for the conversational workflow
- A logo at `logos/logo.png` (Shorts watermark) and `logos/ai_tl_logo.png` (long-form watermark). The `logos/` directory is gitignored — bring your own.

For development and tests:

```bash
pip install -r requirements-dev.txt
playwright install chromium   # only for the visual regression tests
```

### File layout

```
portrait_video_generator/
├── README.md                      # This file
├── CLAUDE.md                      # Architecture + conventions for Claude
├── AGENTS.md                      # Same guidance, agent-neutral
├── requirements.txt               # Runtime dependencies
├── requirements-dev.txt           # + pytest, playwright
│
├── .claude/
│   ├── agents/vtt-clip-finder.md  # Transcript → clip suggestions agent
│   └── skills/
│       ├── generate-long-form/    # /generate-long-form
│       └── generate-thumbnail/    # /generate-thumbnail
│
├── stacked_script/stack.py        # Shorts engine (portrait 9:16)
├── create_clips_from_analysis.py  # Batch clip renderer
├── utils/burn_subs.py             # Standalone subtitle burner
├── pvg.py                         # Legacy Streamlit UI (Shorts only)
├── .streamlit/config.toml         # Upload limits for the legacy UI
│
├── long_form/                     # Long-form editor (landscape 16:9)
│   ├── cli.py                     # analyze / render / thumbnail commands
│   ├── sources.py                 # Source discovery + StreamYard sync
│   ├── analysis.py                # Audio RMS + screen activity detection
│   ├── scheduler.py               # Scene boundaries and layout choice
│   ├── models.py                  # EditPlan / Scene / SourceInfo
│   ├── renderer.py                # FFmpeg filtergraph + chunked rendering
│   ├── thumbnail.py               # Thumbnail composition
│   ├── hyperframes/               # Animated overlay compositions + assets
│   └── STATUS.md                  # Render log and continuation notes
│
├── tests/
│   ├── long_form_test.py          # unittest: sync, scheduling, rendering
│   ├── hyperframes_visual_test.py # pytest + playwright: visual baselines
│   └── hyperframes_baselines/     # Reference PNGs
│
├── logos/                         # Brand assets (gitignored)
├── transcripts/                   # VTT subtitle files (gitignored)
├── source_video/                  # Source recordings (gitignored)
└── output/                        # Rendered video (gitignored)
```

---

## Long-form editor (landscape 16:9)

The long-form pipeline is the newer half of CAIVE. It takes synchronized recordings — typically several StreamYard webcam tracks plus a screen share — and produces a single 1920x1080 edit that cuts between cameras based on who is actually speaking.

It works in two stages, with a reviewable JSON edit plan in between. That plan is the source of truth: previews and final renders come from the same file, so what you approve is what you get.

### Stage 1 — Analyze

```bash
python -m long_form.cli analyze \
  --input-dir source_video \
  --episode "Episode-85" \
  --plan output/long_form/Episode_85/edit-plan.json
```

| Flag | Default | Purpose |
|---|---|---|
| `--input-dir` | required | Directory of MP4 sources |
| `--episode` | required | Episode name; matched against source filenames |
| `--plan` | required | Output path for the JSON edit plan |
| `--seed` | CRC32 of the episode name | Scheduling seed. The same seed always produces the same plan. |
| `--screen` | filename detection | Explicitly name the screen-share file when detection is ambiguous |

**Source discovery** globs `*.mp4` in the input directory and keeps files whose stem contains the episode string (case-insensitively), falling back to matching the first run of digits in the episode name. A file is classified as the screen share if `screen` appears in its filename; everything else is a webcam. Exactly one screen source and at least one webcam are required — pass `--screen PATH` to override.

**Synchronization** reads the StreamYard offset embedded in the filename (`...-00h_00m_01s_313ms-StreamYard.mp4`), then computes the interval all recordings share: `common_start` is the latest start, and the duration runs to the earliest end. Files without a parseable offset are treated as starting at zero.

**Analysis** is purely signal-level — no transcript or speech-to-text is involved:

- *Audio*: each webcam is decoded to 8 kHz mono and reduced to a raw RMS level every **0.5 s**. Levels are deliberately not normalized per track, so they stay comparable across cameras.
- *Screen*: the screen share is decoded to 320x180 grayscale at **1 fps**. A frame counts as *present* if its mean brightness exceeds 5.0 (which rejects black filler but accepts dark application UIs), and as *active* if its difference from the previous frame clears an adaptive threshold — `max(median + 2·MAD, 65th percentile, 0.75)`. Each active sample holds activity on for the following **20 seconds**, so a slide that stays static after a transition still counts as live content.

**Scheduling** then walks the timeline in 5-second steps, snapping each cut up to ±0.5 s onto the quietest point on the audio grid so cuts land in pauses rather than mid-word. For each scene it picks the loudest webcam (holding the previous speaker if nothing clears an RMS of 0.02), then chooses a layout:

| Scene type | What it looks like |
|---|---|
| `webcam_full` | One camera, full frame |
| `webcam_zoom` | One camera, zoomed 1.05x–1.15x. 10% chance, never twice in a row. |
| `webcam_pair` | Two cameras side by side as rounded 960x1080 panels. 10% chance. |
| `three_panel` | Two tall rounded camera tiles on a purple (`#A960FF`) column at left, uncropped screen share at right, with an episode URL in the lower letterbox. 15% chance when screen content exists. |
| `screen_pip` | Full screen share with a 300x300 rounded speaker inset at upper right, wrapped in an animated frame. |
| `screen_full` | Screen share only. Renderable, but the current scheduler never emits it. |

Screen-share runs last 20–26 seconds, require detected activity, stay at least 60 seconds from both ends of the episode, and observe an 8-second cooldown before another run can start. A final pass guarantees every webcam appears at least once in the first two minutes.

Scheduling is fully deterministic for a given seed, so `analyze` twice with the same inputs yields byte-identical plans.

### Stage 2 — Render

```bash
# Preview first
python -m long_form.cli render \
  --plan output/long_form/Episode_85/edit-plan.json \
  --output output/long_form/Episode_85/Episode_85_preview.mp4 \
  --preview-seconds 120

# Then the full episode
python -m long_form.cli render \
  --plan output/long_form/Episode_85/edit-plan.json \
  --output output/long_form/Episode_85/Episode_85_long_form.mp4 \
  --trim-start 4 --trim-end 2 \
  --chunk-seconds 300 --preset veryfast --video-encoder libx264
```

| Flag | Default | Purpose |
|---|---|---|
| `--plan` | required | JSON edit plan |
| `--output` | required | Output MP4 |
| `--preview-seconds` | full length | Render only the opening N seconds, without editing the plan |
| `--trim-start` | `0.0` | Drop N seconds from the start (useful for dead air before the first line) |
| `--trim-end` | `0.0` | Drop N seconds from the end; the fade-out moves to the new ending |
| `--chunk-seconds` | `300.0` | Render in independent chunks and concatenate. `0` renders in one pass. |
| `--video-encoder` | `libx264` | `libx264` or `h264_videotoolbox` (Apple hardware) |
| `--preset` | `ultrafast` | x264 speed preset: `ultrafast` … `medium`. Ignored for VideoToolbox. |
| `--no-coalesce` | off | Disable merging of adjacent identical scenes |
| `--include-screen-audio` | off | Mix screen-share audio in addition to webcam audio |
| `--logo` | `logos/ai_tl_logo.png` | Watermark image |
| `--overwrite` | off | Replace an existing output file |
| `--keep-workdir` | off | Keep the generated FFmpeg filter script for debugging |

> **Note:** the CLI defaults `--preset` to `ultrafast`, while `render_plan()`'s own signature defaults to `veryfast`. For real deliverables pass `--preset veryfast` explicitly — at CRF 20 it produces a dramatically smaller file than `ultrafast` for a modest amount of extra time.

**How rendering works.** Every scene becomes a branch of a single large FFmpeg filtergraph — written to a file and passed via `-filter_complex_script`, because it is far too long for a command line. Each source is decoded once and `split` into as many labels as the plan needs, each branch is trimmed and normalized, all branches are `concat`enated, and overlays are composited on top. Audio is a straight `amix` of every webcam track with audio, run through `alimiter` at 0.95.

**Chunked rendering** is the default because a full episode is a multi-thousand-node filtergraph, and a failure 14 minutes in is painful. `--chunk-seconds 300` renders five-minute segments to a temp directory, then joins them with the concat demuxer using stream copy — so there is no second encode and no generation loss. Fades are chunk-aware: only the first chunk gets the fade-in and only the last gets the fade-out. Each source input gets a 0.5-second decode cushion so a scene ending exactly on a chunk boundary still has its final frame.

Reference timing: a 19-minute episode rendered in four chunks with `libx264 --preset veryfast` took roughly **15–17 minutes** wall-clock and produced about **300 MiB**.

**Verification** is built in. After rendering, the output is probed with ffprobe and checked for 1920x1080, H.264 video, AAC audio, and a duration within 0.25 s of expected. Don't trust a render you haven't probed — `long_form/STATUS.md` records several occasions where a process looked finished but wasn't.

### Overlays

Overlays are pre-rendered HyperFrames compositions — transparent ProRes `.mov` files with animated holographic borders — composited by FFmpeg at render time.

- **Opening lower third**: shows for the first **9.1 seconds**, then slides out.
- **Speaker lower thirds**: appear on `webcam_full` and `webcam_zoom` scenes at least 5 seconds long, starting 12 seconds into the episode. Cards are titled from the speaker's filename — Jason Hand, Tara Schofield, Ryan MacLean, and Stephen Rosenthal are mapped by default; anything else falls back to the file stem with no title. Each occurrence gets its own `trim` and PTS reset so every card starts at its own first frame, with a 0.4-second slide in each direction.
- **CTA toast**: a six-second "like and subscribe" card at **7:00, 14:00, and 21:00** (420 s / 840 s / 1260 s), lower left. Chunked renders pass a time offset so toasts land in the right chunk.
- **Animated frames**: the `screen_pip` inset and the `three_panel` camera column each get their own animated border asset.
- **Logo**: upper right normally, lower right during `screen_pip` scenes so it never collides with the inset.

Lower-third cards use no perspective transforms, so their borders stay parallel to the canvas while the holographic color motion plays.

### HyperFrames compositions

`long_form/hyperframes/` holds the overlay source and the built assets:

| Directory | Contents |
|---|---|
| `lower-third/` | Opening card plus Jason and Tara speaker cards |
| `episode85-lower-third/` | Episode-85 opening card variant |
| `episode85-speaker-lower-thirds/{ryan,stephen}/` | Per-speaker cards, resolved as `<first-name>-lower-third-alpha.mov` |
| `cta/` | Six-second like-and-subscribe toast |
| `pip-frame/` | Animated border for the `screen_pip` inset |
| `three-panel-frame/` | Animated borders for the three-panel camera column |
| `thumbnail-title/`, `thumbnail-title-{side,stacked,diagonal}/` | Holographic title treatments for thumbnails |

Each composition is a standalone `index.html` — a 1920x1080 page with a transparent background, typed composition variables declared on `<html>`, GSAP timelines registered as `window.__timelines["main"]`, and clip children carrying `data-start` / `data-duration` attributes. **The HTML is the source of truth.** Projects with a `package.json` pin `hyperframes@0.8.27` and expose `npm run dev` (preview), `npm run check`, and `npm run render`.

The renderer prefers the `.mov` alpha assets, falls back to the `.hf-frames/frame_%06d.png` sequences, and finally to a PIL-drawn static card if neither is present. The `.mov` files are committed build artifacts.

> **Known gap:** no script in this repo regenerates the `*-alpha.mov` overlay assets. The exact `hyperframes render` invocation used to produce ProRes with alpha — and how each per-speaker variant was rendered with different heading/subheading variables — isn't recorded anywhere. If you need to regenerate them, work it out from the composition's `package.json` scripts and then write the command down here. Thumbnail titles *are* rendered programmatically, in `long_form/thumbnail.py`, via `npx --yes hyperframes@0.8.27 render <project> --format mov --quality high --variables '{"title": "..."}'`.

### Thumbnails

Four layouts, all producing a 1920x1080 PNG with a holographic title and the `ai_tl_logo` watermark:

```bash
# Split screen: two webcams side by side
python -m long_form.cli thumbnail \
  --input-dir source_video --episode "Episode-85" \
  --title "Building agents that actually ship" \
  --output output/long_form/Episode_85/Episode_85_thumbnail.png

# Single guest, title and logo flanking the face
python -m long_form.cli guest-thumbnail \
  --input-dir source_video --episode "Episode-85" --guest "Ryan" \
  --title "..." --at 412 --output .../thumb.png

# A/B alternatives
python -m long_form.cli guest-headshot-thumbnail ... --at 412 [--zoom 1.2] [--x-shift 0.1]
python -m long_form.cli guest-diagonal-thumbnail ... --at 412 [--zoom 1.2] [--x-bias 0.6]
```

`--at` defaults to the midpoint of the synchronized window for `thumbnail`, but is **required** for the three guest variants. These commands need `npx` available, since the title is rendered by the pinned HyperFrames CLI.

### Episode-specific rules

Several behaviors are hard-coded rather than configurable, and will surprise you if you hit them. Sources named `*screen-composite*` suppress screen layouts before the 210-second mark. Episodes matching `episode-85` prefer screen layouts aggressively and force a specific ending structure after 1158 s. Plan validation permits one sub-5-second scene in a narrow window for Episode 85. If you're editing a different episode and the scheduler behaves oddly, check `scheduler.py` and `cli.validate_plan` for a name match before assuming a bug.

---

## Shorts pipeline (portrait 9:16)

### Finding clips in a transcript

The `vtt-clip-finder` agent in `.claude/agents/` reads a VTT transcript and finds segments worth clipping. Invoke it conversationally or by name:

```
@vtt-clip-finder transcripts/Episode-85.vtt
```

It returns exactly five clips ranked by potential, each between **30 seconds and 2:59** (179 s — the YouTube Shorts ceiling), with a target of 120–179 s. It writes its analysis to `transcripts/<Episode>_clip_suggestions.md` next to the VTT, then renders the clips and edits a "Generated Clips" table back into the top of that file.

Titles and descriptions are written in a deliberately straightforward, factual register. Clickbait constructions — "Secret Weapon", "Nobody's Talking About", "This Will Blow Your Mind" — are explicitly banned.

### The suggestions file format

The markdown file is a contract consumed by `create_clips_from_analysis.py`:

```markdown
## CLIP #1: Descriptive title
**Timestamp**: 00:12:34 → 00:14:20 (Duration: 106s)
**Why it works**: One sentence.
**Title:** Plain text title
**Description:** Two or three paragraphs.
**Hashtags:** #eight #to #twelve #tags
---
```

### Rendering clips

```bash
python create_clips_from_analysis.py transcripts/Episode-85_clip_suggestions.md varied
```

The mode argument controls layout: `varied` (the default — 70% multi-cut, 20% single, 10% stacked), `multi`, or a fixed stack of `2`, `3`, or `4`. Output lands in `output/<episode>/`.

### Layouts

- **2-video**: 50/50 split, each half center-cropped to fill 1080x960. Screen recording on top, speaker below.
- **3-video / 4-video**: equal sections stacked vertically (640px and 480px respectively).
- **Multi-cut**: quick cuts every 2.5–3.5 seconds with **speaker-aware selection** — the renderer samples RMS audio every 0.5 s across each segment, averages per camera, and cuts to whoever is actually talking. 50% of segments get a 1.05x–1.15x zoom, no camera holds more than two consecutive segments, and audio is mixed continuously from all sources.

### Captions

VTT subtitles are extracted for the clip's time range, timestamps rebased to zero, converted to ASS with CAIVE styling, and burned in by FFmpeg. Temporary `.srt` and `.ass` files are cleaned up automatically.

- **Font**: National 2, 120pt
- **Fill**: `#ECDDFF` (light lavender) — `&HFFDDEC` in ASS BGR
- **Outline**: `#34008D` (dark purple) — `&H8D0034` in ASS BGR, 3px, with a 3px shadow
- **Position from bottom**: 400px for multi-cut and letterbox, 850px for 2-video, 750px for 3-video
- **Wrapping**: manual, at ~22 characters per line

That last point matters. ASS format's own `WrapStyle`, `MarginL`, and `MarginR` handling proved unreliable and kept letting captions run off the screen edges, so text is pre-wrapped at the word level before being written to the ASS file. **Don't "fix" this by switching back to automatic wrapping.**

### Standalone subtitle burning

```bash
python utils/burn_subs.py <video> <subtitles> [output] [video_mode]
# video_mode: 2 or 3 (default 2) — sets caption vertical position
```

### Branding

A logo watermark is placed at the upper left, 2px from each edge, sized to one third of the top section's height. Optionally, a title up to 50 characters can be burned at top center, 100px down, in National 2 Bold 80pt white with a black outline.

---

## Testing

Two suites, run separately.

**Long-form logic and rendering** — 5 tests, no extra dependencies beyond FFmpeg:

```bash
python -m unittest tests.long_form_test -v
```

These cover StreamYard offset parsing, overlap-window computation, deterministic and valid plan generation, the scheduler's scene-type distribution and screen-run timing rules, and an end-to-end render of all four main scene types through FFmpeg to a verified 1920x1080 H.264/AAC file. The render test synthesizes its own test media with `lavfi`, so it needs `ffmpeg` and `ffprobe` on the `PATH` but no sample footage.

**HyperFrames visual regressions** — 3 tests, requires Playwright:

```bash
pip install -r requirements-dev.txt
playwright install chromium
python -m pytest tests/hyperframes_visual_test.py
```

Each thumbnail-title composition is loaded in headless Chromium at 1920x1080, its GSAP timeline is jumped to `progress(1)` — the settled end state, matching the frame the real pipeline extracts — and screenshotted with a transparent background. The result is diffed against a stored baseline; more than **1%** of pixels differing fails the test. The module skips entirely if Playwright isn't installed.

To accept intentional visual changes:

```bash
UPDATE_HYPERFRAMES_BASELINES=1 python -m pytest tests/hyperframes_visual_test.py
```

Baselines live in `tests/hyperframes_baselines/`. Note that `thumbnail-title/` itself is **not** covered — only the `side`, `stacked`, and `diagonal` variants.

**Pre-commit checks**, as used in `long_form/STATUS.md`:

```bash
python -m py_compile long_form/renderer.py long_form/cli.py
git diff --check
python -m unittest tests.long_form_test -v
```

---

## Technical specifications

| | Shorts | Long-form |
|---|---|---|
| Resolution | 1080x1920 (9:16) | 1920x1080 (16:9) |
| Frame rate | 30 fps | 30 fps |
| Video codec | H.264 (libx264) | H.264 (libx264 or h264_videotoolbox) |
| Audio codec | AAC | AAC 192 kbps, 48 kHz |
| Captions | Burned in from VTT | None |
| Quality | — | CRF 20 (x264) / 8 Mbps (VideoToolbox) |
| Container | MP4, `+faststart` | MP4, `+faststart` |

Section heights in Shorts mode: 960px each for 2-video, 640px for 3-video, 480px for 4-video.

---

## Legacy: Streamlit interface

`pvg.py` is a Streamlit GUI for hands-on portrait work. **It is not actively maintained**, it covers only the Shorts pipeline, and it has no awareness of the long-form editor, HyperFrames overlays, or thumbnails. It predates the conversational workflow and hasn't been updated in some time.

```bash
streamlit run pvg.py
```

It offers drag-and-drop upload of 2–4 MP4s plus a VTT, thumbnail-based position selection, a static layout preview, and download buttons. Upload size is capped at 2 GB via `.streamlit/config.toml` (`maxUploadSize`, in MB); restart the app after changing it.

For anything beyond simple manual portrait stacking, ask Claude instead.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| FFmpeg "matches no streams" during a long-form render | A filtergraph label is being referenced before it's defined. Re-run with `--keep-workdir` and read `filter-complex.txt`. The error message often misattributes the cause. |
| Render appears to finish but the file is wrong | Always probe before believing it: `ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of json <file>` |
| `cannot create compression session: -12908` | VideoToolbox is unavailable in this environment, even with `-allow_sw 1`. Use `--video-encoder libx264`. |
| Render is too slow | Lower the preset to `ultrafast` (much larger files), or reduce `--chunk-seconds` to 180 so failures cost less to recover from. |
| Wrong file picked as the screen share | Detection is filename-based. Pass `--screen PATH` explicitly. |
| "Sources share no common interval" | The recordings don't overlap after applying StreamYard offsets. Check the offsets encoded in the filenames. |
| Captions cut off at the screen edges | Reduce `max_chars_per_line` in `wrap_subtitle_text()`. Do not switch to ASS automatic wrapping. |
| VTT extraction fails | Confirm the VTT covers the clip's time range and uses `HH:MM:SS.mmm` or `MM:SS.mmm` timestamps. Rename files to replace spaces with underscores. |
| Three-panel `drawtext` fails | `renderer.py` points `INTER_REGULAR_FONT` at an absolute path under `~/.cache/hyperframes/fonts/`. Update it for your machine. |
| Logo missing | Shorts expects `logos/logo.png`; long-form expects `logos/ai_tl_logo.png`. The directory is gitignored. |
| MoviePy or Pillow errors | `pip install -r requirements.txt` |

---

## License

MIT. Copyright 2026 Jason Hand.
