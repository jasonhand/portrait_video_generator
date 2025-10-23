# Portrait Video Generator

Transform landscape videos into portrait format content for social media platforms like YouTube Shorts, TikTok, and Instagram Reels. Stack 2-4 video sources vertically with professional styling, captions, and custom branding.

## ✨ Features

### 🎬 Flexible Video Layouts
- **2-video mode**: 50/50 split - perfect for screen recording + speaker view
- **3-video mode**: Three equal sections stacked vertically
- **4-video mode**: Four equal sections - ideal for multi-camera setups
- **Per-video display settings**: Choose zoom & crop or letterbox independently for each video source
- **Smart resizing**: Maintains aspect ratios with intelligent center cropping

### 📝 Advanced Caption System
- **Automatic VTT subtitle extraction and burning**
- **Custom styling**: 120pt light purple (#ECDDFF) text with dark purple (#34008D) outline
- **Smart text wrapping** to prevent overflow
- **Optimal positioning**: 850px from bottom for maximum visibility
- **Preview captions** in layout preview before processing

### 🎨 Professional Branding
- **Custom watermark overlay** in upper-left corner
- **Optional burned-in titles** for each clip
- **Customizable brand colors** throughout the interface
- **Layout preview generator** to verify styling before processing

### 🎯 Multiple Output Modes
- **Full video generation**: Process entire videos with automatic duration sync
- **Clip mode**: Create 1-3 clips with customizable duration (30/45/60 seconds)
- **Video preview**: Generate 5-second previews at custom timestamps
- **Batch processing**: Create multiple clips in a single session

### 🚀 Modern Web Interface
- **Drag-and-drop video upload** (supports files up to 2GB)
- **Visual thumbnail selection** for easy video identification
- **Real-time progress indicators** during processing
- **Inline video preview** with size-optimized display
- **One-click download** for all generated content

## 🚀 Quick Start

### Prerequisites
- **Python 3.8+** ([download here](https://www.python.org/downloads/))
- **Git** (optional, for cloning the repository)

### Installation

1. **Clone or download this repository**:
   ```bash
   git clone https://github.com/yourusername/portrait_video_generator.git
   cd portrait_video_generator
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   This installs:
   - `moviepy` - Video processing engine
   - `pillow` - Image generation for previews
   - `streamlit` - Modern web interface
   - `FFmpeg` - Automatically installed with MoviePy for subtitle burning

### Launch the Web Interface

```bash
streamlit run pvg.py
```

This opens a browser window with the full-featured GUI. The interface provides:

- **Drag-and-drop video upload** (MP4 files up to 2GB each)
- **VTT subtitle file upload** for automatic caption burning
- **Video mode selection** (2, 3, or 4 videos)
- **Visual thumbnail selection** to assign videos to positions
- **Per-video display settings** (zoom & crop or letterbox)
- **Processing options**:
  - Generate full video
  - Create 1-3 clips with custom start times and durations
  - Generate 5-second preview
- **Optional burned-in titles** for each clip
- **Real-time progress tracking**
- **Instant preview and download**

### Upload Size Configuration

Default upload limit is 2GB per file. To change this, edit `.streamlit/config.toml`:

```toml
[server]
maxUploadSize = 2000  # Size in MB (2GB default)
```

## 📖 Usage Guide

### Basic Workflow

1. **Launch the app**: `streamlit run pvg.py`
2. **Upload videos**: Drag and drop 2-4 MP4 files
3. **Upload captions** (optional): Add a VTT subtitle file
4. **Select video mode**: Choose how many videos to stack (2, 3, or 4)
5. **Assign positions**: Use dropdown menus to select which video goes where
6. **Configure display settings**: For each video, choose zoom & crop (default) or letterbox
7. **Choose processing mode**:
   - **Full Video**: Process entire videos
   - **Clips**: Create 1-3 clips with specified start times and durations (30/45/60s)
8. **Add titles** (optional): Enter custom text to burn into each clip
9. **Generate**: Click the button and wait for processing
10. **Download**: Get your finished portrait videos

### Advanced: Standalone Subtitle Burning

For burning subtitles into existing videos:

```bash
python utils/burn_subs.py input_video.mp4 subtitles.vtt output_video.mp4
```

## 🎬 How It Works

The Portrait Video Generator uses a multi-stage processing pipeline:

### 1. Video Upload & Analysis
- Upload 2-4 landscape MP4 video files
- System extracts thumbnails for visual identification
- Detects video dimensions, duration, and codec information

### 2. Layout Configuration
- **Select video mode**: 2, 3, or 4 videos
- **Assign positions**: Choose which video appears in each slot
- **Configure display per video**:
  - **Zoom & Crop** (default): Fills allocated space completely by center-cropping
  - **Letterbox**: Fits entire video with black bars if needed

### 3. Caption Processing (Optional)
- Upload VTT subtitle file covering the full video timeline
- For clips: System automatically extracts relevant subtitle segments
- Converts to ASS format with custom styling:
  - 120pt Arial font
  - Light purple text (#ECDDFF) with dark purple outline (#34008D)
  - Positioned 850px from bottom for optimal mobile viewing
  - Smart text wrapping prevents overflow

### 4. Video Processing
The processing engine (`stacked_script/stack.py`) handles:

- **Resolution normalization**:
  - Target output: 1080x1920 (9:16 portrait)
  - 2-video mode: 960px height per video (50/50 split)
  - 3-video mode: 640px height per video (33/33/33 split)
  - 4-video mode: 480px height per video (25/25/25/25 split)
- **Intelligent cropping**: Maintains aspect ratios with center-based crop
- **Duration sync**: Automatically trims to shortest video length
- **Subtitle burning**: FFmpeg integration for high-quality caption rendering
- **Watermark overlay**: Adds custom logo in upper-left corner (if provided)
- **Title burning**: Optional text overlay for clip identification
- **Audio mixing**: Preserves audio from all source videos

### 5. Output & Download
- **File naming**:
  - Full video: `{name}_portrait_stacked.mp4`
  - Clips: `{name}_clip1_30s.mp4`, `{name}_clip2_45s.mp4`, etc.
  - Preview: `{name}_preview.mp4`
- **Format**: H.264 video codec, AAC audio codec, 30fps
- **Quality**: Optimized for social media platforms
- **Summary**: Processing time, file size, and duration for each output

## 📐 Technical Specifications

### Output Format
- **Resolution**: 1080 x 1920 pixels (Full HD Portrait)
- **Aspect Ratio**: 9:16 (optimized for mobile platforms)
- **Frame Rate**: 30 FPS
- **Video Codec**: H.264 (libx264) with optimized encoding
- **Audio Codec**: AAC
- **Background Color**: #ECDDFF (light purple, between video sections)

### Video Section Dimensions
- **2-video mode**: 1080 x 960px per video (50/50 split)
- **3-video mode**: 1080 x 640px per video (33/33/33 split)
- **4-video mode**: 1080 x 480px per video (25/25/25/25 split)

### Caption Styling
- **Font**: Arial, 120pt bold
- **Text Color**: #ECDDFF (light purple/lavender)
- **Outline**: #34008D (dark purple), 3px width
- **Position**: 850px from bottom (optimized for 9:16 mobile viewing)
- **Text Wrapping**: Automatic at ~22 characters per line
- **Alignment**: Center-aligned with 80px left/right margins
- **Shadow**: 3px offset for enhanced readability

### System Requirements
- **Python**: 3.8 or higher
- **Dependencies**:
  - `moviepy>=2.0.0` - Video processing engine
  - `pillow>=9.2.0` - Image processing
  - `streamlit>=1.28.0` - Web interface
  - `FFmpeg` - Automatically installed with MoviePy
- **Input**: MP4 video files (2-4 required)
- **Optional**: VTT subtitle files, PNG/JPG watermark logo
- **Storage**: Sufficient disk space for processing (at least 2x source file sizes)

## 📄 License

MIT License - Copyright 2025 Jason Hand

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

---

**Made with ❤️ for content creators everywhere**

*Star this project on GitHub if you find it useful!*
