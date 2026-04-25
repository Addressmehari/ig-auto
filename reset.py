#!/usr/bin/env python3
"""
reset.py — Wipe all GitVille data and generated files for a fresh start.

Usage:
    python reset.py          # asks for confirmation
    python reset.py --yes    # skips confirmation
"""

import os
import sys
import json
import shutil
import argparse

# Force UTF-8 output on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.abspath(__file__))

DATA_RESETS = {
    "web/data/houses.json":    [],
    "web/data/roads.json":     [],
    "web/data/world.json":     {"weather": "none", "timeOfDay": "day"},
    "web/data/town_meta.json": {"last_day": 0},
}

GENERATED_FILES = [
    "city_summary.mp4",
    "final_video.mp4",
    "final_branded_video.mp4",
    "population_update.mp4",
    "video_script.txt",
    "video_voice.mp3",
    "output.log",
    "concat_debug.txt",
    "assets/town_recording.mp4",
]


def main():
    parser = argparse.ArgumentParser(description="Reset GitVille database to Day 0.")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    print("\n🏚️  GitVille Reset")
    print("   This will wipe:\n")
    print("   DATA FILES (reset to empty):")
    for path in DATA_RESETS:
        print(f"     • {path}")
    print("\n   GENERATED OUTPUTS (deleted):")
    for path in GENERATED_FILES:
        full = os.path.join(ROOT, path)
        exists = "✓" if os.path.exists(full) else "·"
        print(f"     {exists} {path}")

    if not args.yes:
        print()
        answer = input("   Proceed? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("   Aborted.\n")
            sys.exit(0)

    print()

    # ── Reset data files ──────────────────────────────────────────────────────
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    for rel_path, default_value in DATA_RESETS.items():
        full_path = os.path.join(ROOT, rel_path)
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(default_value, f, indent=2)
        print(f"   ✅ Reset  {rel_path}")

    # ── Delete generated outputs ──────────────────────────────────────────────
    for rel_path in GENERATED_FILES:
        full_path = os.path.join(ROOT, rel_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            print(f"   🗑️  Deleted {rel_path}")

    # ── Clean up any leftover temp dirs ───────────────────────────────────────
    for tmp in ["_compose_tmp", "assets/_rec_tmp"]:
        tmp_path = os.path.join(ROOT, tmp)
        if os.path.isdir(tmp_path):
            shutil.rmtree(tmp_path, ignore_errors=True)
            print(f"   🗑️  Removed {tmp}/")

    print("\n   🎉 Done! Town is back to Day 0.\n")
    print("   Run:  python compose_video.py names.txt\n")


if __name__ == "__main__":
    main()
