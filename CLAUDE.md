# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Video Stacker is a Python script that converts 2 or 3 landscape videos to portrait format. It combines MP4 files into a single portrait video optimized for YouTube Shorts, TikTok, and Instagram Reels (9:16 aspect ratio, 1080x1920 resolution).

**Modes:**
- **2-video mode**: 50/50 split with center-cropped videos filling entire screen (screen recording top, speaker bottom)
- **3-video mode**: Three equal sections stacked vertically (top/middle/bottom)
- **Multi-cut mode**: Dynamic quick cuts between multiple videos (2-4) with random zoom effects for engaging shorts

## Technology Stack

- **Language**: Python 3.6+
- **Main Dependencies**:
  - `moviepy>=2.0.0` - Video processing and editing
  - `Pillow>=9.2.0` - Image processing for preview generation
  - `numpy` - Array handling for video frames
  - `pathlib` - File path handling
  - `argparse` - Command-line interface
  - `FFmpeg` - Subtitle burning and video processing (automatically installed with MoviePy)
- **Output Format**: MP4 with H.264 video codec and AAC audio codec
- **License**: MIT License (Copyright 2025 Jason Hand)

## Development Setup

### Prerequisites
```bash
pip install -r requirements.txt
# Or install individually:
pip install moviepy pillow streamlit
```

### Running the Application

**Web Interface (Recommended for most users):**
```bash
streamlit run pvg.py
```
Opens a browser-based GUI with drag-and-drop upload, visual selection, and real-time progress.

**Command Line Interface (For automation/scripting):**
```bash
# Interactive mode (legacy)
python stacked_script/stack.py

# Automated batch clip creation from markdown analysis
python create_clips_from_analysis.py transcripts/episode_clip_suggestions.md varied

# Help
python stacked_script/stack.py -h
```

**Standalone Subtitle Burning:**
```bash
python utils/burn_subs.py <video_file> <subtitle_file> [output_file] [video_mode]
# video_mode: 2 or 3 (default: 2) - adjusts caption position
```

## Architecture

The script follows a modular design with clear separation of concerns:

### Core Functions
- `get_video_files()` - Discovers MP4 files in specified directory
- `get_vtt_files()` - Discovers VTT subtitle files in specified directory
- `parse_vtt_file()` - Parses VTT files and converts to subtitle entries
- `extract_vtt_segment()` - Extracts subtitle segments for clips from full VTT file
- `convert_srt_to_ass_with_positioning()` - Converts SRT to ASS with custom styling and positioning
- `wrap_subtitle_text()` - Manually wraps subtitle text to prevent overflow
- `cleanup_subtitle_files()` - Removes temporary .srt files after processing
- `display_menu()` - Interactive UI for video selection
- `get_user_selection()` - Handles user input validation (2 or 3 videos)
- `create_portrait_video()` - Main video processing pipeline with subtitle support
- `create_multi_cut_video()` - Creates portrait videos with dynamic quick cuts and random zoom effects
- `create_layout_preview()` - Generates static image preview with caption styling
- `ask_for_layout_preview()` - Prompts user for layout preview
- `ask_for_preview()` - Prompts for 5-second video preview
- `ask_for_clip_mode()` - Prompts for multiple clip generation (1-3 clips, 30/45/60 seconds)

### Video Processing Pipeline
1. **Input Validation**: Checks for at least 2 MP4 files
2. **Mode Selection**: User chooses 2-video or 3-video mode
3. **User Selection**: Interactive menu for choosing videos
   - 2-video mode: Screen recording (top) + Speaker (bottom)
   - 3-video mode: Top/middle/bottom positions
4. **VTT Detection**: Automatically detects VTT subtitle files in directory
5. **Layout Preview**: Optional static image preview showing exact layout with caption styling
6. **Processing Options**:
   - **Clip Mode**: Create 1-3 clips with customizable duration (30/45/60 seconds)
   - **Preview Mode**: Generate 5-second video preview from a specific timestamp
   - **Full Video Mode**: Create complete portrait video
7. **Duration Sync**: Trims all videos to shortest duration
8. **Resolution Processing**:
   - Target: 1080x1920 (portrait 9:16)
   - **2-video mode**: Each video gets 1/2 height (960px) with center cropping
   - **3-video mode**: Each video gets 1/3 height (640px) with center cropping
   - Maintains aspect ratio with intelligent center cropping (horizontal and vertical)
9. **Subtitle Processing**:
   - Automatically extracts relevant subtitle segments from VTT files for clips
   - Converts to ASS format with custom styling
   - Manually wraps text to prevent overflow
   - Burns subtitles with FFmpeg
10. **Logo Overlay**: Adds logo watermark at upper left (2px from edges, 1/3 section height)
11. **Composition**: Vertical stacking with precise positioning
12. **Export**: 30fps MP4 with optimized codecs (H.264/AAC)
13. **Cleanup**: Automatically removes temporary .srt files after processing
14. **Summary**: Displays comprehensive processing information for all clips

### Key Features
- **Flexible Modes**:
  - 2-video (50/50) or 3-video (33/33/33) stacked layouts
  - Multi-cut mode with dynamic quick cuts and zoom effects
- **Multi-Cut Mode Features**:
  - Random cuts every 2.5-3.5 seconds between source videos
  - **Dynamic speaker-aware cutting**: Real-time audio analysis to show the active speaker
  - Random zoom effects on 50% of segments (1.05x to 1.15x zoom)
  - Weighted video selection (95% Primary, 5% Secondary if labeled)
  - Prevents more than 2 consecutive segments from same video
  - Continuous audio mixing from all sources
  - Creates engaging, dynamic content ideal for YouTube Shorts
- **Optional Title Text**: Burn custom title text at the top of videos (max 50 characters)
  - National 2 Bold font, 80pt, white with black outline
  - Positioned at top center, 100px from top
  - Perfect for labeling shorts and clips
- **Advanced Caption System**:
  - Automatic VTT subtitle extraction and burning
  - Custom styling: 120pt light purple (#ECDDFF) text with dark purple (#34008D) outline
  - Smart text wrapping to prevent overflow
  - Dynamic positioning: 400px from bottom for multi-cut/letterbox mode, 850px for 2-video mode
  - Static preview image shows caption styling before video generation
- **Layout Preview**: Generate a static image preview showing exact cropping, positioning, and caption styling before processing
- **Logo Watermark**: Automatic logo overlay in upper-left corner
- **Interactive Selection**: Easy-to-use menu for choosing which videos go where
- **Smart Resizing**: Maintains aspect ratios with intelligent center cropping (both horizontal and vertical)
- **Audio Preservation**: Keeps audio from all source videos
- **Multiple Output Modes**:
  - Full video generation
  - 5-second video preview at custom timestamps
  - Multiple clips (1-3) with customizable duration (30/45/60 seconds)
- **Optimized Output**: 1080x1920 resolution at 30fps with H.264/AAC codecs
- **Duration Sync**: Automatically trims all videos to match the shortest duration
- **Automatic Cleanup**: Removes temporary subtitle files after processing
- **Processing Summary**: Displays filename, duration, file size, and processing time for all clips
- **Error Handling**: Comprehensive validation and troubleshooting tips
- **User Experience**: Clear progress indicators, confirmations, and interactive prompts

## Common Development Tasks

### Testing the Script
```bash
# Create test directory with sample MP4 files
mkdir test_videos
# Add 2+ MP4 files to test_videos/
python stack.py -d test_videos

# Test 2-video mode with layout preview
python stack.py -d test_videos
# Select 2 videos, generate layout preview

# Test 3-video mode with video preview
python stack.py -d test_videos
# Select 3 videos, generate 5-second video preview

# Test clip generation with subtitles
python stack.py -d test_videos
# Select videos, choose clip mode, specify timestamps
# Add VTT file to directory for automatic subtitle extraction

# Test standalone subtitle burning
python utils/burn_subs.py video.mp4 subtitles.srt output.mp4
```

### Dependencies Management
All dependencies are managed via requirements.txt:
```bash
pip install -r requirements.txt
```

Current dependencies:
- moviepy>=2.0.0
- pillow>=9.2.0
- streamlit>=1.28.0

## File Structure
```
portrait_video_generator/
├── pvg.py                        # Web interface (Streamlit GUI)
├── create_clips_from_analysis.py # Automated clip creation from markdown analysis
├── README.md                     # Project documentation
├── CLAUDE.md                     # This file - Development guidance
├── requirements.txt              # Python dependencies
├── .streamlit/                   # Streamlit configuration
│   └── config.toml              # Upload size limits (2GB default) and settings
├── stacked_script/              # Core video processing engine
│   └── stack.py                 # Main video processing functions
├── utils/                       # Utility scripts
│   └── burn_subs.py            # Standalone subtitle burning utility
├── logos/                       # Brand assets (gitignored)
│   └── logo.png                 # Logo watermark image
├── transcripts/                 # VTT subtitle files (gitignored)
├── source_video/                # Source video files for processing (gitignored)
└── output/                      # Generated portrait videos (gitignored)
```

## Streamlit Web Interface

### Overview
`pvg.py` (Portrait Video Generator) provides a modern browser-based GUI that wraps the core `stack.py` functions without modifying the core logic. This allows users to choose between web interface or CLI based on their needs.

### Architecture
- **No modification to stack.py**: Imports functions directly, preserving CLI functionality
- **Temporary file handling**: Uses `tempfile.mkdtemp()` for uploaded files
- **Session state**: Maintains uploaded videos and outputs across reruns
- **Real-time feedback**: Progress bars and status updates during processing
- **Modern design**: Custom purple color scheme (#34008D and #ECDDFF) matching caption styling

### Key Features
- **Drag-and-drop upload**: Multi-file upload for MP4 videos and VTT subtitles
- **Visual thumbnail selection**: Auto-generates thumbnails from videos at 5-second mark
- **Interactive settings**: Sidebar with all processing options
- **Layout preview**: Displays preview image inline before processing
- **Download buttons**: One-click download for all generated videos
- **Processing summary**: Table view with file sizes and processing times
- **Error handling**: User-friendly error messages with expandable details

### UI Components
1. **Header section**: Title and description
2. **Sidebar**: Settings (video mode, processing options, clip settings)
3. **Upload section**: File uploaders for videos and VTT
4. **Thumbnail display**: Grid view of uploaded videos
5. **Position selection**: Dropdowns for each video position
6. **Generate button**: Triggers processing with progress indicators
7. **Results section**: Download buttons and summary statistics

### Processing Modes Supported
- Full video generation
- 5-second video preview (custom timestamp)
- Multiple clips (1-3 clips with 30/45/60 second durations)
- Layout preview (static image)

### Implementation Notes
- Uses `st.session_state` to persist data across interactions
- Creates temporary directory for uploads (cleaned on exit)
- Imports core functions: `create_portrait_video()`, `create_layout_preview()`, `get_existing_subtitles()`
- Thumbnail generation uses MoviePy's `get_frame()` method
- File size formatting and duration formatting helpers for clean display
- Custom CSS for improved styling and layout

### Configuration
Upload size limits are configured in `.streamlit/config.toml`:
- **Default limit**: 2GB (2000MB)
- **Adjustable**: Edit `maxUploadSize` value in config file
- **Applies to**: Video files and VTT subtitle files
- **Note**: Must restart Streamlit app after changing configuration

Example config:
```toml
[server]
maxUploadSize = 2000  # Size in MB (2GB)
maxMessageSize = 2000
```

## Implementation Details

### 2-Video Mode Center Cropping
The 2-video mode uses intelligent center cropping to fill the entire 1080x1920 screen:
1. Resize video to target width (1080px) maintaining aspect ratio
2. If height > allocated space (960px): crop vertically from center
3. If height < allocated space: resize to fill height, then crop horizontally from center
4. Result: Both videos fill exactly 50% of screen with centered content

### Dynamic Speaker Detection for Multi-Cut Videos
The speaker detection system uses real-time audio analysis to automatically show the active speaker during multi-cut videos (stack.py lines 1029-1144):

**How It Works:**
1. **Audio Analysis Function** (`get_audio_level()` - line 1029):
   - Takes a video clip and time offset as input
   - Extracts 0.5-second audio segment at that time
   - Calculates RMS (Root Mean Square) audio level
   - Returns float value representing audio intensity
   - Returns 0.0 if no audio or if time exceeds clip duration

2. **Dynamic Segment Analysis** (lines 1091-1118):
   - For each 2.5-3.5s segment, samples audio every 0.5s throughout the segment duration
   - Collects audio levels from all webcam videos at multiple points within the segment
   - Calculates average audio level for each webcam across all samples
   - Identifies speakers with audio above threshold (0.02 RMS)
   - Sorts speakers by average audio level (loudest first)

3. **Speaker Selection Logic** (lines 1120-1144):
   - Prioritizes the webcam with highest average audio during that segment
   - Always includes screen video as an option (shows all 3 videos in letterbox)
   - Falls back to screen video if no speakers are active
   - Prevents more than 2 consecutive segments from same video for variety
   - Respects Primary/Secondary video weighting if labeled

**Key Improvements Over Previous Static Approach:**
- **Old**: Pre-analyzed entire video once, checked audio only at segment start
- **New**: Analyzes audio dynamically throughout each segment's full duration
- **Result**: Correctly handles back-and-forth conversations where speaker changes mid-segment

**Debug Output:**
Shows speaker levels and dominant speaker selection for each segment:
```
Segment 1: 0.0s-2.8s (2.8s) - Video 2 (WEBCAM) [speakers: Video 2: 0.0245, Video 3: 0.0098] ← DOMINANT
```

### Caption System Architecture

**Why Manual Text Wrapping?**
The caption system uses manual text wrapping because ASS format's automatic wrapping and margin settings were unreliable. After multiple attempts using MarginL, MarginR, and WrapStyle parameters, captions still overflowed off screen edges. The solution is to pre-wrap text at the character level before writing to ASS format.

**Caption Styling Specifications** (stack.py lines 544-578, utils/burn_subs.py lines 91-112):
- **Font**: National 2, 120pt
- **Primary Color**: #ECDDFF (light purple/lavender)
  - RGB: (236, 221, 255)
  - BGR for ASS: &HFFDDEC
- **Outline Color**: #34008D (dark purple)
  - RGB: (52, 0, 141)
  - BGR for ASS: &H8D0034
- **Position**: Dynamic based on video mode
  - **Multi-cut mode (letterbox layout)**: 400px from bottom (MarginV=400) - positioned in bottom third of video, well below center
  - **2-video mode**: 850px from bottom (MarginV=850, which is 1070px from top) - captions in lower half
  - **3-video mode**: 750px from bottom (MarginV=750, which is 1170px from top) - positioned lower in bottom section
  - Optimized positioning ensures captions don't overlap with key video content while remaining visible
- **Text Wrapping**: Manual at ~22 characters per line
- **Padding**: 80px left and right margins
- **Alignment**: Center-aligned (Alignment=2)
- **WrapStyle**: 0 (disabled - manual wrapping used instead)
- **Outline Width**: 3px
- **Shadow**: 3px

**Manual Text Wrapping Function** (`wrap_subtitle_text()` - stack.py line 510, utils/burn_subs.py line 57):
```python
def wrap_subtitle_text(text, max_chars_per_line=22):
    """Manually wrap subtitle text to prevent overflow

    Args:
        text: The subtitle text to wrap
        max_chars_per_line: Maximum characters per line (adjusted for 120pt font)

    Returns:
        Wrapped text with \\N line breaks for ASS format
    """
    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        word_length = len(word)
        # +1 for space before word
        test_length = current_length + word_length + (1 if current_line else 0)

        if test_length <= max_chars_per_line:
            current_line.append(word)
            current_length = test_length
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
            current_length = word_length

    if current_line:
        lines.append(' '.join(current_line))

    return '\\N'.join(lines)
```

**Key Implementation Notes**:
- Max characters per line set to 22 (conservative for 120pt font at 1080px width)
- Wrapping happens at word boundaries to prevent mid-word breaks
- Uses `\\N` for ASS format line breaks (not `\n`)
- Text is collapsed to single line first (`replace('\n', ' ')`) before wrapping
- Applied BEFORE writing to ASS file, not relying on ASS automatic wrapping

**VTT File Processing** (`parse_vtt_file()` - stack.py line 128):
- Automatically detects VTT files in directory
- Parses timestamp format: `HH:MM:SS.mmm --> HH:MM:SS.mmm`
- Extracts text content and converts to subtitle entries
- Handles WEBVTT header and metadata

**Segment Extraction for Clips** (`extract_vtt_segment()` - stack.py line 176):
- Takes full VTT file covering entire unclipped video
- Extracts only the subtitle entries within clip's time range
- Adjusts timestamps to start at 0:00 for the clip
- Writes temporary SRT file for FFmpeg processing
- No manual editing required from user

**ASS Conversion with Positioning** (`convert_srt_to_ass_with_positioning()` - stack.py line 544):
- Converts SRT to ASS (Advanced SubStation Alpha) format
- Sets PlayResX: 1080, PlayResY: 1920 for portrait format
- Applies custom styling with BGR color values
- Uses manual text wrapping to prevent overflow
- Returns path to temporary ASS file for FFmpeg

**FFmpeg Subtitle Burning**:
- Uses `ass` filter to burn subtitles: `f"ass={str(ass_path.absolute())}"`
- Applied during video processing via ffmpeg_params
- Temporary ASS files created and cleaned up automatically

**Automatic Cleanup** (`cleanup_subtitle_files()` - stack.py line 634):
- Removes all temporary .srt files after processing completes
- Displays cleanup progress with file count
- Runs automatically after all clips finish processing
- User sees cleanup confirmation message

**Layout Preview with Captions** (`create_layout_preview()` - stack.py line 222):
- Shows sample caption text: "This is a sample caption to preview the text styling and position"
- Uses PIL ImageDraw to render text with identical styling
- Position: 850px from bottom (matching video captions)
- Demonstrates text wrapping and color scheme
- Quick generation (~2 seconds) for iterating on caption styling

### Logo Positioning
- Size: 1/3 of top section height (maintains aspect ratio)
- Position: (2px, 2px) from top-left corner
- File: `logos/logo.png` (if present)
- Applied to all videos in composite

### Clip Mode Processing
- User can create 1-3 clips per session
- Duration options: 30, 45, or 60 seconds
- Each clip gets extracted subtitle segment from full VTT file
- Processing info collected for all clips and displayed at end:
  - Filename
  - Duration
  - File size
  - Processing time
- Temporary subtitle files cleaned up after all clips complete

## Troubleshooting

Common issues and solutions:

1. **MoviePy not installed**: Run `pip install -r requirements.txt`
2. **Pillow not installed**: Run `pip install pillow`
3. **FFmpeg issues**: MoviePy should install FFmpeg automatically, but you may need to install it manually on some systems
4. **VTT subtitle extraction fails**:
   - Ensure your VTT file is properly formatted
   - Check that the VTT file covers the time range you're trying to clip
   - Verify the VTT file uses standard timestamp format (HH:MM:SS.mmm or MM:SS.mmm)
5. **Captions cut off at edges**:
   - The script uses manual text wrapping at 22 characters per line
   - If captions still overflow, reduce `max_chars_per_line` in `wrap_subtitle_text()`
   - Check that font size is 120pt and margins are 80px (left/right)
6. **Invalid video files**: Ensure all files are valid MP4 format
7. **Insufficient disk space**: Check available storage before processing
8. **Logo not appearing**: Ensure logo file exists at `logos/logo.png`

## Code Quality Guidelines

When modifying this codebase:

1. **Test caption changes visually**: Always generate a layout preview or video preview to verify caption positioning and text wrapping before claiming success
2. **Maintain manual text wrapping**: Don't rely on ASS format's automatic wrapping - it's unreliable
3. **Preserve color consistency**: Use #ECDDFF and #34008D across all caption-related code
4. **Keep cleanup automatic**: Temporary files should always be removed without user intervention
5. **Display comprehensive summaries**: Show all processing info at the end, not incrementally
6. **Handle errors gracefully**: Provide clear error messages and recovery suggestions
7. **Maintain modularity**: Keep functions focused on single responsibilities
8. **Document color formats**: Always include both RGB and BGR values for ASS colors

## Recent Changes History

- **Dynamic speaker-aware cutting**: Improved speaker detection for multi-cut videos (stack.py lines 1091-1144)
  - Replaced static pre-analysis with dynamic real-time audio analysis
  - Samples audio every 0.5s throughout each segment's duration (not just at start)
  - Calculates average RMS audio level for each webcam during the segment
  - Prioritizes the loudest/most active speaker automatically
  - Handles back-and-forth conversations correctly by tracking speaker changes in real-time
  - Adjusted audio threshold from 0.01 to 0.02 RMS to reduce false positives
  - Shows audio levels and dominant speaker in debug output
- **Caption position adjustment**: Moved captions to 400px from bottom (stack.py line 1526)
  - Positions captions in bottom third of video, well below center
  - Optimized for letterbox layout in multi-cut mode (3-section layout)
  - Ensures captions are clearly separated from center content and positioned near bottom
- **VTT-clip-finder agent style update**: Changed default tone to be less clickbaity and more straightforward (.claude/agents/vtt-clip-finder.md lines 76-90)
  - Titles now use descriptive, factual language instead of sensational phrases
  - Removed clickbait patterns like "Secret Weapon", "Nobody's Talking About", "Just Got Exposed"
  - Descriptions focus on technical content and what's demonstrated, not hype or rhetorical hooks
  - Maintains professional, educational tone rather than promotional style
  - Applied to all future YouTube Shorts generation
- **Random zoom effects in multi-cut mode**: Added dynamic zoom feature to multi-cut videos (stack.py lines 1073-1189)
  - 50% chance of zoom per segment (1.05x to 1.15x zoom)
  - Creates more engaging and natural-looking transitions between cuts
  - Zoom applied via resize and center-crop to maintain 1080x1920 portrait format
  - Audio preserved through zoom transformations
- **Optional title text feature**: Added ability to burn custom title text at top of videos (max 50 characters)
  - Uses National 2 Bold font, 80pt, white with black outline
  - Positioned at top center, 100px from top
  - Available in Streamlit interface for all video modes
- **Dynamic caption positioning**: Captions positioned at 850px (2-video) and 750px (3-video) from bottom for optimal placement
- **Font change**: Updated from Arial to National 2 font (stack.py line 578, utils/burn_subs.py line 112)
- **Streamlit status elements**: Added st.status() containers and spinners for better progress feedback
- **Caption overflow fix**: Implemented manual text wrapping at 22 chars/line (stack.py line 510, utils/burn_subs.py line 57)
- **Caption position adjustment**: Moved from MarginV=900 to MarginV=850 for better visibility in 2-video mode
- **Font size increase**: Increased from 96pt to 120pt for better readability
- **Color scheme update**: Changed to #ECDDFF primary and #34008D outline for aesthetic consistency
- **Processing summary**: Modified to collect all clip info and display comprehensive summary at end
- **Automatic cleanup**: Added `cleanup_subtitle_files()` to remove temporary .srt files
- **Layout preview enhancement**: Added sample caption rendering to preview image
