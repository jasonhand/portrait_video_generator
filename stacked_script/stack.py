#!/usr/bin/env python3
"""
Video Stacker - Convert 2 or 3 landscape videos to portrait format
Supports two modes:
- 2-video mode: 50/50 split with center-cropped videos filling entire screen
- 3-video mode: Three equal sections stacked vertically
Combines MP4 files into a single portrait video for YouTube Shorts/TikTok
"""

import os
import sys
from pathlib import Path
from moviepy import VideoFileClip, CompositeVideoClip, ColorClip, TextClip, ImageClip
import argparse
from PIL import Image
import numpy as np
import subprocess
import platform

def find_font_path(font_name="National2-Bold.otf", fallback_font="Arial-Bold"):
    """Find font file path, falling back to system font if not found

    Args:
        font_name: Preferred font filename (e.g., "National2-Bold.otf")
        fallback_font: Fallback font name for FFmpeg (e.g., "Arial-Bold")

    Returns:
        str: Font path or font name for FFmpeg
    """
    # Common font directories by platform
    if platform.system() == "Darwin":  # macOS
        font_dirs = [
            Path.home() / "Library/Fonts",
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        ]
    elif platform.system() == "Windows":
        font_dirs = [
            Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts",
        ]
    else:  # Linux
        font_dirs = [
            Path.home() / ".fonts",
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
        ]

    # Search for the preferred font
    for font_dir in font_dirs:
        if font_dir.exists():
            for font_file in font_dir.rglob(font_name):
                return str(font_file.absolute())

    # Font not found, return fallback font name (FFmpeg will use system font)
    print(f"Warning: {font_name} not found, falling back to {fallback_font}")
    return fallback_font

def parse_time_input(time_str):
    """Parse time input in MM:SS or seconds format

    Examples:
        "12:34" -> 754.0 (12 minutes 34 seconds)
        "1:05" -> 65.0 (1 minute 5 seconds)
        "45" -> 45.0 (45 seconds)
        "0:30" -> 30.0 (30 seconds)

    Returns:
        float: Time in seconds
        None: If parsing fails
    """
    time_str = time_str.strip()

    # Check if input contains a colon (MM:SS format)
    if ':' in time_str:
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                if minutes >= 0 and 0 <= seconds < 60:
                    return float(minutes * 60 + seconds)
            return None
        except ValueError:
            return None
    else:
        # Plain seconds format
        try:
            return float(time_str)
        except ValueError:
            return None

def trim_video(input_path, output_path, trim_start=0, trim_end=0):
    """Trim seconds from the beginning and/or end of a video

    Args:
        input_path: Path to the input video file
        output_path: Path where the trimmed video should be saved
        trim_start: Seconds to trim from the beginning (default: 0, max: 5)
        trim_end: Seconds to trim from the end (default: 0, max: 5)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"\n{'='*60}")
        print("TRIMMING VIDEO...")
        print("="*60)
        print(f"Input: {input_path.name}")

        # Validate trim values
        trim_start = max(0, min(5, trim_start))
        trim_end = max(0, min(5, trim_end))

        print(f"Trimming {trim_start}s from start, {trim_end}s from end")

        # Load the video
        clip = VideoFileClip(str(input_path))
        original_duration = clip.duration

        # Calculate new duration
        new_duration = original_duration - trim_start - trim_end

        if new_duration <= 0:
            print("✗ Error: Trim values would result in zero or negative duration")
            clip.close()
            return False

        print(f"Original duration: {original_duration:.2f}s")
        print(f"New duration: {new_duration:.2f}s")

        # Trim the video
        trimmed_clip = clip.subclipped(trim_start, original_duration - trim_end)

        # Write the output
        print(f"Saving trimmed video to: {output_path.name}")
        trimmed_clip.write_videofile(
            str(output_path),
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio-trim.m4a',
            remove_temp=True,
            fps=30,
            logger='bar'
        )

        # Clean up
        clip.close()
        trimmed_clip.close()

        print(f"\n{'='*60}")
        print("TRIM COMPLETE!")
        print("="*60)
        print(f"Trimmed video saved: {output_path.name}")
        print(f"Duration: {new_duration:.2f} seconds")
        print("="*60)

        return True

    except Exception as e:
        print(f"\n{'='*60}")
        print("ERROR TRIMMING VIDEO")
        print("="*60)
        print(f"Error: {str(e)}")
        print("="*60)
        return False

def create_layout_preview(video_paths, output_path, num_videos=3, sample_time=5.0):
    """Create a static image preview of the final video layout

    Args:
        video_paths: List of Path objects for the video files
        output_path: Path object for the output preview image
        num_videos: Number of videos (2 or 3)
        sample_time: Time in seconds to sample frame from each video
    """
    print(f"\n{'='*60}")
    print("GENERATING LAYOUT PREVIEW...")
    print("="*60)

    # Target dimensions
    target_width = 1080
    target_height = 1920

    # Create background
    background_color = (236, 221, 255)  # #ECDDFF
    preview_image = Image.new('RGB', (target_width, target_height), background_color)

    # Load video frames
    clips = []
    for i, path in enumerate(video_paths):
        print(f"Loading frame from video {i+1}: {path.name}")
        clip = VideoFileClip(str(path))

        # Get frame at sample_time (or start if video is shorter)
        frame_time = min(sample_time, clip.duration - 0.1)
        frame = clip.get_frame(frame_time)

        clips.append((clip, frame))

    # Calculate dimensions based on mode
    if num_videos == 2:
        video_height = target_height // 2  # 960px each
        video_dimensions = [(target_width, video_height), (target_width, video_height)]
        print(f"2-video mode: Each section is {target_width}x{video_height}")
    else:
        video_height = target_height // 3  # 640px each
        video_dimensions = [(target_width, video_height)] * 3
        print(f"3-video mode: Each section is {target_width}x{video_height}")

    # Process each frame
    for i, (clip, frame) in enumerate(clips):
        clip_width, clip_height = video_dimensions[i]

        # Convert frame to PIL Image
        frame_img = Image.fromarray(frame)
        original_width, original_height = frame_img.size

        if num_videos == 2:
            # Apply same logic as video processing: center crop to fill space
            # First resize to target width
            aspect_ratio = original_height / original_width
            new_height = int(clip_width * aspect_ratio)
            frame_resized = frame_img.resize((clip_width, new_height), Image.Resampling.LANCZOS)

            # Center crop vertically if needed
            if new_height > clip_height:
                y_center = new_height // 2
                y_start = y_center - (clip_height // 2)
                frame_cropped = frame_resized.crop((0, y_start, clip_width, y_start + clip_height))
            else:
                # Resize to fill height and crop horizontally
                frame_resized = frame_img.resize((int(original_width * clip_height / original_height), clip_height), Image.Resampling.LANCZOS)
                if frame_resized.width > clip_width:
                    x_center = frame_resized.width // 2
                    x_start = x_center - (clip_width // 2)
                    frame_cropped = frame_resized.crop((x_start, 0, x_start + clip_width, clip_height))
                else:
                    frame_cropped = frame_resized

            # Position: top video at 0, bottom video at video_height
            y_position = 0 if i == 0 else video_height
            preview_image.paste(frame_cropped, (0, y_position))
            print(f"  ✓ Video {i+1} positioned at y={y_position}px")

        else:
            # 3-video mode: same as existing logic
            aspect_ratio = original_height / original_width
            new_height = int(clip_width * aspect_ratio)
            frame_resized = frame_img.resize((clip_width, new_height), Image.Resampling.LANCZOS)

            if new_height > clip_height:
                # Center crop vertically
                y_center = new_height // 2
                y_start = y_center - (clip_height // 2)
                frame_cropped = frame_resized.crop((0, y_start, clip_width, y_start + clip_height))
            else:
                # Resize to fill height
                frame_cropped = frame_img.resize((clip_width, clip_height), Image.Resampling.LANCZOS)

            y_position = i * clip_height
            preview_image.paste(frame_cropped, (0, y_position))
            print(f"  ✓ Video {i+1} positioned at y={y_position}px")

        # Clean up clip
        clip.close()

    # Add visual guides/labels
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(preview_image)

    # Add dividing lines and labels
    if num_videos == 2:
        # Draw line at 50% mark
        line_y = target_height // 2
        draw.line([(0, line_y), (target_width, line_y)], fill=(255, 255, 255), width=3)

        # Add labels with background
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        except:
            font = ImageFont.load_default()

        # Top label
        label1 = "SCREEN RECORDING (TOP 50%)"
        bbox1 = draw.textbbox((0, 0), label1, font=font)
        text_width1 = bbox1[2] - bbox1[0]
        text_height1 = bbox1[3] - bbox1[1]
        x1 = (target_width - text_width1) // 2
        y1 = 30

        # Draw semi-transparent background for text
        padding = 10
        draw.rectangle([x1-padding, y1-padding, x1+text_width1+padding, y1+text_height1+padding],
                      fill=(0, 0, 0, 180))
        draw.text((x1, y1), label1, fill=(255, 255, 255), font=font)

        # Bottom label
        label2 = "SPEAKER (BOTTOM 50%)"
        bbox2 = draw.textbbox((0, 0), label2, font=font)
        text_width2 = bbox2[2] - bbox2[0]
        text_height2 = bbox2[3] - bbox2[1]
        x2 = (target_width - text_width2) // 2
        y2 = line_y + 30

        draw.rectangle([x2-padding, y2-padding, x2+text_width2+padding, y2+text_height2+padding],
                      fill=(0, 0, 0, 180))
        draw.text((x2, y2), label2, fill=(255, 255, 255), font=font)
    else:
        # 3-video mode: draw lines at 33% and 66%
        line_y1 = target_height // 3
        line_y2 = 2 * target_height // 3
        draw.line([(0, line_y1), (target_width, line_y1)], fill=(255, 255, 255), width=3)
        draw.line([(0, line_y2), (target_width, line_y2)], fill=(255, 255, 255), width=3)

        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)
        except:
            font = ImageFont.load_default()

        labels = ["TOP (33%)", "MIDDLE (33%)", "BOTTOM (33%)"]
        y_positions = [30, line_y1 + 30, line_y2 + 30]

        for label, y_pos in zip(labels, y_positions):
            bbox = draw.textbbox((0, 0), label, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (target_width - text_width) // 2

            padding = 10
            draw.rectangle([x-padding, y_pos-padding, x+text_width+padding, y_pos+text_height+padding],
                          fill=(0, 0, 0, 180))
            draw.text((x, y_pos), label, fill=(255, 255, 255), font=font)

    # Add sample caption preview to show caption styling
    # MarginV=960 means 960px from bottom, which is 1920-960=960px from top (absolute center)
    caption_y = target_height - 960

    # Sample two-line caption text
    caption_text = "This is a sample caption\nshowing the text styling"

    try:
        # Use Arial font at 120pt to match video caption styling
        caption_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except:
        caption_font = ImageFont.load_default()

    # Draw caption with same colors as video:
    # Primary color: #ECDDFF (light purple/lavender) = RGB(236, 221, 255)
    # Outline color: #34008D (dark purple) = RGB(52, 0, 141)

    # Word wrap the caption text to fit within screen with padding
    max_text_width = target_width - 80  # 40px padding on each side

    def wrap_text(text, font, max_width):
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    # Wrap the caption text
    caption_lines = wrap_text(caption_text.replace('\n', ' '), caption_font, max_text_width)

    # Calculate total height of caption block
    line_height = 130  # Approximate line height for 120pt font
    total_caption_height = len(caption_lines) * line_height

    # Start y position centered around caption_y
    current_y = caption_y - (total_caption_height // 2)

    for line in caption_lines:
        # Get text bounding box to center horizontally
        bbox = draw.textbbox((0, 0), line, font=caption_font)
        text_width = bbox[2] - bbox[0]
        text_x = (target_width - text_width) // 2

        # Draw outline/shadow effect (dark purple)
        outline_color = (52, 0, 141)  # #34008D
        for offset_x in [-3, -2, -1, 0, 1, 2, 3]:
            for offset_y in [-3, -2, -1, 0, 1, 2, 3]:
                if offset_x != 0 or offset_y != 0:
                    draw.text((text_x + offset_x, current_y + offset_y), line,
                            fill=outline_color, font=caption_font)

        # Draw main text (light purple/lavender)
        primary_color = (236, 221, 255)  # #ECDDFF
        draw.text((text_x, current_y), line, fill=primary_color, font=caption_font)

        current_y += line_height

    print("✓ Added sample caption preview")

    # Save the preview image
    preview_image.save(str(output_path), quality=95)

    print(f"\n{'='*60}")
    print("PREVIEW IMAGE CREATED!")
    print("="*60)
    print(f"Preview saved to: {output_path}")
    print(f"Resolution: {target_width}x{target_height}")
    print("Review this image to see the final video layout.")
    print(f"{'='*60}\n")

def get_video_files(directory):
    """Get all MP4 files from the specified directory"""
    video_extensions = ['.mp4', '.MP4']
    video_files = []

    for ext in video_extensions:
        video_files.extend(Path(directory).glob(f'*{ext}'))

    return sorted(video_files)

def get_subtitle_files(directory):
    """Get all SRT subtitle files from the specified directory"""
    subtitle_extensions = ['.srt', '.SRT']
    subtitle_files = []

    for ext in subtitle_extensions:
        subtitle_files.extend(Path(directory).glob(f'*{ext}'))

    return sorted(subtitle_files)

def cleanup_subtitle_files(directory):
    """Remove all .srt files from the directory after video processing is complete"""
    try:
        srt_files = get_subtitle_files(directory)
        if srt_files:
            print(f"\n{'='*60}")
            print("CLEANING UP")
            print("="*60)
            for srt_file in srt_files:
                try:
                    srt_file.unlink()
                    print(f"✓ Removed: {srt_file.name}")
                except Exception as e:
                    print(f"⚠ Could not remove {srt_file.name}: {e}")
            print(f"✓ Cleanup complete - removed {len(srt_files)} subtitle file(s)")
            print("="*60)
    except Exception as e:
        print(f"⚠ Warning: Could not clean up subtitle files: {e}")

def get_vtt_files(directory):
    """Get all VTT subtitle files from the specified directory"""
    vtt_extensions = ['.vtt', '.VTT']
    vtt_files = []

    for ext in vtt_extensions:
        vtt_files.extend(Path(directory).glob(f'*{ext}'))

    return sorted(vtt_files)

def parse_vtt_timestamp(timestamp_str):
    """Parse VTT timestamp to seconds

    Args:
        timestamp_str: Timestamp in VTT format (HH:MM:SS.mmm or MM:SS.mmm)

    Returns:
        float: Time in seconds
    """
    try:
        # Remove any whitespace
        timestamp_str = timestamp_str.strip()

        # Split by ':' to get parts
        parts = timestamp_str.split(':')

        if len(parts) == 3:
            # HH:MM:SS.mmm format
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            # MM:SS.mmm format
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        else:
            return 0.0
    except:
        return 0.0

def extract_vtt_segment(vtt_path, start_time, duration, output_path):
    """Extract a segment from a VTT file and adjust timestamps

    Args:
        vtt_path: Path to the source VTT file
        start_time: Start time in seconds
        duration: Duration in seconds
        output_path: Path where the extracted SRT file should be saved

    Returns:
        Path to the extracted SRT file, or None if extraction failed
    """
    try:
        end_time = start_time + duration

        print(f"\nExtracting subtitles from VTT file...")
        print(f"Source: {vtt_path.name}")
        print(f"Time range: {start_time:.1f}s - {end_time:.1f}s")

        # Read the VTT file
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Parse VTT and extract relevant cues
        extracted_cues = []
        i = 0
        cue_number = 1

        while i < len(lines):
            line = lines[i].strip()

            # Skip header and empty lines
            if line.startswith('WEBVTT') or line == '' or line.startswith('NOTE'):
                i += 1
                continue

            # Check if this line contains a timestamp (cue timing line)
            if '-->' in line:
                # Parse the timestamp line
                timestamp_parts = line.split('-->')
                if len(timestamp_parts) == 2:
                    cue_start_str = timestamp_parts[0].strip()
                    cue_end_str = timestamp_parts[1].strip().split()[0]  # Remove any styling info

                    cue_start = parse_vtt_timestamp(cue_start_str)
                    cue_end = parse_vtt_timestamp(cue_end_str)

                    # Check if this cue overlaps with our desired time range
                    if cue_start < end_time and cue_end > start_time:
                        # Adjust timestamps relative to clip start
                        adjusted_start = max(0, cue_start - start_time)
                        adjusted_end = min(duration, cue_end - start_time)

                        # Only include if the adjusted times are valid
                        if adjusted_end > adjusted_start and adjusted_start < duration:
                            # Collect the subtitle text (next lines until empty line)
                            i += 1
                            text_lines = []
                            while i < len(lines) and lines[i].strip() != '':
                                text_lines.append(lines[i].strip())
                                i += 1

                            if text_lines:
                                extracted_cues.append({
                                    'number': cue_number,
                                    'start': adjusted_start,
                                    'end': adjusted_end,
                                    'text': '\n'.join(text_lines)
                                })
                                cue_number += 1
                        else:
                            i += 1
                    else:
                        i += 1
                else:
                    i += 1
            else:
                i += 1

        if not extracted_cues:
            print("⚠ No subtitles found in the specified time range")
            return None

        # Write to SRT format
        with open(output_path, 'w', encoding='utf-8') as f:
            for cue in extracted_cues:
                # SRT format: cue number
                f.write(f"{cue['number']}\n")

                # SRT timestamp format: HH:MM:SS,mmm --> HH:MM:SS,mmm
                start_hours = int(cue['start'] // 3600)
                start_minutes = int((cue['start'] % 3600) // 60)
                start_seconds = int(cue['start'] % 60)
                start_millis = int((cue['start'] % 1) * 1000)

                end_hours = int(cue['end'] // 3600)
                end_minutes = int((cue['end'] % 3600) // 60)
                end_seconds = int(cue['end'] % 60)
                end_millis = int((cue['end'] % 1) * 1000)

                f.write(f"{start_hours:02d}:{start_minutes:02d}:{start_seconds:02d},{start_millis:03d} --> ")
                f.write(f"{end_hours:02d}:{end_minutes:02d}:{end_seconds:02d},{end_millis:03d}\n")

                # Subtitle text
                f.write(f"{cue['text']}\n\n")

        print(f"✓ Extracted {len(extracted_cues)} subtitle cue(s)")
        print(f"✓ Saved to: {output_path.name}")

        return output_path

    except Exception as e:
        print(f"\n{'='*60}")
        print("ERROR EXTRACTING VTT SEGMENT")
        print("="*60)
        print(f"Error: {str(e)}")
        print("="*60)
        return None


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

def convert_srt_to_ass_with_positioning(srt_path, ass_path, margin_vertical=550, max_chars_per_line=22):
    """Convert SRT to ASS format with custom vertical positioning

    Args:
        srt_path: Path to input SRT file
        ass_path: Path to output ASS file
        margin_vertical: Vertical margin from bottom in pixels
        max_chars_per_line: Maximum characters per line for text wrapping (default: 22)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Parse the SRT file
        subtitles = parse_srt_file(srt_path)

        if not subtitles:
            print("✗ Failed to parse SRT file")
            return False

        # Create ASS file with custom styling
        with open(ass_path, 'w', encoding='utf-8') as f:
            # Write ASS header
            f.write("[Script Info]\n")
            f.write("ScriptType: v4.00+\n")
            f.write("PlayResX: 1080\n")
            f.write("PlayResY: 1920\n")
            f.write("WrapStyle: 0\n")  # No wrapping - we'll do it manually
            f.write("\n")

            # Write styles section with MarginV positioning
            # Primary color: #ECDDFF (light purple/lavender) -> &HFFDDEC in BGR format
            # Outline/Shadow color: #34008D (dark purple) -> &H8D0034 in BGR format
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            f.write(f"Style: Default,National 2,120,&HFFDDEC,&HFFDDEC,&H8D0034,&H808D0034,0,0,0,0,100,100,0,0,1,3,3,2,80,80,{margin_vertical},1\n")
            f.write("\n")

            # Write events section
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

            for sub in subtitles:
                # Convert seconds to ASS time format (H:MM:SS.cc)
                def seconds_to_ass_time(seconds):
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    centisecs = int((seconds % 1) * 100)
                    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

                start_time = seconds_to_ass_time(sub['start'])
                end_time = seconds_to_ass_time(sub['end'])

                # Manually wrap the text to prevent overflow
                text = wrap_subtitle_text(sub['text'].replace('\n', ' '), max_chars_per_line)

                f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n")

        print(f"✓ Converted SRT to ASS with MarginV={margin_vertical}, max {max_chars_per_line} chars/line")
        return True

    except Exception as e:
        print(f"✗ Error converting SRT to ASS: {e}")
        import traceback
        traceback.print_exc()
        return False

def burn_subtitles_with_ffmpeg(input_video_path, subtitle_path, output_video_path, margin_vertical=550):
    """Burn subtitles into video using FFmpeg directly

    Args:
        input_video_path: Path to input video file
        subtitle_path: Path to SRT subtitle file
        output_video_path: Path for output video with burned subtitles
        margin_vertical: Vertical margin from bottom in pixels (default: 550)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"Burning subtitles using FFmpeg...")
        print(f"Input video: {input_video_path}")
        print(f"Subtitle file: {subtitle_path}")
        print(f"Output video: {output_video_path}")

        # Convert SRT to ASS with positioning
        ass_path = subtitle_path.parent / f"{subtitle_path.stem}.ass"
        if not convert_srt_to_ass_with_positioning(subtitle_path, ass_path, margin_vertical):
            return False

        # Use just the filename since we'll run FFmpeg in the same directory
        input_filename = str(input_video_path.name)
        ass_filename = str(ass_path.name)
        output_filename = str(output_video_path.name)

        # Build FFmpeg command - use ASS file with embedded positioning
        command = [
            'ffmpeg',
            '-i', input_filename,
            '-vf', f"ass={ass_filename}",
            '-codec:a', 'copy',
            '-y',  # Overwrite output file if it exists
            output_filename
        ]

        print(f"FFmpeg command: {' '.join(command)}")
        print(f"Working directory: {input_video_path.parent}")
        print("Running FFmpeg (this may take a minute)...")

        # Run FFmpeg in the same directory as the video
        result = subprocess.run(command, capture_output=True, text=True, cwd=str(input_video_path.parent))

        # Clean up ASS file
        try:
            ass_path.unlink()
        except:
            pass

        if result.returncode == 0:
            print("✓ Subtitles burned successfully!")
            return True
        else:
            print(f"✗ FFmpeg failed with return code: {result.returncode}")
            print(f"✗ FFmpeg stderr: {result.stderr[-500:]}")  # Last 500 chars
            return False

    except Exception as e:
        print(f"✗ Error burning subtitles: {e}")
        import traceback
        traceback.print_exc()
        return False

def parse_srt_file(srt_path):
    """Parse SRT file and return list of subtitle entries

    Args:
        srt_path: Path to SRT file

    Returns:
        List of dicts with 'start', 'end', and 'text' keys, or empty list if parsing fails
    """
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split by double newline to get individual subtitle blocks
        blocks = content.strip().split('\n\n')
        subtitles = []

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            # Skip the subtitle number (first line)
            # Second line is the timestamp
            timestamp_line = lines[1]

            # Parse timestamp: HH:MM:SS,mmm --> HH:MM:SS,mmm
            if '-->' not in timestamp_line:
                continue

            times = timestamp_line.split('-->')
            start_str = times[0].strip()
            end_str = times[1].strip()

            # Convert to seconds
            def time_to_seconds(time_str):
                # Format: HH:MM:SS,mmm
                time_str = time_str.replace(',', '.')
                parts = time_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds

            start_time = time_to_seconds(start_str)
            end_time = time_to_seconds(end_str)

            # Remaining lines are the subtitle text
            text = '\n'.join(lines[2:])

            subtitles.append({
                'start': start_time,
                'end': end_time,
                'text': text
            })

        return subtitles

    except Exception as e:
        print(f"Error parsing SRT file: {e}")
        return []

def get_subtitles_for_clip(clip_video_path, directory, start_time, duration):
    """Get subtitles for a clip from VTT file (automatically, no prompts)

    Args:
        clip_video_path: Path to the already-created clipped video file
        directory: Directory containing video and subtitle files
        start_time: Start time of the clip in seconds
        duration: Duration of the clip in seconds

    Returns:
        Path to subtitle file (SRT), or None if no VTT files found
    """
    # Check if there are any VTT files in the directory
    vtt_files = get_vtt_files(directory)

    if not vtt_files:
        return None

    # Automatically use the first VTT file found
    selected_vtt = vtt_files[0]
    print(f"\n✓ Found VTT file: {selected_vtt.name}")
    print(f"  Extracting subtitles for clip...")

    # Extract the segment from the VTT file
    srt_filename = f"{clip_video_path.stem}.srt"
    srt_path = directory / srt_filename

    extracted_srt = extract_vtt_segment(selected_vtt, start_time, duration, srt_path)

    if extracted_srt:
        return extracted_srt
    else:
        print("\n⚠ VTT extraction failed.")
        return None

def get_existing_subtitles(directory, start_time, duration):
    """Automatically extract subtitles from VTT file if available (no prompts)

    Args:
        directory: Directory containing subtitle files
        start_time: Start time for the video segment in seconds
        duration: Duration of the video segment in seconds

    Returns:
        Path to extracted SRT subtitle file, or None if no VTT files found
    """
    vtt_files = get_vtt_files(directory)

    if not vtt_files:
        return None

    # Automatically use the first VTT file found
    selected_vtt = vtt_files[0]
    print(f"\n✓ Found VTT file: {selected_vtt.name}")
    print(f"  Extracting subtitles...")

    # Extract the segment from VTT file
    srt_filename = f"temp_subtitles_{int(start_time)}_{int(duration)}.srt"
    srt_path = directory / srt_filename

    extracted_srt = extract_vtt_segment(selected_vtt, start_time, duration, srt_path)

    if extracted_srt:
        return extracted_srt
    else:
        print("\n⚠ VTT extraction failed.")
        return None

def display_menu(video_files):
    """Display menu for selecting videos"""
    print("\n" + "="*60)
    print("VIDEO STACKER - Portrait Format Creator")
    print("="*60)
    print("\nAvailable MP4 files:")

    for i, video in enumerate(video_files, 1):
        print(f"{i}. {video.name}")

    print("\nModes:")
    print("- 2 videos: 50/50 split with center-cropped videos (fills entire screen)")
    print("- 3 videos: Three equal sections stacked vertically")
    print("- 4 videos: Four equal sections stacked vertically")
    print("- multi: Random quick cuts between videos (2.5-3.5 seconds each)")
    return video_files

def get_user_selection(video_files):
    """Get user's selection of videos based on chosen mode"""
    # First, ask how many videos to use
    while True:
        try:
            mode_input = input("\nHow many videos do you want to combine? (2, 3, 4, or 'multi'): ").strip().lower()

            # Handle 'multi' mode
            if mode_input == 'multi':
                print("\nMulti-cut mode selected!")
                print("All available videos will be used with random quick cuts (2.5-3.5 seconds each)")
                # Return all videos for multi-cut mode
                return video_files, 'multi'

            # Handle numeric modes
            num_videos = int(mode_input)
            if num_videos in [2, 3, 4]:
                break
            else:
                print("Please enter 2, 3, 4, or 'multi'")
        except ValueError:
            print("Please enter a valid number (2, 3, 4) or 'multi'")

    selected_videos = []

    if num_videos == 2:
        positions = ["screen recording (top)", "speaker (bottom)"]
        print("\n50/50 split layout")
        print("Screen recording will fill the top half (center-cropped)")
        print("Speaker video will fill the bottom half (center-cropped)")
    elif num_videos == 3:
        positions = ["top", "middle", "bottom"]
        print("\nThree equal sections")
    else:  # 4 videos
        positions = ["top", "2nd", "3rd", "bottom"]
        print("\nFour equal sections")

    for i, position in enumerate(positions):
        while True:
            try:
                choice = input(f"\nSelect video for {position} position (1-{len(video_files)}): ")
                index = int(choice) - 1

                if 0 <= index < len(video_files):
                    if video_files[index] in selected_videos:
                        print("Video already selected. Please choose a different one.")
                        continue
                    selected_videos.append(video_files[index])
                    print(f"Selected: {video_files[index].name}")
                    break
                else:
                    print(f"Please enter a number between 1 and {len(video_files)}")
            except ValueError:
                print("Please enter a valid number")

    return selected_videos, num_videos

def create_multi_cut_video(video_paths, output_path, start_time=0, duration=None, subtitle_path=None, title_text=None, progress_callback=None, video_offsets=None, screen_weight=3):
    """Create portrait video with random quick cuts between source videos with varying zoom levels

    Features:
        - Random cuts every 2.5-3.5 seconds between videos
        - 50% chance of zoom effect per segment (1.05x to 1.15x zoom)
        - Continuous audio mixing from all sources
        - Center-cropped to fill 1080x1920 portrait format
        - Special letterbox layout for screen video segments (shows all 3 videos)

    Args:
        video_paths: List of video file paths (2-4 videos)
        output_path: Output video path
        start_time: Start time for clipping
        duration: Duration for clipping
        subtitle_path: Optional path to SRT subtitle file
        title_text: Optional title text to burn at top (max 50 characters)
        progress_callback: Optional callback function(current_frame, total_frames) for progress updates
    """
    import random
    import time
    start_processing_time = time.time()

    print(f"\n{'='*60}")
    print("CREATING MULTI-CUT VIDEO...")
    print("="*60)
    print(f"Mode: Quick cuts alternating between {len(video_paths)} videos")
    print(f"Cut duration: Random 2.5-3.5 seconds per segment")
    print(f"Zoom effects: 50% chance per segment (1.05x-1.15x zoom)")

    # Load video clips
    clips = []
    clip_paths = list(video_paths)  # working copy, may be filtered after offset check

    for i, path in enumerate(clip_paths):
        print(f"Loading video {i+1}: {path.name}")
        clip = VideoFileClip(str(path))
        clips.append(clip)

    # Compute per-clip local start times (absolute_start - file_recording_offset)
    if video_offsets is None:
        video_offsets = [0.0] * len(clips)
    local_starts = [start_time - offset for offset in video_offsets]

    # Filter: local_start must be >= 0 (recording had already started) AND < clip.duration (not past end)
    # A negative local_start means this file started recording AFTER the clip begins — wrong content, exclude it
    valid_mask = [0.0 <= ls < c.duration for c, ls in zip(clips, local_starts)]
    if not all(valid_mask):
        excluded_names = [clip_paths[i].name for i, v in enumerate(valid_mask) if not v]
        print(f"\nExcluding videos outside clip time range: {excluded_names}")
        clips = [clips[i] for i, v in enumerate(valid_mask) if v]
        clip_paths = [clip_paths[i] for i, v in enumerate(valid_mask) if v]
        local_starts = [local_starts[i] for i, v in enumerate(valid_mask) if v]

    if not clips:
        raise ValueError(f"No source videos cover start_time={start_time:.2f}s")

    # Identify screen and webcam videos from the filtered list
    screen_video_index = None
    webcam_video_indices = []
    for i, path in enumerate(clip_paths):
        if 'screen' in path.name.lower():
            screen_video_index = i
            print(f"  → Detected as SCREEN video (will use letterbox layout)")
        else:
            webcam_video_indices.append(i)
            print(f"  → Detected as WEBCAM video")

    # Determine target duration based on available content in each clip
    min_available = min(clip.duration - ls for clip, ls in zip(clips, local_starts))
    if duration:
        target_duration = min(duration, min_available)
    else:
        target_duration = min_available

    print(f"\nProcessing {target_duration:.2f} seconds from time {start_time:.1f}s")

    # Trim all clips to the target duration using their local start times
    clips = [clip.subclipped(ls, ls + target_duration) for clip, ls in zip(clips, local_starts)]

    # Define target dimensions for portrait format
    target_width = 1080
    target_height = 1920

    print(f"\nTarget output resolution: {target_width}x{target_height}")
    print("Each video will fill the entire screen with center-cropping")

    # Analyze audio levels to detect who's speaking
    print(f"\nAnalyzing audio to detect speakers...")

    def get_audio_level(clip, start_time, duration=0.5):
        """Get RMS audio level for a clip segment"""
        try:
            end_time = min(start_time + duration, clip.duration)
            if start_time >= clip.duration:
                return 0.0

            audio_segment = clip.subclipped(start_time, end_time).audio
            if audio_segment is None:
                return 0.0

            # Get audio array and calculate RMS
            audio_array = audio_segment.to_soundarray(fps=22050)
            rms = (audio_array ** 2).mean() ** 0.5
            return float(rms)
        except:
            return 0.0

    # Generate speaker-aware cut schedule with dynamic audio analysis
    print(f"\nGenerating speaker-aware cut schedule...")
    cut_schedule = []
    current_time = 0.0
    video_indices = list(range(len(clip_paths)))

    # Separate Primary and Secondary video indices for weighted selection
    primary_indices = [i for i, path in enumerate(clip_paths) if 'Primary' in path.name]
    secondary_indices = [i for i, path in enumerate(clip_paths) if 'Secondary' in path.name]

    # Track previous video selections to enforce alternation
    last_video_index = None
    consecutive_count = 0

    def weighted_choice(options):
        """Choose from options, giving screen_weight times more weight to the screen video."""
        weights = [screen_weight if idx == screen_video_index else 1 for idx in options]
        return random.choices(options, weights=weights, k=1)[0]

    while current_time < target_duration:
        # Random duration between 2.5-3.5 seconds
        segment_duration = random.uniform(2.5, 3.5)

        # Don't exceed total duration
        if current_time + segment_duration > target_duration:
            segment_duration = target_duration - current_time

        # Dynamically analyze audio throughout this segment to find the dominant speaker
        # Sample audio at multiple points within the segment duration
        num_samples = max(1, int(segment_duration / 0.5))  # Sample every 0.5s within segment
        speaker_levels = {idx: [] for idx in webcam_video_indices}  # Track levels for each webcam

        for sample_offset in range(num_samples):
            sample_time = current_time + (sample_offset * 0.5)
            if sample_time >= target_duration:
                break

            for idx in webcam_video_indices:
                level = get_audio_level(clips[idx], sample_time, duration=0.5)
                speaker_levels[idx].append(level)

        # Calculate average audio level for each webcam during this segment
        speaker_avg_levels = {}
        for idx, levels in speaker_levels.items():
            if levels:
                speaker_avg_levels[idx] = sum(levels) / len(levels)
            else:
                speaker_avg_levels[idx] = 0.0

        # Find webcams with significant audio (above threshold)
        audio_threshold_adjusted = 0.02  # Slightly higher threshold to reduce false positives
        active_speakers_now = [idx for idx, level in speaker_avg_levels.items() if level > audio_threshold_adjusted]

        # Sort active speakers by audio level (loudest first)
        active_speakers_now.sort(key=lambda idx: speaker_avg_levels[idx], reverse=True)

        # Build list of eligible videos (speaking webcams + screen video)
        eligible_videos = []

        # Prefer the loudest speaker if there are multiple active speakers
        if active_speakers_now:
            # Add the dominant speaker first (highest audio)
            eligible_videos.append(active_speakers_now[0])
            # Add other active speakers as backup options
            eligible_videos.extend(active_speakers_now[1:])

        # Always allow screen video (shows all 3 videos)
        if screen_video_index is not None:
            eligible_videos.append(screen_video_index)

        # If no one is speaking, default to screen video or all videos
        if len(eligible_videos) == 1 and eligible_videos[0] == screen_video_index:
            # Only screen video is eligible, that's fine
            pass
        elif not active_speakers_now and screen_video_index is None:
            # No active speakers and no screen video - use all webcams
            eligible_videos = webcam_video_indices.copy()

        # Remove duplicates while preserving order (loudest speaker first)
        seen = set()
        eligible_videos = [x for x in eligible_videos if not (x in seen or seen.add(x))]

        # Choose a video with alternation constraint (max 2 consecutive)
        if consecutive_count >= 2:
            # Force switch to a different video
            available_videos = [idx for idx in eligible_videos if idx != last_video_index]

            # If all eligible videos are the same as last, allow it
            if not available_videos:
                available_videos = eligible_videos

            # Apply Primary/Secondary weighting to available videos
            if primary_indices:
                # Filter available videos to separate Primary and Secondary
                available_primary = [idx for idx in available_videos if idx in primary_indices]
                available_secondary = [idx for idx in available_videos if idx in secondary_indices]

                # 95% chance for Primary, 5% for Secondary (if both are available)
                if available_primary and available_secondary:
                    video_index = weighted_choice(available_primary if random.random() < 0.95 else available_secondary)
                elif available_primary:
                    video_index = weighted_choice(available_primary)
                elif available_secondary:
                    video_index = weighted_choice(available_secondary)
                else:
                    video_index = weighted_choice(available_videos)
            else:
                # No Primary/Secondary labels - use default behavior
                video_index = weighted_choice(available_videos)

            consecutive_count = 1
        else:
            # Can choose from eligible videos with Primary preference
            if primary_indices:
                # Filter eligible videos
                eligible_primary = [idx for idx in eligible_videos if idx in primary_indices]
                eligible_secondary = [idx for idx in eligible_videos if idx in secondary_indices]

                # 95% chance for Primary, 5% for Secondary
                if eligible_primary and eligible_secondary and random.random() < 0.95:
                    video_index = weighted_choice(eligible_primary)
                elif eligible_secondary and random.random() >= 0.95:
                    video_index = weighted_choice(eligible_secondary)
                elif eligible_primary:
                    video_index = weighted_choice(eligible_primary)
                else:
                    video_index = weighted_choice(eligible_videos)
            else:
                # No Primary/Secondary labels - use default behavior
                video_index = weighted_choice(eligible_videos)

            # Check if we're continuing with the same video
            if video_index == last_video_index:
                consecutive_count += 1
            else:
                consecutive_count = 1

        # Add random zoom level (50% chance of zoom)
        # Zoom range: 1.0 (no zoom) to 1.15 (15% zoom in)
        if random.random() < 0.5:
            zoom_factor = random.uniform(1.05, 1.15)
        else:
            zoom_factor = 1.0  # No zoom

        cut_schedule.append({
            'start': current_time,
            'end': current_time + segment_duration,
            'duration': segment_duration,
            'video_index': video_index,
            'zoom_factor': zoom_factor,
            'active_speakers': active_speakers_now.copy(),
            'speaker_levels': speaker_avg_levels.copy()
        })

        last_video_index = video_index
        current_time += segment_duration

    print(f"✓ Created {len(cut_schedule)} segments (dynamic speaker-aware)")
    for i, segment in enumerate(cut_schedule):
        zoom_info = f" (zoom: {segment['zoom_factor']:.2f}x)" if segment['zoom_factor'] > 1.0 else ""

        # Show speaker levels for this segment
        if segment['active_speakers']:
            speaker_info_parts = []
            for idx in segment['active_speakers']:
                level = segment['speaker_levels'].get(idx, 0.0)
                speaker_info_parts.append(f"Video {idx+1}: {level:.4f}")
            speaker_info = f" [speakers: {', '.join(speaker_info_parts)}]"
        else:
            speaker_info = " [no active speakers]"

        video_name = video_paths[segment['video_index']].name
        video_type = "SCREEN" if segment['video_index'] == screen_video_index else "WEBCAM"
        selected_info = f" ← DOMINANT" if segment['video_index'] in segment['active_speakers'][:1] else ""
        print(f"  Segment {i+1}: {segment['start']:.1f}s-{segment['end']:.1f}s ({segment['duration']:.1f}s) - Video {segment['video_index']+1} ({video_type}){zoom_info}{speaker_info}{selected_info}")

    # Process and resize each clip to fill portrait screen
    print(f"\nProcessing and resizing videos...")
    resized_clips = []

    for i, clip in enumerate(clips):
        print(f"Processing video {i+1}...")

        # Check original audio status
        has_audio_before = "✓" if clip.audio is not None else "✗"
        print(f"  Original audio: {has_audio_before}")

        # Store original audio to preserve it
        original_audio = clip.audio

        # Resize to target width while maintaining aspect ratio
        clip_resized = clip.resized(width=target_width)

        # Center-crop vertically if height exceeds target
        if clip_resized.h > target_height:
            y_center = clip_resized.h // 2
            y_start = y_center - (target_height // 2)
            clip_resized = clip_resized.cropped(y1=y_start, y2=y_start + target_height)
            print(f"  ✓ Zoomed and center-cropped vertically to {target_width}x{target_height}")
        else:
            # If video is shorter than target, resize to fill height and crop horizontally
            clip_resized = clip_resized.resized(height=target_height)
            if clip_resized.w > target_width:
                x_center = clip_resized.w // 2
                x_start = x_center - (target_width // 2)
                clip_resized = clip_resized.cropped(x1=x_start, x2=x_start + target_width)
                print(f"  ✓ Zoomed and center-cropped horizontally to {target_width}x{target_height}")

        # Explicitly preserve audio after transformations
        if original_audio is not None:
            clip_resized = clip_resized.with_audio(original_audio)
            print(f"  ✓ Audio preserved")
        else:
            print(f"  ⚠ No audio to preserve")

        resized_clips.append(clip_resized)

    # Helper function to create letterbox composite for screen segments
    def create_screen_letterbox_composite(screen_clip, webcam_clips, webcam_indices, target_w, target_h):
        """Create a composite showing screen video in middle with webcams on top and bottom"""
        from moviepy import CompositeVideoClip

        # Divide into 3 equal sections (640px each)
        section_height = target_h // 3

        positioned_clips = []

        # Top section: First webcam
        webcam_1 = webcam_clips[0]
        webcam_1_resized = webcam_1.resized(width=target_w)

        # Center-crop vertically if needed
        if webcam_1_resized.h > section_height:
            y_center = webcam_1_resized.h // 2
            y_start = y_center - (section_height // 2)
            webcam_1_resized = webcam_1_resized.cropped(y1=y_start, y2=y_start + section_height)
        else:
            # Resize to fill height if shorter
            webcam_1_resized = webcam_1.resized(height=section_height)
            if webcam_1_resized.w > target_w:
                x_center = webcam_1_resized.w // 2
                x_start = x_center - (target_w // 2)
                webcam_1_resized = webcam_1_resized.cropped(x1=x_start, x2=x_start + target_w)

        webcam_1_positioned = webcam_1_resized.with_position((0, 0))
        positioned_clips.append(webcam_1_positioned)

        # Middle section: Screen video letterboxed
        screen_aspect = screen_clip.w / screen_clip.h
        section_aspect = target_w / section_height

        if screen_aspect > section_aspect:
            # Screen is wider - fit to width
            screen_resized = screen_clip.resized(width=target_w)
        else:
            # Screen is taller - fit to height
            screen_resized = screen_clip.resized(height=section_height)

        # Center the screen video in the middle section
        screen_x = (target_w - screen_resized.w) // 2
        screen_y = section_height + ((section_height - screen_resized.h) // 2)
        screen_positioned = screen_resized.with_position((screen_x, screen_y))

        # Bottom section: Second webcam
        if len(webcam_clips) > 1:
            webcam_2 = webcam_clips[1]
            webcam_2_resized = webcam_2.resized(width=target_w)

            # Center-crop vertically if needed
            if webcam_2_resized.h > section_height:
                y_center = webcam_2_resized.h // 2
                y_start = y_center - (section_height // 2)
                webcam_2_resized = webcam_2_resized.cropped(y1=y_start, y2=y_start + section_height)
            else:
                # Resize to fill height if shorter
                webcam_2_resized = webcam_2.resized(height=section_height)
                if webcam_2_resized.w > target_w:
                    x_center = webcam_2_resized.w // 2
                    x_start = x_center - (target_w // 2)
                    webcam_2_resized = webcam_2_resized.cropped(x1=x_start, x2=x_start + target_w)

            webcam_2_positioned = webcam_2_resized.with_position((0, section_height * 2))
            positioned_clips.append(webcam_2_positioned)

        # Create composite with purple background (#A960FF)
        background = ColorClip(size=(target_w, target_h), color=(169, 96, 255))
        composite = CompositeVideoClip([background, screen_positioned] + positioned_clips)

        return composite

    # Create video segments from cut schedule
    print(f"\nCreating video segments...")
    video_segments = []

    for i, segment in enumerate(cut_schedule):
        video_idx = segment['video_index']
        seg_start = segment['start']  # Timeline position in the output
        seg_end = segment['end']      # Timeline position in the output
        seg_duration = segment['duration']
        zoom_factor = segment['zoom_factor']

        # Extract segment from the source video at the SAME timeline position
        # This keeps video in sync with the continuous mixed audio
        source_start = seg_start
        source_end = seg_end

        # Make sure we don't exceed the source video duration
        if source_end > resized_clips[video_idx].duration:
            # If the segment extends beyond this video's duration, truncate it
            source_end = resized_clips[video_idx].duration
            print(f"  ⚠ Segment {i+1}: Video {video_idx+1} too short, truncating to {source_end:.1f}s")

        # Check if this segment uses the screen video
        if video_idx == screen_video_index and screen_video_index is not None and len(webcam_video_indices) >= 2:
            # Create letterbox composite with all 3 videos
            print(f"  📺 Segment {i+1}: SCREEN video - creating letterbox layout with all 3 videos")

            # Extract segments from all videos at the same time
            screen_segment = clips[screen_video_index].subclipped(source_start, source_end)
            webcam_segments = [clips[idx].subclipped(source_start, source_end) for idx in webcam_video_indices]

            # Create composite (no zoom for screen segments)
            segment_clip = create_screen_letterbox_composite(
                screen_segment,
                webcam_segments,
                webcam_video_indices,
                target_width,
                target_height
            )

            # Set duration explicitly
            segment_clip = segment_clip.with_duration(seg_duration)

            zoom_info = " (letterbox layout)"
        else:
            # Normal single-video segment
            # Extract the segment from the chosen video
            segment_clip = resized_clips[video_idx].subclipped(source_start, source_end)

            # Apply zoom if zoom_factor > 1.0
            if zoom_factor > 1.0:
                # Store original audio
                original_audio = segment_clip.audio

                # Calculate new dimensions after zoom
                new_width = int(target_width * zoom_factor)
                new_height = int(target_height * zoom_factor)

                # Resize to zoomed dimensions
                segment_clip = segment_clip.resized(width=new_width, height=new_height)

                # Center crop back to target dimensions
                x_center = new_width // 2
                y_center = new_height // 2
                x_start = x_center - (target_width // 2)
                y_start = y_center - (target_height // 2)

                segment_clip = segment_clip.cropped(
                    x1=x_start,
                    y1=y_start,
                    x2=x_start + target_width,
                    y2=y_start + target_height
                )

                # Restore audio after transformations
                if original_audio is not None:
                    segment_clip = segment_clip.with_audio(original_audio)

                zoom_info = f" (zoom: {zoom_factor:.2f}x)"
            else:
                zoom_info = ""

        # Verify audio is present after subclipping
        has_audio_after_subclip = "✓" if segment_clip.audio is not None else "✗"

        video_segments.append(segment_clip)

        print(f"  ✓ Segment {i+1}: Video {video_idx+1} from {source_start:.1f}s to {source_end:.1f}s (duration: {seg_duration:.1f}s) - Audio: {has_audio_after_subclip}{zoom_info}")

    # Concatenate all segments (video only, we'll add mixed audio separately)
    print(f"\nConcatenating {len(video_segments)} video segments...")
    from moviepy import concatenate_videoclips, CompositeAudioClip

    # Debug: Check which segments have audio
    for i, seg in enumerate(video_segments):
        has_audio = "✓" if seg.audio is not None else "✗"
        print(f"  Segment {i+1}: Audio {has_audio}")

    # Concatenate video segments without audio (we'll add mixed audio next)
    final_video = concatenate_videoclips(video_segments, method="compose")

    # Mix audio from ALL source videos throughout the entire duration
    # This ensures all audio plays continuously regardless of which video is shown
    print(f"\nMixing audio from all {len(clips)} source videos to play continuously...")
    audio_tracks = []
    for i, clip in enumerate(clips):
        if clip.audio is not None:
            # Ensure audio is trimmed to exact target duration to prevent cutout
            audio_duration = min(clip.audio.duration, target_duration)
            audio_trimmed = clip.audio.subclipped(0, audio_duration)
            print(f"  ✓ Adding continuous audio from video {i+1} (duration: {audio_duration:.2f}s)")
            audio_tracks.append(audio_trimmed)
        else:
            print(f"  ⚠ Video {i+1} has no audio track")

    if audio_tracks:
        # Composite all audio tracks together (they all play at once)
        mixed_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.with_audio(mixed_audio)
        print(f"✓ Mixed audio from {len(audio_tracks)} video(s) - all audio plays continuously")
    else:
        print("⚠ Warning: No audio tracks found in any source video")

    # Add logo overlay
    # Logo is in the parent directory's logos folder
    logo_path = Path(__file__).parent.parent / "logos" / "logo.png"
    if logo_path.exists():
        print("\nAdding logo overlay...")
        try:
            logo_clip = ImageClip(str(logo_path))
            logo_height = target_height // 6  # 1/6 of screen height for full-screen mode
            logo_resized = logo_clip.resized(height=logo_height)
            logo_positioned = logo_resized.with_position((2, 2)).with_duration(target_duration)

            # Composite logo onto video
            # Preserve audio explicitly — CompositeVideoClip does not inherit audio from child clips
            _audio_before_logo = final_video.audio
            final_video = CompositeVideoClip([final_video, logo_positioned], size=(target_width, target_height))
            if _audio_before_logo is not None:
                final_video = final_video.with_audio(_audio_before_logo)
            print(f"✓ Logo added at upper left (size: {logo_resized.w}x{logo_resized.h})")
        except Exception as e:
            print(f"Warning: Could not add logo overlay: {e}")
    else:
        print(f"\nWarning: Logo file not found at {logo_path}")

    # Determine output path - if subtitles or title, create temp file first
    if subtitle_path or title_text:
        temp_output = output_path.parent / f"temp_{output_path.name}"
        final_output = output_path
    else:
        temp_output = output_path
        final_output = output_path

    # Write the output file
    print(f"\nSaving to: {temp_output if (subtitle_path or title_text) else output_path}")
    print("This may take several minutes depending on video length and quality...")

    logger = 'bar'

    final_video.write_videofile(
        str(temp_output),
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='temp-audio.m4a',
        remove_temp=True,
        fps=30,
        logger=logger
    )

    # Clean up
    for clip in clips:
        clip.close()
    for clip in resized_clips:
        clip.close()
    for segment in video_segments:
        segment.close()
    final_video.close()

    # Burn subtitles and/or title text using FFmpeg
    if subtitle_path or title_text:
        print(f"\n{'='*60}")
        if subtitle_path and title_text:
            print("BURNING SUBTITLES AND TITLE")
        elif subtitle_path:
            print("BURNING SUBTITLES")
        else:
            print("BURNING TITLE")
        print("="*60)

        vf_filters = []

        # Add subtitle filter if provided
        if subtitle_path:
            # For multi-cut mode with letterbox layout:
            # Layout is 3 sections: Webcam (top 640px), Screen (middle 640px), Webcam (bottom 640px)
            # Screen and bottom webcam touch at 1280px from top = 640px from bottom
            # Position captions in the bottom third of the video (well below center) at 400px from bottom
            margin_vertical = 400
            print(f"Caption position: {margin_vertical}px from bottom (positioned in bottom third of video)")

            # Check if subtitle file is VTT, if so convert to SRT first
            if subtitle_path.suffix.lower() == '.vtt':
                print(f"Converting VTT to SRT for time range {start_time}s to {start_time + target_duration}s...")
                srt_path = subtitle_path.parent / f"{subtitle_path.stem}_clip_temp.srt"
                extracted_srt = extract_vtt_segment(subtitle_path, start_time, target_duration, srt_path)
                if extracted_srt:
                    subtitle_path = extracted_srt
                    print(f"✓ VTT converted to SRT: {subtitle_path.name}")
                else:
                    print(f"✗ Failed to extract VTT segment")
                    subtitle_path = None

            # Convert SRT to ASS with positioning
            if subtitle_path:
                ass_path = subtitle_path.parent / f"{subtitle_path.stem}_temp.ass"
                if convert_srt_to_ass_with_positioning(subtitle_path, ass_path, margin_vertical):
                    vf_filters.append(f"ass={str(ass_path.absolute())}")

        # Add title text filter if provided
        if title_text:
            title_text = title_text[:50]
            title_text_escaped = title_text.replace("'", "'\\''").replace(":", "\\:")

            logo_height = target_height // 6
            logo_x_offset = logo_height + 20
            title_y = 50

            # Find font path dynamically
            font_path = find_font_path("National2-Bold.otf", "Arial-Bold")

            title_filter = (
                f"drawtext=text='{title_text_escaped}':"
                f"fontfile={font_path}:"
                f"fontsize=80:"
                f"fontcolor=white:"
                f"borderw=3:"
                f"bordercolor=#34008D:"
                f"x={logo_x_offset}:"
                f"y={title_y}"
            )
            vf_filters.append(title_filter)
            print(f"Title text: '{title_text}' (position: top left next to logo)")

        # Combine filters
        if vf_filters:
            vf_string = ",".join(vf_filters)

            # Source audio directly from webcam files to bypass MoviePy's broken audio mux.
            # MoviePy writes real audio to temp-audio.m4a but its internal mux produces a
            # silent stream in the temp MP4 — so -codec:a copy would copy silence.
            audio_sources = [(clip_paths[idx], local_starts[idx]) for idx in webcam_video_indices]
            if not audio_sources and screen_video_index is not None:
                audio_sources = [(clip_paths[screen_video_index], local_starts[screen_video_index])]

            if audio_sources:
                command = ['ffmpeg', '-i', str(temp_output.absolute())]
                for path, audio_start in audio_sources:
                    command += ['-ss', f'{audio_start:.3f}', '-t', f'{target_duration:.3f}', '-i', str(path.absolute())]

                video_filter = f'[0:v]{vf_string}[vout]'
                if len(audio_sources) > 1:
                    audio_inputs = ''.join(f'[{i+1}:a]' for i in range(len(audio_sources)))
                    audio_filter = f'{audio_inputs}amix=inputs={len(audio_sources)}:duration=first:dropout_transition=0[aout]'
                    filter_complex = f'{video_filter};{audio_filter}'
                    audio_map = '[aout]'
                else:
                    filter_complex = video_filter
                    audio_map = '1:a'

                command += [
                    '-filter_complex', filter_complex,
                    '-map', '[vout]',
                    '-map', audio_map,
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                    '-c:a', 'aac', '-b:a', '192k',
                    '-y', str(final_output.absolute())
                ]
            else:
                command = [
                    'ffmpeg',
                    '-i', str(temp_output.absolute()),
                    '-vf', vf_string,
                    '-an',
                    '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                    '-y', str(final_output.absolute())
                ]

            print("Running FFmpeg to burn subtitles/overlays with direct audio from source files...")
            result = subprocess.run(command, capture_output=True, text=True, cwd=str(temp_output.parent))

            # Cleanup temporary subtitle files
            if subtitle_path:
                try:
                    ass_path.unlink()
                    print(f"✓ Cleaned up temporary ASS file")
                except:
                    pass

                # Also clean up temporary SRT file if it was created from VTT
                if subtitle_path.name.endswith('_clip_temp.srt'):
                    try:
                        subtitle_path.unlink()
                        print(f"✓ Cleaned up temporary SRT file")
                    except:
                        pass

            if result.returncode == 0:
                print("✓ Text overlays burned successfully!")
                try:
                    temp_output.unlink()
                    print(f"✓ Removed temporary file: {temp_output.name}")
                except Exception as e:
                    print(f"Warning: Could not remove temp file: {e}")
            else:
                print(f"⚠ Warning: Text overlay burning failed. Using video without overlays.")
                print(f"FFmpeg error output:\n{result.stderr}")
                if temp_output.exists() and not final_output.exists():
                    temp_output.rename(final_output)

    print(f"\n{'='*60}")
    print("MULTI-CUT VIDEO CREATED!")
    print("="*60)
    final_file = final_output if (subtitle_path or title_text) else output_path
    print(f"Portrait video created: {final_file.name}")
    print(f"Duration: {target_duration:.2f} seconds")
    print(f"Segments: {len(cut_schedule)} quick cuts")
    print(f"Resolution: {target_width}x{target_height}")
    print("Ready for YouTube Shorts and TikTok!")
    print("="*60)

def create_portrait_video(video_paths, output_path, num_videos=3, preview_only=False, start_time=0, duration=None, subtitle_path=None, title_text=None, progress_callback=None, crop_to_fill=True, all_video_files=None):
    """Create portrait video by stacking videos

    Args:
        video_paths: List of video file paths to DISPLAY in the final video
        output_path: Output video path
        num_videos: Number of videos to stack (2, 3, or 4)
        preview_only: Whether to create preview only
        start_time: Start time for clipping
        duration: Duration for clipping
        subtitle_path: Optional path to SRT subtitle file
        title_text: Optional title text to burn at top (max 50 characters)
        progress_callback: Optional callback function(current_frame, total_frames) for progress updates
        crop_to_fill: Boolean or list of booleans. If True, zoom and crop videos to fill sections;
                     if False, fit entire video with letterboxing. Can be a single value for all videos
                     or a list with one value per video. (default: True)
        all_video_files: Optional list of ALL video files for continuous audio mixing. If provided,
                        audio from ALL these videos will be mixed together, even if only a subset
                        of videos are displayed (useful for single-video or stacked modes).
    """
    # Convert crop_to_fill to list if it's a single boolean
    if isinstance(crop_to_fill, bool):
        crop_to_fill = [crop_to_fill] * num_videos
    elif len(crop_to_fill) != num_videos:
        raise ValueError(f"crop_to_fill list must have {num_videos} values, got {len(crop_to_fill)}")
    import time
    start_processing_time = time.time()

    print(f"\n{'='*60}")
    if preview_only:
        print("CREATING 5-SECOND PREVIEW...")
    else:
        print("PROCESSING VIDEOS...")
    print("="*60)
    
    # Load video clips
    clips = []
    for i, path in enumerate(video_paths):
        print(f"Loading video {i+1}: {path.name}")
        clip = VideoFileClip(str(path))
        clips.append(clip)
    
    # Determine duration for processing
    if preview_only or duration:
        # For preview mode or custom duration
        target_duration = duration if duration else 5.0  # 5 seconds for preview
        min_duration = min(clip.duration for clip in clips)

        # Calculate the actual end time
        end_time = start_time + target_duration

        # Check if we have enough duration from the start_time
        if end_time > min_duration:
            target_duration = min_duration - start_time
            end_time = min_duration
            print(f"\nAdjusting duration to {target_duration:.2f} seconds (limited by video length)")
        else:
            print(f"\nCreating clip with {target_duration:.2f} seconds from time {start_time:.1f}s to {end_time:.1f}s")

        # Trim all clips to the target duration starting from start_time
        clips = [clip.subclipped(start_time, end_time) for clip in clips]
    else:
        # Full video processing
        min_duration = min(clip.duration for clip in clips)
        print(f"\nShortest video duration: {min_duration:.2f} seconds")
        print("All videos will be trimmed to this duration for synchronization.")
        
        # Trim all clips to the same duration
        clips = [clip.subclipped(0, min_duration) for clip in clips]
        target_duration = min_duration
    
    # Define target dimensions for portrait format (9:16 aspect ratio)
    # Common resolutions: 1080x1920 (Full HD) or 720x1280 (HD)
    target_width = 1080
    target_height = 1920
    
    print(f"\nTarget output resolution: {target_width}x{target_height}")

    if num_videos == 1:
        # 1-video mode: Full screen
        video_height = target_height  # Video takes entire screen height
        video_dimensions = [(target_width, video_height)]
        print(f"Single video mode: {target_width}x{target_height} (full screen)")
    elif num_videos == 2:
        # 2-video mode: Split screen 50/50 (top and bottom)
        video_height = target_height // 2  # Each video gets exactly half the height (960px)

        video_dimensions = [(target_width, video_height), (target_width, video_height)]
        print(f"Screen recording section (top): {target_width}x{video_height}")
        print(f"Speaker section (bottom): {target_width}x{video_height}")
        print("Note: Videos will be center-cropped to fit the 9:16 portrait aspect ratio")
    elif num_videos == 3:
        # 3-video mode: Each video takes 1/3 of the height
        video_height = target_height // 3
        video_dimensions = [(target_width, video_height)] * 3
        print(f"Each video section: {target_width}x{video_height}")
    else:
        # 4-video mode: Each video takes 1/4 of the height
        video_height = target_height // 4  # 480px each
        video_dimensions = [(target_width, video_height)] * 4
        print(f"Each video section: {target_width}x{video_height}")
    
    # Create background color clip
    background_color = (236, 221, 255)  # #ECDDFF converted to RGB
    background_clip = ColorClip(size=(target_width, target_height), 
                               color=background_color, 
                               duration=target_duration)
    
    # Resize and position each clip
    positioned_clips = [background_clip]  # Start with background
    
    for i, clip in enumerate(clips):
        print(f"Processing clip {i+1}...")
        
        clip_width, clip_height = video_dimensions[i]
        
        if num_videos == 1:
            # 1-video mode: Full screen
            print("  Processing video (full screen)...")

            if crop_to_fill[i]:
                # FILL MODE: Zoom and crop to fill screen completely (no black bars)
                clip_resized = clip.resized(width=clip_width)

                # Center-crop vertically if height exceeds screen
                if clip_resized.h > clip_height:
                    y_center = clip_resized.h // 2
                    y_start = y_center - (clip_height // 2)
                    clip_resized = clip_resized.cropped(y1=y_start, y2=y_start + clip_height)
                    print(f"  ✓ Zoomed and center-cropped vertically to {clip_width}x{clip_height}")
                else:
                    # If video is shorter than screen, resize to fill height
                    clip_resized = clip_resized.resized(height=clip_height)
                    # Center-crop horizontally if needed
                    if clip_resized.w > clip_width:
                        x_center = clip_resized.w // 2
                        x_start = x_center - (clip_width // 2)
                        clip_resized = clip_resized.cropped(x1=x_start, x2=x_start + clip_width)
                        print(f"  ✓ Zoomed and center-cropped horizontally to {clip_width}x{clip_height}")
            else:
                # FIT MODE: Scale to fit entire video within screen (may have black bars)
                video_aspect = clip.w / clip.h
                section_aspect = clip_width / clip_height

                if video_aspect > section_aspect:
                    clip_resized = clip.resized(width=clip_width)
                else:
                    clip_resized = clip.resized(height=clip_height)
                print(f"  ✓ Scaled to fit entire video (letterboxed if needed)")

            # Position at center
            positioned_clip = clip_resized.with_position(('center', 0))
            print(f"  ✓ Positioned at center (0px)")
        elif num_videos == 2:
            # Special handling for 2-video mode: 50/50 split
            if i == 0:
                print("  Processing screen recording (top half)...")
            else:
                print("  Processing speaker video (bottom half)...")

            if crop_to_fill[i]:
                # FILL MODE: Zoom and crop to fill section completely (no black bars)
                # Resize to target width while maintaining aspect ratio
                clip_resized = clip.resized(width=clip_width)

                # Center-crop vertically if height exceeds allocated space
                if clip_resized.h > clip_height:
                    # Crop from center
                    y_center = clip_resized.h // 2
                    y_start = y_center - (clip_height // 2)
                    clip_resized = clip_resized.cropped(y1=y_start, y2=y_start + clip_height)
                    print(f"  ✓ Zoomed and center-cropped vertically to {clip_width}x{clip_height}")
                else:
                    # If video is shorter than allocated space, resize to fill height
                    clip_resized = clip_resized.resized(height=clip_height)
                    # Center-crop horizontally if needed
                    if clip_resized.w > clip_width:
                        x_center = clip_resized.w // 2
                        x_start = x_center - (clip_width // 2)
                        clip_resized = clip_resized.cropped(x1=x_start, x2=x_start + clip_width)
                        print(f"  ✓ Zoomed and center-cropped horizontally to {clip_width}x{clip_height}")
            else:
                # FIT MODE: Scale to fit entire video within section (may have black bars)
                # Calculate aspect ratios
                video_aspect = clip.w / clip.h
                section_aspect = clip_width / clip_height

                if video_aspect > section_aspect:
                    # Video is wider than section - fit to width
                    clip_resized = clip.resized(width=clip_width)
                else:
                    # Video is taller than section - fit to height
                    clip_resized = clip.resized(height=clip_height)
                print(f"  ✓ Scaled to fit entire video (letterboxed if needed)")

            # Position the clip
            if i == 0:
                # Position at top (y=0)
                positioned_clip = clip_resized.with_position(('center', 0))
                print(f"  ✓ Positioned at top (0px)")
            else:
                # Position at bottom half (y=960)
                y_position = clip_height  # Second video starts where first one ends
                positioned_clip = clip_resized.with_position(('center', y_position))
                print(f"  ✓ Positioned at bottom half ({y_position}px)")
        else:
            # 3-video or 4-video mode: Standard stacking logic
            if crop_to_fill[i]:
                # FILL MODE: Zoom and crop to fill section completely (no black bars)
                clip_resized = clip.resized(width=clip_width)

                if clip_resized.h > clip_height:
                    y_center = clip_resized.h // 2
                    y_start = y_center - (clip_height // 2)
                    clip_resized = clip_resized.cropped(y1=y_start, y2=y_start + clip_height)
                else:
                    clip_resized = clip_resized.resized(height=clip_height)
                print(f"  ✓ Zoomed and cropped to fill section ({clip_width}x{clip_height})")
            else:
                # FIT MODE: Scale to fit entire video within section (may have black bars)
                # Calculate aspect ratios
                video_aspect = clip.w / clip.h
                section_aspect = clip_width / clip_height

                if video_aspect > section_aspect:
                    # Video is wider than section - fit to width
                    clip_resized = clip.resized(width=clip_width)
                else:
                    # Video is taller than section - fit to height
                    clip_resized = clip.resized(height=clip_height)
                print(f"  ✓ Scaled to fit entire video (letterboxed if needed)")

            # Calculate y_position for multi-video mode (3 or 4 videos)
            y_position = i * clip_height
            positioned_clip = clip_resized.with_position(('center', y_position))
        
        positioned_clips.append(positioned_clip)

    # Add logo overlay
    logo_path = Path(__file__).parent / "logos" / "logo.png"
    if logo_path.exists():
        print("Adding logo overlay...")
        try:
            # Load the logo image
            logo_clip = ImageClip(str(logo_path))

            # Calculate logo height: 1/3 the height of the top video section (2/3 of previous size)
            if num_videos == 1:
                # In 1-video mode, video takes full height
                top_section_height = target_height
            elif num_videos == 2:
                # In 2-video mode, top video is 50% of total height
                top_section_height = target_height // 2
            elif num_videos == 3:
                # In 3-video mode, each section is 1/3 of total height
                top_section_height = target_height // 3
            else:
                # In 4-video mode, each section is 1/4 of total height
                top_section_height = target_height // 4

            logo_height = top_section_height // 3  # Changed from // 2 to // 3 for 2/3 size reduction

            # Resize logo maintaining aspect ratio
            logo_resized = logo_clip.resized(height=logo_height)

            # Position closer to upper left corner (2px from both edges)
            logo_positioned = logo_resized.with_position((2, 2)).with_duration(target_duration)

            positioned_clips.append(logo_positioned)
            print(f"✓ Logo added at upper left (size: {logo_resized.w}x{logo_resized.h})")

        except Exception as e:
            print(f"Warning: Could not add logo overlay: {e}")
    else:
        print(f"Warning: Logo file not found at {logo_path}")

    print("Compositing final video...")

    # Create the final composite video
    final_video = CompositeVideoClip(positioned_clips, size=(target_width, target_height))

    # Mix audio from ALL source videos to ensure continuous audio playback
    # This is especially important for single-video mode where only one video is displayed
    # but we want to hear all audio tracks from all sources
    from moviepy import CompositeAudioClip
    audio_tracks = []

    if all_video_files:
        # Load audio from ALL videos (for single/stacked modes with continuous audio)
        print(f"\nMixing audio from all {len(all_video_files)} source videos (continuous audio mode)...")
        for i, path in enumerate(all_video_files):
            try:
                # Load just the audio from each video file
                temp_clip = VideoFileClip(str(path))
                # Apply same time range as the display clips
                if preview_only or duration:
                    end_time = start_time + target_duration
                    temp_clip = temp_clip.subclipped(start_time, end_time)

                if temp_clip.audio is not None:
                    # Ensure audio is trimmed to exact target duration to prevent cutout
                    audio_duration = min(temp_clip.audio.duration, target_duration)
                    audio_trimmed = temp_clip.audio.subclipped(0, audio_duration)
                    print(f"  ✓ Adding continuous audio from video {i+1}: {path.name} (duration: {audio_duration:.2f}s)")
                    audio_tracks.append(audio_trimmed)
                else:
                    print(f"  ⚠ Video {i+1} has no audio track")
            except Exception as e:
                print(f"  ⚠ Could not load audio from {path.name}: {e}")
    else:
        # Use audio from displayed videos only (standard mode)
        print(f"\nMixing audio from {len(clips)} displayed videos...")
        for i, clip in enumerate(clips):
            if clip.audio is not None:
                # Ensure audio is trimmed to exact target duration to prevent cutout
                audio_duration = min(clip.audio.duration, target_duration)
                audio_trimmed = clip.audio.subclipped(0, audio_duration)
                print(f"  ✓ Adding audio from video {i+1} (duration: {audio_duration:.2f}s)")
                audio_tracks.append(audio_trimmed)
            else:
                print(f"  ⚠ Video {i+1} has no audio track")

    if audio_tracks:
        # Composite all audio tracks together (they all play at once)
        mixed_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.with_audio(mixed_audio)
        print(f"✓ Mixed audio from {len(audio_tracks)} video(s) - all audio plays continuously")
    else:
        print("⚠ Warning: No audio tracks found in any source video")

    # Determine output path - if subtitles, create temp file first
    if subtitle_path:
        temp_output = output_path.parent / f"temp_{output_path.name}"
        final_output = output_path
    else:
        temp_output = output_path
        final_output = output_path

    # Write the output file
    print(f"Saving to: {temp_output if subtitle_path else output_path}")
    print("This may take several minutes depending on video length and quality...")

    # For now, disable custom progress callback due to MoviePy compatibility issues
    # Default to 'bar' logger which shows progress in terminal
    logger = 'bar'

    final_video.write_videofile(
        str(temp_output),
        codec='libx264',
        audio_codec='aac',
        temp_audiofile='temp-audio.m4a',
        remove_temp=True,
        fps=30,
        logger=logger
    )
    
    # Clean up
    for clip in clips:
        clip.close()
    final_video.close()

    # Debug: Check subtitle_path value
    print(f"\n[DEBUG] subtitle_path = {subtitle_path}")
    print(f"[DEBUG] subtitle_path type = {type(subtitle_path)}")
    print(f"[DEBUG] subtitle_path exists? {subtitle_path.exists() if subtitle_path else 'N/A'}")

    # Burn subtitles and/or title text using FFmpeg
    if subtitle_path or title_text:
        print(f"\n{'='*60}")
        if subtitle_path and title_text:
            print("BURNING SUBTITLES AND TITLE")
        elif subtitle_path:
            print("BURNING SUBTITLES")
        else:
            print("BURNING TITLE")
        print("="*60)

        # Build FFmpeg filter complex for text overlays
        vf_filters = []

        # Add subtitle filter if provided
        if subtitle_path:
            # Calculate margin and text wrapping based on video mode and crop settings
            # margin_vertical: distance from bottom of screen in pixels
            # max_chars_per_line: fewer chars = shorter lines = less video coverage
            #   - 2-video: Each section is 960px tall (1920 / 2)
            #   - 3-video: Each section is 640px tall (1920 / 3)
            #   - 4-video: Each section is 480px tall (1920 / 4)
            max_chars_per_line = 22  # Default

            # Position captions in lower third of video (550px from bottom = 1370px from top)
            margin_vertical = 550

            if num_videos == 1:
                # 1-video mode: Lower third positioning
                print(f"Caption position: {margin_vertical}px from bottom (1-video mode, lower third)")
            elif num_videos == 2:
                # 2-video stacked mode: Lower third positioning
                # Use shorter lines (15 chars) to reduce video coverage
                max_chars_per_line = 15
                print(f"Caption position: {margin_vertical}px from bottom (2-video mode, lower third)")
                print(f"Text wrapping: {max_chars_per_line} chars/line (shorter lines for less coverage)")
            elif num_videos == 3:
                # 3-video mode: Lower third positioning
                print(f"Caption position: {margin_vertical}px from bottom (3-video mode, lower third)")
            else:  # 4 videos
                # 4-video mode: Lower third positioning
                print(f"Caption position: {margin_vertical}px from bottom (4-video mode, lower third)")

            # Convert SRT to ASS for subtitles
            ass_path = subtitle_path.parent / f"{subtitle_path.stem}_temp.ass"
            if convert_srt_to_ass_with_positioning(subtitle_path, ass_path, margin_vertical, max_chars_per_line):
                vf_filters.append(f"ass={str(ass_path.absolute())}")

        # Add title text filter if provided
        if title_text:
            # Limit title length
            title_text = title_text[:50]
            # Escape special characters for FFmpeg
            title_text_escaped = title_text.replace("'", "'\\''").replace(":", "\\:")

            # Calculate logo dimensions for positioning
            # Logo is 1/3 of top section height
            if num_videos == 1:
                top_section_height = target_height  # 1920px (full screen)
            elif num_videos == 2:
                top_section_height = target_height // 2  # 960px
            elif num_videos == 3:
                top_section_height = target_height // 3  # 640px
            else:  # 4 videos
                top_section_height = target_height // 4  # 480px
            logo_height = top_section_height // 3

            # Position title text next to logo
            # Logo is at x=2, with its width, so text starts after logo + small gap
            # Assuming logo aspect ratio is roughly square, logo_width ≈ logo_height
            logo_x_offset = logo_height + 20  # logo width + 20px gap
            title_y = 50  # 50px from top (moved down for better spacing)

            # Find font path dynamically
            font_path = find_font_path("National2-Bold.otf", "Arial-Bold")

            # Title styling: National 2 font, 80pt, white with dark purple outline
            # Outline color matches caption outline: #34008D (dark purple)
            # Position next to logo at top left
            title_filter = (
                f"drawtext=text='{title_text_escaped}':"
                f"fontfile={font_path}:"
                f"fontsize=80:"
                f"fontcolor=white:"
                f"borderw=3:"
                f"bordercolor=#34008D:"
                f"x={logo_x_offset}:"
                f"y={title_y}"
            )
            vf_filters.append(title_filter)
            print(f"Title text: '{title_text}' (position: top left next to logo, x={logo_x_offset}, y={title_y})")

        # Combine filters
        if vf_filters:
            vf_string = ",".join(vf_filters)

            # Build FFmpeg command
            command = [
                'ffmpeg',
                '-i', str(temp_output.absolute()),
                '-vf', vf_string,
                '-codec:a', 'copy',
                '-y',
                str(final_output.absolute())
            ]

            print("Running FFmpeg to burn text overlays...")
            result = subprocess.run(command, capture_output=True, text=True, cwd=str(temp_output.parent))

            # Clean up temporary ASS file if created
            if subtitle_path:
                try:
                    ass_path.unlink()
                except:
                    pass

            if result.returncode == 0:
                print("✓ Text overlays burned successfully!")
                # Remove the temp file
                try:
                    temp_output.unlink()
                    print(f"✓ Removed temporary file: {temp_output.name}")
                except Exception as e:
                    print(f"Warning: Could not remove temp file: {e}")
            else:
                print(f"⚠ Warning: Text overlay burning failed. Using video without overlays.")
                print(f"FFmpeg error: {result.stderr[-500:]}")
                # Rename temp to final if burning failed
                if temp_output.exists() and not final_output.exists():
                    temp_output.rename(final_output)

    print(f"\n{'='*60}")
    if preview_only:
        print("PREVIEW CREATED!")
        print("="*60)
        print(f"Preview video created: {output_path.name}")
        print(f"Duration: {target_duration:.2f} seconds")
        print(f"Resolution: {target_width}x{target_height}")
        print("Review this preview to check framing and layout.")
    else:
        print("VIDEO CREATED!")
        print("="*60)
        final_file = final_output if subtitle_path else output_path
        print(f"Portrait video created: {final_file.name}")
        print(f"Duration: {target_duration:.2f} seconds")
        print(f"Resolution: {target_width}x{target_height}")
        print("Ready for YouTube Shorts and TikTok!")
    print("="*60)

def ask_for_preview():
    """Ask user if they want to create a preview first"""
    while True:
        choice = input("\nWould you like to create a 5-second preview first? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no")

def choose_preview_time(min_duration):
    """Let user choose what part of the video to use for preview"""
    max_minutes = int(min_duration - 5) // 60
    max_seconds = int(min_duration - 5) % 60

    print(f"\nVideo duration: {int(min_duration//60)}:{int(min_duration%60):02d} ({min_duration:.1f} seconds)")
    print("Choose the starting time for the 5-second preview:")
    print(f"Format: MM:SS or seconds (e.g., '12:34' or '754')")

    while True:
        time_input = input(f"Start time (0:00 to {max_minutes}:{max_seconds:02d}): ").strip()
        start_time = parse_time_input(time_input)

        if start_time is None:
            print("Invalid format. Use MM:SS (e.g., 12:34) or seconds (e.g., 754)")
            continue

        if 0 <= start_time <= min_duration - 5:
            return start_time
        else:
            print(f"Please enter a time between 0:00 and {max_minutes}:{max_seconds:02d}")

def get_clip_start_times(selected_videos, num_clips, clip_duration):
    """Get start times for creating clips

    Args:
        selected_videos: List of selected video paths
        num_clips: Number of clips to create (1-3)
        clip_duration: Duration of each clip in seconds (30, 45, or 60)

    Returns:
        List of start times in seconds
    """
    print(f"\n{'='*60}")
    print(f"CLIP CREATION MODE - {clip_duration}-Second Clips")
    print("="*60)
    print(f"You will create {num_clips} separate {clip_duration}-second portrait video{'s' if num_clips > 1 else ''}.")
    print("Please provide a starting time for each clip.")
    print("Format: MM:SS or seconds (e.g., '12:34' or '754')\n")

    start_times = []

    # Get minimum duration by checking the selected videos
    temp_clips = [VideoFileClip(str(path)) for path in selected_videos]
    min_duration = min(clip.duration for clip in temp_clips)
    for clip in temp_clips:
        clip.close()

    duration_minutes = int(min_duration // 60)
    duration_seconds = int(min_duration % 60)
    print(f"Shortest video duration: {duration_minutes}:{duration_seconds:02d} ({min_duration:.1f} seconds)")

    max_start_time = min_duration - clip_duration  # Need at least clip_duration seconds from start time

    if max_start_time < 0:
        print(f"\nWarning: Videos are only {min_duration:.1f} seconds long.")
        print(f"Clips will be created with maximum available duration (up to {min_duration:.1f}s)")
        max_start_time = 0

    max_minutes = int(max(0, max_start_time) // 60)
    max_seconds = int(max(0, max_start_time) % 60)

    for i in range(num_clips):
        while True:
            time_input = input(f"Start time for clip {i+1} (0:00 to {max_minutes}:{max_seconds:02d}): ").strip()
            start_time = parse_time_input(time_input)

            if start_time is None:
                print("Invalid format. Use MM:SS (e.g., 12:34) or seconds (e.g., 754)")
                continue

            if 0 <= start_time <= max(0, max_start_time):
                start_times.append(start_time)
                # Display in both formats
                start_min = int(start_time // 60)
                start_sec = int(start_time % 60)
                print(f"  ✓ Clip {i+1} will start at {start_min}:{start_sec:02d} ({start_time:.1f}s)")
                break
            else:
                print(f"Please enter a time between 0:00 and {max_minutes}:{max_seconds:02d}")

    return start_times

def ask_for_layout_preview():
    """Ask user if they want to see a layout preview image first"""
    while True:
        choice = input("\nWould you like to see a layout preview image first? (y/n): ").strip().lower()
        if choice in ['y', 'yes']:
            return True
        elif choice in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no")

def ask_for_clip_mode():
    """Ask user how many clips they want to create (1-3)

    Returns:
        int: Number of clips to create (1-3), or 0 if user doesn't want clips
    """
    while True:
        choice = input("\nHow many clips would you like to create? (1-3, or 0 to skip): ").strip()
        try:
            num_clips = int(choice)
            if 0 <= num_clips <= 3:
                return num_clips
            else:
                print("Please enter a number between 0 and 3")
        except ValueError:
            print("Please enter a valid number (0-3)")

def ask_for_clip_duration():
    """Ask user to choose clip duration (30, 45, or 60 seconds)

    Returns:
        int: Clip duration in seconds (30, 45, or 60)
    """
    while True:
        print("\nChoose clip duration:")
        print("1. 30 seconds")
        print("2. 45 seconds")
        print("3. 60 seconds")
        choice = input("\nDuration choice (1-3): ").strip()
        if choice in ['1', '2', '3']:
            duration_map = {'1': 30, '2': 45, '3': 60}
            duration = duration_map[choice]
            print(f"✓ Selected: {duration}-second clips")
            return duration
        else:
            print("Please enter 1, 2, or 3")

def main():
    parser = argparse.ArgumentParser(description='Stack 2 or 3 landscape MP4 videos into portrait format')
    parser.add_argument('-d', '--directory', help='Directory containing MP4 files')
    args = parser.parse_args()
    
    # Get directory from user if not provided as argument
    if args.directory:
        directory = Path(args.directory)
    else:
        directory_input = input("Enter the directory path containing your MP4 files: ").strip()
        directory = Path(directory_input)
    
    # Validate directory
    if not directory.exists():
        print(f"Error: Directory '{directory}' does not exist.")
        sys.exit(1)
    
    if not directory.is_dir():
        print(f"Error: '{directory}' is not a directory.")
        sys.exit(1)
    
    # Get available video files
    video_files = get_video_files(directory)
    
    if len(video_files) < 2:
        print(f"Error: Need at least 2 MP4 files. Found {len(video_files)} files.")
        sys.exit(1)
    
    # Display menu and get user selection
    video_files = display_menu(video_files)
    selected_videos, num_videos = get_user_selection(video_files)

    # Generate output filename
    timestamp = Path(selected_videos[0]).stem
    if num_videos == 'multi':
        output_filename = f"{timestamp}_portrait_multicut.mp4"
    else:
        output_filename = f"{timestamp}_portrait_stacked.mp4"
    output_path = directory / output_filename

    # Confirm before processing
    print(f"\n{'='*60}")
    print("CONFIRMATION")
    print("="*60)

    if num_videos == 'multi':
        print("Selected mode: Multi-cut (random quick cuts)")
        print(f"All {len(selected_videos)} videos will be used:")
        for i, video in enumerate(selected_videos, 1):
            print(f"{i}. {video.name}")
        print("\n→ Videos will alternate randomly every 2.5-3.5 seconds")
        print("→ Each video will fill the entire screen (center-cropped)")
    elif num_videos == 2:
        print("Selected videos (2-video mode):")
        print(f"1. Screen recording (top 50%): {selected_videos[0].name}")
        print("   → Will be center-cropped to fill top half of screen")
        print(f"2. Speaker (bottom 50%): {selected_videos[1].name}")
        print("   → Will be center-cropped to fill bottom half of screen")
    elif num_videos == 3:
        print("Selected videos (3-video mode - top to bottom):")
        for i, video in enumerate(selected_videos, 1):
            print(f"{i}. {video.name}")
    else:  # 4 videos
        print("Selected videos (4-video mode - top to bottom):")
        for i, video in enumerate(selected_videos, 1):
            print(f"{i}. {video.name}")

    print(f"\nOutput file: {output_filename}")

    # Ask if user wants to see a layout preview image (skip for multi mode)
    want_layout_preview = False
    if num_videos != 'multi':
        want_layout_preview = ask_for_layout_preview()

    if want_layout_preview:
        # Create layout preview filename
        preview_image_filename = f"{timestamp}_layout_preview.jpg"
        preview_image_path = directory / preview_image_filename

        try:
            # Create the layout preview image
            create_layout_preview(selected_videos, preview_image_path, num_videos,
                                sample_time=5.0)

            # Ask user to review and confirm
            print("Please open and review the preview image to check:")
            print("• Video positioning and cropping")
            print("• Overall layout and composition")

            proceed = input("\nDo you want to proceed with video creation? (y/n): ").strip().lower()
            if proceed not in ['y', 'yes']:
                print("Video creation cancelled. Preview image has been saved for your reference.")
                sys.exit(0)

        except Exception as e:
            print(f"\nError creating layout preview: {str(e)}")
            print("Skipping layout preview and continuing...")

    # Ask how many clips user wants to create
    num_clips = ask_for_clip_mode()

    if num_clips > 0:
        # Ask for clip duration
        clip_duration = ask_for_clip_duration()

        # Get start times for the requested number of clips
        start_times = get_clip_start_times(selected_videos, num_clips, clip_duration)

        # Track clip information for final summary
        clip_info = []

        # Create the clips
        for i, start_time in enumerate(start_times, 1):
            clip_filename = f"{timestamp}_clip{i}_{clip_duration}s.mp4"
            clip_path = directory / clip_filename

            print(f"\n{'='*60}")
            print(f"Creating Clip {i} of {num_clips}")
            print("="*60)

            try:
                import time
                clip_start_time = time.time()

                # Get subtitles first
                subtitle_file = get_existing_subtitles(directory, start_time=start_time, duration=clip_duration)

                # Create clip with appropriate function based on mode
                if num_videos == 'multi':
                    # Multi-cut mode
                    create_multi_cut_video(selected_videos, clip_path,
                                         start_time=start_time,
                                         duration=clip_duration,
                                         subtitle_path=subtitle_file)
                else:
                    # Standard stacking modes
                    create_portrait_video(selected_videos, clip_path, num_videos,
                                        preview_only=False, start_time=start_time,
                                        duration=clip_duration, subtitle_path=subtitle_file)

                if subtitle_file:
                    print(f"✓ Clip {i} completed with subtitles!")
                else:
                    print(f"✓ Clip {i} completed without subtitles!")

                # Calculate processing time and get file info
                clip_end_time = time.time()
                total_time = clip_end_time - clip_start_time
                file_size_bytes = clip_path.stat().st_size
                file_size_mb = file_size_bytes / (1024 * 1024)

                # Store info for final summary
                clip_info.append({
                    'filename': clip_filename,
                    'duration': clip_duration,
                    'processing_time': total_time,
                    'file_size_mb': file_size_mb
                })

            except Exception as e:
                print(f"\nError creating clip {i}: {str(e)}")
                print("Continuing with next clip...")
                continue

        print(f"\n{'='*60}")
        print("ALL CLIPS COMPLETED!")
        print("="*60)
        print(f"{num_clips} {clip_duration}-second clip{'s' if num_clips > 1 else ''} {'have' if num_clips > 1 else 'has'} been created in: {directory}")
        print()

        # Display summary for all clips
        for i, info in enumerate(clip_info, 1):
            # Format time as MM:SS or HH:MM:SS
            total_time = info['processing_time']
            if total_time < 3600:
                time_str = f"{int(total_time // 60)}:{int(total_time % 60):02d}"
            else:
                hours = int(total_time // 3600)
                minutes = int((total_time % 3600) // 60)
                seconds = int(total_time % 60)
                time_str = f"{hours}:{minutes:02d}:{seconds:02d}"

            print(f"Clip {i}: {info['filename']}")
            print(f"  Duration: {info['duration']} seconds")
            print(f"  File size: {info['file_size_mb']:.2f} MB")
            print(f"  Processing time: {time_str}")
            print()

        # Clean up .srt files
        cleanup_subtitle_files(directory)

        sys.exit(0)

    # Get video duration to determine preview options and subtitle extraction
    temp_clips = [VideoFileClip(str(path)) for path in selected_videos]
    min_duration = min(clip.duration for clip in temp_clips)
    for clip in temp_clips:
        clip.close()

    # Ask if user wants a preview first
    want_preview = ask_for_preview()

    if want_preview:
        if min_duration < 5:
            print(f"\nVideo is only {min_duration:.1f} seconds long. Creating preview with full duration.")
            preview_start = 0
            preview_duration = min_duration
        else:
            preview_start = choose_preview_time(min_duration)
            preview_duration = 5.0

        # Extract subtitles for the preview time range
        preview_subtitle_file = get_existing_subtitles(directory, start_time=preview_start, duration=preview_duration)

        # Create preview filename
        preview_filename = f"{timestamp}_preview.mp4"
        preview_path = directory / preview_filename

        try:
            # Create the preview with appropriate function based on mode
            if num_videos == 'multi':
                create_multi_cut_video(selected_videos, preview_path,
                                     start_time=preview_start,
                                     duration=preview_duration,
                                     subtitle_path=preview_subtitle_file)
            else:
                create_portrait_video(selected_videos, preview_path, num_videos,
                                    preview_only=True, start_time=preview_start, subtitle_path=preview_subtitle_file)

            # Ask user to review and confirm
            print(f"\n{'='*60}")
            print("PREVIEW REVIEW")
            print("="*60)
            print(f"Preview saved as: {preview_filename}")
            print("Please review the preview video to check:")
            if num_videos == 'multi':
                print("• Quick cut transitions between videos")
                print("• Video cropping and centering")
                print("• Caption styling, positioning, and colors")
            else:
                print("• Caption styling, positioning, and colors")
                print("• Screen recording zoom and positioning")
                print("• Speaker cropping and centering")
            print("• Overall layout and quality")

            proceed = input("\nDo you want to proceed with the full video? (y/n): ").strip().lower()
            if proceed not in ['y', 'yes']:
                print("Full video processing cancelled. Preview file has been saved.")
                sys.exit(0)

        except Exception as e:
            print(f"\nError creating preview: {str(e)}")
            print("Skipping preview and proceeding with full video...")

    # Confirm before full processing
    confirm = input("\nProceed with full video creation? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("Operation cancelled.")
        sys.exit(0)

    # Extract subtitles for the full video
    subtitle_file = get_existing_subtitles(directory, start_time=0, duration=min_duration)

    try:
        # Create the full portrait video with appropriate function based on mode
        if num_videos == 'multi':
            create_multi_cut_video(selected_videos, output_path,
                                 start_time=0,
                                 duration=None,
                                 subtitle_path=subtitle_file)
        else:
            create_portrait_video(selected_videos, output_path, num_videos, subtitle_path=subtitle_file)

        # Clean up .srt files after successful video creation
        cleanup_subtitle_files(directory)

    except Exception as e:
        print(f"\nError during video processing: {str(e)}")
        print("\nTroubleshooting tips:")
        print("1. Ensure all video files are valid MP4 format")
        print("2. Check that you have enough disk space")
        print("3. Verify that FFmpeg is properly installed")
        print("4. Try with shorter video clips first")
        sys.exit(1)

if __name__ == "__main__":
    # Check if moviepy is installed
    try:
        from moviepy import VideoFileClip, CompositeVideoClip, ColorClip, TextClip, ImageClip
    except ImportError:
        print("Error: moviepy is required but not installed.")
        print("Install it using: pip install moviepy")
        sys.exit(1)

    main()