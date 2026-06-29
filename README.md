# Portrait Video Generator

Transform landscape videos into portrait format content for social media platforms like YouTube Shorts, TikTok, and Instagram Reels. Stack 2-4 video sources vertically with professional styling, captions, and custom branding.

## Recommended Workflow: Claude Code + VTT Clip Finder

The primary way to use this project is through **Claude Code** with the built-in `vtt-clip-finder` agent. The agent reads a VTT transcript, identifies the best moments for YouTube Shorts, and writes a structured markdown file that drives automated clip generation — no manual timestamp hunting required.

### Prerequisites

- [Claude Code](https://claude.ai/code) installed and authenticated
- Python 3.8+ with dependencies installed (`pip install -r requirements.txt`)
- FFmpeg available on your PATH

## Installation

```bash
git clone https://github.com/jasonhand/portrait_video_generator.git
cd portrait_video_generator
pip install -r requirements.txt
```

### File Layout

```
portrait_video_generator/
├── pvg.py                        # Web interface (Streamlit GUI)
├── create_clips_from_analysis.py # Automated clip creation from markdown analysis
├── requirements.txt
├── .streamlit/
│   └── config.toml              # Upload size limits (2GB default)
├── stacked_script/
│   └── stack.py                 # Core video processing functions
├── utils/
│   └── burn_subs.py            # Standalone subtitle burning utility
├── logos/                       # Brand assets — create locally, not tracked by git
├── transcripts/                 # VTT files and clip-analysis markdown — not tracked
├── source_video/                # Source MP4s for processing — not tracked
└── output/                      # Generated portrait videos — not tracked
```

Place your logo at `logos/logo.png` to enable the watermark overlay.

### Step-by-Step

**1. Add your source videos**

Copy your MP4 files into the `source_video/` directory:

```bash
mkdir -p source_video
cp /path/to/your/recordings/*.mp4 source_video/
```

The tool works best with 2–3 video sources recorded simultaneously — for example, a screen recording and one or two webcam feeds. Multi-cut mode analyzes audio levels automatically to determine which speaker is active at any moment.

**Naming your files:** If all your source videos share a common word or phrase, include that same phrase in your VTT filename and the script will match them automatically. For example, videos named `interview_camera.mp4` and `interview_screen.mp4` will be picked up when your VTT is named `interview.vtt`. If no match is found, the script falls back to using all MP4s in `source_video/`, so generic filenames work fine too.

**2. Add your VTT transcript**

Copy your VTT subtitle file into the `transcripts/` directory:

```bash
mkdir -p transcripts
cp /path/to/your/subtitles.vtt transcripts/
```

Your VTT file should cover the full duration of the recording and use standard timestamp format (`HH:MM:SS.mmm --> HH:MM:SS.mmm`). Most recording platforms (StreamYard, Riverside, Descript, YouTube auto-captions) can export VTT directly.

**3. Open Claude Code in this project directory**

```bash
cd portrait_video_generator
claude
```

**4. Invoke the vtt-clip-finder agent**

In the Claude Code prompt, type:

```
@vtt-clip-finder analyze transcripts/Episode74.vtt
```

Or ask naturally:

```
Use the vtt-clip-finder agent to analyze transcripts/Episode74.vtt and generate YouTube Shorts clips
```

The agent will:
- Read the full VTT transcript
- Identify the 5 best segments (30s–2:59 each) with strong opening hooks
- Write clip suggestions with titles, descriptions, timestamps, and hashtags to `transcripts/Episode74_clip_suggestions.md`

**5. Review the clip suggestions**

Open `transcripts/Episode74_clip_suggestions.md` and review the proposed clips. Edit any titles, timestamps, or descriptions before generating video.

**6. Generate all clips**

Ask Claude Code to start generation:

```
Generate all clips for Episode 74
```

Or run directly from the terminal:

```bash
python create_clips_from_analysis.py transcripts/Episode74_clip_suggestions.md varied
```

Claude Code monitors progress and updates the markdown file with a **Generated Clips** table when all clips are complete.

**7. Find your output files**

Finished clips are saved to `output/<name>/` where `<name>` is derived from your markdown filename. For example, if you ran the agent on `transcripts/interview.vtt`, look in:

```
output/interview/
  interview_clip1_multi-cut.mp4
  interview_clip2_multi-cut.mp4
  ...
```

**8. Review and trim**

Play the clips in `output/Episode74/`. If you need to trim the start or end of any clip, ask Claude Code:

```
Cut the first second from Episode74_clip1_multi-cut.mp4
```

---

### What the vtt-clip-finder Agent Does

The agent is configured specifically for this project and applies the following rules automatically:

- **Clip length**: 30 seconds minimum, 2:59 maximum
- **No overlap**: clips never share timestamp ranges
- **Hook-first**: opening 5 seconds must be strong enough to stop a scroll
- **Tone**: descriptive and factual — no clickbait phrasing
- **Output**: saves directly to `transcripts/<EpisodeName>_clip_suggestions.md` in the format `create_clips_from_analysis.py` expects

### Clip Suggestions File Format

The generated markdown drives video creation. Each clip section looks like:

```markdown
## CLIP #1: Title Here

**Timestamp**: 00:07:47.211 → 00:09:18.763 (Duration: 92s / 1:32)
**Why it works**: ...

**Title:**
YouTube title here

**Description:**
Three-paragraph YouTube description...

**Hashtags:**
#Tag1 #Tag2 ...
```

After generation, a **Generated Clips** table is appended automatically:

```markdown
## Generated Clips

| Clip | Title | Timestamp | Duration | File | Size |
|------|-------|-----------|----------|------|------|
| 1    | ...   | ...       | ...      | ...  | ...  |
```

---

## Alternative: Web Interface

For one-off processing or when you don't have a VTT transcript:

```bash
streamlit run pvg.py
```

Upload 2–4 MP4 files, assign positions, configure settings, and download the result. Supports files up to 2GB (configurable in `.streamlit/config.toml`).

### Web Interface Workflow

1. Upload 2–4 MP4 files and an optional VTT subtitle file
2. Select video mode (2, 3, or 4 stacked videos)
3. Assign each video to a position
4. Choose zoom & crop or letterbox display per video
5. Select processing mode: full video, clips (30/45/60s), or 5-second preview
6. Optionally add a burned-in title (max 50 characters)
7. Click **Generate** and download the result

---

## Alternative: CLI

For scripting or automation without Claude Code:

```bash
# Batch clip creation from a markdown analysis file
python create_clips_from_analysis.py transcripts/episode_clip_suggestions.md varied

# Standalone subtitle burning
python utils/burn_subs.py input_video.mp4 subtitles.vtt output_video.mp4
```

### Multi-Cut Mode (Python API)

```python
from stacked_script.stack import create_multi_cut_video

create_multi_cut_video(
    video_paths=[video1, video2, video3],
    output_path="output.mp4",
    start_time=0.0,
    duration=180.0,
    subtitle_path="subtitles.vtt",
    title_text=None
)
```

---

## Features

### Video Layouts
- **2-video mode**: 50/50 split — screen recording top, speaker bottom
- **3-video mode**: Three equal sections stacked vertically
- **4-video mode**: Four equal sections for multi-camera setups
- **Multi-cut mode**: Dynamic quick cuts with speaker-aware switching, random zoom effects (1.05x–1.15x on 50% of segments), and letterbox layout for screen + webcam content

### Caption System
- Automatic VTT extraction and burning via FFmpeg
- National 2 font, 120pt, light purple (#ECDDFF) with dark purple (#34008D) outline
- Manual text wrapping at ~22 characters per line
- Positioning: 850px from bottom (2-video), 750px (3-video), 400px (multi-cut)

### Audio
- Audio sourced directly from webcam files via FFmpeg `filter_complex amix`
- Continuous mixed audio across all source videos throughout the full clip duration
- Speaker-aware cutting uses real-time RMS analysis (sampled every 0.5s per segment)

### Branding
- Logo watermark at upper-left (`logos/logo.png`)
- Optional burned-in title text per clip (National 2 Bold, 80pt)

---

## Technical Specifications

| Property | Value |
|----------|-------|
| Output resolution | 1080 × 1920 (9:16) |
| Frame rate | 30 FPS |
| Video codec | H.264 (libx264) |
| Audio codec | AAC 192k |
| 2-video section | 1080 × 960px |
| 3-video section | 1080 × 640px |
| 4-video section | 1080 × 480px |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No audio in output | Webcam files must be in `source_video/` — screen recordings have no audio |
| MoviePy not installed | `pip install -r requirements.txt` |
| FFmpeg issues | Install FFmpeg manually if auto-install fails |
| VTT extraction fails | Verify VTT uses standard format: `HH:MM:SS.mmm --> HH:MM:SS.mmm` |
| Captions overflow edges | Reduce `max_chars_per_line` in `wrap_subtitle_text()` in `stack.py` |
| Logo not appearing | Ensure file exists at `logos/logo.png` |
| Clips generated with wrong video | Rename your MP4s to share a common word with your VTT filename, or remove unrelated MP4s from `source_video/` — the script uses all files there as a fallback |

---

## License

MIT License — Copyright 2026 Jason Hand
