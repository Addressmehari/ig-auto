import subprocess
import os
import argparse
import json
import random

def get_stats_intelligently(names_file, mode="population"):
    """
    Analyzes current data/houses.json and the provided names file 
    to determine counts for either 'population' or 'abandoned'.
    """
    current_data = []
    if os.path.exists("data/houses.json"):
        try:
            with open("data/houses.json", "r") as f:
                current_data = json.load(f)
        except Exception:
            pass

    new_names_set = set()
    if os.path.exists(names_file):
        with open(names_file, 'r', encoding='utf-8') as f:
            content = f.read()
            new_names_set = set([n.strip() for n in content.replace(',', '\n').split('\n') if n.strip()])

    if mode == "abandoned":
        old_abandoned = len([h for h in current_data if h.get('abandoned', False)])
        newly_abandoned = 0
        for h in current_data:
            if 'username' in h and not h.get('abandoned', False) and h['username'] not in new_names_set:
                newly_abandoned += 1
        return old_abandoned, old_abandoned + newly_abandoned
    else:
        old_active = len([h for h in current_data if 'username' in h and not h.get('abandoned', False)])
        new_active = len(new_names_set)
        return old_active, new_active

def create_video(stats, output_name="update.mp4", total_duration=10, sequential=False, meme_sound=None, meme_start=7.5, meme_duration=3.0, new_names_list=None):
    """
    Creates a video with pulsing icons and counters.
    """
    width, height = 1080, 1920
    fps = 60
    bg_image = "image.png"
    font_path = "C\\:/Windows/Fonts/impact.ttf"
    if not os.path.exists("C:/Windows/Fonts/impact.ttf"):
        font_path = "C\\:/Windows/Fonts/arialbd.ttf"
    
    if not os.path.exists(bg_image):
        print(f"Error: {bg_image} not found.")
        return

    # Prepare inputs
    inputs = ['-loop', '1', '-framerate', str(fps), '-t', str(total_duration), '-i', bg_image]
    unique_icons = []
    for s in stats:
        if s.get('icon') and s['icon'] not in unique_icons:
            unique_icons.append(s['icon'])
    
    for icon in unique_icons:
        inputs += ['-i', icon]
        
    if meme_sound:
        inputs += ['-i', meme_sound]

    # Background filter
    filter_chain = (
        f"[0:v]scale='if(gt(iw/ih,{width/height}),-1,{height})':'if(gt(iw/ih,{width/height}),{height},-1)',"
        f"crop={width}:{height},"
        f"zoompan=z='1+0.0002*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={fps},"
        f"gblur=sigma=10[bg];"
    )

    last_res = "bg"
    audio_streams = []
    
    num_layout_stats = 1 if sequential else len(stats)
    box_height = 900
    spacing = 100
    start_y = (height - (box_height * num_layout_stats)) // 2 + 100

    for i, stat in enumerate(stats):
        curr_v = last_res
        s_time = stat.get('startTime', 0)
        e_time = stat.get('endTime', total_duration)
        
        if sequential:
            wait_dur, hold_dur = 0.5, 0.5
            y_offset = start_y
            enable_expr = f"between(t,{s_time},{e_time})"
        else:
            wait_dur, hold_dur = 1.0, 2.0
            y_offset = start_y + i * (box_height + spacing)
            enable_expr = "1"
            
        stat_hold = 1.0 if (i == len(stats) - 1 and sequential) else hold_dur
        start_frame = int((s_time + wait_dur) * fps)
        end_frame = int((e_time - stat_hold) * fps)
        count_duration_frames = max(1, end_frame - start_frame)

        # Audio Ticks
        num_ticks = abs(stat['end'] - stat['start'])
        if num_ticks > 0:
            tick_start = s_time + wait_dur
            tick_end = e_time - stat_hold
            tick_dur = max(0.1, tick_end - tick_start)
            # Cap ticks at 25 per second for a clean sound
            effective_ticks = min(num_ticks, int(tick_dur * 25))
            if effective_ticks > 0:
                interval = tick_dur / effective_ticks
                audio_streams.append(f"a{i}")
                filter_chain += (
                    f"sine=f=1800:d={total_duration},volume='if(between(t,{tick_start},{tick_end})*lt(mod(t-{tick_start},{interval}),0.02),1.2,0)':eval=frame[a{i}];"
                )

        # Label
        label_size = 60
        filter_chain += f"[{curr_v}]drawtext=fontfile='{font_path}':text='{stat['label']}':fontcolor=white:fontsize={label_size}:x=(w-text_w)/2:y={y_offset - 100}:borderw=4:bordercolor=black:enable='{enable_expr}'[v{i}l];"
        
        curr_v = f"v{i}l"
        has_icon = bool(stat.get('icon'))
        
        # Icon processing
        if has_icon:
            idx = unique_icons.index(stat['icon']) + 1
            icon_name = os.path.basename(stat['icon'])
            icon_width = 350 if icon_name == 'house.png' else 470
            pulse_expr = f"(1+0.05*sin(2*PI*(t-{s_time})/1.5))"
            filter_chain += (
                f"[{idx}:v]scale={icon_width}:-1[ic{i}];"
                f"[ic{i}]scale='iw*{pulse_expr}':-1:eval=frame[ip{i}];"
                f"[{curr_v}][ip{i}]overlay=x=(main_w-overlay_w)/2:y={y_offset - 20}:enable='{enable_expr}'[v{i}i];"
            )
            curr_v = f"v{i}i"

        # Counter Expression
        counter_base_size = 240
        pulse_expr_fs = f"{counter_base_size}*(1+0.08*sin(2*PI*(t-{s_time})/1.5))"
        counter_expr = (
            f"if(lt(n,{start_frame}), {stat['start']}, "
            f"if(gt(n,{end_frame}), {stat['end']}, "
            f"{stat['start']} + ({stat['end']}-{stat['start']})*(n-{start_frame})/{count_duration_frames}))"
        )
        
        # Sign logic
        sign_char = "+" if stat['end'] > stat['start'] else ("-" if stat['end'] < stat['start'] else "")
        counter_y = y_offset + 380 if has_icon else y_offset + 250
            
        # 1. Counter WITH Sign (During animation)
        filter_chain += (
            f"[{curr_v}]drawtext=fontfile='{font_path}':text='{sign_char}%{{eif\\:{counter_expr}\\:d}}':"
            f"fontcolor='{stat['color']}':fontsize='{pulse_expr_fs}':"
            f"x=(w-text_w)/2:y={counter_y}:"
            f"borderw=5:bordercolor=white:shadowcolor=black@0.5:shadowx=4:shadowy=4:"
            f"enable='{enable_expr}*between(n,{start_frame},{end_frame-1})'[v{i}c_mid];"
        )
        
        last_res = f"v{i}c_mid"
        
        # New Names Rapid Flash
        if stat['label'] == "NEW CITIZENS" and new_names_list:
            count_time_start = s_time + wait_dur
            count_time_end = e_time - stat_hold
            count_dur = count_time_end - count_time_start
            time_per_name = count_dur / max(1, len(new_names_list))
            for j, name in enumerate(new_names_list):
                name_start = count_time_start + j * time_per_name
                name_end = name_start + time_per_name
                if j == len(new_names_list) - 1:
                    name_end = e_time
                name_y = counter_y + 250
                filter_chain += (
                    f"[{last_res}]drawtext=fontfile='{font_path}':text='@{name}':"
                    f"fontcolor='#00FFCC':fontsize='70':"
                    f"x=(w-text_w)/2:y={name_y}:"
                    f"borderw=3:bordercolor=black:"
                    f"enable='between(t,{name_start},{name_end})'[v{i}n{j}];"
                )
                last_res = f"v{i}n{j}"
        
        # 2. Counter WITHOUT Sign + Glass Shine (Static periods)
        # We add a "shine" layer using a white copy with a shimmering alpha pulse
        shimmer_expr = f"0.4 + 0.4*sin(2*PI*(t-{s_time})*4)" # Fast sparkle
        
        filter_chain += (
            # Base colored text
            f"[{last_res}]drawtext=fontfile='{font_path}':text='%{{eif\\:{counter_expr}\\:d}}':"
            f"fontcolor='{stat['color']}':fontsize='{pulse_expr_fs}':"
            f"x=(w-text_w)/2:y={counter_y}:"
            f"borderw=5:bordercolor=white:shadowcolor=black@0.5:shadowx=4:shadowy=4:"
            f"enable='{enable_expr}*not(between(n,{start_frame},{end_frame-1}))'[v{i}c_base];"
            
            # Glass Shine Highlight layer (White shimmer)
            f"[v{i}c_base]drawtext=fontfile='{font_path}':text='%{{eif\\:{counter_expr}\\:d}}':"
            f"fontcolor=white:alpha='{shimmer_expr}':fontsize='{pulse_expr_fs}':"
            f"x=(w-text_w)/2-3:y={counter_y}-3:" # Slight offset for 3D glass edge
            f"enable='{enable_expr}*gt(n,{end_frame-1})'[v{i}c];"
        )
        last_res = f"v{i}c"

    # Audio Mix
    if audio_streams:
        filter_chain += "".join([f"[{a}]" for a in audio_streams]) + f"amix=inputs={len(audio_streams)}[outa_ticks];"
    else:
        filter_chain += f"anullsrc=r=44100:cl=mono:d={total_duration}[outa_ticks];"
        
    # Meme Sound Integration
    if meme_sound:
        meme_idx = len(unique_icons) + 1
        filter_chain += (
            f"[{meme_idx}:a]atrim=duration={meme_duration},adelay={meme_start*1000}|{meme_start*1000},volume=0.8[memea];"
            f"[outa_ticks][memea]amix=inputs=2:normalize=0[outa];"
        )
        map_audio = "[outa]"
    else:
        map_audio = "[outa_ticks]"

    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', filter_chain.strip().rstrip(';'),
        '-map', f"[{last_res}]",
        '-map', map_audio,
        '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(fps),
        '-c:a', 'aac', '-b:a', '128k',
        output_name
    ]

    print(f"Generating video: {output_name}...")
    try:
        subprocess.run(cmd, check=True)
        print("Success!")
    except subprocess.CalledProcessError:
        print("FFmpeg error.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["population", "abandoned", "summary"], default="population")
    parser.add_argument("--names", type=str)
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--newcomers", type=int, default=0)
    parser.add_argument("--abandoned", type=int, default=0)
    parser.add_argument("--new-names", type=str, default="")
    parser.add_argument("--output", type=str)
    parser.add_argument("--duration", type=float, default=10.0)
    
    args = parser.parse_args()
    
    stats_to_show = []
    is_sequential = False
    selected_meme = None
    meme_start_time = 9.0
    meme_dur = 3.0
    
    if args.mode == "summary":
        # Multi-counter mode (Sequential scenes with 0.8s gaps)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        house_icon = os.path.join(base_dir, 'images', 'house.png')
        abandoned_icon = os.path.join(base_dir, 'images', 'abonded_house.png')
        
        stats_to_show.append({'label': "NEW CITIZENS", 'start': 0, 'end': args.newcomers, 'color': '#00FFCC', 'startTime': 0, 'endTime': 2.8, 'icon': house_icon})
        stats_to_show.append({'label': "LEFT CITY", 'start': 0, 'end': args.abandoned, 'color': '#FF5555', 'startTime': 3.6, 'endTime': 6.4, 'icon': abandoned_icon})
        
        # Population Change Meme Logic
        pop_start = args.start or 0
        pop_end = args.end or 0
        
        if pop_end > pop_start:
            # Increase
            meme_paths = [r"c:\Users\sbava\OneDrive\Documents\gitville\meme sound effects\anime-wow-sound-effect.mp3"]
            valid = [p for p in meme_paths if os.path.exists(p)]
            if valid:
                selected_meme = valid[0]
                meme_start_time = 9.0
                meme_dur = 3.0
        elif pop_end < pop_start:
            # Decrease
            meme_paths = [
                r"c:\Users\sbava\OneDrive\Documents\gitville\meme sound effects\faaah.mp3",
                r"c:\Users\sbava\OneDrive\Documents\gitville\meme sound effects\windows-xp-startup_1ph012N.mp3"
            ]
            valid = [p for p in meme_paths if os.path.exists(p)]
            if valid:
                selected_meme = random.choice(valid)
                if "faaah" in selected_meme:
                    meme_start_time = 10.0
                    meme_dur = 1.0
                else:
                    meme_start_time = 9.0
                    meme_dur = 3.0
        
        if selected_meme:
            args.duration = max(args.duration, meme_start_time + meme_dur)
        
        stats_to_show.append({'label': "TOTAL POPULATION", 'start': pop_start, 'end': pop_end, 'color': '#FFD700', 'startTime': 7.2, 'endTime': args.duration, 'icon': None})
        output_name = args.output or "city_summary.mp4"
        is_sequential = True
    else:
        # ... (Single counter mode logic)
        s, e = args.start, args.end
        if args.names:
            s, e = get_stats_intelligently(args.names, mode=args.mode)
        
        label = "HOUSE COUNT" if args.mode == "population" else "ABANDONED HOUSES"
        color = "#FFD700"
        stats_to_show.append({'label': label, 'start': s or 0, 'end': e or 0, 'color': color})
        output_name = args.output or f"{args.mode}_update.mp4"

    names_list = [n.strip() for n in args.new_names.split(',')] if args.new_names else []
    create_video(stats_to_show, output_name, total_duration=args.duration, sequential=is_sequential, meme_sound=selected_meme, meme_start=meme_start_time, meme_duration=meme_dur, new_names_list=names_list)
