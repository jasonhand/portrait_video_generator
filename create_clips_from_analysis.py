#!/usr/bin/env python3
"""
Automated clip creation from VTT analysis
Reads clip suggestions markdown file and generates video clips using stack.py
"""

import sys
import re
import random
from pathlib import Path
from stacked_script.stack import create_portrait_video, create_multi_cut_video, extract_vtt_segment

def parse_video_offset(video_path):
    """Parse recording start offset from a StreamYard filename.

    E.g. Episode_71-Jason-screen-00h_04m_12s_868ms-StreamYard.mp4 -> 252.868
    Returns 0.0 if no timestamp pattern found (webcam files that start at 0).
    """
    m = re.search(r'(\d+)h_(\d+)m_(\d+)s_(\d+)ms', video_path.stem)
    if m:
        h, mn, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return h * 3600 + mn * 60 + s + ms / 1000.0
    return 0.0


def parse_timestamp(timestamp_str):
    """Parse timestamp in format HH:MM:SS.mmm or HH:MM:SS to seconds

    Examples:
        "00:04:10.358" -> 250.358
        "00:01:04.942" -> 64.942
        "00:04:10" -> 250.0
        "00:01:04" -> 64.0
    """
    # Remove any whitespace
    timestamp_str = timestamp_str.strip()

    # Split by colon
    parts = timestamp_str.split(':')

    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        # Handle both integer and float seconds
        seconds = float(parts[2]) if '.' in parts[2] else int(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1]) if '.' in parts[1] else int(parts[1])
        return minutes * 60 + seconds
    else:
        return float(timestamp_str)

def extract_clips_from_markdown(md_file_path):
    """Extract clip information from markdown analysis file

    Returns:
        List of dicts with clip information: {
            'number': int,
            'title': str,
            'start_time': float (seconds),
            'duration': float (seconds),
            'youtube_title': str
        }
    """
    clips = []

    with open(md_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all CLIP sections (supports both ## and ### heading levels)
    clip_pattern = r'##+ CLIP #(\d+):(.*?)(?=##+ CLIP #|\Z)'
    clip_matches = re.finditer(clip_pattern, content, re.DOTALL)

    for match in clip_matches:
        clip_num = int(match.group(1))
        clip_content = match.group(2)

        # Extract timestamp (format: 00:04:10.358 → 00:05:01.492 or 00:04:10 → 00:05:01)
        timestamp_match = re.search(r'\*\*Timestamp\*\*:\s*(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*→\s*(\d{2}:\d{2}:\d{2}(?:\.\d+)?)', clip_content)
        if not timestamp_match:
            print(f"Warning: Could not find timestamp for Clip #{clip_num}")
            continue

        start_time_str = timestamp_match.group(1)
        end_time_str = timestamp_match.group(2)

        start_time = parse_timestamp(start_time_str)
        end_time = parse_timestamp(end_time_str)
        duration = end_time - start_time

        # Extract title (the text after "CLIP #X:")
        title_match = re.search(r'##+ CLIP #\d+:\s*(.+?)(?=\n)', clip_content)
        title = title_match.group(1).strip() if title_match else f"Clip {clip_num}"

        # Extract YouTube title
        youtube_title_match = re.search(r'\*\*YOUTUBE SHORTS TITLE\*\*:\s*["\']?(.+?)["\']?(?=\n)', clip_content)
        youtube_title = youtube_title_match.group(1).strip() if youtube_title_match else title

        clips.append({
            'number': clip_num,
            'title': title,
            'start_time': start_time,
            'duration': duration,
            'youtube_title': youtube_title
        })

    return clips

def find_source_videos(episode_name):
    """Find source video files for the episode.

    Matching strategy (in order):
    1. Files whose name contains the episode name (case-insensitive substring match)
    2. If episode name contains a number, files whose name contains that number
    3. If neither strategy finds anything, all MP4s in source_video/ are used

    Args:
        episode_name: Identifier derived from the markdown filename
                      (e.g., "my_interview", "ep55", "summer_recap")

    Returns:
        List of Path objects for video files, or None if source_video/ is missing
    """
    source_dir = Path(__file__).parent / "source_video"

    if not source_dir.exists():
        print(f"Error: source_video directory not found at {source_dir}")
        return None

    all_videos = sorted(source_dir.glob("*.mp4"))

    if not all_videos:
        print(f"Error: No MP4 files found in {source_dir}")
        return None

    # Strategy 1: substring match on full episode name
    video_files = [vf for vf in all_videos if episode_name.lower() in vf.stem.lower()]

    # Strategy 2: match on any number embedded in the episode name
    if not video_files:
        episode_num = re.search(r'(\d+)', episode_name)
        if episode_num:
            num = episode_num.group(1)
            video_files = [vf for vf in all_videos if num in vf.stem]

    # Strategy 3: use everything in source_video/
    if not video_files:
        print(f"No videos matched '{episode_name}' — using all {len(all_videos)} file(s) in source_video/")
        video_files = list(all_videos)
    else:
        print(f"Found {len(video_files)} source video(s) matching '{episode_name}':")

    for vf in video_files:
        print(f"  - {vf.name}")

    return video_files

def find_vtt_file(episode_name):
    """Find VTT subtitle file for the episode

    Args:
        episode_name: Episode identifier (e.g., "ep55", "Ep54", "DD_On_Iceburg")

    Returns:
        Path object for VTT file, or None if not found
    """
    transcripts_dir = Path(__file__).parent / "transcripts"

    # Try exact match first
    vtt_file = transcripts_dir / f"{episode_name}.vtt"
    if vtt_file.exists():
        return vtt_file

    # Try with _transcript suffix (e.g., DD_On_Iceburg_transcript.vtt)
    vtt_file = transcripts_dir / f"{episode_name}_transcript.vtt"
    if vtt_file.exists():
        return vtt_file

    # Try case-insensitive search
    for vtt in transcripts_dir.glob("*.vtt"):
        if vtt.stem.lower() == episode_name.lower():
            return vtt
        # Also check if episode name is a substring of the VTT filename
        if episode_name.lower() in vtt.stem.lower():
            return vtt

    print(f"Warning: No VTT file found for episode '{episode_name}'")
    return None

def select_random_video_style(available_videos):
    """Always return multi-cut style (mixed-cut with quick cuts between videos)

    Distribution:
    - 100% chance: Multi-cut (random quick cuts every 1.5-3.5 seconds between all videos)

    Args:
        available_videos: List of available video paths

    Returns:
        Tuple of (style_type, video_indices, style_name)
        - style_type: Always 'multi'
        - video_indices: List of all video indices
        - style_name: Always 'multi-cut'
    """
    # Always use multi-cut style with all videos
    all_indices = list(range(len(available_videos)))
    return ('multi', all_indices, 'multi-cut')


def create_clips(md_file_path, video_mode='varied'):
    """Create video clips from markdown analysis

    Args:
        md_file_path: Path to the markdown analysis file
        video_mode: Video style mode:
            - 'varied': Multi-cut mode only (100% multi-cut with random quick cuts every 1.5-3.5 seconds)
            - 2, 3, or 4: Fixed number of videos to stack
            - 'multi': Multi-cut mode (random quick cuts every 1.5-3.5 seconds)
    """
    md_path = Path(md_file_path)

    if not md_path.exists():
        print(f"Error: Markdown file not found: {md_file_path}")
        return False

    print(f"\n{'='*60}")
    print("AUTOMATED CLIP CREATION FROM ANALYSIS")
    print("="*60)
    print(f"Analysis file: {md_path.name}")

    # Extract episode name from filename (e.g., "ep55_clip_suggestions.md" -> "ep55")
    episode_name = md_path.stem.replace('_clip_suggestions', '').replace('_v2', '')
    print(f"Episode: {episode_name}")

    # Find source videos
    video_files = find_source_videos(episode_name)
    if not video_files:
        return False

    # Check if we're using varied mode
    use_varied_mode = (video_mode == 'varied')

    if use_varied_mode:
        print(f"\nUsing VARIED mode (100% multi-cut style with quick cuts between all videos)")
        print(f"Available videos for multi-cut:")
        for i, vf in enumerate(video_files, 1):
            print(f"  {i}. {vf.name}")
    else:
        # Fixed video mode
        if isinstance(video_mode, str) and video_mode == 'multi':
            selected_videos = video_files
            print(f"\nUsing multi-cut mode with all {len(video_files)} videos")
        else:
            # Determine how many videos to use based on video_mode
            if len(video_files) < video_mode:
                print(f"Warning: Only {len(video_files)} videos found, but mode requires {video_mode}")
                video_mode = len(video_files)

            selected_videos = video_files[:video_mode]
            print(f"\nUsing {video_mode}-video mode with:")

        for i, vf in enumerate(selected_videos, 1):
            print(f"  {i}. {vf.name}")

    # Find VTT file
    vtt_file = find_vtt_file(episode_name)
    if vtt_file:
        print(f"\nSubtitles: {vtt_file.name}")
    else:
        print("\nNo subtitles found - clips will be created without captions")

    # Extract clip information from markdown
    print(f"\nParsing clip information from {md_path.name}...")
    clips = extract_clips_from_markdown(md_path)

    if not clips:
        print("Error: No clips found in markdown file")
        return False

    print(f"Found {len(clips)} clips to create:")
    for clip in clips:
        print(f"  Clip #{clip['number']}: {clip['title']}")
        print(f"    Start: {clip['start_time']:.2f}s, Duration: {clip['duration']:.2f}s")

    # Create output directory
    output_dir = Path(__file__).parent / "output" / episode_name
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")

    # Create each clip
    print(f"\n{'='*60}")
    print("CREATING CLIPS")
    print("="*60)

    for clip in clips:
        clip_num = clip['number']
        print(f"\n--- Creating Clip #{clip_num} ---")
        print(f"Title: {clip['youtube_title']}")
        print(f"Start: {clip['start_time']:.2f}s, Duration: {clip['duration']:.2f}s")

        # Select video style for this clip
        if use_varied_mode:
            style_type, video_indices, style_name = select_random_video_style(video_files)
            print(f"🎨 Style: {style_name} (type: {style_type})")
            selected_videos = [video_files[i] for i in video_indices]
        else:
            # Use fixed style
            style_type = 'multi' if video_mode == 'multi' else 'stacked'
            style_name = video_mode

        # Create output filename with style indicator
        if use_varied_mode:
            output_filename = f"{episode_name}_clip{clip_num}_{style_name}.mp4"
        else:
            output_filename = f"{episode_name}_clip{clip_num}.mp4"
        output_path = output_dir / output_filename

        # Extract subtitles for this clip if VTT exists
        subtitle_file = None
        if vtt_file:
            try:
                # Create output path for extracted subtitles
                srt_filename = f"temp_subtitles_{int(clip['start_time'])}_{int(clip['duration'])}.srt"
                srt_path = vtt_file.parent / srt_filename

                # Extract subtitles directly from the specific VTT file
                subtitle_file = extract_vtt_segment(
                    vtt_file,
                    start_time=clip['start_time'],
                    duration=clip['duration'],
                    output_path=srt_path
                )
            except Exception as e:
                print(f"Warning: Could not extract subtitles: {e}")

        # Create the clip based on style type
        # Note: create_portrait_video handles audio mixing internally
        # We pass only the videos we want to DISPLAY, and it will mix their audio
        try:
            if style_type == 'single':
                # Single video mode - show one video full screen
                # Pass only the selected video for display
                create_portrait_video(
                    selected_videos,  # Pass only selected video
                    output_path,
                    num_videos=1,
                    preview_only=False,
                    start_time=clip['start_time'],
                    duration=clip['duration'],
                    subtitle_path=subtitle_file,
                    title_text=None,
                    progress_callback=None,
                    crop_to_fill=True,
                    all_video_files=video_files  # Pass all videos for audio mixing
                )
            elif style_type == 'multi':
                # Multi-cut mode (random quick cuts with continuous audio)
                # This already mixes audio from all sources internally
                offsets = [parse_video_offset(v) for v in selected_videos]
                create_multi_cut_video(
                    selected_videos,
                    output_path,
                    start_time=clip['start_time'],
                    duration=clip['duration'],
                    subtitle_path=subtitle_file,
                    title_text=None,
                    progress_callback=None,
                    video_offsets=offsets
                )
            else:
                # Stacked mode - show 2 or 3 videos stacked
                # Pass only selected videos for display
                num_videos = len(selected_videos)
                create_portrait_video(
                    selected_videos,  # Pass only selected videos
                    output_path,
                    num_videos=num_videos,
                    preview_only=False,
                    start_time=clip['start_time'],
                    duration=clip['duration'],
                    subtitle_path=subtitle_file,
                    title_text=None,
                    progress_callback=None,
                    crop_to_fill=True,
                    all_video_files=video_files  # Pass all videos for audio mixing
                )

            print(f"✓ Clip #{clip_num} created: {output_filename}")

        except Exception as e:
            print(f"✗ Error creating Clip #{clip_num}: {e}")
            import traceback
            traceback.print_exc()
            continue

    print(f"\n{'='*60}")
    print("CLIP CREATION COMPLETE")
    print("="*60)
    print(f"All clips saved to: {output_dir}")
    print("="*60)

    # Clean up temporary subtitle files
    if vtt_file:
        transcripts_dir = vtt_file.parent
        temp_srt_files = list(transcripts_dir.glob("temp_subtitles_*.srt"))
        if temp_srt_files:
            print(f"\n🧹 Cleaning up temporary subtitle files...")
            for temp_file in temp_srt_files:
                try:
                    temp_file.unlink()
                    print(f"  ✓ Removed: {temp_file.name}")
                except Exception as e:
                    print(f"  ⚠ Could not remove {temp_file.name}: {e}")
            print(f"✓ Cleaned up {len(temp_srt_files)} temporary file(s)")
        else:
            print(f"\n✓ No temporary subtitle files to clean up")

    return True

def main():
    """Main entry point for CLI usage"""
    if len(sys.argv) < 2:
        print("Usage: python create_clips_from_analysis.py <markdown_file> [video_mode]")
        print("\nExample:")
        print("  python create_clips_from_analysis.py transcripts/ep55_clip_suggestions.md varied")
        print("  python create_clips_from_analysis.py transcripts/ep55_clip_suggestions.md 2")
        print("\nArguments:")
        print("  markdown_file: Path to clip suggestions markdown file")
        print("  video_mode: Video style mode [default: varied]")
        print("    - 'varied': Multi-cut mode only (100% multi-cut with random quick cuts every 1.5-3.5s)")
        print("    - 'multi': Multi-cut mode only (random quick cuts every 1.5-3.5s)")
        print("    - 2, 3, or 4: Fixed number of videos to stack")
        sys.exit(1)

    md_file = sys.argv[1]

    # Parse video_mode argument
    if len(sys.argv) > 2:
        video_mode_arg = sys.argv[2]
        if video_mode_arg.lower() in ['varied', 'multi']:
            video_mode = video_mode_arg.lower()
        else:
            try:
                video_mode = int(video_mode_arg)
            except ValueError:
                print(f"Error: Invalid video_mode '{video_mode_arg}'")
                print("Must be 'varied', 'multi', or a number (2, 3, 4)")
                sys.exit(1)
    else:
        video_mode = 'varied'  # Default to varied mode

    success = create_clips(md_file, video_mode)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
