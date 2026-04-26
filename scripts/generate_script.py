import os
import random
import json
import requests
import argparse
import sys
import io
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import edge_tts
import subprocess


# ── Rotating CTA closers (picked by day % 12) ────────────────────────────────
CTA_CLOSERS = [
    "Drop a follow — your house breaks ground tomorrow.",
    "One follow = one house. Yours is waiting.",
    "Follow now and watch your house appear in the next update.",
    "Your plot is already reserved. Just follow to claim it.",
    "Every follower gets a house. Don't miss yours.",
    "The town keeps growing. Follow and be part of it.",
    "Hit follow and your name goes on a front door.",
    "Follow and I'll build your house before sunrise.",
    "This town has room for you. Follow to move in.",
    "Follow today — your neighbours are already waiting.",
    "New house every day for every new follower. You next?",
    "Follow and the construction crew gets to work immediately.",
]



def prepare_text_for_tts(text):
    """Refines the text for a more natural sounding narration with proper pauses."""
    # 1. Remove emojis
    text = text.encode('ascii', 'ignore').decode('ascii')
    # 2. Convert '+300' → '300' and '-10' → '10'
    text = re.sub(r'\+(\d+)', r'\1', text)
    text = re.sub(r'\-(\d+)', r'\1', text)
    # 3. Convert '0 people' → 'no people'
    text = text.replace("0 people", "no people")
    # 4. Add periods so TTS pauses between lines
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    processed = []
    for line in lines:
        if not line.endswith(('.', '!', '?')):
            line += '.'
        processed.append(line)
    return "  ".join(processed)


def get_town_stats(names_file, houses_file):
    """
    Calculates stats from names.txt and houses.json.
    Manages the persistent day counter (does NOT increment — pipeline does that).
    """
    current_houses = []
    if os.path.exists(houses_file):
        with open(houses_file, 'r', encoding='utf-8') as f:
            current_houses = json.load(f)

    existing_residents = set(
        h['username'] for h in current_houses
        if 'username' in h and not h.get('abandoned', False)
    )

    target_residents = set()
    if os.path.exists(names_file):
        with open(names_file, 'r', encoding='utf-8') as f:
            content = f.read()
            target_residents = set(
                n.strip() for n in content.replace(',', '\n').split('\n') if n.strip()
            )

    new_followers = len(target_residents - existing_residents)
    unfollows     = len(existing_residents - target_residents)
    total_pop     = len(target_residents)

    # Persistent day counter
    meta_file = "web/data/town_meta.json"
    day_x = 1
    if os.path.exists(meta_file):
        try:
            with open(meta_file, 'r') as f:
                meta = json.load(f)
                day_x = meta.get("last_day", 1)
        except Exception:
            day_x = 1

    # Just ensure stats day is set
    stats_day = day_x

    return {
        "new_followers": new_followers,
        "unfollows":     unfollows,
        "total":         total_pop,
        "day":           day_x,
    }



async def main():
    load_dotenv()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    parser = argparse.ArgumentParser(description="Generate a video script for GitVille using Groq AI.")
    parser.add_argument("--names",      default="names.txt",        help="Path to names.txt")
    parser.add_argument("--houses",     default="web/data/houses.json", help="Path to houses.json")
    parser.add_argument("--model",      default="qwen/qwen3-32b",   help="Groq model")
    parser.add_argument("--day",        type=int,                   help="Override Day number")
    parser.add_argument("--newcomers",  type=int,                   help="Override newcomers count")
    parser.add_argument("--unfollows",  type=int,                   help="Override unfollows count")
    parser.add_argument("--male",       action="store_true",        help="Force male voice")
    args = parser.parse_args()

    stats = get_town_stats(args.names, args.houses)

    if args.newcomers is not None:
        stats['new_followers'] = args.newcomers
    if args.unfollows is not None:
        stats['unfollows'] = args.unfollows

    day_to_use = args.day if args.day is not None else stats['day']

    # ── Script template ───────────────────────────────────────────────────────
    texts = [
        f"Day {day_to_use} of building a town for every follower. Today's report:",
        f"{stats['new_followers']} people moved in.",
        f"{stats['unfollows']} people left.",
        f"Current population: {stats['total']}.",
        f"Step 1: Follow this page.\nStep 2: Visit the link in bio.\nStep 3: Search your username to see your house.\nIf your house is not found, it will be built in tomorrow's video!\n{CTA_CLOSERS[day_to_use % len(CTA_CLOSERS)]}"
    ]

    script_template = "\n[ 0.5s pause ]\n".join(texts[:4]) + "\n\n[ 2.0s pause ]\n\n" + texts[4]

    print("\n--- GENERATED VIDEO SCRIPT ---")
    print(script_template)
    print("------------------------------\n")

    with open("video_script.txt", "w", encoding="utf-8") as f:
        f.write(script_template)

    # ── TTS ───────────────────────────────────────────────────────────────────
    print("Generating voice narration (with precise pauses for stat sync)...")
    try:
        # Randomly pick male or female voice each run, unless forced
        if args.male:
            gender = "male"
        else:
            gender = random.choice(["male", "female"])
        voice = "en-US-GuyNeural" if gender == "male" else "en-US-JennyNeural"
        print(f"  🎙️  Voice gender: {gender} ({voice})")
        # Save gender choice so compose_video.py picks the matching avatar
        import json as _json
        with open("voice_choice.json", "w") as _vf:
            _json.dump({"gender": gender, "voice": voice}, _vf)
        audio_files = []
        for i, text in enumerate(texts):
            fname = f"voice{i}.mp3"
            await edge_tts.Communicate(prepare_text_for_tts(text), voice).save(fname)
            audio_files.append(fname)
            
        silences = [0.5, 1.2, 1.2, 2.0] # Duration of silence after clip 0, 1, 2, 3
        
        cmd = ['ffmpeg', '-y']
        filter_parts = []
        
        input_idx = 0
        for i in range(len(texts)):
            cmd.extend(['-i', audio_files[i]])
            filter_parts.append(f"[{input_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{input_idx}];")
            input_idx += 1
            
            if i < len(silences):
                cmd.extend(['-f', 'lavfi', '-t', str(silences[i]), '-i', 'anullsrc=r=44100:cl=stereo'])
                filter_parts.append(f"[{input_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{input_idx}];")
                input_idx += 1
                
        concat_inputs = "".join([f"[a{i}]" for i in range(input_idx)])
        filter_complex = "".join(filter_parts) + f"{concat_inputs}concat=n={input_idx}:v=0:a=1[aout]"
        
        cmd.extend([
            '-filter_complex', filter_complex,
            '-map', '[aout]',
            '-c:a', 'libmp3lame', '-b:a', '192k',
            'video_voice.mp3'
        ])
        
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Cleanup
        for fname in audio_files:
            if os.path.exists(fname):
                os.remove(fname)
                
        print(f"Voice saved to video_voice.mp3 (Voice: {voice})")
    except Exception as e:
        print(f"Error generating TTS: {e}")

    print(f"Script saved to video_script.txt (Day {day_to_use})")


if __name__ == "__main__":
    asyncio.run(main())
