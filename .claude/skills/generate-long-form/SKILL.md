---
name: generate-long-form
description: Generates an experimental 16:9 long-form edit from synchronized webcam and screen-share MP4 sources. Use when the user asks to create, preview, or render a long-form episode from files in source_video/.
disable-model-invocation: true
---

# Generate Long-Form Video

Use the isolated `long_form` CLI. Never call or modify the Shorts generator, transcript suggestions, or portrait rendering functions. The long-form editor may use the shared `ai_tl_logo` asset, but does not alter Shorts behavior.

The episode name is supplied in `$ARGUMENTS`. If it is missing, ask for it before running commands.

## Workflow

1. Define these paths from the episode name:
   - Plan: `output/long_form/<episode>/edit-plan.json`
   - Preview: `output/long_form/<episode>/<episode>_preview.mp4`
   - Final: `output/long_form/<episode>/<episode>_long_form.mp4`
2. Analyze the synchronized recordings:

   ```bash
   python -m long_form.cli analyze --input-dir source_video --episode "<episode>" --plan "output/long_form/<episode>/edit-plan.json"
   ```

3. Report the matched screen/webcam files, common duration, seed, and scene-type counts. Stop and explain any source-classification error; use `--screen PATH` only after identifying the intended screen file from the filenames or asking the user.
4. Render a two-minute preview from the saved plan:

   ```bash
   python -m long_form.cli render --plan "output/long_form/<episode>/edit-plan.json" --output "output/long_form/<episode>/<episode>_preview.mp4" --preview-seconds 120
   ```

5. Give the user the preview path and ask them to review scene choices, speaker framing, screen legibility, PiP placement, synchronization, and audio. Do not begin the full render until they approve it.
6. After approval, render from the same plan:

   ```bash
   python -m long_form.cli render --plan "output/long_form/<episode>/edit-plan.json" --output "output/long_form/<episode>/<episode>_long_form.mp4"
   ```

7. Monitor the process until it finishes. Report the final path, duration, resolution, codecs, size, and edit-plan path from the CLI verification output.

## Safety and reruns

- Do not pass `--overwrite` without explicit user approval when an output already exists.
- Screen-source audio is excluded by default. Use `--include-screen-audio` only when the user confirms that unique program audio is needed.
- Treat the JSON edit plan as the source of truth: previews and final renders must use the same plan.
- If a render fails, preserve the error output and rerun with `--keep-workdir` to inspect the generated FFmpeg filter graph.
