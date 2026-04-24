#!/usr/bin/env python3
"""
compose_video.py  —  GitVille One-Command Video Pipeline

Usage:
    python compose_video.py names.txt
    python compose_video.py names.txt --skip-record   # reuse existing town_recording.mp4
    python compose_video.py names.txt --skip-text     # skip text overlays on final video
    python compose_video.py names.txt --url http://localhost:5501/web/

The 5-step chain:
    [1] fetch_houses  → data/houses.json + data/roads.json
    [2] make_video    → city_summary.mp4  (animated stats counter)
    [3] gen_script    → video_script.txt + video_voice.mp3  (AI narration)
    [4] record_town   → assets/town_recording.mp4  (Playwright browser recording)
    [5] compose       → final_video.mp4  (final stitched video)
"""

import subprocess
import sys
import os
import json
import argparse
import time
import io

# ── Force UTF-8 on Windows terminals ────────────────────────────────────────
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths (all relative to this file's location = project root) ─────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")

FETCH_HOUSES  = os.path.join(SCRIPTS, "fetch_houses.py")
MAKE_VIDEO    = os.path.join(SCRIPTS, "make_video.py")
GEN_SCRIPT    = os.path.join(SCRIPTS, "generate_script.py")
RECORD_TOWN   = os.path.join(SCRIPTS, "record_town.py")
COMPOSE_VIDEO = os.path.join(SCRIPTS, "compose_video.py")

HOUSES_JSON   = os.path.join(ROOT, "data", "houses.json")
META_JSON     = os.path.join(ROOT, "data", "town_meta.json")
CITY_SUMMARY  = os.path.join(ROOT, "city_summary.mp4")
VIDEO_SCRIPT  = os.path.join(ROOT, "video_script.txt")
VIDEO_VOICE   = os.path.join(ROOT, "video_voice.mp3")
RECORDING     = os.path.join(ROOT, "assets", "town_recording.mp4")
FINAL_VIDEO   = os.path.join(ROOT, "final_video.mp4")


# ── Helpers ──────────────────────────────────────────────────────────────────

def banner(step, total, title):
    bar = "─" * 54
    print(f"\n┌{bar}┐")
    print(f"│  STEP {step}/{total}  {title:<44}│")
    print(f"└{bar}┘")


def run(cmd, label, cwd=ROOT, capture=True):
    """Run a subprocess, stream output, exit on failure."""
    t0 = time.time()
    print(f"  ▶  {label}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=True,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        elapsed = time.time() - t0
        print(f"  ✅ Done in {elapsed:.1f}s")
        return result
    except subprocess.CalledProcessError as e:
        print(f"\n  ❌ FAILED — {label}")
        if capture and e.stderr:
            for line in e.stderr.strip().split("\n")[-15:]:
                print(f"     {line}")
        sys.exit(1)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def compute_stats_before(names_set):
    """
    Calculate old_active, newcomers, newly_abandoned before fetch_houses updates the data.
    We read the CURRENT houses.json so we can pass accurate numbers to make_video.
    """
    houses = load_json(HOUSES_JSON) or []
    existing_active = set(
        h["username"] for h in houses
        if "username" in h and not h.get("abandoned", False)
    )
    newcomers_set = names_set - existing_active
    newcomers = len(newcomers_set)
    newly_abandoned = len(existing_active - names_set)
    old_active = len(existing_active)
    new_active = len(names_set)
    newcomer_names_str = ",".join(list(newcomers_set))
    return old_active, new_active, newcomers, newly_abandoned, newcomer_names_str


def read_names(names_file):
    with open(names_file, "r", encoding="utf-8") as f:
        content = f.read()
    return set(n.strip() for n in content.replace(",", "\n").split("\n") if n.strip())


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GitVille — full video pipeline in one command",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("names", help="Path to names.txt (your followers list)")
    parser.add_argument("--output", default=FINAL_VIDEO, help="Final video output path")
    parser.add_argument("--url", default="http://127.0.0.1:5501/web/",
                        help="Web app URL for recording (default: http://127.0.0.1:5501/web/)")
    parser.add_argument("--record-duration", type=int, default=30,
                        help="Town recording duration in seconds (default: 30)")
    parser.add_argument("--skip-record", action="store_true",
                        help="Skip Step 4 — reuse existing assets/town_recording.mp4")
    parser.add_argument("--skip-text", action="store_true",
                        help="Skip text overlays in the final composition")
    parser.add_argument("--bg-music", default="subway_surfers.mp3",
                        help="Path to background music file")
    parser.add_argument("--groq-model", default="qwen/qwen3-32b",
                        help="Groq model to use for script generation")
    args = parser.parse_args()

    # Validate names file
    names_file = os.path.abspath(args.names)
    if not os.path.exists(names_file):
        print(f"❌ Names file not found: {names_file}")
        sys.exit(1)

    names_set = read_names(names_file)
    if not names_set:
        print(f"❌ No names found in {names_file}")
        sys.exit(1)

    total_steps = 5 if not args.skip_record else 4

    print(f"\n{'═' * 56}")
    print(f"  🏘️   GitVille Video Pipeline")
    print(f"  📋  {len(names_set)} names  |  output → {os.path.basename(args.output)}")
    print(f"{'═' * 56}")

    # ── Pre-calculate stats BEFORE we mutate houses.json ──────────────────
    old_active, new_active, newcomers, newly_abandoned, newcomer_names_str = compute_stats_before(names_set)
    print(f"\n  📊  Stats preview:")
    print(f"      Population:  {old_active} → {new_active}")
    print(f"      Newcomers:   +{newcomers}")
    print(f"      Left:        -{newly_abandoned}")

    # ─────────────────────────────────────────────────────────────────────
    # STEP 1 — Update houses.json
    # ─────────────────────────────────────────────────────────────────────
    banner(1, total_steps, "Updating town data (fetch_houses)")
    run(
        [sys.executable, FETCH_HOUSES, names_file],
        "Syncing city for new follower list...",
        capture=False,
    )

    # ─────────────────────────────────────────────────────────────────────
    # STEP 2 — Generate city_summary.mp4 (animated stats)
    # ─────────────────────────────────────────────────────────────────────
    banner(2, total_steps, "Generating stats animation (make_video)")
    run(
        [
            sys.executable, MAKE_VIDEO,
            "--mode", "summary",
            "--newcomers", str(newcomers),
            "--abandoned", str(newly_abandoned),
            "--start", str(old_active),
            "--end", str(new_active),
            "--output", CITY_SUMMARY,
        ] + (["--new-names", newcomer_names_str] if newcomer_names_str else []),
        f"Rendering city_summary.mp4 (+{newcomers} / -{newly_abandoned} / pop {new_active})...",
        capture=False,
    )

    # ─────────────────────────────────────────────────────────────────────
    # STEP 3 — Generate AI script + voice narration
    # ─────────────────────────────────────────────────────────────────────
    banner(3, total_steps, "Generating AI script & voice (generate_script)")
    run(
        [
            sys.executable, GEN_SCRIPT,
            "--names", names_file,
            "--houses", HOUSES_JSON,
            "--model", args.groq_model,
            "--newcomers", str(newcomers),
            "--unfollows", str(newly_abandoned),
        ],
        "Calling Groq AI + edge-tts for narration...",
        capture=False,
    )

    if not os.path.exists(VIDEO_VOICE):
        print("  ❌ video_voice.mp3 was not generated. Aborting.")
        sys.exit(1)
    if not os.path.exists(VIDEO_SCRIPT):
        print("  ❌ video_script.txt was not generated. Aborting.")
        sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────
    # STEP 4 — Record the town (Playwright)
    # ─────────────────────────────────────────────────────────────────────
    step_num = 4
    if args.skip_record:
        if not os.path.exists(RECORDING):
            print(f"\n  ❌ --skip-record was set but {RECORDING} does not exist!")
            sys.exit(1)
        print(f"\n  ⏭️   Skipping Step 4 (using existing {os.path.basename(RECORDING)})")
    else:
        banner(step_num, total_steps, "Recording town footage (record_town)")
        record_cmd = [
            sys.executable, RECORD_TOWN,
            "--output", RECORDING,
            "--duration", str(args.record_duration),
            "--url", args.url,
        ]
        run(record_cmd, f"Playwright recording ({args.record_duration}s) → {args.url}...", capture=False)
        if not os.path.exists(RECORDING):
            print("  ❌ Recording failed — town_recording.mp4 not found.")
            sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────
    # STEP 5 — Compose final video
    # ─────────────────────────────────────────────────────────────────────
    banner(5, total_steps, "Composing final video (compose_video)")
    compose_cmd = [
        sys.executable, COMPOSE_VIDEO,
        "--recording", RECORDING,
        "--voice", VIDEO_VOICE,
        "--script", VIDEO_SCRIPT,
        "--stats-video", CITY_SUMMARY,
        "--output", args.output,
    ]
    if args.skip_text:
        compose_cmd.append("--skip-text")
    if args.bg_music:
        compose_cmd.extend(["--bg-music", args.bg_music])

    run(compose_cmd, "Stitching all clips together...", capture=False)

    # ─────────────────────────────────────────────────────────────────────
    # Done!
    # ─────────────────────────────────────────────────────────────────────
    output_size_mb = os.path.getsize(args.output) / (1024 * 1024) if os.path.exists(args.output) else 0
    print(f"\n{'═' * 56}")
    print(f"  🎉  PIPELINE COMPLETE!")
    print(f"  🎬  {args.output}  ({output_size_mb:.1f} MB)")
    print(f"{'═' * 56}\n")


if __name__ == "__main__":
    main()
