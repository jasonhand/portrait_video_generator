#!/usr/bin/env python3
"""
Streamlit web interface for Video Stacker - Modern UI
Provides a user-friendly GUI for creating portrait videos from landscape sources
"""

import streamlit as st
from pathlib import Path
import tempfile
import shutil
from datetime import datetime
import time
from PIL import Image
import base64

# Import functions from the main script
from stacked_script.stack import (
    create_portrait_video,
    create_multi_cut_video,
    create_layout_preview,
    get_vtt_files,
    trim_video
)

# Page configuration
st.set_page_config(
    page_title="Portrait Video Generator",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Modern CSS styling with custom color palette
st.markdown("""
    <style>
    /* Global Styles */
    .main {
        background: #34008D;
        color: #ECDDFF;
    }

    /* Block container styling */
    .block-container {
        background: #34008D;
        color: #ECDDFF;
    }

    /* Header Styles */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #ECDDFF;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    .header-logo {
        width: 150px;
        height: 150px;
        object-fit: contain;
    }

    .subtitle {
        font-size: 1.1rem;
        color: #ECDDFF;
        margin-bottom: 2rem;
        opacity: 0.9;
    }

    /* General text color */
    .stMarkdown, p, span, div, label {
        color: #ECDDFF !important;
    }

    h1, h2, h3, h4, h5, h6 {
        color: #ECDDFF !important;
    }

    /* Card Styles */
    [data-testid="stExpander"] {
        background: #ECDDFF;
        border-radius: 12px;
        border: 1px solid #A960FF;
        box-shadow: 0 1px 3px 0 rgba(169, 96, 255, 0.3);
        margin-bottom: 1rem;
    }

    [data-testid="stExpander"] * {
        color: #8000FF !important;
    }

    /* Upload Zone Styles */
    [data-testid="stFileUploader"] {
        background: #ECDDFF;
        border: 2px dashed #A960FF;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
    }

    [data-testid="stFileUploader"]:hover {
        border-color: #FF0080;
        background: #ECDDFF;
    }

    [data-testid="stFileUploader"] * {
        color: #8000FF !important;
    }

    [data-testid="stFileUploader"] label {
        color: #8000FF !important;
    }

    [data-testid="stFileUploader"] section {
        color: #8000FF !important;
    }

    /* Button Styles */
    .stButton > button {
        background: linear-gradient(135deg, #A960FF 0%, #FF0080 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        transition: all 0.3s;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(169, 96, 255, 0.4);
        background: linear-gradient(135deg, #FF0080 0%, #A960FF 100%);
    }

    /* Tab Styles */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(169, 96, 255, 0.15);
        padding: 8px;
        border-radius: 12px;
        box-shadow: 0 1px 3px 0 rgba(169, 96, 255, 0.3);
        border: 1px solid #A960FF;
    }

    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: 600;
        color: #ECDDFF !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #A960FF 0%, #FF0080 100%);
        color: white !important;
    }

    /* Info Box Styles */
    .info-box {
        background: #ECDDFF;
        border: 1px solid #A960FF;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        color: #8000FF;
    }

    .info-box * {
        color: #8000FF !important;
    }

    .success-box {
        background: #ECDDFF;
        border: 1px solid #00CAFF;
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        color: #8000FF;
    }

    .success-box * {
        color: #8000FF !important;
    }

    /* Status Indicator */
    .status-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 16px;
        font-size: 0.875rem;
        font-weight: 600;
    }

    .status-ready {
        background: rgba(0, 202, 255, 0.2);
        color: #00CAFF;
    }

    /* Video Preview Card */
    .video-card {
        background: rgba(169, 96, 255, 0.1);
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
        border: 1px solid #A960FF;
        display: flex;
        align-items: center;
        gap: 1rem;
    }

    /* Input fields - default dark background */
    input, textarea, select {
        background-color: rgba(169, 96, 255, 0.15) !important;
        color: #ECDDFF !important;
        border: 1px solid #A960FF !important;
    }

    /* Selectbox specific styling - darker text for better readability */
    [data-baseweb="select"] {
        color: #8000FF !important;
    }

    [data-baseweb="select"] * {
        color: #8000FF !important;
    }

    /* Selectbox value text */
    [data-baseweb="select"] > div {
        color: #8000FF !important;
    }

    /* Selectbox dropdown menu */
    [role="listbox"] {
        background-color: #ECDDFF !important;
    }

    [role="option"] {
        color: #8000FF !important;
    }

    [role="option"] * {
        color: #8000FF !important;
    }

    [role="option"] span {
        color: #8000FF !important;
    }

    [role="option"] div {
        color: #8000FF !important;
    }

    [role="option"]:hover {
        background-color: rgba(169, 96, 255, 0.2) !important;
        color: #34008D !important;
    }

    [role="option"]:hover * {
        color: #34008D !important;
    }

    /* Dropdown popover menu items */
    [data-baseweb="popover"] {
        background-color: #ECDDFF !important;
    }

    [data-baseweb="popover"] * {
        color: #8000FF !important;
    }

    [data-baseweb="popover"] li {
        color: #8000FF !important;
    }

    [data-baseweb="popover"] [role="option"] {
        color: #8000FF !important;
    }

    /* Dropdown list items */
    ul[role="listbox"] li {
        color: #8000FF !important;
    }

    ul[role="listbox"] li * {
        color: #8000FF !important;
    }

    /* Input fields inside expanders (light background) */
    [data-testid="stExpander"] input,
    [data-testid="stExpander"] textarea,
    [data-testid="stExpander"] select {
        background-color: white !important;
        color: #8000FF !important;
        border: 1px solid #A960FF !important;
    }

    /* Radio and checkbox labels - default */
    .stRadio label, .stCheckbox label {
        color: #ECDDFF !important;
    }

    /* Radio and checkbox labels inside expanders */
    [data-testid="stExpander"] .stRadio label,
    [data-testid="stExpander"] .stCheckbox label {
        color: #8000FF !important;
    }

    /* Progress Styles */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #A960FF 0%, #FF0080 50%, #00CAFF 100%);
    }

    /* Checkbox Styles */
    [data-testid="stCheckbox"] {
        color: #A960FF;
    }

    /* Text color for emphasis */
    [data-testid="stMarkdownContainer"] strong {
        color: #ECDDFF;
    }

    /* Sticky logo in top-right corner */
    .sticky-logo {
        position: fixed;
        top: 10px;
        right: 10px;
        width: 60px;
        height: 60px;
        object-fit: contain;
        z-index: 9999;
        opacity: 0.7;
        transition: opacity 0.3s;
    }

    .sticky-logo:hover {
        opacity: 1;
    }

    /* Fix white space at bottom */
    .main .block-container {
        padding-bottom: 5rem;
        background: #34008D;
        min-height: 100vh;
    }

    /* Ensure entire page has dark background */
    .stApp {
        background: #34008D;
    }

    section[data-testid="stSidebar"] {
        background: #34008D;
    }

    /* Limit video preview height */
    video {
        max-height: 500px !important;
        width: auto !important;
        margin: 0 auto !important;
        display: block !important;
    }

    [data-testid="stVideo"] {
        display: flex !important;
        justify-content: center !important;
    }

    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

def format_file_size(size_bytes):
    """Convert bytes to human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def format_duration(seconds):
    """Convert seconds to MM:SS format"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"

def parse_time_to_seconds(time_str):
    """Parse time string (MM:SS or HH:MM:SS) to seconds

    Args:
        time_str: Time string in format MM:SS or HH:MM:SS

    Returns:
        float: Time in seconds, or None if invalid format
    """
    try:
        time_str = time_str.strip()
        parts = time_str.split(':')

        if len(parts) == 2:
            # MM:SS format
            mins, secs = parts
            return int(mins) * 60 + float(secs)
        elif len(parts) == 3:
            # HH:MM:SS format
            hours, mins, secs = parts
            return int(hours) * 3600 + int(mins) * 60 + float(secs)
        else:
            return None
    except (ValueError, AttributeError):
        return None

def calculate_duration(start_time_str, stop_time_str):
    """Calculate duration between start and stop times

    Args:
        start_time_str: Start time string (MM:SS or HH:MM:SS)
        stop_time_str: Stop time string (MM:SS or HH:MM:SS)

    Returns:
        float: Duration in seconds, or None if invalid
    """
    start_seconds = parse_time_to_seconds(start_time_str)
    stop_seconds = parse_time_to_seconds(stop_time_str)

    if start_seconds is None or stop_seconds is None:
        return None

    duration = stop_seconds - start_seconds

    # Validate duration is positive and not exceeding 3 minutes (180 seconds)
    if duration <= 0:
        return None
    if duration > 180:
        return None

    return duration

def render_trim_ui(video_path, video_name, unique_key):
    """Render trim UI for a specific video

    Args:
        video_path: Path object to the video file
        video_name: Display name for the video
        unique_key: Unique key for Streamlit widgets
    """
    st.markdown("---")

    # Check if this video already has a trimmed version
    video_path_str = str(video_path)
    has_trimmed = video_path_str in st.session_state.trimmed_videos

    with st.expander(f"✂️ Trim {video_name}", expanded=False):
        st.markdown("Remove up to 5 seconds from the beginning or end of this video")

        col1, col2 = st.columns(2)
        with col1:
            trim_start = st.number_input(
                "Trim from start (seconds)",
                min_value=0,
                max_value=5,
                value=0,
                step=1,
                key=f"trim_start_{unique_key}",
                help="Remove up to 5 seconds from the beginning"
            )
        with col2:
            trim_end = st.number_input(
                "Trim from end (seconds)",
                min_value=0,
                max_value=5,
                value=0,
                step=1,
                key=f"trim_end_{unique_key}",
                help="Remove up to 5 seconds from the end"
            )

        if trim_start > 0 or trim_end > 0:
            if st.button("✂️ Apply Trim", type="primary", use_container_width=True, key=f"apply_trim_{unique_key}"):
                with st.status("Trimming video...", expanded=True) as trim_status:
                    st.write(f"Trimming {trim_start}s from start, {trim_end}s from end...")

                    # Create trimmed output path
                    trimmed_filename = f"{video_path.stem}_trimmed_{trim_start}s_{trim_end}s.mp4"
                    trimmed_path = video_path.parent / trimmed_filename

                    with st.spinner("Processing..."):
                        success = trim_video(video_path, trimmed_path, trim_start, trim_end)

                    if success and trimmed_path.exists():
                        st.session_state.trimmed_videos[video_path_str] = trimmed_path
                        trim_status.update(label="✓ Trim complete!", state="complete", expanded=False)
                        st.success(f"✅ Trimmed video created: {trimmed_filename}")
                        st.rerun()
                    else:
                        st.error("❌ Trim operation failed. Please try again.")
                        trim_status.update(label="✗ Trim failed", state="error", expanded=False)
        else:
            st.info("💡 Set trim values above to enable trimming")

    # Show trimmed video if it exists
    if has_trimmed:
        trimmed_path = st.session_state.trimmed_videos[video_path_str]
        if trimmed_path.exists():
            st.markdown(f"### ✂️ Trimmed: {video_name}")
            trimmed_size = trimmed_path.stat().st_size

            with open(trimmed_path, 'rb') as video_file:
                st.video(video_file.read())
            st.markdown(f"**{trimmed_path.name}** • {format_file_size(trimmed_size)}")

            # Download trimmed video
            with open(trimmed_path, 'rb') as f:
                st.download_button(
                    label=f"⬇️ Download Trimmed {video_name}",
                    data=f,
                    file_name=trimmed_path.name,
                    mime='video/mp4',
                    key=f"download_trimmed_{unique_key}",
                    use_container_width=True
                )

def get_video_thumbnail(video_path, time_sec=5):
    """Generate thumbnail from video at specified time"""
    try:
        from moviepy import VideoFileClip
        with st.spinner(f"Generating thumbnail..."):
            with VideoFileClip(str(video_path)) as clip:
                frame = clip.get_frame(min(time_sec, clip.duration - 1))
            return Image.fromarray(frame)
    except Exception as e:
        st.error(f"Could not generate thumbnail: {e}")
        return None

# Initialize session state
if 'temp_dir' not in st.session_state:
    st.session_state.temp_dir = None
if 'video_files' not in st.session_state:
    st.session_state.video_files = []
if 'vtt_file' not in st.session_state:
    st.session_state.vtt_file = None
if 'output_files' not in st.session_state:
    st.session_state.output_files = []
if 'current_tab' not in st.session_state:
    st.session_state.current_tab = "Upload"
if 'preview_files' not in st.session_state:
    st.session_state.preview_files = []
if 'clip_config' not in st.session_state:
    st.session_state.clip_config = None
if 'trimmed_videos' not in st.session_state:
    st.session_state.trimmed_videos = {}  # Dict to track trimmed versions: {original_path: trimmed_path}
if 'persistent_output_dir' not in st.session_state:
    # Create a persistent output directory that survives page refreshes
    st.session_state.persistent_output_dir = Path(tempfile.gettempdir()) / f"pvg_outputs_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.session_state.persistent_output_dir.mkdir(parents=True, exist_ok=True)
if 'generated_videos' not in st.session_state:
    st.session_state.generated_videos = {}  # Dict to store {filename: {'path': Path, 'size': int, 'time': float, 'duration': float}}

# Header with logo
# Load and encode logo
logo_path = Path("logos/logo.png")
if logo_path.exists():
    with open(logo_path, "rb") as f:
        logo_data = base64.b64encode(f.read()).decode()
    logo_html = f'<img src="data:image/png;base64,{logo_data}" class="header-logo">'
else:
    logo_html = ""

st.markdown(f'''
    <div class="main-header">
        {logo_html}
        <span>Portrait Video Generator</span>
    </div>
''', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Upload your videos and create portrait formatted content for YouTube Shorts, TikTok, and Instagram Reels</p>', unsafe_allow_html=True)

# Add sticky logo in corner (visible throughout app)
if logo_html:
    st.markdown(f'<img src="data:image/png;base64,{logo_data}" class="sticky-logo">', unsafe_allow_html=True)

# Create tabs
tab1, tab2 = st.tabs(["📤 Upload", "⚙️ Settings & Generate"])

# TAB 1: Upload
with tab1:
    # Unified file upload for videos and VTT
    st.markdown("### Upload Files")
    st.markdown("Upload 2-4 video files (MP4) and optionally 1 subtitle file (VTT)")

    # Single file uploader for both videos and VTT
    uploaded_files = st.file_uploader(
        "Choose video files (MP4) and/or subtitle file (VTT)",
        type=['mp4', 'vtt'],
        accept_multiple_files=True,
        help="Upload 2-4 MP4 videos and optionally 1 VTT subtitle file",
        key="unified_uploader"
    )

    if uploaded_files:
        # Separate videos from VTT files
        video_files = [f for f in uploaded_files if f.name.lower().endswith('.mp4')]
        vtt_files = [f for f in uploaded_files if f.name.lower().endswith('.vtt')]

        # Validate video count
        if len(video_files) < 1:
            st.warning("⚠️ Please upload at least 1 video")
        elif len(video_files) > 4:
            st.warning("⚠️ Maximum 4 videos allowed")
        else:
            # Create temporary directory if needed
            if st.session_state.temp_dir is None:
                st.session_state.temp_dir = tempfile.mkdtemp()

            temp_dir = Path(st.session_state.temp_dir)
            st.session_state.video_files = []

            # Save video files
            for uploaded_file in video_files[:4]:
                video_path = temp_dir / uploaded_file.name
                with open(video_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                st.session_state.video_files.append(video_path)

            # Save VTT file if provided
            if vtt_files:
                if len(vtt_files) > 1:
                    st.warning("⚠️ Multiple VTT files detected. Using the first one.")
                vtt_file = vtt_files[0]
                vtt_path = temp_dir / vtt_file.name
                with open(vtt_path, 'wb') as f:
                    f.write(vtt_file.getbuffer())
                st.session_state.vtt_file = vtt_path
            else:
                # Clear VTT file if not provided
                st.session_state.vtt_file = None

            # Display upload summary
            st.markdown("---")
            st.markdown(f'<div class="success-box">✅ <strong>{len(st.session_state.video_files)} videos uploaded</strong></div>', unsafe_allow_html=True)

            # Show uploaded videos
            st.markdown("#### Uploaded Videos")
            for idx, video_path in enumerate(st.session_state.video_files):
                st.markdown(f"**{idx + 1}.** {video_path.name}")
                size_mb = video_path.stat().st_size / (1024*1024)
                st.markdown(f"<span style='color: #A960FF;'>{size_mb:.1f} MB</span>", unsafe_allow_html=True)

            # Show VTT file if uploaded
            if st.session_state.vtt_file:
                st.markdown("---")
                st.markdown(f'<div class="success-box">✅ <strong>Subtitle file: {st.session_state.vtt_file.name}</strong></div>', unsafe_allow_html=True)

    # Continue to Settings Button
    if st.session_state.video_files and len(st.session_state.video_files) >= 1:
        st.markdown("---")
        st.markdown("""
        <div class="success-box">
            <strong>✅ Files Ready!</strong><br>
            Continue to Settings & Generate to configure your videos.
        </div>
        """, unsafe_allow_html=True)

# TAB 2: Settings & Processing
with tab2:
    if not st.session_state.video_files or len(st.session_state.video_files) < 1:
        st.markdown('<div class="info-box">ℹ️ Please upload at least 1 video in the Upload tab first</div>', unsafe_allow_html=True)
    else:
        # Show persistent storage info if videos have been generated
        if st.session_state.generated_videos:
            st.markdown(f'''
            <div class="success-box">
                ✅ <strong>{len(st.session_state.generated_videos)} video(s) saved and ready</strong><br>
                Your generated videos are preserved in memory and available for download below.
            </div>
            ''', unsafe_allow_html=True)

        st.markdown("### Processing Configuration")

        # Video mode selection
        col1, col2 = st.columns(2)
        with col1:
            # Determine available video modes based on uploaded videos
            max_videos = min(len(st.session_state.video_files), 4)
            available_modes = list(range(1, max_videos + 1)) + ['multi']

            def format_video_mode(x):
                if x == 'multi':
                    return "Multi-cut (random quick cuts + zoom effects)"
                elif x == 1:
                    return "1-video (full screen)"
                elif x == 2:
                    return f"{x}-video (50/50 split)"
                elif x == 3:
                    return f"{x}-video (33/33/33 split)"
                else:
                    return f"{x}-video (25/25/25/25 split)"

            video_mode = st.radio(
                "Video Mode",
                options=available_modes,
                format_func=format_video_mode,
                help="Choose how many videos to stack, or multi-cut for dynamic random cuts (2.5-3.5s) with random zoom effects (50% chance, 1.05x-1.15x zoom)"
            )

        with col2:
            processing_mode = st.radio(
                "Output Mode",
                options=["Full Video", "Clips"],
                help="Choose what to generate"
            )

        st.markdown("---")

        # Video selection section (if user has more videos than selected mode)
        # Skip selection if multi-cut mode (uses all videos)
        if video_mode == 'multi':
            # Multi-cut mode uses all uploaded videos
            selected_video_indices = list(range(len(st.session_state.video_files)))
            st.markdown(f"### Multi-Cut Mode")
            st.markdown(f"All {len(st.session_state.video_files)} videos will be used with random quick cuts (2.5-3.5s each) and dynamic zoom effects (50% chance per segment)")
            st.markdown("---")
        elif len(st.session_state.video_files) > video_mode:
            st.markdown("### Video Selection")
            st.markdown(f"You have {len(st.session_state.video_files)} videos uploaded but selected {video_mode}-video mode. Choose which videos to use:")

            selected_video_indices = []

            # Create position labels based on video mode
            if video_mode == 1:
                position_labels = ["Video"]
            elif video_mode == 2:
                position_labels = ["Top Position", "Bottom Position"]
            elif video_mode == 3:
                position_labels = ["Top Position", "Middle Position", "Bottom Position"]
            else:  # 4 videos
                position_labels = ["Top Position", "2nd Position", "3rd Position", "Bottom Position"]

            # Create selectboxes for each position
            for i in range(video_mode):
                video_options = {idx: f"{idx + 1}. {path.name}" for idx, path in enumerate(st.session_state.video_files)}

                selected_idx = st.selectbox(
                    position_labels[i],
                    options=list(video_options.keys()),
                    format_func=lambda x: video_options[x],
                    key=f"video_select_{i}",
                    help=f"Choose which video to use for {position_labels[i].lower()}"
                )
                selected_video_indices.append(selected_idx)

            # Check for duplicates
            if len(selected_video_indices) != len(set(selected_video_indices)):
                st.warning("⚠️ You've selected the same video multiple times. Each position should use a different video.")

            st.markdown("---")
        else:
            # Use all available videos in order
            selected_video_indices = list(range(video_mode))

        st.markdown("---")

        # Caption Settings (only show if VTT file is uploaded)
        burn_captions = False
        if st.session_state.vtt_file:
            st.markdown("### Caption Settings")
            burn_captions = st.checkbox(
                "🔥 Burn captions into video",
                value=False,
                help="Check this to permanently embed subtitles into the video. Uncheck to generate videos without captions."
            )
            if burn_captions:
                st.markdown('<div class="info-box">✓ Captions will be burned into the video with custom styling (120pt light purple text)</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="info-box">ℹ️ Videos will be generated without captions</div>', unsafe_allow_html=True)
            st.markdown("---")

        # Settings based on mode
        if processing_mode == "Clips":
            st.markdown("### Clip Configuration")
            num_clips = st.slider("Number of clips", 1, 3, 1)

            clip_timestamps = []
            clip_durations = []
            clip_titles = []
            clip_crop_settings = []  # Store crop settings per clip

            # Create position labels based on video mode
            if video_mode == 'multi':
                position_labels = []  # Multi-cut doesn't need position labels
            elif video_mode == 1:
                position_labels = ["Video"]
            elif video_mode == 2:
                position_labels = ["Top Video", "Bottom Video"]
            elif video_mode == 3:
                position_labels = ["Top Video", "Middle Video", "Bottom Video"]
            else:  # 4 videos
                position_labels = ["Top Video", "2nd Video", "3rd Video", "Bottom Video"]

            for i in range(num_clips):
                with st.expander(f"📹 Clip {i+1}", expanded=True):
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        start_time = st.text_input(
                            "Start Time",
                            value=f"{i*2}:00",
                            key=f"clip_start_{i}",
                            placeholder="MM:SS or HH:MM:SS",
                            help="Enter start time (e.g., 1:30 or 0:01:30)"
                        )
                        clip_timestamps.append(start_time)

                    with col2:
                        stop_time = st.text_input(
                            "Stop Time",
                            value=f"{i*2 + 1}:00",
                            key=f"clip_stop_{i}",
                            placeholder="MM:SS or HH:MM:SS",
                            help="Enter stop time (max 3 minutes from start)"
                        )

                    # Calculate duration and display validation
                    duration = calculate_duration(start_time, stop_time)
                    if duration is None:
                        st.error("⚠️ Invalid time range. Please check your start/stop times. Duration must be positive and not exceed 3 minutes.")
                        clip_durations.append(None)
                    else:
                        st.success(f"✓ Clip duration: {format_duration(duration)} ({duration:.1f}s)")
                        clip_durations.append(duration)

                    title = st.text_input(
                        "Title (optional)",
                        value="",
                        max_chars=50,
                        key=f"clip_title_{i}",
                        placeholder="Enter a short title..."
                    )
                    clip_titles.append(title if title.strip() else None)

                    # Video Display Settings for this clip (skip for multi-cut mode)
                    if video_mode != 'multi':
                        st.markdown("**Video Display Settings**")
                        st.markdown("Configure how each video should be sized for this clip:")

                        current_clip_crop_settings = []
                        for video_idx in range(video_mode):
                            enable_letterbox = st.checkbox(
                                f"Enable Letterbox for {position_labels[video_idx]}",
                                value=False,
                                key=f"clip_{i}_letterbox_{video_idx}",
                                help=f"Check to fit entire video (letterbox). Uncheck for zoom & crop (default)."
                            )
                            # Invert the logic: checkbox checked = letterbox (False for crop_to_fill)
                            # checkbox unchecked = zoom & crop (True for crop_to_fill)
                            current_clip_crop_settings.append(not enable_letterbox)

                        clip_crop_settings.append(current_clip_crop_settings)
                    else:
                        # Multi-cut mode doesn't use crop settings
                        clip_crop_settings.append([])

            st.markdown("---")

            # Preview option for clips
            st.markdown("### Preview Options")
            generate_preview = st.checkbox(
                "🔍 Generate 5-second previews first",
                value=False,
                help="Create quick 5-second previews of each clip before processing full videos"
            )
        else:
            # Full Video mode - simple video display settings (skip for multi-cut)
            if video_mode != 'multi':
                st.markdown("### Video Display Settings")
                st.markdown("Configure how each video should be sized:")

                # Create position labels based on video mode
                if video_mode == 1:
                    position_labels = ["Video"]
                elif video_mode == 2:
                    position_labels = ["Top Video", "Bottom Video"]
                elif video_mode == 3:
                    position_labels = ["Top Video", "Middle Video", "Bottom Video"]
                else:  # 4 videos
                    position_labels = ["Top Video", "2nd Video", "3rd Video", "Bottom Video"]

                full_video_crop_settings = []
                for video_idx in range(video_mode):
                    enable_letterbox = st.checkbox(
                        f"Enable Letterbox for {position_labels[video_idx]}",
                        value=False,
                        key=f"full_video_letterbox_{video_idx}",
                        help=f"Check to fit entire video (letterbox). Uncheck for zoom & crop (default)."
                    )
                    # Invert the logic: checkbox checked = letterbox (False for crop_to_fill)
                    # checkbox unchecked = zoom & crop (True for crop_to_fill)
                    full_video_crop_settings.append(not enable_letterbox)
            else:
                # Multi-cut mode doesn't use crop settings
                full_video_crop_settings = []

        st.markdown("---")

        # Action button
        if processing_mode == "Clips":
            button_label = "🔍 Generate Preview" if generate_preview else "▶️ Generate Clips"
        else:
            button_label = "▶️ Generate Full Video"

        if st.button(button_label, type="primary", use_container_width=True):
            st.markdown("### 🎬 Processing Videos")

            # Use persistent output directory instead of temp directory
            output_dir = st.session_state.persistent_output_dir
            output_dir.mkdir(exist_ok=True)

            # Select videos based on user selection or default order
            selected_videos = [st.session_state.video_files[idx] for idx in selected_video_indices]

            # Parse timestamp helper (uses the parse_time_to_seconds function)
            def parse_timestamp(ts):
                seconds = parse_time_to_seconds(ts)
                if seconds is None:
                    # Fallback to simple integer if parse fails
                    try:
                        return int(ts)
                    except ValueError:
                        return 0
                return seconds

            # Handle clips mode
            if processing_mode == "Clips":
                # Validate all clip durations before processing
                invalid_clips = [i+1 for i, duration in enumerate(clip_durations) if duration is None]
                if invalid_clips:
                    st.error(f"❌ Cannot generate clips. Please fix the time ranges for clip(s): {', '.join(map(str, invalid_clips))}")
                    st.stop()

                # Determine if we're in preview mode
                is_preview_mode = generate_preview
                duration_label = "preview" if is_preview_mode else "clip"

                # Store clip configuration in session state for later
                if is_preview_mode:
                    st.session_state.clip_config = {
                        'timestamps': clip_timestamps,
                        'durations': clip_durations,
                        'titles': clip_titles,
                        'video_mode': video_mode,
                        'num_clips': num_clips
                    }
                    st.session_state.preview_files = []

                # Process clips (either previews or full)
                st.session_state.output_files = []
                progress_text = f"Generating {duration_label}s" if is_preview_mode else "Processing clips"
                overall_progress = st.progress(0, text=f"{progress_text} 0/{num_clips}...")
                preview_container = st.container()

                for i in range(num_clips):
                    current_clip_duration = clip_durations[i]
                    current_clip_title = clip_titles[i]
                    start_sec = parse_timestamp(clip_timestamps[i])

                    # In preview mode, only generate 5 seconds
                    actual_duration = 5.0 if is_preview_mode else current_clip_duration

                    status_label = f"Generating Preview {i+1}/{num_clips}" if is_preview_mode else f"Processing Clip {i+1}/{num_clips}"

                    with st.status(f"{status_label}...", expanded=True) as status:
                        clip_start_time = time.time()

                        if is_preview_mode:
                            output_filename = f"preview{i+1}_{int(current_clip_duration)}s.mp4"
                        else:
                            output_filename = f"clip{i+1}_{int(current_clip_duration)}s.mp4"

                        output_path_full = output_dir / output_filename

                        # Get subtitles if available and burn_captions is enabled
                        subtitle_file = None
                        if st.session_state.vtt_file and burn_captions:
                            st.write("📝 Processing subtitles...")
                            from stacked_script.stack import get_existing_subtitles
                            import shutil as sh
                            # For previews, extract subtitles for the 5-second duration
                            subtitle_duration = actual_duration if is_preview_mode else current_clip_duration
                            subtitle_file = get_existing_subtitles(temp_dir, start_time=start_sec, duration=subtitle_duration)
                            if subtitle_file:
                                subtitle_file_in_output = output_dir / subtitle_file.name
                                sh.copy(subtitle_file, subtitle_file_in_output)
                                subtitle_file = subtitle_file_in_output
                                st.write("✓ Subtitles ready")
                        elif st.session_state.vtt_file and not burn_captions:
                            st.write("ℹ️ Skipping captions (burn captions disabled)")

                        if is_preview_mode:
                            st.write(f"🔍 Generating 5-second preview from {clip_timestamps[i]} (full clip: {current_clip_duration}s)...")
                        else:
                            st.write("🎬 Encoding...")

                        if current_clip_title:
                            st.write(f"📋 Title: '{current_clip_title}'")

                        with st.spinner("Processing..."):
                            # Use multi-cut function for multi mode, otherwise use standard stacking
                            if video_mode == 'multi':
                                create_multi_cut_video(
                                    selected_videos,
                                    output_path_full,
                                    start_time=start_sec,
                                    duration=actual_duration,
                                    subtitle_path=subtitle_file,
                                    title_text=current_clip_title,
                                    progress_callback=None
                                )
                            else:
                                create_portrait_video(
                                    selected_videos,
                                    output_path_full,
                                    video_mode,
                                    preview_only=False,
                                    start_time=start_sec,
                                    duration=actual_duration,
                                    subtitle_path=subtitle_file,
                                    title_text=current_clip_title,
                                    progress_callback=None,
                                    crop_to_fill=clip_crop_settings[i]  # Use per-clip crop settings
                                )

                        if output_path_full.exists():
                            processing_time = time.time() - clip_start_time
                            file_size = output_path_full.stat().st_size

                            file_info = {
                                'path': output_path_full,
                                'name': output_path_full.name,
                                'size': file_size,
                                'time': processing_time,
                                'duration': actual_duration,
                                'full_duration': current_clip_duration
                            }

                            # Store in persistent generated_videos dict
                            video_key = f"{output_path_full.name}_{datetime.now().timestamp()}"
                            st.session_state.generated_videos[video_key] = file_info

                            if is_preview_mode:
                                st.session_state.preview_files.append(file_info)
                            else:
                                st.session_state.output_files.append(file_info)

                            complete_label = f"Preview {i+1} complete!" if is_preview_mode else f"Clip {i+1} complete!"
                            st.write(f"✓ Complete: {output_path_full.name}")
                            status.update(label=complete_label, state="complete", expanded=False)

                            # Show video
                            with preview_container:
                                if is_preview_mode:
                                    st.markdown(f"### 🔍 Preview {i+1} (5s from {clip_timestamps[i]}, full: {current_clip_duration}s)")
                                else:
                                    st.markdown(f"### 🎬 Clip {i+1}")
                                with open(output_path_full, 'rb') as video_file:
                                    st.video(video_file.read())
                                st.markdown(f"**{output_path_full.name}** • {format_file_size(file_size)} • {format_duration(processing_time)}")

                                # Add trim UI for this clip
                                render_trim_ui(output_path_full, f"Clip {i+1}", f"clip_{i}_{is_preview_mode}")

                                st.markdown("---")

                    progress_update = f"Generated {i+1}/{num_clips} {duration_label}s" if is_preview_mode else f"Processed {i+1}/{num_clips} clips"
                    overall_progress.progress(int(((i + 1) / num_clips) * 100), text=progress_update)

                completion_text = f"✅ All {num_clips} previews generated!" if is_preview_mode else f"✅ All {num_clips} clips complete!"
                overall_progress.progress(100, text=completion_text)

                # Show continue button after previews
                if is_preview_mode and st.session_state.preview_files:
                    st.markdown("---")
                    st.markdown('<div class="info-box">💡 <strong>Previews look good?</strong><br>Uncheck "Generate 5-second previews first" above and click "Generate Clips" to process the full videos with subtitles and titles.</div>', unsafe_allow_html=True)

                # Download section for full clips
                if st.session_state.output_files:
                    st.markdown("### 📥 Download Your Videos")
                    for output in st.session_state.output_files:
                        with open(output['path'], 'rb') as f:
                            st.download_button(
                                label=f"⬇️ Download {output['name']}",
                                data=f,
                                file_name=output['name'],
                                mime='video/mp4',
                                key=f"download_{output['name']}",
                                use_container_width=True
                            )

                # Download section for preview clips
                if is_preview_mode and st.session_state.preview_files:
                    st.markdown("### 📥 Download Preview Videos")
                    for output in st.session_state.preview_files:
                        with open(output['path'], 'rb') as f:
                            st.download_button(
                                label=f"⬇️ Download {output['name']}",
                                data=f,
                                file_name=output['name'],
                                mime='video/mp4',
                                key=f"download_preview_{output['name']}",
                                use_container_width=True
                            )

            # Handle Full Video mode
            else:
                st.markdown("### 🎬 Generating Full Video")

                with st.status("Processing full video...", expanded=True) as status:
                    start_time = time.time()
                    if video_mode == 'multi':
                        output_filename = f"portrait_full_multicut.mp4"
                    else:
                        output_filename = f"portrait_full_{video_mode}video.mp4"
                    output_path = output_dir / output_filename

                    st.write("🎬 Creating full portrait video...")

                    # Get subtitles if available and burn_captions is enabled
                    subtitle_file = None
                    if st.session_state.vtt_file and burn_captions:
                        st.write("📝 Processing subtitles...")
                        st.write("✓ Subtitles ready")
                        subtitle_file = st.session_state.vtt_file
                    elif st.session_state.vtt_file and not burn_captions:
                        st.write("ℹ️ Skipping captions (burn captions disabled)")

                    with st.spinner("Processing..."):
                        # Use multi-cut function for multi mode, otherwise use standard stacking
                        if video_mode == 'multi':
                            create_multi_cut_video(
                                selected_videos,
                                output_path,
                                start_time=0,
                                duration=None,
                                subtitle_path=subtitle_file,
                                title_text=None,
                                progress_callback=None
                            )
                        else:
                            create_portrait_video(
                                selected_videos,
                                output_path,
                                video_mode,
                                preview_only=False,
                                start_time=0,
                                duration=None,
                                subtitle_path=subtitle_file,
                                title_text=None,
                                progress_callback=None,
                                crop_to_fill=full_video_crop_settings
                            )

                    if output_path.exists():
                        processing_time = time.time() - start_time
                        file_size = output_path.stat().st_size

                        # Store in persistent generated_videos dict
                        video_key = f"{output_path.name}_{datetime.now().timestamp()}"
                        st.session_state.generated_videos[video_key] = {
                            'path': output_path,
                            'name': output_path.name,
                            'size': file_size,
                            'time': processing_time,
                            'duration': None
                        }

                        st.write(f"✓ Complete!")
                        status.update(label="Full video complete!", state="complete", expanded=False)

                        # Show preview
                        st.markdown("### 🎬 Video Preview")
                        with open(output_path, 'rb') as video_file:
                            st.video(video_file.read())
                        st.markdown(f"**{output_path.name}** • {format_file_size(file_size)} • {format_duration(processing_time)}")

                        # Download button
                        st.markdown("### 📥 Download Video")
                        with open(output_path, 'rb') as f:
                            st.download_button(
                                label=f"⬇️ Download {output_path.name}",
                                data=f,
                                file_name=output_path.name,
                                mime='video/mp4',
                                key=f"download_full",
                                use_container_width=True
                            )

                        # Add trim UI for full video
                        render_trim_ui(output_path, "Full Video", "full_video")

        # Always show generated videos section at the bottom if any exist
        if st.session_state.generated_videos:
            st.markdown("---")
            st.markdown("## 📦 All Generated Videos")
            st.markdown(f"**{len(st.session_state.generated_videos)} video(s) generated in this session**")
            st.markdown("*Videos remain available until you close this browser tab*")

            # Display all generated videos with download buttons
            for video_key, video_info in st.session_state.generated_videos.items():
                video_path = video_info['path']

                # Check if file still exists
                if video_path.exists():
                    st.markdown("---")
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"### 🎬 {video_info['name']}")
                        st.markdown(f"**Size:** {format_file_size(video_info['size'])} • **Processing Time:** {format_duration(video_info['time'])}")

                        # Show video preview
                        with open(video_path, 'rb') as video_file:
                            st.video(video_file.read())

                    with col2:
                        # Download button
                        with open(video_path, 'rb') as f:
                            st.download_button(
                                label=f"⬇️ Download",
                                data=f,
                                file_name=video_info['name'],
                                mime='video/mp4',
                                key=f"persistent_download_{video_key}",
                                use_container_width=True
                            )

                        # Delete button
                        if st.button(f"🗑️ Remove", key=f"delete_{video_key}", use_container_width=True):
                            try:
                                video_path.unlink()
                                del st.session_state.generated_videos[video_key]
                                st.rerun()
                            except Exception as e:
                                st.error(f"Could not delete file: {e}")
                else:
                    # File no longer exists, remove from session state
                    del st.session_state.generated_videos[video_key]
                    st.rerun()

# Cleanup on session end
def cleanup_temp_files():
    if st.session_state.temp_dir and Path(st.session_state.temp_dir).exists():
        try:
            shutil.rmtree(st.session_state.temp_dir)
        except:
            pass

import atexit
atexit.register(cleanup_temp_files)
