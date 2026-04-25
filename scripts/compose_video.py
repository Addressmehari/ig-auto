#!/usr/bin/env python3
"""
compose_video.py — Composes the final GitVille daily update video.

NEW APPROACH: Record ONE ~20s screen recording of the web app
(pan around, tap latest houses, show the town) and drop it in assets/.
The script auto-slices it into all the clips needed.

Combines:
  - Auto-sliced screen recording segments
  - Auto-extracted stats scenes (from city_summary.mp4)
  - Voice narration (video_voice.mp3)
  - Text overlays per the cut plan

Usage:
  python scripts/compose_video.py
  python scripts/compose_video.py --recording assets/screen_recording.mp4
  python scripts/compose_video.py --skip-text
"""

import subprocess
import os
import sys
import argparse
import re
import shutil
import random

# ──────────────────── Video Settings ──────────────────────────
WIDTH = 1080
HEIGHT = 1920
FPS = 60
TRANSITION_DUR = 0.3  # seconds per xfade transition

# ─── xfade transition types between clips ─────────────────────
TRANSITIONS = ["smoothup", "slideleft", "fadewhite", "dissolve", "slideup", "circlecrop", "fade"]


def run_cmd(cmd, label="", capture=True):
    """Run a subprocess command with error handling."""
    print(f"  ⚙️  {label}..." if label else "  ⚙️  Running ffmpeg...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=capture, text=True)
        return result
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Error: {e}")
        if capture and e.stderr:
            for line in e.stderr.strip().split('\n')[-10:]:
                print(f"     {line}")
        sys.exit(1)


def probe_duration(filepath):
    """Get media file duration in seconds."""
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', filepath],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


def get_font():
    """Get available Impact-style font path for FFmpeg."""
    # Windows paths
    if os.path.exists("C:/Windows/Fonts/impact.ttf"):
        return r"C\:/Windows/Fonts/impact.ttf"
    if os.path.exists("C:/Windows/Fonts/arialbd.ttf"):
        return r"C\:/Windows/Fonts/arialbd.ttf"
        
    # Linux (GitHub Actions) paths
    linux_fonts = [
        "/usr/share/fonts/truetype/roboto/hinted/Roboto-Black.ttf",
        "/usr/share/fonts/truetype/open-sans/OpenSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for f in linux_fonts:
        if os.path.exists(f):
            return f
            
    return "arial.ttf"


def parse_script(script_file):
    """Parse video_script.txt to extract key data for text overlays."""
    with open(script_file, 'r', encoding='utf-8') as f:
        content = f.read()

    day = 1
    m = re.search(r'Day (\d+)', content)
    if m:
        day = int(m.group(1))

    newcomers = 0
    m = re.search(r'\+(\d+) people moved in', content)
    if m:
        newcomers = int(m.group(1))

    unfollows = 0
    m = re.search(r'-(\d+) people left', content)
    if m:
        unfollows = int(m.group(1))

    population = 0
    m = re.search(r'Current population: (\d+)', content)
    if m:
        population = int(m.group(1))

    # Event line: the line after "Current population: X"
    event_line = "The town is buzzing with excitement!"
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        if line.startswith("Current population"):
            if i + 1 < len(lines):
                candidate = lines[i + 1]
                candidate = candidate.encode('ascii', 'ignore').decode('ascii').strip()
                if candidate:
                    event_line = candidate
            break

    houses_built = newcomers
    m = re.search(r'I built (\d+) new house', content)
    if m:
        houses_built = int(m.group(1))

    return {
        'day': day,
        'newcomers': newcomers,
        'unfollows': unfollows,
        'population': population,
        'event_line': event_line,
        'houses_built': houses_built,
    }


def compute_recording_slices(rec_duration):
    """
    Given a screen recording, compute 3 slices.
    Clip 1: Hook (used before stats)
    Clip 2: Tutorial (used after stats, shows the 4 steps)
    Clip 3: CTA (shows the final call to action)
    """
    proportions = [0.25, 0.55, 0.20]

    slices = []
    cursor = 0.0
    for p in proportions:
        dur = rec_duration * p
        slices.append((cursor, dur))
        cursor += dur

    return slices


def prepare_clip(input_file, output_file, duration, trim_start=0):
    """Scale, crop, and trim a clip to 1080x1920 with no audio."""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(trim_start),
        '-i', input_file,
        '-t', str(duration),
        '-vf', (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"setsar=1,"
            f"tpad=stop_mode=clone:stop_duration=20,"
            f"fps=fps={FPS}"
        ),
        '-r', str(FPS),
        '-vsync', 'cfr',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-an',
        output_file,
    ]
    run_cmd(cmd, f"Preparing {os.path.basename(output_file)}")


def add_text_overlays(input_file, output_file, texts, font):
    """Add one or more text overlays to a clip using drawtext filters."""
    if not texts:
        shutil.copy2(input_file, output_file)
        return

    # First pass: draw box backgrounds, then text on top
    box_filters = []
    text_filters = []

    for t in texts:
        text = t['text'].replace("'", "\u2019").replace(":", "\\:")
        size = t.get('size', 70)
        color = t.get('color', 'white')
        appear = t.get('appear', 0)
        fade_in = t.get('fade_in', 0.3)
        pos = t.get('position', 'center')
        box = t.get('box', False)
        box_color = t.get('box_color', 'black@0.55')
        border_color = t.get('border_color', 'black')
        border_w = t.get('border_w', 5)
        shadow_color = t.get('shadow_color', 'black@0.8')
        shadow_x = t.get('shadow_x', 4)
        shadow_y = t.get('shadow_y', 4)

        if pos == 'center':
            x, y = '(w-text_w)/2', '(h-text_h)/2'
        elif pos == 'top':
            x, y = '(w-text_w)/2', str(HEIGHT // 5)
        elif pos == 'bottom_third':
            x, y = '(w-text_w)/2', str(int(HEIGHT * 0.73))
        elif pos == 'custom_y':
            x, y = '(w-text_w)/2', str(t.get('y', HEIGHT // 2))
        elif pos == 'left_pad':
            x, y = str(t.get('x', 60)), str(t.get('y', HEIGHT // 2))
        else:
            x, y = '(w-text_w)/2', '(h-text_h)/2'

        # Support optional disappear + fade_out for one-at-a-time effect
        if 'disappear' in t:
            disappear = t['disappear']
            fade_out = t.get('fade_out', 0.25)
            alpha = (
                f"if(lt(t,{appear}),0,"
                f"if(lt(t,{appear + fade_in}),(t-{appear})/{fade_in},"
                f"if(lt(t,{disappear}),1,"
                f"if(lt(t,{disappear + fade_out}),1-(t-{disappear})/{fade_out},0))))"
            )
        else:
            alpha = f"if(lt(t,{appear}),0,if(lt(t,{appear + fade_in}),(t-{appear})/{fade_in},1))"

        box_str = f":box=1:boxcolor={box_color}:boxborderw={t.get('box_pad', 20)}" if box else ""

        text_filters.append(
            f"drawtext=fontfile='{font}':text='{text}':"
            f"fontcolor={color}:fontsize={size}:"
            f"x={x}:y={y}:"
            f"borderw={border_w}:bordercolor={border_color}:"
            f"shadowcolor={shadow_color}:shadowx={shadow_x}:shadowy={shadow_y}:"
            f"alpha='{alpha}'"
            f"{box_str}"
        )

    vf = ",".join(text_filters)
    cmd = [
        'ffmpeg', '-y',
        '-i', input_file,
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-an',
        output_file,
    ]
    run_cmd(cmd, f"Adding text to {os.path.basename(output_file)}")


def add_character_overlay(input_file, output_file, poses):
    """
    Overlay multiple character PNGs (transparent BG) onto the bottom half of the clip.
    poses: list of dicts {"path": str, "start": float, "end": float}
    """
    valid_poses = [p for p in poses if os.path.exists(p["path"])]
    if not valid_poses:
        print(f"  ⚠️  No character images found — skipping overlay")
        shutil.copy2(input_file, output_file)
        return

    char_h = int(HEIGHT * 0.7)
    anchor_y = HEIGHT - char_h

    inputs = ['-i', input_file]
    filter_complex_parts = []
    
    # Scale each pose image
    for i, pose in enumerate(valid_poses):
        inputs.extend(['-i', pose["path"]])
        filter_complex_parts.append(f"[{i+1}:v]scale=-2:{char_h}[c{i}]")
    
    # Chain overlays with enable='between(t,s,e)'
    curr_v = "[0:v]"
    for i, pose in enumerate(valid_poses):
        out_v = f"[v{i+1}]"
        # If it's the last one, we don't necessarily need a label, 
        # but we need to add setsar=1 to the final output.
        s = pose["start"]
        e = pose["end"]
        filter_complex_parts.append(f"{curr_v}[c{i}]overlay=(W-w)/2:{anchor_y}:enable='between(t,{s},{e})':format=auto{out_v}")
        curr_v = out_v

    # Final touch: setsar=1 on the last video node
    filter_complex_parts.append(f"{curr_v}setsar=1[fout]")
    filter_complex = ";".join(filter_complex_parts)

    cmd = [
        'ffmpeg', '-y',
    ] + inputs + [
        '-filter_complex', filter_complex,
        '-map', '[fout]',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-an',
        output_file,
    ]
    run_cmd(cmd, f"Overlaying {len(valid_poses)} poses on {os.path.basename(output_file)}")


def concat_with_xfade(clip_files, output_file):
    """Join all clips using xfade transitions."""
    if len(clip_files) == 1:
        shutil.copy2(clip_files[0], output_file)
        return

    durations = [probe_duration(f) for f in clip_files]

    inputs = []
    for f in clip_files:
        inputs += ['-i', f]

    # All clips are already prepared at constant 60fps — just alias the streams.
    # Do NOT use setpts=PTS-STARTPTS here; it resets PTS to 0 for each input
    # independently, causing xfade to see a 1/0 frame rate and fail.
    parts = []
    for i in range(len(clip_files)):
        parts.append(f"[{i}:v]format=yuv420p[v{i}]")

    prev = "v0"
    offset_acc = durations[0] - TRANSITION_DUR

    for i in range(1, len(clip_files)):
        trans = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        out_label = f"xf{i}" if i < len(clip_files) - 1 else "vfinal"

        parts.append(
            f"[{prev}][v{i}]xfade=transition={trans}:duration={TRANSITION_DUR}:offset={offset_acc:.3f}[{out_label}]"
        )
        prev = out_label

        if i < len(clip_files) - 1:
            offset_acc += durations[i] - TRANSITION_DUR

    filter_str = ";\n".join(parts)

    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', filter_str,
        '-map', '[vfinal]',
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-r', str(FPS),
        '-an',
        output_file,
    ]
    run_cmd(cmd, "Concatenating clips with transitions", capture=False)


def extract_stats_audio(stats_video, output_audio):
    """Extract audio from city_summary.mp4 (has tick sounds + meme sounds)."""
    cmd = [
        'ffmpeg', '-y',
        '-i', stats_video,
        '-vn',
        '-acodec', 'pcm_s16le',
        '-ar', '44100', '-ac', '2',
        output_audio,
    ]
    run_cmd(cmd, "Extracting stats audio")


def mix_final_audio(video_file, voice_file, stats_audio_file, bg_music_file, stats_offset, output_file):
    """Mix voice narration + stats audio + bg music onto the final video."""
    has_stats = stats_audio_file and os.path.exists(stats_audio_file)
    has_bg = bg_music_file and os.path.exists(bg_music_file)

    cmd = ['ffmpeg', '-y', '-i', video_file, '-i', voice_file]
    
    input_idx = 2
    filter_parts = []
    # Mix components: index 0 is the setup string, remaining are node names
    mix_inputs = ["[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=1.0[voice];", "[voice]"]
    
    if has_stats:
        cmd.extend(['-i', stats_audio_file])
        delay_ms = int(stats_offset * 1000)
        filter_parts.append(
            f"[{input_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms},volume=0.8[stats];"
        )
        mix_inputs.append("[stats]")
        input_idx += 1
        
    if has_bg:
        cmd.extend(['-stream_loop', '-1', '-i', bg_music_file])
        # Very low volume (12%) so voice is clearly heard
        filter_parts.append(
            f"[{input_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.12[bg];"
        )
        mix_inputs.append("[bg]")
        input_idx += 1
        
    if len(mix_inputs) > 2:
        mix_nodes = "".join(mix_inputs[1:])
        filter_str = mix_inputs[0] + "".join(filter_parts) + f"{mix_nodes}amix=inputs={len(mix_inputs)-1}:duration=first:normalize=0[aout]"
        cmd.extend([
            '-filter_complex', filter_str,
            '-map', '0:v', '-map', '[aout]',
        ])
    else:
        cmd.extend(['-map', '0:v', '-map', '1:a'])
        
    cmd.extend([
        '-c:v', 'copy',
        '-c:a', 'aac', '-b:a', '192k',
        '-shortest',
        output_file,
    ])

    run_cmd(cmd, "Mixing final audio", capture=False)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Compose the final GitVille video")
    parser.add_argument("--recording", default=None,
                        help="Single screen recording to auto-slice (default: auto-detect in assets/)")
    parser.add_argument("--voice", default="video_voice.mp3", help="Voice narration")
    parser.add_argument("--script", default="video_script.txt", help="Script file")
    parser.add_argument("--stats-video", default="city_summary.mp4", help="Stats animation")
    parser.add_argument("--bg-music", default=None, help="Background music file")
    parser.add_argument("--output", default="final_video.mp4", help="Output file")
    parser.add_argument("--skip-text", action="store_true", help="Skip text overlays")
    args = parser.parse_args()

    # ─── Parse Script ─────────────────────────────────────────
    if not os.path.exists(args.script):
        print(f"❌ Script file not found: {args.script}")
        sys.exit(1)

    data = parse_script(args.script)
    print(f"\n🏘️  GitVille Composer")
    print(f"   Day {data['day']} | Pop: {data['population']} | +{data['newcomers']}/-{data['unfollows']}")
    print(f"   Event: \"{data['event_line'][:60]}\"")

    # ─── Check Voice ──────────────────────────────────────────
    if not os.path.exists(args.voice):
        print(f"❌ Voice file not found: {args.voice}")
        sys.exit(1)
    voice_dur = probe_duration(args.voice)
    print(f"   Voice: {voice_dur:.2f}s")

    # ─── Find Screen Recording ────────────────────────────────
    recording = args.recording
    if not recording:
        # Auto-detect: look for any video file in assets/
        assets_dir = "assets"
        if os.path.isdir(assets_dir):
            for f in os.listdir(assets_dir):
                if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
                    recording = os.path.join(assets_dir, f)
                    break

    if not recording or not os.path.exists(recording):
        print(f"\n❌ No screen recording found!")
        print(f"   Record a ~20s video of your town and save it as:")
        print(f"   assets/screen_recording.mp4")
        print(f"\n   Just pan around the town, tap on latest houses,")
        print(f"   show NPCs walking, zoom in/out — keep it natural!")
        sys.exit(1)

    rec_dur = probe_duration(recording)
    print(f"   Recording: {recording} ({rec_dur:.2f}s)")

    # ─── Check Stats Video ────────────────────────────────────
    has_stats = os.path.exists(args.stats_video)
    if has_stats:
        stats_dur = probe_duration(args.stats_video)
        print(f"   Stats video: {args.stats_video} ({stats_dur:.2f}s)")
    else:
        stats_dur = 0
        print(f"   ⚠️  Stats video not found — will use recording for everything")

    # ─── Create Temp Dir ──────────────────────────────────────
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), "_compose_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    font = get_font()

    # ─── Calculate Clip Durations ─────────────────────────────
    # Final video = voice duration
    # 8 clips, 7 transitions → sum(clip_dur) - 7*TRANSITION_DUR = voice_dur
    # → sum(clip_dur) = voice_dur + 7*TRANSITION_DUR
    num_clips = 6 if has_stats else 3
    num_transitions = num_clips - 1
    total_clip_time = voice_dur + num_transitions * TRANSITION_DUR

    if has_stats:
        # 6 clips: recording(hook) + stats(3 scenes) + recording(tutorial) + recording(cta)
        # Stats scenes have fixed durations from city_summary.mp4
        # NEW CITIZENS: 0→2.8s, LEFT CITY: 3.6→6.4s, POPULATION: 7.2→end
        stats_clip_durs = [3.5, 3.6, stats_dur - 7.1]
        stats_total = sum(stats_clip_durs)

        # Remaining time for recording clips
        rec_clip_total = total_clip_time - stats_total

        # 3 recording clips
        rec_proportions = [0.25, 0.55, 0.20]
        rec_clip_durs = [rec_clip_total * p for p in rec_proportions]
    else:
        # No stats video — all clips from recording
        rec_proportions = [0.25, 0.55, 0.20]
        rec_clip_durs = [total_clip_time * p for p in rec_proportions]

    # ─── Slice Recording ──────────────────────────────────────
    print(f"\n📹 Step 1: Slicing screen recording into clips...")

    rec_slices = compute_recording_slices(rec_dur)
    rec_clip_files = []

    # ── Text overlays for each recording slice ─────────────────
    rec_texts = [

        # ── Clip 1: Hook ──────────────────────────────────────────
        [
            # GITVILLE label: bright gold, thick BLACK border
            {
                "text": "GITVILLE",
                "position": "custom_y", "y": int(HEIGHT * 0.35),
                "size": 100, "color": "#FFD700",
                "appear": 0.0, "fade_in": 0.2,
                "border_w": 8, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 5, "shadow_y": 5,
            },
            # DAY number: pure white, extra-thick BLACK border
            {
                "text": f"DAY {data['day']}",
                "position": "custom_y", "y": int(HEIGHT * 0.45),
                "size": 200, "color": "white",
                "appear": 0.1, "fade_in": 0.15,
                "border_w": 10, "border_color": "black",
                "shadow_color": "black@0.95", "shadow_x": 6, "shadow_y": 6,
            },
            # Subtitle: bright cyan, thick BLACK border
            {
                "text": "Daily Update",
                "position": "custom_y", "y": int(HEIGHT * 0.63),
                "size": 55, "color": "#00E5FF",
                "appear": 0.4, "fade_in": 0.3,
                "border_w": 5, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 3, "shadow_y": 3,
            },
        ],

        # ── Clip 2: Tutorial ──────────────────────────────────────
        # Text stays in UPPER HALF only (y < HEIGHT/2 = 960px).
        # Character avatar sits in the bottom half.
        # Steps appear ONE AT A TIME — each fades out before the next.
        [
            # Persistent header (stays whole clip) — BLACK on solid GOLD
            {
                "text": "  HOW TO GET YOUR HOUSE  ",
                "position": "custom_y", "y": int(HEIGHT * 0.04),
                "size": 58, "color": "black",
                "appear": 0.0, "fade_in": 0.2,
                "box": True, "box_color": "#FFD700@1.0", "box_pad": 20,
                "border_w": 0, "border_color": "black",
                "shadow_color": "black@0.0", "shadow_x": 0, "shadow_y": 0,
            },
            # Step 1 — WHITE on solid BLUE, fades out at t=3.8
            {
                "text": "  1.  Follow this page  ",
                "position": "custom_y", "y": int(HEIGHT * 0.18),
                "size": 62, "color": "white",
                "appear": 0.5, "fade_in": 0.3,
                "disappear": 3.8, "fade_out": 0.3,
                "box": True, "box_color": "#1565C0@1.0", "box_pad": 22,
                "border_w": 6, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 4, "shadow_y": 4,
            },
            # Step 2 — BLACK on solid LIME, fades out at t=7.5
            {
                "text": "  2.  Tap link in bio  ",
                "position": "custom_y", "y": int(HEIGHT * 0.18),
                "size": 62, "color": "black",
                "appear": 4.2, "fade_in": 0.3,
                "disappear": 7.5, "fade_out": 0.3,
                "box": True, "box_color": "#76FF03@1.0", "box_pad": 22,
                "border_w": 0, "border_color": "black",
                "shadow_color": "black@0.0", "shadow_x": 0, "shadow_y": 0,
            },
            # Step 3 — YELLOW on solid PURPLE, fades out at t=11.2
            {
                "text": "  3.  Search your username  ",
                "position": "custom_y", "y": int(HEIGHT * 0.18),
                "size": 62, "color": "#FFE500",
                "appear": 7.9, "fade_in": 0.3,
                "disappear": 11.2, "fade_out": 0.3,
                "box": True, "box_color": "#6A1B9A@1.0", "box_pad": 22,
                "border_w": 6, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 4, "shadow_y": 4,
            },
            # Closing note — BLACK on solid CYAN, stays till end
            {
                "text": "  Not there yet? Builds overnight!  ",
                "position": "custom_y", "y": int(HEIGHT * 0.18),
                "size": 46, "color": "black",
                "appear": 11.6, "fade_in": 0.4,
                "box": True, "box_color": "#00E5FF@1.0", "box_pad": 18,
                "border_w": 0, "border_color": "black",
                "shadow_color": "black@0.0", "shadow_x": 0, "shadow_y": 0,
            },
        ],

        # ── Clip 3: CTA (no character) ────────────────────────────
        [
            # BLACK text on solid GOLD
            {
                "text": "  YOUR HOUSE IS WAITING  ",
                "position": "custom_y", "y": int(HEIGHT * 0.37),
                "size": 76, "color": "black",
                "appear": 0.1, "fade_in": 0.2,
                "box": True, "box_color": "#FFD700@1.0", "box_pad": 24,
                "border_w": 0, "border_color": "black",
                "shadow_color": "black@0.0", "shadow_x": 0, "shadow_y": 0,
            },
            # WHITE text on solid RED box, BLACK border
            {
                "text": "  FOLLOW + FIND YOUR NAME  ",
                "position": "custom_y", "y": int(HEIGHT * 0.52),
                "size": 54, "color": "white",
                "appear": 0.8, "fade_in": 0.25,
                "box": True, "box_color": "#D50000@1.0", "box_pad": 20,
                "border_w": 6, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 4, "shadow_y": 4,
            },
            # Lime green floating text, black border, no box
            {
                "text": "New houses built EVERY day",
                "position": "custom_y", "y": int(HEIGHT * 0.66),
                "size": 46, "color": "#76FF03",
                "appear": 1.6, "fade_in": 0.35,
                "border_w": 6, "border_color": "black",
                "shadow_color": "black@0.9", "shadow_x": 4, "shadow_y": 4,
            },
        ],

    ]



    rec_target_durs = rec_clip_durs if has_stats else rec_clip_durs
    clip_names = ["hook", "tutorial", "cta"]

    # ── Pick character poses that MATCH the voice gender ───────
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    gender = None
    voice_choice_file = "voice_choice.json"
    if os.path.exists(voice_choice_file):
        try:
            import json as _json
            with open(voice_choice_file, "r") as _vf:
                gender = _json.load(_vf).get("gender")  # "male" or "female"
        except Exception:
            gender = None

    if gender not in ["male", "female"]:
        gender = random.choice(["male", "female"])

    suffix = "m" if gender == "male" else "f"
    poses_paths = [os.path.join(project_root, "images", f"pose{j}_{suffix}.png") for j in range(1, 5)]

    # Fallback to other gender if primary poses are missing
    if not any(os.path.exists(p) for p in poses_paths):
        suffix = "f" if suffix == "m" else "m"
        poses_paths = [os.path.join(project_root, "images", f"pose{j}_{suffix}.png") for j in range(1, 5)]

    # Define timing for poses (roughly matching the tutorial steps text)
    # Step 1: 0.5-3.8, Step 2: 4.2-7.5, Step 3: 7.9-11.2, Step 4: 11.6-end
    chosen_poses = [
        {"path": poses_paths[0], "start": 0.0,  "end": 4.0},
        {"path": poses_paths[1], "start": 4.0,  "end": 7.7},
        {"path": poses_paths[2], "start": 7.7,  "end": 11.4},
        {"path": poses_paths[3], "start": 11.4, "end": 999.0},
    ]

    print(f"  [CHAR]  Tutorial character: {gender} (4 poses loaded)")

    for i, (start, natural_dur) in enumerate(rec_slices):
        target_dur = rec_target_durs[i]
        actual_dur = target_dur

        raw_file   = os.path.join(tmp_dir, f"rec_{clip_names[i]}_raw.mp4")
        char_file  = os.path.join(tmp_dir, f"rec_{clip_names[i]}_char.mp4")
        final_file = os.path.join(tmp_dir, f"rec_{clip_names[i]}.mp4")

        prepare_clip(recording, raw_file, actual_dur, trim_start=start)

        # ── Tutorial clip only: overlay the character poses in the bottom half ──
        if i == 1 and not args.skip_text:
            add_character_overlay(raw_file, char_file, chosen_poses)
            base_for_text = char_file
        else:
            base_for_text = raw_file

        # ── Add text overlays on top ──
        if not args.skip_text and i < len(rec_texts) and rec_texts[i]:
            add_text_overlays(base_for_text, final_file, rec_texts[i], font)
        else:
            shutil.copy2(base_for_text, final_file)

        rec_clip_files.append(final_file)
        print(f"  ✅ {clip_names[i]}: {start:.1f}s → {start + actual_dur:.1f}s ({actual_dur:.2f}s)")

    # ─── Extract Stats Clips ─────────────────────────────────
    stats_clip_files = []
    stats_offset_in_timeline = 0

    if has_stats:
        print(f"\n📊 Step 2: Extracting stats scenes from city_summary...")

        # Scene timings from make_video.py
        stats_scenes = [
            ("new_citizens", 0.0, stats_clip_durs[0]),
            ("left_city", 3.5, stats_clip_durs[1]),
            ("population", 7.1, stats_clip_durs[2]),
        ]

        for name, trim_start, dur in stats_scenes:
            out_file = os.path.join(tmp_dir, f"stats_{name}.mp4")
            prepare_clip(args.stats_video, out_file, dur, trim_start=trim_start)
            stats_clip_files.append(out_file)
            print(f"  ✅ {name}: trim@{trim_start:.1f}s ({dur:.2f}s)")

    # ─── Build Final Clip Order ───────────────────────────────
    # Order: hook → stats(3) → tutorial → cta
    if has_stats:
        ordered_clips = [
            rec_clip_files[0],      # hook
            stats_clip_files[0],    # new citizens
            stats_clip_files[1],    # left city
            stats_clip_files[2],    # population
            rec_clip_files[1],      # tutorial
            rec_clip_files[2],      # cta
        ]
        # Stats audio starts when clip2 (index 1) begins in the timeline
        # = duration_of_clip1 - transition_dur (because of xfade overlap)
        stats_offset_in_timeline = probe_duration(rec_clip_files[0]) - TRANSITION_DUR
    else:
        ordered_clips = rec_clip_files

    print(f"\n🎬 Step 3: Concatenating {len(ordered_clips)} clips with transitions...")
    concat_file = os.path.join(tmp_dir, "concat_video.mp4")
    concat_with_xfade(ordered_clips, concat_file)
    concat_dur = probe_duration(concat_file)
    print(f"  ✅ Concatenated: {concat_dur:.2f}s (voice: {voice_dur:.2f}s)")

    # ─── Extract Stats Audio + Mix ────────────────────────────
    stats_audio = None
    if has_stats:
        print(f"\n🔊 Step 4: Extracting stats audio (ticks + SFX)...")
        stats_audio = os.path.join(tmp_dir, "stats_audio.wav")
        extract_stats_audio(args.stats_video, stats_audio)
        print(f"  ✅ Stats audio → offset at {stats_offset_in_timeline:.2f}s")

    print(f"\n🎙️  Step 5: Mixing voice + stats audio + bg music...")
    mix_final_audio(concat_file, args.voice, stats_audio, args.bg_music, stats_offset_in_timeline, args.output)

    final_duration = probe_duration(args.output)
    print(f"\n✅ Done! → {args.output} ({final_duration:.2f}s)")

    # ─── Cleanup ──────────────────────────────────────────────
    print("🧹 Cleaning up temp files...")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print("🎉 All done!\n")


if __name__ == "__main__":
    main()
