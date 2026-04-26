import subprocess
import sys
import os
import json
import argparse

def run_step(cmd):
    print(f"\n[{' '.join(cmd)}]")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print("\n❌ Step failed! Stopping pipeline.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Step 2: Create the video")
    parser.add_argument("--url", default="http://127.0.0.1:5501/web/", help="Web app URL for recording")
    parser.add_argument("--record-duration", type=int, default=30, help="Town recording duration in seconds")
    parser.add_argument("--groq-model", default="qwen/qwen3-32b", help="Groq model to use")
    parser.add_argument("--bg-music", default="subway_surfers.mp3", help="Background music")
    parser.add_argument("--male", action="store_true", help="Use male voice narration")
    args = parser.parse_args()

    print("==================================================")
    print("🎬 STEP 2: CREATING THE DAILY VIDEO")
    print("==================================================")

    if not os.path.exists("web/data/daily_stats.json"):
        print("❌ web/data/daily_stats.json not found! Please run step1_update_data.py first.")
        sys.exit(1)

    with open("web/data/daily_stats.json", "r", encoding="utf-8") as f:
        stats = json.load(f)

    newcomers = stats["newcomers"]
    newly_abandoned = stats["newly_abandoned"]
    old_active = stats["old_active"]
    new_active = stats["new_active"]
    newcomer_names_str = stats["newcomer_names_str"]

    # 1. Generate the Stats Animation (city_summary.mp4)
    print("\n📊 1/4: Generating Stats Animation...")
    make_video_cmd = [
        sys.executable, "scripts/make_video.py",
        "--mode", "summary",
        "--newcomers", str(newcomers),
        "--abandoned", str(newly_abandoned),
        "--start", str(old_active),
        "--end", str(new_active),
        "--output", "city_summary.mp4",
    ]
    if newcomer_names_str:
        make_video_cmd.extend(["--new-names", newcomer_names_str])
    run_step(make_video_cmd)

    # 2. Generate the AI Script and Voiceover
    print("\n🤖 2/4: Generating AI Script and Voiceover...")
    gen_script_cmd = [
        sys.executable, "scripts/generate_script.py",
        "--names", "followers.txt",
        "--houses", "web/data/houses.json",
        "--model", args.groq_model,
        "--newcomers", str(newcomers),
        "--unfollows", str(newly_abandoned)
    ]
    if args.male:
        gen_script_cmd.append("--male")
    run_step(gen_script_cmd)

    # 3. Record the live website
    print(f"\n🎥 3/4: Recording the updated city website at {args.url}...")
    run_step([
        sys.executable, "scripts/record_town.py",
        "--output", "assets/town_recording.mp4",
        "--duration", str(args.record_duration),
        "--url", args.url
    ])

    # 4. Compose the final video
    print("\n🎞️ 4/4: Composing the final video...")
    run_step([
        sys.executable, "scripts/compose_video.py",
        "--recording", "assets/town_recording.mp4",
        "--voice", "video_voice.mp3",
        "--script", "video_script.txt",
        "--stats-video", "city_summary.mp4",
        "--output", "final_video.mp4",
        "--bg-music", args.bg_music
    ])

    print("\n==================================================")
    print("✅ STEP 2 COMPLETE!")
    print("==================================================")
    print("Your daily video is ready: final_video.mp4")

if __name__ == "__main__":
    main()
