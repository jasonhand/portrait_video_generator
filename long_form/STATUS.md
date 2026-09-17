# Long-Form Editor Continuation Notes

This file is the handoff document for the next agent session. The long-form editor is experimental and intentionally isolated from the Shorts generator.

## Current project state

- Repository: `/Users/jason.hand/Dev/portrait_video_generator`
- Main long-form code: `long_form/renderer.py`, `long_form/cli.py`, `long_form/models.py`, `long_form/scheduler.py`, `long_form/analysis.py`, `long_form/sources.py`
- Tests: `tests/long_form_test.py`
- Episode plan: `output/long_form/Episode_84/edit-plan-final.json`
- Episode source files are three synchronized 1920x1080/30fps StreamYard MP4s: Jason webcam, Tara webcam, and Tara screen share.
- Episode duration is approximately 1172.4 seconds before trim and 1168.4 seconds after `--trim-start 4`.
- The plan contains 223 scenes: 128 `screen_pip`, 62 `webcam_full`, 16 `webcam_zoom`, 10 `three_panel`, and 7 `webcam_pair`.

## Styling implemented

- 16:9 1920x1080 long-form output; no burned captions.
- Four-second opening trim so Tara's response is the first spoken content.
- Soft fade-in from black and fade-out to black.
- Full-screen webcam, zoomed webcam, two-camera side-by-side, screen-only, screen + PIP, and three-panel scenes.
- Three-panel style has two tall rounded webcam panels on the left and the screen share on the right. The screen share is not cropped.
- Three-panel background is purple (`#A960FF`), with `AI Tools Lab` and `View more episodes at dtdg.co/aitl` text.
- The three-panel URL is larger, bold, centered in the lower purple letterbox area, and white with a subtle dark-purple outline.
- Lower-third cards no longer use perspective/rotateX/rotateY transforms, so their borders remain parallel to the video canvas while preserving holographic color motion and slide animations.
- Logo placement is close to the canvas edge, with scene-specific upper-right/lower-right placement.
- HyperFrames lower thirds use animated holographic borders and reverse slide-out animation. Speaker cards include:
  - Jason Hand — Senior Advocate - AI & Cloud
  - Tara Schofield — Technical Advocate - Cloud
- CTA toast uses matching holographic styling and `#FF0080` styling.

## HyperFrames assets

Transparent ProRes assets have been generated from the HyperFrames compositions:

```text
long_form/hyperframes/lower-third/lower-third-alpha.mov
long_form/hyperframes/lower-third/jason-lower-third-alpha.mov
long_form/hyperframes/lower-third/tara-lower-third-alpha.mov
long_form/hyperframes/cta/cta-alpha.mov
long_form/hyperframes/pip-frame/pip-frame-alpha.mov
long_form/hyperframes/three-panel-frame/three-panel-frame-alpha.mov
```

The original PNG frame sequences remain in `.hf-frames*` directories for fallback/debugging. HyperFrames source files are the corresponding `index.html` files and their package metadata.

## Hybrid renderer changes

`render_plan()` now accepts:

- `video_encoder` (`libx264` or `h264_videotoolbox`)
- `preset` (`ultrafast` through `medium` for x264)
- `apply_tail`
- `coalesce_identical`

`render_plan_chunked()` renders bounded chunks and concatenates them with stream copy. The CLI exposes:

```text
--chunk-seconds SECONDS   default 300; use 0 for one-pass rendering
--video-encoder ENCODER   libx264 or h264_videotoolbox
--preset PRESET           x264 speed preset
--no-coalesce             disable identical-scene coalescing
```

The source inputs receive a 0.5-second decode cushion so a scene ending exactly at a chunk boundary still has a final frame.

Fade handling is chunk-aware. `render_plan_chunked()` passes `apply_fade_in=True` only to the first chunk and `apply_fade_out=True` only to the final chunk. Middle chunks receive neither fade. One-pass renders continue to receive both fades. A 60-second two-chunk smoke render has verified the corrected behavior and concat output.

Speaker lower-third events are also independent. The renderer creates one overlay operation per scheduled occurrence, with that occurrence's own enter/exit timing. This fixes the case where Jason's card around 8:16 could slide away and then reappear because multiple intervals had been combined under the first interval's animation expression.

The three-panel frame filter had a critical ordering bug: its animated frame overlay was referencing `three_left_*` before `_stacked_camera_filter()` defined that label. This produced a misleading FFmpeg “matches no streams” failure, often appearing to implicate speaker lower-thirds. The filter order is now corrected: build the camera panel first, then overlay the animated frame, then stack it with the screen panel.

## Verified commands

Run the tests:

```bash
python -m py_compile long_form/renderer.py long_form/cli.py
git diff --check
python -m unittest tests.long_form_test -v
```

The tests currently pass (5 tests). A three-minute one-pass render after the three-panel fix also completed and verified as 1920x1080 H.264/AAC. A 60-second two-chunk smoke render completed and verified before the latest filter-order fix.

## Current full-render status

The latest completed full render was:

```bash
python -m long_form.cli render \
  --plan output/long_form/Episode_84/edit-plan-final.json \
  --output output/long_form/Episode_84/Episode_84_full_fixed_animation.mp4 \
  --trim-start 4 \
  --trim-end 2 \
  --chunk-seconds 300 \
  --preset veryfast \
  --video-encoder libx264 \
  --overwrite
```

The previous full-render process was interrupted while the three-panel label bug was still present. After fixing the bug, a new full render was started. When resuming, first check whether it is still running and whether the target MP4 exists. Do not assume completion without probing the file.

```bash
ls -lh output/long_form/Episode_84/Episode_84_full_holographic_all_overlays.mp4
ffprobe -v error -show_entries format=duration:stream=codec_name,codec_type,width,height \
  -of json output/long_form/Episode_84/Episode_84_full_holographic_all_overlays.mp4
```

Verified properties:

- Duration: `1166.454362` seconds.
- Video: H.264, 1920x1080, 30fps.
- Audio: AAC, 48kHz.

Latest completed full-render timing: 1,050.46 seconds wall-clock (approximately 17 minutes 30 seconds) for four chunks using `libx264` with the `veryfast` preset. The verified output was 304.04 MiB and 1166.454362 seconds long.

The final two seconds are removed from the source timeline before chunking, so the final chunk receives the only fade-out at the shortened video end. The first four seconds remain trimmed from the opening. No intermediate chunk receives a fade.

The three-panel HyperFrames border asset was regenerated after moving its frame from `left: -6px; width: 452px` to `left: 0px; width: 448px`, keeping both animated outlines inside the 440px camera column.

Speaker lower-third assets now use a per-event filter branch:
`trim=duration=9.1,setpts=PTS-STARTPTS+EVENT_START/TB`. This resets every card to its first frame and prevents the later Tara/Jason cards from inheriting the looped movie's global animation phase.

The recurring CTA toast uses the same reset strategy. For each scheduled event, the renderer trims the six-second HyperFrames CTA, resets its PTS, and shifts it to the event's local timeline. `render_plan_chunked()` passes the chunk offset so toasts scheduled at 420s and 840s appear in the correct chunks. The final verified output is `Episode_84_final_with_cta_v2.mp4`, 1166.454362s, 301.94 MiB; render wall-clock time was 899.68s (approximately 15 minutes).

Current submission output: `Episode_84_final_submission.mp4`. It includes the corrected 448px three-panel camera canvas, matching Inter typography, and removes the 14:11–14:24 dead-air/repeated segment (851–864s on the rendered timeline). Final duration is 1153.453s (19:13.45), 1920×1080 H.264/AAC; the candidate render took 904.53s and the final cut preserves the ending fade-out.

Latest submission output is `Episode_84_final_submission_v2.mp4`, rebuilt from the corrected candidate after confirming both three-panel frame edges are visible and the title/URL use Inter styling. It remains 1153.453s (19:13.45), 1920×1080 H.264/AAC, with the ending fade-out preserved.

Latest output is `Episode_84_final_no_ai_tools_lab.mp4`. The top “AI Tools Lab” text was removed from three-panel scenes while retaining the bottom URL, CTA toasts, borders, lower thirds, trims, and final fade-out. Verified duration: 1153.453s (19:13.45), 1920×1080 H.264/AAC.

## Hardware encoder note

`h264_videotoolbox` is implemented, but this environment returned:

```text
cannot create compression session: -12908
```

Even with `-allow_sw 1`, VideoToolbox was unavailable. Use `libx264` here. On a compatible Mac, test VideoToolbox with a 30-second chunk before starting a full render.

## Known considerations for the next session

1. Check the current full-render process and target file before starting another render.
2. If the render is still active, let it finish; otherwise rerun the hybrid command above.
3. Verify duration/codecs with `ffprobe` before reporting success.
4. Keep the Shorts pipeline under `stacked_script/` unchanged.
5. Do not delete source videos, plans, or HyperFrames assets.
6. If render speed remains insufficient, use `--preset ultrafast` or reduce `--chunk-seconds` to 180. Smaller chunks make recovery easier but increase concat overhead.
7. The current `veryfast`/CRF 20 software encode is much smaller than `ultrafast`; use `ultrafast` only when time is more important than file size.
8. The existing `Episode_84_full_holographic_all_overlays.mp4` was created before the chunk-aware fade fix. Rerender it if the final deliverable must not contain fades at chunk boundaries.
9. The full render that was active while the speaker-card bug was discovered was stopped before completion. Rerender the full episode after this speaker-event fix before reviewing the final output.
10. The lower-third HTML was updated to remove perspective skew and the three-panel URL styling was updated. HyperFrames lint passes; the local runtime check is blocked by the sandbox's socket permission. Regenerate the lower-third PNG/alpha assets and rerender the final video before reviewing these latest visual changes.
