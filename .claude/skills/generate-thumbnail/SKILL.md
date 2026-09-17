---
name: generate-thumbnail
description: Generates a thumbnail PNG for a long-form episode as a side-by-side screenshot of its two webcam sources, with the ai_tl_logo watermark and a holographic-styled, left-aligned title overlaid. Use when the user asks to create or regenerate a thumbnail for a long-form episode.
disable-model-invocation: true
---

# Generate Thumbnail

Use the isolated `long_form` CLI. Never call or modify the Shorts generator, transcript suggestions, or portrait rendering functions. The long-form editor may use the shared `ai_tl_logo` asset, but does not alter Shorts behavior.

The episode name and title text are supplied in `$ARGUMENTS`. If either is missing, ask for it before running commands.

## Workflow

1. Identify the source directory containing the episode's raw webcam MP4s (usually `source_video/`, matching the same convention as `analyze`). If the episode has more than one webcam pair (e.g. rerecorded segments), ask the user which one to use.
2. Run the thumbnail command:

   ```bash
   python -m long_form.cli thumbnail \
     --input-dir source_video \
     --episode "<episode>" \
     --title "<episode title text>" \
     --output "output/long_form/<episode>/<episode>_thumbnail.png"
   ```

   This finds the episode's two webcam sources (any screen-share files present are ignored), captures a synchronized frame from each (defaulting to the midpoint of their common overlap), and places them side by side. Use `--at SECONDS` for a different moment (seconds into the synchronized window, same timeline as the edit plan).

3. Report the resulting PNG path and file size. Generation is cheap (no multi-minute render), so no approval gate is needed — just let the user ask for a regenerate with a different `--at` or `--title` if they aren't happy with the result.

## Notes

- Layout: the two webcam frames are center-cropped to fill the left and right halves of a 1920x1080 canvas (960x1080 each), left webcam first in filename sort order.
- The title overlay is rendered via a HyperFrames composition (`long_form/hyperframes/thumbnail-title/`) reusing the same holographic gradient-border styling as the long-form lower-thirds; the title text is left-aligned inside the card. The rendered title frame is then composited onto the split-screen screenshot in Python.
- The `ai_tl_logo` is placed in the upper-right corner by the compositor, cropped/scaled the same way as the corner watermark in final long-form renders.
- If the render step fails, check that `npx` and Node.js are available; the CLI shells out to a pinned `hyperframes@0.8.27`.
