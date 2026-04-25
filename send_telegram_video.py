import requests
import os
import json
import base64
from dotenv import load_dotenv
from instagrapi import Client

# Load environment variables
load_dotenv()

def generate_groq_caption(api_key):
    """Generates a creative Instagram caption using Groq AI."""
    if not api_key:
        print("⚠️ GROQ_API_KEY not found. Using default caption.")
        return "🎬 Your daily GitVille video is ready!"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Try to read some context from video_script.txt if it exists
    context = ""
    if os.path.exists("video_script.txt"):
        try:
            with open("video_script.txt", "r", encoding="utf-8") as f:
                context = f.read().split("\n\n")[0] # Just the stats part
        except:
            pass

    prompt = f"Generate a short, engaging Instagram caption for a daily 'GitVille' update video. GitVille is a virtual town where every follower gets a house. {context}. Keep it catchy, use emojis, and don't include the steps to join (I will add them separately). Just the hook and body."

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a social media manager for GitVille, a virtual town built for followers."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 1,
        "max_completion_tokens": 1024,
        "top_p": 1,
        "stream": False
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        caption = data['choices'][0]['message']['content'].strip()
        return caption
    except Exception as e:
        print(f"❌ Error generating Groq caption: {e}")
        return "🎬 Your daily GitVille video is ready!"

def upload_to_instagram(video_path, caption):
    """Uploads the video to Instagram using a saved session (from env or file)."""
    cl = Client()
    session_loaded = False

    # 1. Try loading from Base64 Environment Variable (GitHub Secrets)
    session_b64 = os.getenv("IG_SESSION_B64")
    if session_b64:
        print("🔐 Loading Instagram session from IG_SESSION_B64...")
        try:
            session_data = json.loads(base64.b64decode(session_b64).decode('utf-8'))
            cl.set_settings(session_data)
            session_loaded = True
        except Exception as e:
            print(f"⚠️ Failed to decode IG_SESSION_B64: {e}")

    # 2. Fallback to local session.json
    if not session_loaded:
        session_file = "session.json"
        if os.path.exists(session_file):
            print(f"📂 Loading Instagram session from {session_file}...")
            try:
                cl.load_settings(session_file)
                session_loaded = True
            except Exception as e:
                print(f"⚠️ Failed to load {session_file}: {e}")

    if not session_loaded:
        raise Exception("No Instagram session found (checked IG_SESSION_B64 and session.json).")

    print(f"📸 Uploading {video_path} to Instagram...")
    try:
        
        # Hardcoded steps to join
        onboarding_steps = (
            "\n\n--- HOW TO JOIN ---\n"
            "1️⃣ Follow this page\n"
            "2️⃣ Tap the link in bio\n"
            "3️⃣ Search your username to see your house\n\n"
            "Built with ❤️ by GitVille"
        )
        
        full_caption = f"{caption}{onboarding_steps}"
        
        # Upload reel
        cl.clip_upload(video_path, full_caption)
        print("✅ Video uploaded successfully to Instagram!")
    except Exception as e:
        print(f"❌ Error uploading to Instagram: {e}")
        raise e

def send_telegram_message(token, chat_id, message):
    """Sends a simple text message to Telegram."""
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        requests.post(url, json=payload).raise_for_status()
    except Exception as e:
        print(f"❌ Error sending Telegram notification: {e}")

def send_telegram_video(token, chat_id, video_path, caption):
    if not token or not chat_id:
        print("Error: BOT_TOKEN or CHAT_ID not found in environment variables.")
        return

    if not os.path.exists(video_path):
        print(f"Error: Video file {video_path} not found.")
        return

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    
    print(f"📤 Uploading {video_path} to Telegram...")
    
    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            payload = {
                "chat_id": chat_id,
                "caption": caption
            }
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            print("✅ Video sent successfully to Telegram!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error sending video to Telegram: {e}")

if __name__ == "__main__":
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    GROQ_KEY = os.getenv("GROQ_API_KEY")
    VIDEO_PATH = "final_video.mp4"
    
    # 1. Generate Caption
    caption = generate_groq_caption(GROQ_KEY)
    
    # 2. Upload to Instagram
    print(f"📸 Starting Instagram upload for {VIDEO_PATH}...")
    try:
        upload_to_instagram(VIDEO_PATH, caption)
        send_telegram_message(BOT_TOKEN, CHAT_ID, "✅ Video successfully uploaded to Instagram!")
    except Exception as e:
        send_telegram_message(BOT_TOKEN, CHAT_ID, f"❌ Instagram upload failed: {e}")
    
    # 3. Send the video itself to Telegram
    send_telegram_video(BOT_TOKEN, CHAT_ID, VIDEO_PATH, caption)
