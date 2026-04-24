#!/usr/bin/env python3
"""
record_town.py - Automatically records the GitVille web app as a video.

Uses Playwright to:
  1. Launch the web page (localhost or file://)
  2. Hide UI overlays for a clean cinematic view
  3. Perform scripted camera movements (pan, zoom, click houses)
  4. Save the browser viewport recording as assets/town_recording.mp4

The camera choreography:
  - NEVER zooms out past 1.0 (prevents lag)
  - Visits only a FEW random spots (not the whole map)
  - Moves at a relaxed, natural pace
  - Adapts to any town size (1 house or 1000 houses)

Usage:
  python scripts/record_town.py --url "http://127.0.0.1:5501/web/"
  python scripts/record_town.py --duration 25
"""

import asyncio
import os
import sys
import io
import json
import argparse
import random
import subprocess

# Force UTF-8 stdout on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# --- Configuration ---
VIEWPORT_W = 1080
VIEWPORT_H = 1920
DEFAULT_DURATION = 20  # seconds
OVERVIEW_ZOOM = 1.0    # Brief full-town shot (only at the very start)
CLOSEUP_ZOOM = 1.7     # Close-up house viewing (stays here most of the video)


def grid_to_world(gx, gy):
    """Convert grid (isometric) coords to world coords. Matches web app's gridToWorld()."""
    return (gx - gy) * 50, (gx + gy) * 25


def get_house_data():
    """Load houses.json to know how many houses exist and where the latest ones are."""
    houses_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "houses.json")
    if not os.path.exists(houses_file):
        return [], []

    with open(houses_file, 'r', encoding='utf-8') as f:
        houses = json.load(f)

    active = [h for h in houses if 'username' in h and not h.get('abandoned', False) and not h.get('obstacle')]
    active.sort(key=lambda h: h.get('joined_at', ''), reverse=True)

    return houses, active


def build_camera_choreography(houses, newest_houses, duration):
    """
    Simple choreography:
      1. Brief overview at start (~2s) — show the full town once
      2. Zoom into close-up and STAY there
      3. Slowly pan between 3-4 random houses, clicking some
      4. Never zoom back out — entire video is close-up after the intro
    """
    all_with_coords = [h for h in houses if 'username' in h and not h.get('obstacle')]
    if not all_with_coords:
        all_with_coords = [{'x': 0, 'y': 0, 'username': 'empty'}]

    # Center of town
    start_wx, start_wy = grid_to_world(0, 0)

    # Newest houses (stars of the show)
    newest_world = []
    for h in newest_houses[:3]:
        wx, wy = grid_to_world(h['x'], h['y'])
        newest_world.append((wx, wy, h))

    # Pick 2 random houses for variety
    non_newest = [h for h in all_with_coords if h not in newest_houses[:3]]
    random_picks = random.sample(non_newest, min(2, len(non_newest))) if non_newest else []
    random_world = []
    for h in random_picks:
        wx, wy = grid_to_world(h['x'], h['y'])
        random_world.append((wx, wy, h))

    # === BUILD KEYFRAMES ===
    # overview (2s) → zoom in → close-up for the rest
    keyframes = []

    # --- PHASE 1: Brief overview (0s → 2s) ---
    keyframes.append({
        'time': 0,
        'x': start_wx, 'y': start_wy,
        'zoom': OVERVIEW_ZOOM, 'label': 'overview'
    })

    # --- PHASE 2: Zoom into first house (2s → 4s) ---
    if newest_world:
        wx, wy, h = newest_world[0]
    else:
        wx, wy = start_wx, start_wy
        h = all_with_coords[0]
    keyframes.append({
        'time': 3.5,
        'x': wx, 'y': wy - 20,
        'zoom': CLOSEUP_ZOOM, 'label': f'zoom_in ({h["username"]})'
    })

    # --- PHASE 3: Stay close-up, drift between houses (4s → end) ---
    # Build a visit list: newest + random, interleaved
    visit_spots = []
    if newest_world:
        visit_spots.append(newest_world[0])  # newest #1 (already zoomed here)
    if random_world:
        visit_spots.append(random_world[0])  # random #1
    if len(newest_world) >= 2:
        visit_spots.append(newest_world[1])  # newest #2
    if len(random_world) >= 2:
        visit_spots.append(random_world[1])  # random #2
    if len(newest_world) >= 3:
        visit_spots.append(newest_world[2])  # newest #3

    # Remove duplicates (first house is already where we zoomed in)
    if visit_spots:
        visit_spots = visit_spots[1:]  # skip first, we're already there

    # Distribute remaining time evenly across spots
    close_start = 4.5  # start drifting after zoom-in settles
    close_end = duration - 0.5  # leave 0.5s to settle at the end
    available = close_end - close_start

    if visit_spots:
        time_per_spot = available / len(visit_spots)

        for i, (wx, wy, h) in enumerate(visit_spots):
            # Arrive at house
            arrive_t = close_start + i * time_per_spot
            keyframes.append({
                'time': arrive_t,
                'x': wx, 'y': wy - 20,
                'zoom': CLOSEUP_ZOOM, 'label': f'visit ({h["username"]})'
            })

            # Click house (spawn NPC) — only on newest houses
            if h in [nw[2] for nw in newest_world]:
                click_t = arrive_t + time_per_spot * 0.4
                keyframes.append({
                    'time': click_t,
                    'x': wx, 'y': wy - 20,
                    'zoom': CLOSEUP_ZOOM,
                    'click_grid': (h['x'], h['y']),
                    'label': f'click ({h["username"]})'
                })

            # Slight drift after visiting (feels alive)
            drift_t = arrive_t + time_per_spot * 0.7
            keyframes.append({
                'time': drift_t,
                'x': wx + 30, 'y': wy + 10,
                'zoom': CLOSEUP_ZOOM - 0.05, 'label': 'drift'
            })

    # --- END: Stay close-up, slight settle ---
    keyframes.append({
        'time': duration,
        'x': keyframes[-1]['x'] if keyframes else start_wx,
        'y': keyframes[-1]['y'] if keyframes else start_wy,
        'zoom': CLOSEUP_ZOOM, 'label': 'end (close-up)'
    })

    keyframes.sort(key=lambda k: k['time'])
    return keyframes


async def record(url, output_path, duration, keyframes):
    """Launch Playwright, execute choreography, and record."""
    from playwright.async_api import async_playwright

    print(f"  [LAUNCH] Browser ({VIEWPORT_W}x{VIEWPORT_H})...")

    # Use a temp dir for the raw webm so we can trim it properly
    raw_dir = os.path.join(os.path.dirname(os.path.abspath(output_path)), "_rec_tmp")
    os.makedirs(raw_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': VIEWPORT_W, 'height': VIEWPORT_H},
            record_video_dir=raw_dir,
            record_video_size={'width': VIEWPORT_W, 'height': VIEWPORT_H},
        )

        page = await context.new_page()

        print(f"  [LOAD] {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)

        # Wait for canvas
        await page.wait_for_selector('#gameCanvas', timeout=10000)
        await asyncio.sleep(2)  # Let renderer stabilize

        # Hide UI overlays for cinematic recording
        print(f"  [UI] Hiding overlays for cinematic view...")
        await page.evaluate("""() => {
            const ui = document.getElementById('ui-layer');
            if (ui) ui.style.display = 'none';
            const loading = document.getElementById('loading-screen');
            if (loading) loading.style.display = 'none';
        }""")

        # Mark the start of choreography (for trimming later)
        # Small pause so any remaining UI transitions finish
        await asyncio.sleep(0.5)

        # Execute choreography
        print(f"  [REC] Recording {duration}s of camera choreography...")
        choreo_start_wall = asyncio.get_event_loop().time()
        STEP_INTERVAL = 0.025  # 25ms = 40fps camera updates
        elapsed = 0.0

        while elapsed < duration:
            # Find current and next keyframe
            prev_kf = keyframes[0]
            next_kf = keyframes[-1]
            for i in range(len(keyframes) - 1):
                if keyframes[i]['time'] <= elapsed <= keyframes[i + 1]['time']:
                    prev_kf = keyframes[i]
                    next_kf = keyframes[i + 1]
                    break

            # Smooth step interpolation (ease-in-out)
            kf_duration = next_kf['time'] - prev_kf['time']
            if kf_duration > 0:
                t = (elapsed - prev_kf['time']) / kf_duration
                t = t * t * (3 - 2 * t)
            else:
                t = 1.0

            cam_x = prev_kf['x'] + (next_kf['x'] - prev_kf['x']) * t
            cam_y = prev_kf['y'] + (next_kf['y'] - prev_kf['y']) * t
            cam_zoom = prev_kf['zoom'] + (next_kf['zoom'] - prev_kf['zoom']) * t

            # Clamp zoom
            cam_zoom = max(OVERVIEW_ZOOM, cam_zoom)

            # Apply camera
            await page.evaluate(f"""() => {{
                camera.x = {cam_x};
                camera.y = {cam_y};
                camera.zoom = {cam_zoom};
            }}""")

            # Click house if scheduled
            if 'click_grid' in next_kf:
                click_time = next_kf['time']
                if abs(elapsed - click_time) < STEP_INTERVAL:
                    gx, gy = next_kf['click_grid']
                    screen_pos = await page.evaluate(f"""() => {{
                        const worldPos = gridToWorld({gx}, {gy});
                        const centerX = canvas.width / 2;
                        const centerY = canvas.height / 2;
                        return {{
                            x: (worldPos.x - camera.x) * camera.zoom + centerX,
                            y: (worldPos.y - camera.y) * camera.zoom + centerY
                        }};
                    }}""")
                    sx, sy = screen_pos['x'], screen_pos['y']
                    if 0 <= sx <= VIEWPORT_W and 0 <= sy <= VIEWPORT_H:
                        await page.mouse.click(sx, sy)
                        print(f"     [CLICK] House at ({gx},{gy}) -> screen ({sx:.0f},{sy:.0f})")

            await asyncio.sleep(STEP_INTERVAL)
            elapsed += STEP_INTERVAL

            # Progress every 5 seconds
            if int(elapsed * 10) % 50 == 0:
                pct = int((elapsed / duration) * 100)
                label = next_kf.get('label', '')
                print(f"     [{pct:3d}%] t={elapsed:.1f}s zoom={cam_zoom:.2f} -> {label}")

        choreo_wall_time = asyncio.get_event_loop().time() - choreo_start_wall
        print(f"  [OK] Choreography done! (wall time: {choreo_wall_time:.1f}s)")

        # Close and save video
        await page.close()
        await context.close()
        await browser.close()

    # Find the raw webm, convert + TRIM to exactly `duration` seconds from the END
    for f in os.listdir(raw_dir):
        if f.endswith('.webm'):
            webm_path = os.path.join(raw_dir, f)

            # Probe raw duration
            probe = subprocess.run(
                ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', webm_path],
                capture_output=True, text=True
            )
            raw_dur = float(probe.stdout.strip())
            print(f"  [TRIM] Raw recording: {raw_dur:.1f}s -> trimming to last {duration}s")

            # Trim from the end: skip the page-load portion at the start
            skip = max(0, raw_dur - duration - 1)  # 1s buffer before choreography

            subprocess.run([
                'ffmpeg', '-y',
                '-ss', str(skip),
                '-i', webm_path,
                '-t', str(duration + 1),
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
                '-pix_fmt', 'yuv420p',
                '-r', '60',
                '-an',
                output_path,
            ], check=True, capture_output=True)

            # Cleanup
            import shutil
            shutil.rmtree(raw_dir, ignore_errors=True)

            final_dur = float(subprocess.run(
                ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', output_path],
                capture_output=True, text=True
            ).stdout.strip())
            print(f"  [OK] Saved: {output_path} ({final_dur:.1f}s)")
            return

    print(f"  [WARN] Could not find recorded video file")
    import shutil
    shutil.rmtree(raw_dir, ignore_errors=True)


async def async_main():
    parser = argparse.ArgumentParser(description="Auto-record the GitVille town")
    parser.add_argument("--url", default=None,
                        help="URL of the web app (default: file:// path to web/index.html)")
    parser.add_argument("--output", default="assets/town_recording.mp4",
                        help="Output video path")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help="Recording duration in seconds")
    args = parser.parse_args()

    # Resolve URL
    url = args.url
    if not url:
        web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
        index_path = os.path.join(web_dir, "index.html")
        if not os.path.exists(index_path):
            print(f"[ERROR] Web app not found at {index_path}")
            sys.exit(1)
        url = f"file:///{index_path.replace(os.sep, '/')}"

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)

    # Load house data
    print(f"\n=== GitVille Town Recorder ===")
    houses, newest = get_house_data()
    total = len([h for h in houses if 'username' in h and not h.get('obstacle')])
    active = len([h for h in houses if 'username' in h and not h.get('abandoned', False) and not h.get('obstacle')])
    print(f"   Houses: {total} total, {active} active")
    if newest:
        print(f"   Newest: {', '.join(h['username'] for h in newest[:3])}")
    print(f"   Duration: {args.duration}s")
    print(f"   Output: {args.output}")

    # Build camera choreography
    print(f"\n--- Camera Choreography ---")
    keyframes = build_camera_choreography(houses, newest, args.duration)
    for kf in keyframes:
        click = " [CLICK]" if 'click_grid' in kf else ""
        print(f"   [{kf['time']:5.1f}s] zoom={kf['zoom']:.2f}  {kf.get('label', '')}{click}")

    # Record
    print(f"\n--- Starting Recording ---")
    await record(url, args.output, args.duration, keyframes)

    print(f"\n=== Done! ===")


if __name__ == "__main__":
    asyncio.run(async_main())
