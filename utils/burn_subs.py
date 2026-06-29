#!/usr/bin/env python3
"""
Standalone script to burn subtitles into videos using FFmpeg
Usage: python burn_subs.py <video_file> <subtitle_file> [output_file]
"""

import sys
import subprocess
from pathlib import Path

def parse_srt_file(srt_path):
    """Parse SRT file and return list of subtitle entries"""
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()

        blocks = content.strip().split('\n\n')
        subtitles = []

        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue

            timestamp_line = lines[1]
            if '-->' not in timestamp_line:
                continue

            times = timestamp_line.split('-->')
            start_str = times[0].strip()
            end_str = times[1].strip()

            def time_to_seconds(time_str):
                time_str = time_str.replace(',', '.')
                parts = time_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])
                return hours * 3600 + minutes * 60 + seconds

            start_time = time_to_seconds(start_str)
            end_time = time_to_seconds(end_str)
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

def convert_srt_to_ass(srt_path, ass_path, margin_vertical=550):
    """Convert SRT to ASS format with custom vertical positioning"""
    try:
        subtitles = parse_srt_file(srt_path)

        if not subtitles:
            print("✗ Failed to parse SRT file")
            return False

        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write("[Script Info]\n")
            f.write("ScriptType: v4.00+\n")
            f.write("PlayResX: 1080\n")
            f.write("PlayResY: 1920\n")
            f.write("WrapStyle: 0\n")  # No wrapping - we'll do it manually
            f.write("\n")

            # Primary color: #ECDDFF (light purple/lavender) -> &HFFDDEC in BGR format
            # Outline/Shadow color: #34008D (dark purple) -> &H8D0034 in BGR format
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            f.write(f"Style: Default,National 2,120,&HFFDDEC,&HFFDDEC,&H8D0034,&H808D0034,0,0,0,0,100,100,0,0,1,3,3,2,80,80,{margin_vertical},1\n")
            f.write("\n")

            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

            for sub in subtitles:
                def seconds_to_ass_time(seconds):
                    hours = int(seconds // 3600)
                    minutes = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    centisecs = int((seconds % 1) * 100)
                    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

                start_time = seconds_to_ass_time(sub['start'])
                end_time = seconds_to_ass_time(sub['end'])

                # Manually wrap the text to prevent overflow
                text = wrap_subtitle_text(sub['text'].replace('\n', ' '))

                f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n")

        print(f"✓ Converted SRT to ASS with MarginV={margin_vertical}, FontSize=120, manual text wrapping enabled")
        return True

    except Exception as e:
        print(f"✗ Error converting SRT to ASS: {e}")
        return False

def burn_subtitles(video_path, subtitle_path, output_path=None, video_mode=2):
    """Burn subtitles into a video file using FFmpeg

    Args:
        video_path: Path to input video
        subtitle_path: Path to SRT subtitle file
        output_path: Path to output video (optional, defaults to video_with_subs.mp4)
        video_mode: Number of videos stacked (2 or 3, default: 2)
    """
    video_path = Path(video_path)
    subtitle_path = Path(subtitle_path)

    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        return False

    if not subtitle_path.exists():
        print(f"Error: Subtitle file not found: {subtitle_path}")
        return False

    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}_with_subs{video_path.suffix}"
    else:
        output_path = Path(output_path)

    print(f"Input video: {video_path}")
    print(f"Subtitle file: {subtitle_path}")
    print(f"Output video: {output_path}")
    print(f"Video mode: {video_mode}-video")
    print()

    # Calculate margin based on video mode
    # 2-video mode: 850px from bottom (captions in lower half)
    # 3-video mode: 400px from bottom (lower in bottom section)
    # Position captions at absolute center of video (960px from bottom = middle of 1920px screen)
    # This works well for all video modes:
    #   - 2-video: Each section is 960px tall (1920 / 2) - captions at dividing line
    #   - 3-video: Each section is 640px tall (1920 / 3) - captions in center
    #   - 4-video: Each section is 480px tall (1920 / 4) - captions in center
    margin_vertical = 550
    print(f"Caption position: {margin_vertical}px from bottom (lower third)")

    # Convert SRT to ASS with positioning
    ass_path = subtitle_path.parent / f"{subtitle_path.stem}_temp.ass"
    if not convert_srt_to_ass(subtitle_path, ass_path, margin_vertical=margin_vertical):
        return False

    # Build FFmpeg command using ASS file
    command = [
        'ffmpeg',
        '-i', str(video_path.absolute()),
        '-vf', f"ass={str(ass_path.absolute())}",
        '-codec:a', 'copy',
        '-y',
        str(output_path.absolute())
    ]

    print("Running FFmpeg...")
    print(f"Command: {' '.join(command)}")
    print()

    try:
        result = subprocess.run(command, capture_output=False, text=True)

        # Clean up ASS file
        try:
            ass_path.unlink()
        except:
            pass

        if result.returncode == 0:
            print(f"\n✓ Success! Video with subtitles saved to: {output_path}")
            return True
        else:
            print(f"\n✗ FFmpeg failed with return code: {result.returncode}")
            return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python burn_subs.py <video_file> <subtitle_file> [output_file] [video_mode]")
        print()
        print("Arguments:")
        print("  video_file    - Path to input video")
        print("  subtitle_file - Path to SRT subtitle file")
        print("  output_file   - (Optional) Path to output video")
        print("  video_mode    - (Optional) Number of videos stacked: 2 or 3 (default: 2)")
        print()
        print("Examples:")
        print("  python burn_subs.py video.mp4 video.srt")
        print("  python burn_subs.py video.mp4 video.srt output.mp4")
        print("  python burn_subs.py video.mp4 video.srt output.mp4 3")
        sys.exit(1)

    video_file = sys.argv[1]
    subtitle_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else None
    video_mode = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    burn_subtitles(video_file, subtitle_file, output_file, video_mode=video_mode)
